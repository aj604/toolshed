#!/usr/bin/env python3
"""Plan doc-bloat sweep chunks: inventory -> chunk manifest.

Absorbs list-docs.py: enumerates the in-scope docs (git ls-files under
--root, else a filesystem walk; default filter *.md; config exclude/include
globs, whitelist wins), then groups them into bounded chunks a single
detection invocation can hold.

Policy-scope directories (config "policy_scope") become one 'policy' chunk
each — a single POLICY record covers them; they are never walked
file-by-file. Every other doc gets a deterministic doc-kind hint (narrative
if its first line starts with '> As of'; planning if a 'plans' or 'specs'
path segment contains it; else living — a hint the model may override only
with stated evidence), is grouped by (directory, hint), packed under the
caps (chunking.max_docs, default 8; chunking.max_lines, default 1200), and
consecutive underfull chunks with the same hint are coalesced while the
caps hold. A single doc larger than max_lines gets its own chunk.

Chunk ids are content-addressed (sha256 of member paths), so re-planning an
unchanged tree yields the same ids — which is what makes --results-dir
resume work: a chunk whose <id>.json result already exists stays in
"chunks" but leaves "pending".

Usage:
    plan-chunks.py [--config PATH] [--root DIR] [--out FILE] [--results-dir DIR]

Output: manifest JSON {"schema": 1, "chunks": [...], "pending": [ids]} to
--out (stdout if omitted). Sweep chunks are
{"id", "kind": "sweep", "docs": [{"path", "lines", "hint"}]}; policy chunks
are {"id", "kind": "policy", "dir", "files"}. The run-surface report (doc
count, chunk count, projected invocations, resume skips) always prints to
stderr.

Config discovery: --config if given, else <root>/.github/doc-sync/audit-scope.json.
All keys optional; an absent file is pure defaults:
    exclude / include: glob lists ('*' stays within a path segment, '**'
        crosses segments; include re-adds anything it matches — whitelist wins)
    policy_scope: ["docs/superpowers", ...]   directories, prefix match,
        longest declared prefix wins for nested scopes
    chunking: {"max_docs": 8, "max_lines": 1200, "max_chunks": null}
max_chunks non-null is a hard run ceiling: planning more chunks than that
exits 2 naming the count and the knob (default off — big first runs are
legitimate; the protections are structural).

Exit status: 0 on success; 2 on malformed config or a tripped max_chunks.
"""

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys

DEFAULT_MAX_DOCS = 8
DEFAULT_MAX_LINES = 1200


def die(msg):
    """Self-explaining bad-input exit (code 2)."""
    print(msg, file=sys.stderr)
    raise SystemExit(2)


def glob_to_regex(glob):
    """Translate a glob into an anchored regex over POSIX paths.

    '**' matches across segments (including '/'); '*' matches within a segment
    (not '/'); '?' matches one non-'/' char. Everything else is literal.
    fnmatch is avoided deliberately: it treats '**' as two '*' and lets '*'
    cross '/', which is wrong for path-segment semantics.
    """
    i, n = 0, len(glob)
    out = ["(?s:"]
    while i < n:
        c = glob[i]
        if c == "*":
            if i + 1 < n and glob[i + 1] == "*":
                # Consume the run of '*' as a single '**'.
                while i < n and glob[i] == "*":
                    i += 1
                out.append(".*")
                continue
            out.append("[^/]*")
        elif c == "?":
            out.append("[^/]")
        else:
            out.append(re.escape(c))
        i += 1
    out.append(")\\Z")
    return re.compile("".join(out))


def matches_any(path, patterns):
    return any(p.match(path) for p in patterns)


def load_config(path):
    """Return the effective config dict; SystemExit(2) on any malformed key."""
    defaults = {"exclude": [], "include": [], "policy_scope": [],
                "max_docs": DEFAULT_MAX_DOCS, "max_lines": DEFAULT_MAX_LINES,
                "max_chunks": None}
    try:
        with open(path, encoding="utf-8") as f:
            raw = f.read()
    except FileNotFoundError:
        return defaults
    except OSError as e:
        die(f"error: cannot read config {path}: {e}")

    try:
        data = json.loads(raw)
    except json.JSONDecodeError as e:
        die(f"error: malformed config JSON in {path}: {e}")
    if not isinstance(data, dict):
        die(f"error: config {path} must be a JSON object, got {type(data).__name__}")

    for key in ("exclude", "include", "policy_scope"):
        val = data.get(key, [])
        if not (isinstance(val, list) and all(isinstance(g, str) for g in val)):
            die(f"error: config {path}: '{key}' must be a list of strings")
        defaults[key] = val

    chunking = data.get("chunking", {})
    if not isinstance(chunking, dict):
        die(f"error: config {path}: 'chunking' must be an object")
    for key in ("max_docs", "max_lines"):
        if key in chunking:
            v = chunking[key]
            if not (isinstance(v, int) and not isinstance(v, bool) and v >= 1):
                die(f"error: config {path}: chunking.{key} must be an integer >= 1")
            defaults[key] = v
    v = chunking.get("max_chunks")
    if v is not None:
        if not (isinstance(v, int) and not isinstance(v, bool) and v >= 1):
            die(f"error: config {path}: chunking.max_chunks must be null "
                     f"or an integer >= 1")
        defaults["max_chunks"] = v

    defaults["exclude"] = [glob_to_regex(g) for g in defaults["exclude"]]
    defaults["include"] = [glob_to_regex(g) for g in defaults["include"]]
    defaults["policy_scope"] = [d.strip("/") for d in defaults["policy_scope"]]
    return defaults


def candidates(root):
    """Repo-relative POSIX paths under root: git ls-files, else a tree walk."""
    try:
        out = subprocess.run(
            ["git", "ls-files", "-z"],
            cwd=root, capture_output=True, text=True, check=True,
        ).stdout
        return [p for p in out.split("\0") if p]
    except (OSError, subprocess.CalledProcessError):
        return walk(root)


def walk(root):
    paths = []
    for dirpath, _dirs, files in os.walk(root):
        for name in files:
            full = os.path.join(dirpath, name)
            rel = os.path.relpath(full, root)
            paths.append(rel.replace(os.sep, "/"))
    return paths


def select(paths, exclude, include):
    result = []
    for p in paths:
        keep = p.lower().endswith(".md")
        if keep and matches_any(p, exclude):
            keep = False
        if matches_any(p, include):
            keep = True
        if keep:
            result.append(p)
    return sorted(result)


def line_count(full):
    """Number of lines in a file, in-process. Unreadable => 0 (never raises)."""
    try:
        with open(full, encoding="utf-8", errors="replace") as f:
            return len(f.read().splitlines())
    except OSError:
        return 0


def doc_hint(root, path):
    """Deterministic doc-kind hint; the '> As of' anchor wins over location."""
    try:
        with open(os.path.join(root, path), encoding="utf-8", errors="replace") as f:
            first = f.readline()
    except OSError:
        first = ""
    if first.lstrip().startswith("> As of"):
        return "narrative"
    if any(seg in ("plans", "specs") for seg in path.split("/")[:-1]):
        return "planning"
    return "living"


def policy_dir_of(path, policy_dirs):
    """Longest declared dir that is a proper path prefix of path, else None."""
    best = None
    for d in policy_dirs:
        if path.startswith(d + "/") and (best is None or len(d) > len(best)):
            best = d
    return best


def chunk_id(prefix, paths):
    digest = hashlib.sha256("\n".join(paths).encode("utf-8")).hexdigest()
    return f"{prefix}-{digest[:10]}"


def pack(docs, max_docs, max_lines):
    """Greedy pack of one (dir, hint) group; docs pre-sorted by path."""
    chunks, cur, cur_lines = [], [], 0
    for d in docs:
        if cur and (len(cur) + 1 > max_docs or cur_lines + d["lines"] > max_lines):
            chunks.append(cur)
            cur, cur_lines = [], 0
        cur.append(d)
        cur_lines += d["lines"]
    if cur:
        chunks.append(cur)
    return chunks


def coalesce(chunks, max_docs, max_lines):
    """Merge consecutive underfull chunks sharing a hint while the caps hold."""
    merged = []
    for c in chunks:
        if merged:
            prev = merged[-1]
            if (prev[0]["hint"] == c[0]["hint"]
                    and len(prev) + len(c) <= max_docs
                    and sum(d["lines"] for d in prev + c) <= max_lines):
                merged[-1] = prev + c
                continue
        merged.append(c)
    return merged


def plan(root, cfg):
    docs = select(candidates(root), cfg["exclude"], cfg["include"])
    sized = [{"path": p, "lines": line_count(os.path.join(root, p))} for p in docs]

    policy_files, sweep = {}, []
    for d in sized:
        pdir = policy_dir_of(d["path"], cfg["policy_scope"])
        if pdir is not None:
            policy_files.setdefault(pdir, []).append(d["path"])
        else:
            d["hint"] = doc_hint(root, d["path"])
            sweep.append(d)

    chunks = []
    for pdir in sorted(policy_files):
        files = sorted(policy_files[pdir])
        chunks.append({"id": chunk_id("p", files), "kind": "policy",
                       "dir": pdir, "files": files})

    groups = {}
    for d in sweep:
        groups.setdefault((os.path.dirname(d["path"]), d["hint"]), []).append(d)
    packed = []
    for key in sorted(groups):
        packed.extend(pack(sorted(groups[key], key=lambda d: d["path"]),
                           cfg["max_docs"], cfg["max_lines"]))
    packed.sort(key=lambda c: c[0]["path"])
    for c in coalesce(packed, cfg["max_docs"], cfg["max_lines"]):
        chunks.append({"id": chunk_id("c", [d["path"] for d in c]),
                       "kind": "sweep", "docs": c})
    return len(sized), chunks


def main():
    ap = argparse.ArgumentParser(description="Plan doc-bloat sweep chunks.")
    ap.add_argument("--config", help="scope config JSON (default: "
                    "<root>/.github/doc-sync/audit-scope.json)")
    ap.add_argument("--root", default=os.getcwd(),
                    help="repo root to enumerate (default: cwd)")
    ap.add_argument("--out", help="write the manifest here (default: stdout)")
    ap.add_argument("--results-dir", help="existing chunk-result dir; chunks "
                    "with a <id>.json there stay in 'chunks' but leave 'pending'")
    args = ap.parse_args()

    config = args.config or os.path.join(
        args.root, ".github", "doc-sync", "audit-scope.json")
    cfg = load_config(config)
    ndocs, chunks = plan(args.root, cfg)

    for d in cfg["policy_scope"]:
        if not any(c["kind"] == "policy" and c["dir"] == d for c in chunks):
            print(f"note: policy-scope dir {d!r} matches no in-scope docs",
                  file=sys.stderr)

    if cfg["max_chunks"] is not None and len(chunks) > cfg["max_chunks"]:
        die(f"error: planned {len(chunks)} chunks, over "
                 f"chunking.max_chunks={cfg['max_chunks']} in {config} — raise "
                 f"or remove the ceiling to run this audit")

    pending = [c["id"] for c in chunks]
    if args.results_dir:
        pending = [c["id"] for c in chunks if not os.path.exists(
            os.path.join(args.results_dir, c["id"] + ".json"))]

    nsweep = sum(1 for c in chunks if c["kind"] == "sweep")
    report = (f"{ndocs} doc(s) -> {len(chunks)} chunk(s) "
              f"({nsweep} sweep + {len(chunks) - nsweep} policy); "
              f"projected invocations: {len(pending)}")
    if len(pending) < len(chunks):
        report += f" (resume: {len(chunks) - len(pending)} already have results)"
    print(report, file=sys.stderr)

    text = json.dumps({"schema": 1, "chunks": chunks, "pending": pending},
                      indent=2)
    if args.out:
        with open(args.out, "w", encoding="utf-8") as f:
            f.write(text + "\n")
    else:
        print(text)
    return 0


if __name__ == "__main__":
    sys.exit(main())
