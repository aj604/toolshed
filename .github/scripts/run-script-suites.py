#!/usr/bin/env python3
"""Discovery-driven runner for the tests/scripts/*_test.py suites (aj604/toolshed#99).

release.yml used to enumerate every suite by hand — a list a new suite silently
drops off of if nobody remembers to add a line (this happened; caught during
#76). This script replaces the hand list: it globs `tests/scripts/*_test.py`,
runs each suite as its own subprocess, aggregates the results, and fails
loudly on any suite failure. It also refuses to report success when the glob
comes back empty, so a path/rename change can't silently shrink CI's coverage
to zero suites while staying green.

Repo-CI infrastructure, not published plugin content — lives outside plugins/
on purpose (see CLAUDE.md).

Run: python3 .github/scripts/run-script-suites.py
"""

import argparse
import glob
import os
import subprocess
import sys

ROOT = os.path.join(os.path.dirname(__file__), "..", "..")
DEFAULT_DIR = os.path.join(ROOT, "tests", "scripts")


def discover(scripts_dir):
    return sorted(glob.glob(os.path.join(scripts_dir, "*_test.py")))


def run_suite(path):
    """Run one suite as a subprocess, inheriting stdout/stderr so its
    unittest output lands directly in the CI log."""
    result = subprocess.run([sys.executable, path])
    return result.returncode == 0


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--dir", default=DEFAULT_DIR,
        help="directory to glob *_test.py suites from (default: tests/scripts)")
    args = parser.parse_args(argv)

    suites = discover(args.dir)
    if not suites:
        print(
            f"error: no *_test.py suites found under {args.dir} — refusing "
            f"to report a false green",
            file=sys.stderr,
        )
        return 1

    failed = []
    for path in suites:
        name = os.path.basename(path)
        print(f"--- running {name} ---")
        if run_suite(path):
            print(f"PASS {name}")
        else:
            print(f"FAIL {name}")
            failed.append(name)

    passed = len(suites) - len(failed)
    print(f"\n{passed}/{len(suites)} suite(s) passed")
    if failed:
        print("Failed: " + ", ".join(failed), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
