#!/usr/bin/env python3
"""Plan doc-bloat sweep chunks: inventory -> chunk manifest.

Absorbs list-docs.py: enumerates the in-scope docs (git ls-files under
--root, else a filesystem walk; default filter *.md; config exclude/include
globs, whitelist wins), then groups them into bounded chunks a single
detection invocation can hold.

Policy-scope directories (config "policy_scope") become one 'policy' chunk
each — a single POLICY record covers them; they are never walked
file-by-file. Every other doc gets a deterministic doc-kind hint (narrative
if it opens with '> As of' — the file's first line, or the first non-blank
line under a leading title; planning if a 'plans' or 'specs'
path segment contains it; else living — a hint the model may override only
with stated evidence), is grouped by (directory, hint), packed under the
caps (chunking.max_docs, default 8; chunking.max_lines, default 1200), and
consecutive underfull chunks with the same hint are coalesced while the
caps hold. A single doc larger than max_lines gets its own chunk.

Chunk ids are content-addressed (sha256 over member (path, content-sha256)
pairs, the content hash computed during the same read that counts lines), so
re-planning an unchanged tree yields the same ids — which is what makes
--results-dir resume work: a chunk whose <id>.json result already exists,
parses, and names the chunk stays in "chunks" but leaves "pending" — an
edited doc changes its chunk's id and an invalid leftover never counts, so
a stale or garbage prior result is never reused.

Every chunk carries a "turns" budget for the model invocation that will sweep
it: 12 + 2 per doc (4 per planning doc) + 1 per full 600 lines, clamped to
[20, 40]; policy chunks get a flat 20. The workflow passes it to --max-turns;
retry escalation above it is the workflow's job, not the planner's.

Usage:
    plan-chunks.py [--config PATH] [--root DIR] [--out FILE] [--results-dir DIR]
    plan-chunks.py --emit-prompt ID --manifest FILE   # print dispatch prompt
    plan-chunks.py --emit-turns ID --manifest FILE    # print turn budget

--emit-prompt renders the full headless dispatch prompt for one chunk — the
doc list (or policy dir + files) verbatim, the output path chunks/<id>.json,
and the definition of done — so prompt templating lives here, unit-tested,
never in workflow YAML. The executor is handed its slice; it never opens the
manifest.

Output (plan mode): manifest JSON {"schema": 1, "chunks": [...], "pending":
[ids]} to --out (stdout if omitted). Sweep chunks are
{"id", "kind": "sweep", "turns": N, "docs": [{"path", "lines", "hint"}]};
policy chunks are {"id", "kind": "policy", "turns": N, "dir", "files"}. The
run-surface report (doc count, chunk count, projected invocations, resume
skips) always prints to stderr.

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


def read_doc(full):
    """(line count, content sha256) in one read. Unreadable => (0, '')."""
    try:
        with open(full, encoding="utf-8", errors="replace") as f:
            text = f.read()
        return len(text.splitlines()), hashlib.sha256(
            text.encode("utf-8", "replace")).hexdigest()
    except OSError:
        return 0, ""


def doc_hint(root, path):
    """Deterministic doc-kind hint; the '> As of' anchor wins over location.

    growing-docs' template puts the anchor on the first line under the title;
    older narrative docs carry it as the file's literal first line. Accept
    both: the anchor counts on line 1, or as the first non-blank line after
    a leading '#' title. Any other first line means not-narrative.
    """
    try:
        with open(os.path.join(root, path), encoding="utf-8", errors="replace") as f:
            head = [f.readline().lstrip() for _ in range(6)]
    except OSError:
        head = []
    anchored = bool(head) and head[0].startswith("> As of")
    if not anchored and head and head[0].startswith("#"):
        for line in head[1:]:
            if not line.strip():
                continue
            anchored = line.startswith("> As of")
            break
    if anchored:
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


def chunk_id(prefix, members):
    """Content-address a chunk by its members' (path, content-sha) pairs."""
    digest = hashlib.sha256("\n".join(
        f"{path}\0{sha}" for path, sha in members).encode("utf-8")).hexdigest()
    return f"{prefix}-{digest[:10]}"


TURNS_BASE = 12
TURNS_PER_DOC = {"planning": 4}          # every other hint costs 2
TURNS_PER_LINES = 600
TURNS_FLOOR, TURNS_CEIL = 20, 40
TURNS_POLICY = 20


def turn_budget(docs):
    """Deterministic per-chunk model-invocation budget for a sweep chunk."""
    turns = TURNS_BASE
    turns += sum(TURNS_PER_DOC.get(d["hint"], 2) for d in docs)
    turns += sum(d["lines"] for d in docs) // TURNS_PER_LINES
    return max(TURNS_FLOOR, min(TURNS_CEIL, turns))


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
    sized, shas = [], {}
    for p in docs:
        lines, sha = read_doc(os.path.join(root, p))
        sized.append({"path": p, "lines": lines})
        shas[p] = sha

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
        chunks.append({"id": chunk_id("p", [(f, shas[f]) for f in files]),
                       "kind": "policy", "turns": TURNS_POLICY,
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
        chunks.append({"id": chunk_id("c", [(d["path"], shas[d["path"]])
                                            for d in c]),
                       "kind": "sweep", "turns": turn_budget(c), "docs": c})
    return len(sized), chunks


SWEEP_PROMPT = """\
You are a headless chunk executor. Invoke the doc-lifecycle:detecting-doc-bloat
skill for the verdict rules and output contract, then audit exactly the docs
listed below — no others. This list is your entire scope; do not enumerate or
open anything outside it.

Chunk {id} (sweep):
{doc_lines}

The kind hints are the planner's; override one only with stated evidence, per
the skill. Write the chunk result object {{"chunk": "{id}", "records": [...]}}
to chunks/{id}.json — an empty records array if nothing is bloated. Done means
exactly that file, in the chunk-result shape the skill's contract defines;
then stop. Orchestration, retries, and assembly belong to the workflow.
"""

POLICY_PROMPT = """\
You are a headless chunk executor. Invoke the doc-lifecycle:detecting-doc-bloat
skill for the POLICY rules. Directory {dir} is declared policy scope: emit
exactly one POLICY record covering it — never walk its files individually —
and copy this files list verbatim into the record's files field:
{file_lines}

This list is your entire scope; do not enumerate the tree or open anything
outside it (sampling a few of the listed files for the evidence field is the
audit, per the skill).

Write the chunk result object {{"chunk": "{id}", "records": [<the one POLICY
record>]}} to chunks/{id}.json. Done means exactly that file, in the
chunk-result shape the skill's contract defines; then stop.
"""


def usable_result(results_dir, cid):
    """True only for a parseable result that names this chunk. An invalid
    file surviving a failed CI retry must not mask the chunk as done."""
    path = os.path.join(results_dir, cid + ".json")
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, json.JSONDecodeError, UnicodeDecodeError):
        return False
    return isinstance(data, dict) and data.get("chunk") == cid


def load_manifest(path):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, json.JSONDecodeError) as e:
        die(f"error: cannot read manifest {path}: {e}")


def find_chunk(man, cid):
    for c in man.get("chunks", []):
        if c.get("id") == cid:
            return c
    die(f"error: chunk {cid} not found in manifest")


def emit_prompt(chunk):
    if chunk["kind"] == "policy":
        return POLICY_PROMPT.format(
            id=chunk["id"], dir=chunk["dir"],
            file_lines="\n".join(f"  - {f}" for f in chunk["files"]))
    return SWEEP_PROMPT.format(
        id=chunk["id"],
        doc_lines="\n".join(
            f"  - {d['path']} ({d['lines']} lines, hint: {d['hint']})"
            for d in chunk["docs"]))


def main():
    ap = argparse.ArgumentParser(description="Plan doc-bloat sweep chunks.")
    ap.add_argument("--config", help="scope config JSON (default: "
                    "<root>/.github/doc-sync/audit-scope.json)")
    ap.add_argument("--root", default=os.getcwd(),
                    help="repo root to enumerate (default: cwd)")
    ap.add_argument("--out", help="write the manifest here (default: stdout)")
    ap.add_argument("--results-dir", help="existing chunk-result dir; chunks "
                    "with a <id>.json there stay in 'chunks' but leave 'pending'")
    ap.add_argument("--emit-prompt", metavar="ID",
                    help="print the dispatch prompt for one manifest chunk")
    ap.add_argument("--emit-turns", metavar="ID",
                    help="print the turn budget for one manifest chunk")
    ap.add_argument("--manifest", help="manifest JSON for --emit-prompt/"
                    "--emit-turns")
    args = ap.parse_args()

    if args.emit_prompt or args.emit_turns:
        if not args.manifest:
            die("error: --emit-prompt/--emit-turns require --manifest")
        man = load_manifest(args.manifest)
        if args.emit_prompt:
            print(emit_prompt(find_chunk(man, args.emit_prompt)), end="")
        else:
            # v0.7.0 manifests predate 'turns'; the floor is the safe default.
            print(find_chunk(man, args.emit_turns).get("turns", TURNS_FLOOR))
        return 0

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
        pending = [c["id"] for c in chunks
                   if not usable_result(args.results_dir, c["id"])]

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
