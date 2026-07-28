#!/usr/bin/env python3
"""Run-surface rendering for the read-only audit lane (doc-audit.yml, #71).

The workflow gathers facts and runs the engine's own CLI (`drift-plan`,
`drift-audit`); this script owns every user-facing string for that lane —
the self-explaining outcome, pinned lineage, and cost/budget observability —
so it is unit-testable instead of living as jq/heredoc templates in YAML.

Every one of the report contract's five result states renders here, plus the
one state the contract itself cannot describe: the audit job produced no
report file at all (a crashed job, a stray chunk-worker entry per the engine
README's warning). That is rendered as its own typed problem
(`audit-report-missing`), never silence and never an empty-looking report.

Usage:
    render-audit-summary.py cost --execution-log FILE --out FILE
    render-audit-summary.py summary --report FILE [--cost FILE]

`cost` is best-effort and never fails the run: an absent or unreadable
execution log, or one with no `result` event, writes
`{"available": false, "turns": null, "cost_usd": null, "duration_ms": null}`
rather than erroring — cost is observability, never a gate.

`summary` appends the rendered Markdown to the file named by
$GITHUB_STEP_SUMMARY (stdout when unset).

Exit status: 0 whenever a subcommand ran with valid arguments — including a
missing or unreadable --report/--cost *file*, which renders (or, for `cost`,
records) as its own typed outcome rather than failing the script; a typed
render IS success here, even when it describes a failed audit. 2 is reserved
for bad invocation only: a missing required flag or an unknown subcommand,
both caught by argparse before either subcommand's body runs.
"""

import argparse
import json
import os
import sys


# -- cost extraction ---------------------------------------------------------

def extract_cost(execution_log_path):
    """{"available", "turns", "cost_usd", "duration_ms"} — never raises.

    claude-code-action's execution output is a JSON list of events (or a single
    event); the last "result" event carries the run's totals. Missing,
    unreadable, or empty of a result event is simply "not available" — a
    best-effort observability figure, never worth failing the run over.
    """
    unavailable = {"available": False, "turns": None, "cost_usd": None,
                   "duration_ms": None}
    try:
        with open(execution_log_path, encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, ValueError, UnicodeDecodeError):
        return unavailable
    events = data if isinstance(data, list) else [data]
    results = [e for e in events
               if isinstance(e, dict) and e.get("type") == "result"]
    if not results:
        return unavailable
    last = results[-1]
    return {
        "available": True,
        "turns": last.get("num_turns"),
        "cost_usd": last.get("total_cost_usd"),
        "duration_ms": last.get("duration_ms"),
    }


# -- rendering ----------------------------------------------------------------

def _lineage_line(lineage):
    return (
        f"**Lineage:** commit `{lineage.get('base_commit', '?')}` &middot; "
        f"mode `{lineage.get('audit_mode', '?')}` &middot; "
        f"ruleset v{lineage.get('ruleset_version', '?')} &middot; "
        f"plugin {lineage.get('plugin_version', '?')} &middot; "
        f"registry `{lineage.get('registry_digest', '?')}`"
    )


def _cost_lines(cost):
    if cost is None:
        return []
    if not cost.get("available"):
        return ["", "**Cost & budget:** not available for this run."]
    return [
        "",
        "**Cost & budget (observability only — does not narrow the declared "
        f"scope above):** {cost.get('turns')} turn(s), "
        f"${cost.get('cost_usd')}, {cost.get('duration_ms')}ms",
    ]


def render_missing_report(report_path):
    lines = [
        "## Doc audit: NO REPORT PRODUCED",
        "",
        f"The audit job produced no report at `{report_path}` — this is a "
        "failure of the job itself, not an audit finding. A missing report "
        "is never rendered as an empty or clean result.",
        "",
        "**Problems:**",
        "- `audit-report-missing`: no report file was found where the audit "
        "job was expected to write one — check the `audit` job's logs",
    ]
    return lines


def render_invalid(payload):
    lines = ["## Doc audit: INVALID", "", "The run cannot be trusted — no findings are reported.", "",
             "**Problems:**"]
    for problem in payload.get("problems", []):
        where = f" ({problem.get('location')})" if problem.get("location") else ""
        lines.append(f"- `{problem.get('code')}`: {problem.get('message')}{where}")
    return lines


def render_stale(payload):
    lineage = payload.get("lineage", {})
    lines = ["## Doc audit: STALE", "",
             "The report no longer matches the repository it describes.", "",
             "**Stale reasons:**"]
    for reason in payload.get("stale_reasons", []):
        lines.append(
            f"- `{reason.get('code')}`: {reason.get('message')} "
            f"(reported `{reason.get('reported')}`, now `{reason.get('current')}`)"
        )
    lines += ["", _lineage_line(lineage)]
    return lines


def _records_section(records):
    counts = {}
    for r in records:
        counts[r.get("code")] = counts.get(r.get("code"), 0) + 1
    lines = ["", "| Code | Count |", "|---|---|"]
    for code in sorted(counts):
        lines.append(f"| {code} | {counts[code]} |")
    lines.append("")
    lines.append(
        f"{len(records)} record(s) total — see the report artifact for "
        "the full list."
    )
    return lines


def render_partial(payload):
    lineage = payload.get("lineage", {})
    records = payload.get("records", [])
    incomplete = payload.get("incomplete", [])
    lines = [
        f"## Doc audit: PARTIAL — {len(records)} finding(s), "
        f"{len(incomplete)} scope(s) not examined",
        "",
        "The declared scope was **not** fully examined — a missing finding "
        "proves nothing for the scopes below.",
        "",
        "**Not examined:**",
    ]
    for entry in incomplete:
        lines.append(f"- `{entry.get('scope')}`: {entry.get('reason')}")
    if records:
        lines += _records_section(records)
    lines += ["", _lineage_line(lineage)]
    return lines


def render_clean(payload):
    lineage = payload.get("lineage", {})
    return [
        "## Doc audit: CLEAN", "",
        "The declared scope was examined; no findings.", "",
        _lineage_line(lineage),
    ]


def render_findings(payload):
    lineage = payload.get("lineage", {})
    records = payload.get("records", [])
    lines = [f"## Doc audit: FINDINGS — {len(records)} record(s)"]
    lines += _records_section(records)
    lines += ["", _lineage_line(lineage)]
    return lines


RENDERERS = {
    "invalid": render_invalid,
    "stale": render_stale,
    "partial": render_partial,
    "clean": render_clean,
    "findings": render_findings,
}


def render(report_path, cost):
    """The full Markdown body for one audit run, as a list of lines."""
    try:
        with open(report_path, encoding="utf-8") as f:
            payload = json.load(f)
    except (OSError, ValueError, UnicodeDecodeError):
        lines = render_missing_report(report_path)
    else:
        renderer = RENDERERS.get(payload.get("status"))
        if renderer is None:
            lines = render_missing_report(report_path)
        else:
            lines = renderer(payload)
    lines = list(lines) + _cost_lines(cost)
    return "\n".join(lines) + "\n"


def _write_summary(text):
    path = os.environ.get("GITHUB_STEP_SUMMARY")
    if path:
        with open(path, "a", encoding="utf-8") as f:
            f.write(text)
    else:
        sys.stdout.write(text)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="mode", required=True)

    cost = sub.add_parser("cost")
    cost.add_argument("--execution-log", required=True)
    cost.add_argument("--out", required=True)

    summary = sub.add_parser("summary")
    summary.add_argument("--report", required=True)
    summary.add_argument("--cost", default=None)

    args = parser.parse_args()

    if args.mode == "cost":
        with open(args.out, "w", encoding="utf-8") as f:
            json.dump(extract_cost(args.execution_log), f)
        return 0

    cost_data = None
    if args.cost:
        try:
            with open(args.cost, encoding="utf-8") as f:
                cost_data = json.load(f)
        except (OSError, ValueError, UnicodeDecodeError):
            cost_data = {"available": False, "turns": None, "cost_usd": None,
                         "duration_ms": None}

    text = render(args.report, cost_data)
    _write_summary(text)
    return 0


if __name__ == "__main__":
    sys.exit(main())
