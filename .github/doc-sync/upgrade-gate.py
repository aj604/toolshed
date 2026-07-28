#!/usr/bin/env python3
"""Version-comparison gate for the doc-sync self-upgrade pipeline.

The upgrade workflow (doc-sync-upgrade.yml) reads the installed version from
.github/doc-sync/installed-version and the latest release tag from the GitHub
API; this script owns the one decision between them so the semver comparison is
unit-tested instead of living in YAML string-fu.

Usage:
    upgrade-gate.py compare --current X.Y.Z --latest A.B.C

Prints exactly one decision token on stdout:
    current   installed is at (or past) the latest release — nothing to do
    upgrade   a strictly newer release exists — regenerate wiring, open a PR
    ahead     installed is newer than any release (a dev/prerelease pin) —
              skip, never downgrade

    upgrade-gate.py normalize --version <raw> --out FILE

Writes `target=X.Y.Z` to FILE (a `$GITHUB_OUTPUT`) — the same strict parse, used
to shape-check a human's `workflow_dispatch` input before it names a git ref.
The dispatched value reaches the clone only through the normalized output, so a
value carrying a ref expression, a path separator, or shell metacharacters fails
here rather than becoming argv.

    upgrade-gate.py notice --issues FILE --title FILE --out FILE

Prints `open` or `exists` and writes `notice=<decision>` to FILE (a
`$GITHUB_OUTPUT`) — whether the detecting job should file a notice for this
release, or whether one already stands. `--issues` is `gh issue list --json
number,title` output; `--title` is the file `render-report.py upgrade-notice`
wrote, so the dedupe key is the exact title a reader would see. One open notice
per release: a weekly check that keeps finding the same unreviewed release keeps
quiet.

Exit status: 0 with a decision on stdout; 2 on unparseable input (empty,
non-numeric, or not exactly three dot-separated components; an issue list that
is not a JSON array). A malformed version fails the workflow step red rather
than silently guessing.
"""

import argparse
import json
import sys


def parse(version):
    # Tolerate a leading 'v' (release tags are v-prefixed; installed-version is
    # bare) so a tag slipping through either side doesn't misfire.
    v = version[1:] if version[:1] == "v" else version
    parts = v.split(".")
    if len(parts) != 3:
        raise ValueError(f"expected X.Y.Z, got {version!r}")
    if not all(p.isdigit() for p in parts):
        raise ValueError(f"non-numeric component in {version!r}")
    return tuple(int(p) for p in parts)


def decide(current, latest):
    if latest > current:
        return "upgrade"
    if current > latest:
        return "ahead"
    return "current"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="mode", required=True)

    cmp_ = sub.add_parser("compare")
    cmp_.add_argument("--current", required=True)
    cmp_.add_argument("--latest", required=True)

    norm = sub.add_parser("normalize")
    norm.add_argument("--version", required=True)
    norm.add_argument("--out", required=True)

    note = sub.add_parser("notice")
    note.add_argument("--issues", required=True)
    note.add_argument("--title", required=True)
    note.add_argument("--out", required=True)

    args = parser.parse_args()

    if args.mode == "notice":
        try:
            with open(args.title, encoding="utf-8") as f:
                title = f.read().strip()
            with open(args.issues, encoding="utf-8") as f:
                issues = json.load(f)
        except (OSError, json.JSONDecodeError) as e:
            print(f"error: {e}", file=sys.stderr)
            return 2
        if not title:
            print("error: --title file is empty", file=sys.stderr)
            return 2
        if not isinstance(issues, list):
            print("error: --issues must be a JSON array "
                  "(gh issue list --json number,title)", file=sys.stderr)
            return 2
        standing = any(isinstance(i, dict) and i.get("title") == title
                       for i in issues)
        decision = "exists" if standing else "open"
        with open(args.out, "a", encoding="utf-8") as f:
            f.write(f"notice={decision}\n")
        print(decision)
        return 0

    if args.mode == "normalize":
        try:
            version = ".".join(str(p) for p in parse(args.version))
        except ValueError as e:
            print(f"error: {e}", file=sys.stderr)
            return 2
        with open(args.out, "a", encoding="utf-8") as f:
            f.write(f"target={version}\n")
        print(version)
        return 0

    try:
        current = parse(args.current)
        latest = parse(args.latest)
    except ValueError as e:
        print(f"error: {e}", file=sys.stderr)
        return 2

    print(decide(current, latest))
    return 0


if __name__ == "__main__":
    sys.exit(main())
