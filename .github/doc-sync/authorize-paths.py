#!/usr/bin/env python3
"""Path authority for the model-produced edit sets in the doc-sync/doc-bloat lanes.

The model steps hold no repository write authority. A model job runs read-only
and emits its edits as a patch artifact; a separate credentialed job runs this
script to decide which paths that artifact is allowed to touch, stages exactly
those, and opens the PR. An artifact naming any other path fails the job loudly
— no PR, nothing staged. The authority is derived from the validated report, so
it is the report (not the model's own claim about what it edited) that bounds
the diff.

Two duties:

1. Derive the authority from the report:
       authorize-paths.py expected --report FILE --lane {drift|prune|distill}
                          [--config PATH] --out FILE
   drift    the file of every STALE record's location — the fix lane edits
            those locations and nothing else.
   prune    every prune-lane record's doc, plus each EXTRACT-AND-MOVE target.
   distill  every distill-lane record's doc (POLICY: its files), each MERGE-DOC
            target, and docs/decisions.md — plus "scope" mode: the distiller
            chooses where residue lands and which inbound references it
            repoints, so its targets cannot be enumerated up front. Scope mode
            authorizes any in-scope documentation file instead of an exact list.
   A record naming a path outside the documentation authority (the wiring, a
   path escaping the repo, a non-doc file) fails derivation — it is not a
   documentation finding.

2. Check an edit set against that authority:
       authorize-paths.py check --expected FILE
                          [--paths FILE|-] [--patch FILE]... [--patches-dir DIR]
                          [--repo DIR] [--allow-workflow-state]
   Patch paths are read with `git apply --numstat` (git parses the patch; this
   script never applies it). On success the authorized paths print to stdout,
   one per line, for `git add --pathspec-from-file=` — the explicit staging list
   that replaces `git add -A`. On violation every offending path prints with its
   reason and the exit status is 1.
   --allow-workflow-state additionally authorizes the pipeline's own state files
   (marker, last-stales) — for the post-staging re-check in the credentialed job
   that writes them. A model patch is never checked with that flag, so a patch
   reaching for the marker still fails.

Generate patches with --no-renames: `git apply --numstat` reports a detected
rename as its destination path only, which would leave the source path
unchecked. A patch carrying a rename record is therefore refused outright
rather than half-checked.

Path-glob semantics (`*` within a segment, `**` across) and the audit-scope
exclude/include lists are plan-chunks.py's, imported rather than restated.

Config discovery: --config if given, else .github/doc-sync/audit-scope.json
under the cwd. Only "exclude"/"include" are read. `include` re-admits non-`.md`
documentation everywhere; `exclude` applies in scope mode only. Deliberate:
`exclude` scopes the *bloat audit's corpus*, while drift is diff-scoped over the
whole repo, so refusing an exactly-named STALE record because its doc sits
outside the bloat corpus would fail a legitimate fix. Scope mode has no exact
list to lean on, so there the audited corpus is the write surface.

Two boundaries this does not draw, and why:
- Agent-instruction docs (CLAUDE.md, AGENTS.md, SKILL.md files) are writable
  like any other `.md` — they are exactly the docs this pipeline maintains, so
  denying them would deny the product. What executes without review is the
  wiring, and that is denied outright.
- The report bounding the authority is itself model output, so this confines an
  edit set to documentation the report named; it does not establish that the
  report was honest. That is the approval-set stage of the re-architecture
  (aj604/toolshed#57); here PR review is the backstop.

Exit status: 0 authorized; 1 a path outside the authority; 2 bad input.
"""

import argparse
import glob as globlib
import importlib.util
import json
import os
import posixpath
import re
import subprocess
import sys

DECISION_LOG = "docs/decisions.md"

# Never model-writable, whatever a record says: git's own directory, and the
# pipeline's wiring and state. A record or a patch naming one of these is not a
# documentation finding — it is the mutation path this split exists to close.
DENY_PREFIXES = (".git/", ".github/workflows/", ".github/doc-sync/")

# Written by the credentialed job itself, never by a model patch. `check
# --allow-workflow-state` is the only way in.
WORKFLOW_STATE = (".github/doc-sync-marker",
                  ".github/doc-sync/last-stales.json")


def die(msg):
    """Self-explaining bad-input exit (code 2)."""
    print(msg, file=sys.stderr)
    raise SystemExit(2)


def _load(module_name, *candidates):
    """Import a helper script from the first candidate path that exists.

    Vendored installs put every script in one directory; in the plugin source
    tree each lives under the skill that owns it. No bytecode cache: a
    __pycache__/ inside .github/doc-sync/ would be one careless `git add -A`
    away from a consumer's history.
    """
    sys.dont_write_bytecode = True
    here = os.path.dirname(os.path.abspath(__file__))
    for rel in candidates:
        path = os.path.normpath(os.path.join(here, rel))
        if not os.path.isfile(path):
            continue
        spec = importlib.util.spec_from_file_location(module_name, path)
        mod = importlib.util.module_from_spec(spec)
        try:
            spec.loader.exec_module(mod)
        except (OSError, SyntaxError) as e:
            die(f"error: cannot load {path}: {e}")
        return mod
    die(f"error: cannot find {module_name} beside {here}")


def load_sync_gate():
    """The lane mapping's one owner."""
    return _load("sync_gate", "sync-gate.py")


def load_plan_chunks():
    """The path-glob semantics' one owner."""
    return _load("plan_chunks", "plan-chunks.py",
                 "../../detecting-doc-bloat/scripts/plan-chunks.py")


def load_scope(path):
    """The audit scope's raw exclude/include glob lists."""
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
    except FileNotFoundError:
        return {"exclude": [], "include": []}
    except (OSError, json.JSONDecodeError) as e:
        die(f"error: cannot read config {path}: {e}")
    if not isinstance(data, dict):
        die(f"error: config {path} must be a JSON object")
    scope = {}
    for key in ("exclude", "include"):
        val = data.get(key, [])
        if not (isinstance(val, list) and all(isinstance(g, str) for g in val)):
            die(f"error: config {path}: '{key}' must be a list of strings")
        scope[key] = val
    return scope


def load_records(path):
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, json.JSONDecodeError) as e:
        die(f"error: cannot read report {path}: {e}")
    if isinstance(data, list):
        return data
    records = data.get("records") if isinstance(data, dict) else None
    if not isinstance(records, list):
        die(f"error: report {path} carries no records array")
    return records


WINDOWS_DRIVE_RE = re.compile(r"^[A-Za-z]:")


def safety_error(path):
    """Why this path may never be written by a model edit set — or None."""
    if not isinstance(path, str) or not path.strip():
        return "empty path"
    if path != path.strip():
        return "leading or trailing whitespace"
    if "\\" in path or "\n" in path or "\t" in path:
        return "backslash or control character in path"
    if path.startswith("/") or WINDOWS_DRIVE_RE.match(path):
        return "absolute path"
    if posixpath.normpath(path) != path:
        return (f"not a normalized repo-relative path "
                f"(normalizes to {posixpath.normpath(path)!r})")
    if path == ".." or path.startswith("../"):
        return "escapes the repository"
    if any(path.startswith(p) for p in DENY_PREFIXES):
        return "the pipeline's own wiring and state are never model-writable"
    return None


def matches_any(path, patterns):
    return any(p.match(path) for p in patterns)


def kind_error(path, include):
    """Why this path is not a documentation file — or None."""
    if matches_any(path, include) or path.lower().endswith(".md"):
        return None
    return "not a documentation file (*.md, or an audit-scope 'include' glob)"


def scope_error(path, include, exclude):
    """Why this path is outside the audited documentation scope — or None."""
    # Whitelist wins, exactly as plan-chunks.py selects the audited corpus.
    if matches_any(path, include):
        return None
    err = kind_error(path, include)
    if err:
        return err
    if matches_any(path, exclude):
        return "outside the audited documentation scope (audit-scope 'exclude')"
    return None


def target_of(record):
    proposal = record.get("proposal")
    return proposal.get("target") if isinstance(proposal, dict) else None


def derive(records, lane, in_lane):
    """The paths the report authorizes this lane's edit set to touch."""
    paths = []
    records = [r for r in records if isinstance(r, dict)]
    if lane == "drift":
        for r in records:
            if r.get("verdict") != "STALE":
                continue
            loc = r.get("location")
            loc = loc if isinstance(loc, str) else ""
            paths.append(loc.rpartition(":")[0] or loc)
        return paths
    for r in records:
        if not in_lane(r, lane):
            continue
        if r.get("verdict") == "POLICY":
            # A POLICY record's doc is the covered directory; its files are the
            # complete mandate (validate-bloat-output.py enforces the list).
            files = r.get("files")
            paths.extend(files if isinstance(files, list) else [files])
        else:
            paths.append(r.get("doc"))
        if r.get("verdict") in ("EXTRACT-AND-MOVE", "MERGE-DOC"):
            paths.append(target_of(r))
    if lane == "distill":
        # The distiller appends exactly one entry to the decision log.
        paths.append(DECISION_LOG)
    return paths


def run_expected(args):
    scope = load_scope(args.config or os.path.join(
        os.getcwd(), ".github", "doc-sync", "audit-scope.json"))
    glob_to_regex = load_plan_chunks().glob_to_regex
    include = [glob_to_regex(g) for g in scope["include"]]
    in_lane = load_sync_gate().in_lane if args.lane != "drift" else None

    errs, paths = [], []
    for p in derive(load_records(args.report), args.lane, in_lane):
        if not isinstance(p, str) or not p.strip():
            errs.append(f"a {args.lane}-lane record names no usable path ({p!r})")
            continue
        err = safety_error(p) or kind_error(p, include)
        if err:
            errs.append(f"{p}: {err}")
        elif p not in paths:
            paths.append(p)

    if errs:
        for e in errs:
            print(e, file=sys.stderr)
        print(f"\nFAILED: {len(errs)} record path(s) outside the documentation "
              f"authority — no PR, nothing staged", file=sys.stderr)
        return 1

    expected = {"lane": args.lane,
                "mode": "scope" if args.lane == "distill" else "exact",
                "paths": sorted(paths),
                "scope": scope}
    with open(args.out, "w", encoding="utf-8") as f:
        json.dump(expected, f, indent=2)
        f.write("\n")
    print(f"{args.lane}: {len(paths)} path(s) authorized by the report "
          f"({expected['mode']} mode)", file=sys.stderr)
    return 0


class Authority:
    """The derived authority, as the check side asks it questions."""

    def __init__(self, data, allow_workflow_state):
        if not (isinstance(data, dict) and data.get("mode") in ("exact", "scope")
                and isinstance(data.get("paths"), list)
                and isinstance(data.get("scope"), dict)):
            die("error: --expected must be an authorize-paths.py 'expected' file")
        glob_to_regex = load_plan_chunks().glob_to_regex
        self.mode = data["mode"]
        self.exact = set(data["paths"])
        if allow_workflow_state:
            self.exact |= set(WORKFLOW_STATE)
        self.include = [glob_to_regex(g) for g in data["scope"].get("include", [])]
        self.exclude = [glob_to_regex(g) for g in data["scope"].get("exclude", [])]

    def error(self, path):
        # An exact grant is already authority-checked (at derivation, or by the
        # --allow-workflow-state contract), so it answers first.
        if path in self.exact:
            return None
        err = safety_error(path)
        if err:
            return err
        if self.mode == "scope":
            return scope_error(path, self.include, self.exclude)
        return "not named by any record the report authorized for this lane"


RENAME_HEADER_RE = re.compile(r"^rename (from|to) ", re.M)


def rename_record_error(patch):
    """A rename record hides its source path from --numstat — refuse it."""
    try:
        with open(patch, encoding="utf-8", errors="replace") as f:
            text = f.read()
    except OSError as e:
        die(f"error: cannot read patch {patch}: {e}")
    if RENAME_HEADER_RE.search(text):
        return (f"{patch}: carries a rename record, which reports only its "
                f"destination to the authority check — regenerate the patch "
                f"with --no-renames")
    return None


def patch_paths(repo, patch):
    """Every path a patch touches, per `git apply --numstat` (never applied)."""
    try:
        if os.path.getsize(patch) == 0:
            return []
    except OSError as e:
        die(f"error: cannot read patch {patch}: {e}")
    # Absolute: `git -C <repo>` resolves the patch path relative to <repo>.
    proc = subprocess.run(
        ["git", "-C", repo, "apply", "--numstat", os.path.abspath(patch)],
        capture_output=True, text=True, check=False)
    if proc.returncode != 0:
        die(f"error: cannot read patch {patch}: {proc.stderr.strip()}")
    paths = []
    for line in proc.stdout.splitlines():
        parts = line.split("\t")
        if len(parts) < 3:
            continue
        paths.append("\t".join(parts[2:]))
    return paths


def read_path_list(src):
    raw = sys.stdin.read() if src == "-" else open(src, encoding="utf-8").read()
    return [line for line in raw.splitlines() if line.strip()]


def run_check(args):
    try:
        with open(args.expected, encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, json.JSONDecodeError) as e:
        die(f"error: cannot read --expected {args.expected}: {e}")
    authority = Authority(data, args.allow_workflow_state)

    if not (args.paths or args.patch or args.patches_dir):
        die("error: check needs --paths, --patch, or --patches-dir")
    patches = list(args.patch or [])
    if args.patches_dir:
        # A patches dir with no series in it is a lane that landed nothing —
        # an empty authorized set, not bad input.
        patches.extend(sorted(globlib.glob(
            os.path.join(args.patches_dir, "**", "*.patch"), recursive=True)))

    changed, errs, authorized = [], [], []
    if args.paths:
        try:
            changed.extend(read_path_list(args.paths))
        except OSError as e:
            die(f"error: cannot read --paths {args.paths}: {e}")
    for patch in patches:
        err = rename_record_error(patch)
        if err:
            errs.append(err)
            continue
        changed.extend(patch_paths(args.repo, patch))

    for path in changed:
        err = authority.error(path)
        if err:
            errs.append(f"{path}: {err}")
        elif path not in authorized:
            authorized.append(path)

    if errs:
        errs = list(dict.fromkeys(errs))
        for e in errs:
            print(e, file=sys.stderr)
        print(f"\nFAILED: {len(errs)} unauthorized path(s) — the edit set "
              f"reaches outside what the report authorized; nothing staged, "
              f"no PR", file=sys.stderr)
        return 1

    for path in sorted(authorized):
        print(path)
    print(f"{len(authorized)} path(s) authorized", file=sys.stderr)
    return 0


def main():
    ap = argparse.ArgumentParser(
        description="Derive and enforce the path authority for a model edit set.")
    sub = ap.add_subparsers(dest="mode", required=True)

    exp = sub.add_parser("expected", help="derive the authority from a report")
    exp.add_argument("--report", required=True)
    exp.add_argument("--lane", choices=["drift", "prune", "distill"],
                     required=True)
    exp.add_argument("--config", help="audit-scope JSON (default: "
                     ".github/doc-sync/audit-scope.json under the cwd)")
    exp.add_argument("--out", required=True)

    chk = sub.add_parser("check", help="check an edit set against the authority")
    chk.add_argument("--expected", required=True)
    chk.add_argument("--paths", help="file of changed paths, one per line "
                     "('-' for stdin)")
    chk.add_argument("--patch", action="append",
                     help="patch file to read paths from (repeatable)")
    chk.add_argument("--patches-dir", help="directory tree of *.patch files")
    chk.add_argument("--repo", default=os.getcwd(),
                     help="git dir to parse patches with (default: cwd)")
    chk.add_argument("--allow-workflow-state", action="store_true",
                     help="also authorize the pipeline's own state files "
                          "(marker, last-stales) — never for a model patch")

    args = ap.parse_args()
    return run_expected(args) if args.mode == "expected" else run_check(args)


if __name__ == "__main__":
    sys.exit(main())
