#!/usr/bin/env python3
"""Gate decisions for the doc-sync nightly pipeline.

The workflow (doc-sync.yml) gathers facts via git/gh and performs side effects
(commit, PR, issue); this script owns every branchy decision in between so the
decision matrix is unit-testable instead of living in YAML.

Usage:
    sync-gate.py pre  --commits N --open-prs N --open-issues N
    sync-gate.py post --report FILE --cap N

Prints exactly one decision token on stdout:
    pre:  skip-empty     nothing new since the marker
          skip-pending   an open doc-sync PR or issue awaits a human
          detect         run detection
    post: advance-marker no stale claims — marker-only commit
          blast-radius   stale count exceeds cap — open issue, keep marker
          proceed        run the fix step and open a PR

Exit status: 0 with a decision on stdout; 2 on bad input.
"""

import argparse
import json
import sys


def decide_pre(commits, open_prs, open_issues):
    if commits == 0:
        return "skip-empty"
    if open_prs > 0 or open_issues > 0:
        return "skip-pending"
    return "detect"


def decide_post(records, cap):
    # Count from records, never the summary — the validator already checked
    # the summary, and the records are the authoritative payload.
    stale = sum(
        1 for r in records if isinstance(r, dict) and r.get("verdict") == "STALE"
    )
    if stale == 0:
        return "advance-marker"
    if stale > cap:
        return "blast-radius"
    return "proceed"


def load_records(path):
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    if isinstance(data, list):
        return data
    if isinstance(data, dict) and isinstance(data.get("records"), list):
        return data["records"]
    raise ValueError(
        "report must be a JSON array of records, or an object with a 'records' array"
    )


def nonneg(value):
    n = int(value)
    if n < 0:
        raise argparse.ArgumentTypeError(f"must be >= 0, got {n}")
    return n


def positive(value):
    n = int(value)
    if n < 1:
        raise argparse.ArgumentTypeError(f"must be >= 1, got {n}")
    return n


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="mode", required=True)

    pre = sub.add_parser("pre")
    pre.add_argument("--commits", type=nonneg, required=True)
    pre.add_argument("--open-prs", type=nonneg, required=True)
    pre.add_argument("--open-issues", type=nonneg, required=True)

    post = sub.add_parser("post")
    post.add_argument("--report", required=True)
    post.add_argument("--cap", type=positive, required=True)

    args = parser.parse_args()

    if args.mode == "pre":
        print(decide_pre(args.commits, args.open_prs, args.open_issues))
        return 0

    try:
        records = load_records(args.report)
    except (OSError, ValueError, json.JSONDecodeError) as e:
        print(f"error: {e}", file=sys.stderr)
        return 2
    print(decide_post(records, args.cap))
    return 0


if __name__ == "__main__":
    sys.exit(main())
