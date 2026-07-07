#!/usr/bin/env python3
"""Run-surface rendering for the doc-sync nightly pipeline.

The workflow (doc-sync.yml) gathers facts and performs side effects; sync-gate.py
owns the decisions; this script owns every user-facing string — step summaries,
::notice:: annotations, and issue/PR bodies — so the pipeline's self-explaining
exits are unit-testable instead of living as jq/heredoc templates in YAML.

Usage:
    render-report.py pre-summary --decision D --marker M --head H --commits N --open-prs N --open-issues N
    render-report.py no-drift-summary --commits N --head H [--push-rejected]
    render-report.py issue-body --report FILE --cap N --marker M --head H
    render-report.py blast-summary --report FILE --cap N --issue-url URL
    render-report.py pr-body --report FILE --marker M --head H
    render-report.py pr-title --report FILE --date YYYY-MM-DD
    render-report.py pr-summary --report FILE --pr-url URL
    render-report.py bloat-pre-summary --decision {detect|skip-pending}
    render-report.py bloat-pr-body --report FILE
    render-report.py bloat-pr-title --report FILE --lane L --date YYYY-MM-DD
    render-report.py bloat-pr-summary --report FILE --lane L --pr-url URL
    render-report.py bloat-skip-summary --lane L --reason {skip-empty|skip-pending|skip-noop}
    render-report.py bloat-triage --report FILE

Body subcommands (issue-body, pr-body) print markdown on stdout for --body-file.
Summary subcommands append to the file named by $GITHUB_STEP_SUMMARY (stdout when
unset) and print ::notice:: annotations on stdout where the old workflow did.

Exit status: 0 on success; 2 on bad input.
"""

import argparse
import json
import os
import sys


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


def by_verdict(records, verdict):
    return [r for r in records if isinstance(r, dict) and r.get("verdict") == verdict]


def write_summary(text):
    path = os.environ.get("GITHUB_STEP_SUMMARY")
    if path:
        with open(path, "a", encoding="utf-8") as f:
            f.write(text + "\n")
    else:
        print(text)


def notice(text):
    print(f"::notice::{text}")


def render_pre_summary(args):
    if args.decision == "skip-empty":
        notice("doc-sync skipped: nothing new since the marker")
        write_summary(
            f"⏭️ **Skipped — nothing to sync.** No commits (beyond marker bookkeeping) "
            f"since marker `{args.marker}`. No model calls were made."
        )
    elif args.decision == "skip-pending":
        notice("doc-sync skipped: a doc-sync PR/issue awaits a human")
        write_summary(
            f"⏭️ **Skipped — pending human review.** Open doc-sync PRs: {args.open_prs}, "
            f"open `doc-sync` issues: {args.open_issues}. The nightly resumes after they "
            f"are merged/closed. No model calls were made."
        )
    elif args.decision == "detect":
        write_summary(
            f"▶️ **Checking {args.commits} commit(s)** for doc drift over "
            f"`{args.marker}..{args.head}`."
        )
    else:
        raise ValueError(f"unknown pre-gate decision: {args.decision!r}")


def render_no_drift_summary(args):
    if args.push_rejected:
        notice(
            "marker push rejected (branch protection?) — marker will advance with the "
            "next doc-sync PR"
        )
        write_summary(
            f"✅ **No drift** ({args.commits} commit(s) checked) — but the marker push "
            f"was rejected (branch protection?); it will advance with the next doc-sync PR."
        )
    else:
        write_summary(
            f"✅ **No drift.** {args.commits} commit(s) checked, all doc claims still "
            f"hold; marker advanced to `{args.head}`."
        )


def render_issue_body(records, cap, marker, head):
    lines = [
        f"Nightly doc-sync found more stale claims than the blast-radius cap ({cap}) "
        f"over `{marker}..{head}`.",
        "Per the doc-lifecycle guardrails this is escalated instead of opened as a giant PR.",
        "The sync marker was NOT advanced; close this issue after handling to let the "
        "nightly resume.",
        "",
        "## Stale claims",
    ]
    for r in by_verdict(records, "STALE"):
        lines.append(f"- `{r['location']}` — {r['claim']}")
        lines.append(f"  - **evidence:** {r['evidence']}")
        lines.append(f"  - **drafted fix:** {r['fix']}")
    return "\n".join(lines)


def render_blast_summary(records, cap, issue_url):
    stale = len(by_verdict(records, "STALE"))
    return (
        f"🛑 **Blast-radius stop.** {stale} stale claims exceed the cap ({cap}) — "
        f"escalated as {issue_url} instead of a giant PR. Marker NOT advanced; the "
        f"nightly resumes when the issue is closed."
    )


def md_cell(text):
    # Cells escape | and flatten newlines so evidence can't break its row.
    return str(text).replace("|", "\\|").replace("\n", " ")


def render_pr_body(records, marker, head):
    lines = [
        f"Nightly doc sync over `{marker}..{head}` — merge to advance the marker, "
        "close to re-check next run.",
        "",
        "| Fixed (see diff) | Why it was stale |",
        "|---|---|",
    ]
    for r in by_verdict(records, "STALE"):
        lines.append(f"| `{r['location']}` | {md_cell(r['evidence'])} |")
    unverifiable = by_verdict(records, "UNVERIFIABLE")
    if unverifiable:
        lines.append("")
        lines.append("| Flagged for a human — not edited | Why unverifiable |")
        lines.append("|---|---|")
        for r in unverifiable:
            lines.append(f"| `{r['location']}` | {md_cell(r['evidence'])} |")
    return "\n".join(lines)


def render_pr_title(records, date):
    stale = len(by_verdict(records, "STALE"))
    flagged = len(by_verdict(records, "UNVERIFIABLE"))
    title = "docs: nightly sync — 1 fix" if stale == 1 else f"docs: nightly sync — {stale} fixes"
    if flagged > 0:
        title += f", {flagged} flagged"
    return f"{title} ({date})"


def render_pr_summary(records, pr_url):
    stale = len(by_verdict(records, "STALE"))
    return (
        f"📝 **Drift found and fixed.** {stale} stale claim(s) corrected — review "
        f"{pr_url}. Merging it advances the marker; closing it unmerged re-checks the "
        f"range next night."
    )


def render_bloat_pre_summary(decision):
    if decision == "detect":
        return "▶️ **Weekly doc-bloat sweep** — auditing every doc (incl. `docs/plans/`)."
    if decision == "skip-pending":
        return ("⏭️ **Skipped — both bloat PRs are open.** `doc-bloat/prune` and "
                "`doc-bloat/distill` await review; the sweep resumes after they merge/close.")
    raise ValueError(f"unknown bloat-pre decision: {decision!r}")


def bloat_change_cell(r):
    where = r.get("location") or r.get("doc")
    verdict = r["verdict"]
    if verdict == "DISTILL":
        verdict = f"DISTILL({r.get('status')})"
    cell = f"`{verdict}` @ `{where}`"
    if r["verdict"] == "POLICY":
        cell += f" ({len(r.get('files') or [])} files)"
    return cell


def render_bloat_rollup(records):
    counts, docs = {}, set()
    for r in records:
        counts[r["verdict"]] = counts.get(r["verdict"], 0) + 1
        docs.add(r["doc"])
    order = ["CUT", "CONDENSE", "EXTRACT-AND-MOVE", "RETIRE-DOC",
             "MERGE-DOC", "DISTILL", "POLICY"]
    parts = [f"{v.lower().replace('-', ' ')} {counts[v]}" for v in order if v in counts]
    return (f"**Rollup:** {len(records)} record(s) across {len(docs)} doc(s) — "
            + ", ".join(parts))


def render_bloat_pr_body(records):
    lines = [
        "Proposed by the weekly doc-bloat sweep — each row is applied in the diff below. "
        "Draft PR: review, drop any commit you don't want, merge to accept.",
        "",
        render_bloat_rollup(records),
        "",
        "| Change (see diff) | Why it's bloat |",
        "|---|---|",
    ]
    for r in records:
        lines.append(f"| {bloat_change_cell(r)} | {md_cell(r['evidence'])} |")
    return "\n".join(lines)


def render_bloat_triage(records):
    """In-session triage view: rollup, then records grouped by doc, one line
    per record — the human approves by the [id]s shown."""
    by_doc = {}
    for r in records:
        by_doc.setdefault(r["doc"], []).append(r)
    lines = [render_bloat_rollup(records), ""]
    for doc in sorted(by_doc):
        lines.append(doc)
        for r in by_doc[doc]:
            verdict = r["verdict"]
            if verdict == "DISTILL":
                verdict = f"DISTILL({r.get('status')})"
            where = r.get("location") or ""
            extra = f" ({len(r.get('files') or [])} files)" if r["verdict"] == "POLICY" else ""
            lines.append(f"  [{r['id']}] {verdict:<14} {where}{extra} — "
                         f"{md_cell(r['evidence'])}")
    return "\n".join(lines)


def render_bloat_pr_title(records, lane, date):
    n = len(records)
    noun = "change" if n == 1 else "changes"
    return f"docs: bloat {lane} — {n} {noun} ({date})"


def render_bloat_pr_summary(records, lane, pr_url):
    n = len(records)
    return (f"🧹 **Bloat sweep — {lane} lane.** {n} proposed change(s) — review {pr_url}. "
            f"Draft PR: merge to accept, close to discard.")


def render_bloat_skip_summary(lane, reason):
    msgs = {
        "skip-empty": f"✅ **{lane} lane: nothing to propose.** The sweep found no {lane} findings.",
        "skip-pending": f"⏭️ **{lane} lane skipped.** An open `doc-bloat/{lane}` PR awaits review.",
        "skip-noop": (f"✅ **{lane} lane: no diff to propose.** The approved {lane} records "
                      f"produced no change — already applied, or every claim failed re-verification."),
    }
    if reason not in msgs:
        raise ValueError(f"unknown skip reason: {reason!r}")
    return msgs[reason]


def nonneg(value):
    n = int(value)
    if n < 0:
        raise argparse.ArgumentTypeError(f"must be >= 0, got {n}")
    return n


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="mode", required=True)

    pre = sub.add_parser("pre-summary")
    pre.add_argument("--decision", required=True)
    pre.add_argument("--marker", required=True)
    pre.add_argument("--head", required=True)
    pre.add_argument("--commits", type=nonneg, required=True)
    pre.add_argument("--open-prs", type=nonneg, required=True)
    pre.add_argument("--open-issues", type=nonneg, required=True)

    nodrift = sub.add_parser("no-drift-summary")
    nodrift.add_argument("--commits", type=nonneg, required=True)
    nodrift.add_argument("--head", required=True)
    nodrift.add_argument("--push-rejected", action="store_true")

    issue = sub.add_parser("issue-body")
    issue.add_argument("--report", required=True)
    issue.add_argument("--cap", type=nonneg, required=True)
    issue.add_argument("--marker", required=True)
    issue.add_argument("--head", required=True)

    blast = sub.add_parser("blast-summary")
    blast.add_argument("--report", required=True)
    blast.add_argument("--cap", type=nonneg, required=True)
    blast.add_argument("--issue-url", required=True)

    prbody = sub.add_parser("pr-body")
    prbody.add_argument("--report", required=True)
    prbody.add_argument("--marker", required=True)
    prbody.add_argument("--head", required=True)

    prtitle = sub.add_parser("pr-title")
    prtitle.add_argument("--report", required=True)
    prtitle.add_argument("--date", required=True)

    prsum = sub.add_parser("pr-summary")
    prsum.add_argument("--report", required=True)
    prsum.add_argument("--pr-url", required=True)

    bpre = sub.add_parser("bloat-pre-summary")
    bpre.add_argument("--decision", required=True)

    bbody = sub.add_parser("bloat-pr-body")
    bbody.add_argument("--report", required=True)

    btitle = sub.add_parser("bloat-pr-title")
    btitle.add_argument("--report", required=True)
    btitle.add_argument("--lane", required=True)
    btitle.add_argument("--date", required=True)

    bsum = sub.add_parser("bloat-pr-summary")
    bsum.add_argument("--report", required=True)
    bsum.add_argument("--lane", required=True)
    bsum.add_argument("--pr-url", required=True)

    bskip = sub.add_parser("bloat-skip-summary")
    bskip.add_argument("--lane", required=True)
    bskip.add_argument("--reason", required=True)

    btriage = sub.add_parser("bloat-triage")
    btriage.add_argument("--report", required=True)

    args = parser.parse_args()

    try:
        if args.mode == "pre-summary":
            render_pre_summary(args)
        elif args.mode == "no-drift-summary":
            render_no_drift_summary(args)
        elif args.mode == "bloat-pre-summary":
            write_summary(render_bloat_pre_summary(args.decision))
        elif args.mode == "bloat-skip-summary":
            write_summary(render_bloat_skip_summary(args.lane, args.reason))
        else:
            records = load_records(args.report)
            if args.mode == "issue-body":
                print(render_issue_body(records, args.cap, args.marker, args.head))
            elif args.mode == "blast-summary":
                write_summary(render_blast_summary(records, args.cap, args.issue_url))
            elif args.mode == "pr-body":
                print(render_pr_body(records, args.marker, args.head))
            elif args.mode == "pr-title":
                print(render_pr_title(records, args.date))
            elif args.mode == "pr-summary":
                write_summary(render_pr_summary(records, args.pr_url))
            elif args.mode == "bloat-pr-body":
                print(render_bloat_pr_body(records))
            elif args.mode == "bloat-pr-title":
                print(render_bloat_pr_title(records, args.lane, args.date))
            elif args.mode == "bloat-pr-summary":
                write_summary(render_bloat_pr_summary(records, args.lane, args.pr_url))
            elif args.mode == "bloat-triage":
                print(render_bloat_triage(records))
    except (OSError, ValueError, KeyError, json.JSONDecodeError) as e:
        print(f"error: {e!r}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
