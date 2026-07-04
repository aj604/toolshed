#!/usr/bin/env python3
"""List the in-scope documentation paths for a detecting-doc-bloat full audit.

Emits the doc paths the skill should audit so the model never enumerates the
repo with shell find/ls (which the CI allowlist denies). Deterministic: the
candidate universe is `git ls-files` under --root (untracked/gitignored files
excluded for free); if --root is not a git repo, falls back to a filesystem
walk. Default filter keeps paths ending in .md (case-insensitive) — README,
CLAUDE.md, AGENTS.md included. Config narrows or widens that set.

Usage:
    list-docs.py [--config PATH] [--root DIR] [--with-lines]

Config discovery: --config if given, else <root>/.github/doc-sync/audit-scope.json.
An absent config file is fine — pure defaults, no error.

Config shape: {"exclude": ["<glob>", ...], "include": ["<glob>", ...]}
Both keys optional (missing => empty), each an array of glob strings; {} is valid.
Globs match POSIX repo-relative paths: '*' matches within a path segment (not
'/'), '**' matches across segments. exclude drops matches; include then re-adds
any candidate it matches — even a non-.md file or one an exclude removed
(whitelist wins).

Output: repo-relative POSIX paths, one per line, sorted by path, to stdout.
With --with-lines: `<path>\t<linecount>` per line, sorted by linecount
descending then path ascending — a size map to plan sweep order. Line counts are
computed in-process (no subprocess); an unreadable file counts as 0 but is still
listed.

Exit status: 0 on success; 2 on malformed config (bad JSON, or a non-list
'exclude'/'include') — self-explaining, since nothing downstream should run on
a broken scope config.
"""

import argparse
import json
import os
import re
import subprocess
import sys


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
    """Return (exclude_globs, include_globs) as compiled regexes.

    Missing file => ([], []). Malformed JSON or a non-list value for either key
    => SystemExit(2) with a message naming the file and the problem.
    """
    try:
        with open(path, encoding="utf-8") as f:
            raw = f.read()
    except FileNotFoundError:
        return [], []
    except OSError as e:
        sys.exit(f"error: cannot read config {path}: {e}")

    try:
        data = json.loads(raw)
    except json.JSONDecodeError as e:
        sys.exit(f"error: malformed config JSON in {path}: {e}")

    if not isinstance(data, dict):
        sys.exit(f"error: config {path} must be a JSON object, got {type(data).__name__}")

    compiled = {}
    for key in ("exclude", "include"):
        val = data.get(key, [])
        if not isinstance(val, list):
            sys.exit(f"error: config {path}: '{key}' must be a list of glob strings, "
                     f"got {type(val).__name__}")
        if not all(isinstance(g, str) for g in val):
            sys.exit(f"error: config {path}: '{key}' must contain only strings")
        compiled[key] = [glob_to_regex(g) for g in val]
    return compiled["exclude"], compiled["include"]


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


def main():
    parser = argparse.ArgumentParser(
        description="List in-scope doc paths for a doc-bloat full audit.")
    parser.add_argument("--config", help="scope config JSON (default: "
                        "<root>/.github/doc-sync/audit-scope.json)")
    parser.add_argument("--root", default=os.getcwd(),
                        help="repo root to enumerate (default: cwd)")
    parser.add_argument("--with-lines", action="store_true",
                        help="append a tab + line count to each path and sort by "
                        "count descending (then path) — a size map to plan sweep order")
    args = parser.parse_args()

    config = args.config or os.path.join(
        args.root, ".github", "doc-sync", "audit-scope.json")
    exclude, include = load_config(config)

    docs = select(candidates(args.root), exclude, include)
    if args.with_lines:
        sized = [(p, line_count(os.path.join(args.root, p))) for p in docs]
        for p, n in sorted(sized, key=lambda pn: (-pn[1], pn[0])):
            print(f"{p}\t{n}")
    else:
        for p in docs:
            print(p)
    return 0


if __name__ == "__main__":
    sys.exit(main())
