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

Exit status: 0 with a decision on stdout; 2 on unparseable input (empty,
non-numeric, or not exactly three dot-separated components). A malformed
version fails the workflow step red rather than silently guessing.
"""

import argparse
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

    args = parser.parse_args()

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
