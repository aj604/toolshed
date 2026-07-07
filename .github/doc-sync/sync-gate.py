#!/usr/bin/env python3
"""Gate decisions for the doc-sync nightly pipeline.

The workflow (doc-sync.yml) gathers facts via git/gh and performs side effects
(commit, PR, issue); this script owns every branchy decision in between so the
decision matrix is unit-testable instead of living in YAML.

Usage:
    sync-gate.py pre         --commits N --open-prs N --open-issues N
    sync-gate.py post        --report FILE --cap N
    sync-gate.py bloat-pre   --prune-pr-open N --distill-pr-open N
    sync-gate.py bloat-lane  --report FILE --lane {prune|distill} --pr-open N --out FILE
    sync-gate.py bloat-retry --execution-log FILE --turns N

Prints exactly one decision token on stdout:
    pre:        skip-empty     nothing new since the marker
                skip-pending   an open doc-sync PR or issue awaits a human
                detect         run detection
    post:       advance-marker no stale claims — marker-only commit
                blast-radius   stale count exceeds cap — open issue, keep marker
                proceed        run the fix step and open a PR
    bloat-pre:  skip-pending   both lanes have open PRs
                detect         at least one lane is free
    bloat-lane: skip-pending   a lane PR is already open
                skip-empty     no findings in the lane
                open           findings await review
bloat-lane also copies the report's "unswept" gap list into --out so the PR
body can render the banner from the lane file.

bloat-retry is the exception: it classifies a failed sweep attempt from
claude-code-action's execution-output JSON and prints GITHUB_OUTPUT lines
    mode=escalate|fresh
    turns=N
A budget-shaped failure (result subtype error_max_turns) escalates to
ceil(N*1.5) capped at 60 — an identical retry would re-buy the same failure;
anything else (seam rejection, infra failure, missing log) retries fresh at
the same budget. The reason always prints to stderr.

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


PRUNE_VERDICTS = {"CUT", "CONDENSE", "EXTRACT-AND-MOVE"}
DISTILL_DOC_VERDICTS = {"MERGE-DOC", "RETIRE-DOC"}


def in_lane(record, lane):
    verdict = record.get("verdict")
    if lane == "prune":
        return verdict in PRUNE_VERDICTS
    if lane == "distill":
        if verdict in DISTILL_DOC_VERDICTS or verdict == "POLICY":
            return True
        return verdict == "DISTILL" and record.get("status") == "ready"
    raise ValueError(f"unknown lane: {lane!r}")


def filter_lane(records, lane):
    return [r for r in records if isinstance(r, dict) and in_lane(r, lane)]


def decide_bloat_pre(prune_pr_open, distill_pr_open):
    if prune_pr_open > 0 and distill_pr_open > 0:
        return "skip-pending"
    return "detect"


def decide_bloat_lane(records, lane, pr_open):
    if pr_open > 0:
        return "skip-pending"
    if not filter_lane(records, lane):
        return "skip-empty"
    return "open"


def load_records(path):
    return load_report(path)[0]


def load_report(path):
    """(records, unswept-or-None) from a report file, either shape."""
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    if isinstance(data, list):
        return data, None
    if isinstance(data, dict) and isinstance(data.get("records"), list):
        return data["records"], data.get("unswept")
    raise ValueError(
        "report must be a JSON array of records, or an object with a 'records' array"
    )


RETRY_ESCALATION = 1.5
RETRY_CEIL = 60


def result_subtype(execution_log_path):
    """The result event's subtype from claude-code-action's execution output.

    The log is either the SDK event stream (array, result event last) or a
    bare result object. (None, reason) when it cannot be read — the caller
    treats that as not-budget-shaped.
    """
    try:
        with open(execution_log_path, encoding="utf-8") as f:
            data = json.load(f)
    except FileNotFoundError:
        return None, f"no execution log at {execution_log_path}"
    except (OSError, json.JSONDecodeError, UnicodeDecodeError) as e:
        return None, f"unreadable execution log: {e}"
    events = data if isinstance(data, list) else [data]
    results = [e for e in events
               if isinstance(e, dict) and e.get("type") == "result"]
    if not results:
        return None, "no result event in execution log"
    return results[-1].get("subtype"), None


def decide_bloat_retry(execution_log_path, turns):
    """(mode, retry_turns, reason) for a failed sweep attempt."""
    subtype, problem = result_subtype(execution_log_path)
    if subtype == "error_max_turns":
        escalated = min(RETRY_CEIL, -(-turns * 3 // 2))  # ceil(turns * 1.5)
        return ("escalate", escalated,
                f"attempt exhausted its max-turns budget ({turns}); an identical "
                f"retry would re-buy the failure — escalating to {escalated}")
    why = problem or f"result subtype {subtype!r} — not budget-shaped"
    return ("fresh", turns,
            f"{why}; fresh identical retry at the same budget ({turns})")


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

    bpre = sub.add_parser("bloat-pre")
    bpre.add_argument("--prune-pr-open", type=nonneg, required=True)
    bpre.add_argument("--distill-pr-open", type=nonneg, required=True)

    blane = sub.add_parser("bloat-lane")
    blane.add_argument("--report", required=True)
    blane.add_argument("--lane", choices=["prune", "distill"], required=True)
    blane.add_argument("--pr-open", type=nonneg, required=True)
    blane.add_argument("--out", required=True)

    bretry = sub.add_parser("bloat-retry")
    bretry.add_argument("--execution-log", required=True)
    bretry.add_argument("--turns", type=positive, required=True)

    args = parser.parse_args()

    if args.mode == "bloat-retry":
        mode, turns, reason = decide_bloat_retry(args.execution_log, args.turns)
        print(reason, file=sys.stderr)
        print(f"mode={mode}")
        print(f"turns={turns}")
        return 0

    if args.mode == "pre":
        print(decide_pre(args.commits, args.open_prs, args.open_issues))
        return 0

    if args.mode == "bloat-pre":
        print(decide_bloat_pre(args.prune_pr_open, args.distill_pr_open))
        return 0

    if args.mode == "bloat-lane":
        try:
            records, unswept = load_report(args.report)
        except (OSError, ValueError, json.JSONDecodeError) as e:
            print(f"error: {e}", file=sys.stderr)
            return 2
        lane_out = {"records": filter_lane(records, args.lane)}
        if unswept:
            lane_out["unswept"] = unswept
        with open(args.out, "w", encoding="utf-8") as f:
            json.dump(lane_out, f)
        print(decide_bloat_lane(records, args.lane, args.pr_open))
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
