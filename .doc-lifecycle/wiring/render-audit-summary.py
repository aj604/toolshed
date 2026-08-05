#!/usr/bin/env python3
"""Run-surface rendering for the read-only audit lane (doc-audit.yml, #71).

The workflow gathers facts and runs the engine's own CLI (`drift-plan`,
`drift-audit`); this script owns every user-facing string for that lane —
the self-explaining outcome, pinned lineage, and cost/budget observability —
so it is unit-testable instead of living as jq/heredoc templates in YAML.

Every one of the report contract's five result states renders here, plus the
two states the contract itself cannot describe, because neither produces a
report to carry them:

  * the audit job produced no report file at all (a crashed job, a stray
    chunk-worker entry per the engine README's warning) — rendered as its own
    typed problem (`audit-report-missing`), never silence and never an
    empty-looking report;
  * the lane's repository-integrity gate refused (check-repo-integrity.py,
    #185) — rendered from that gate's own verdict file, naming every
    `evidence-integrity-*` problem it found, so a refusal states itself here
    instead of surfacing only as a red step in a collapsed job log.

Usage:
    render-audit-summary.py cost --execution-log FILE [--execution-log FILE ...] --out FILE
    render-audit-summary.py summary --report FILE [--cost FILE]
                                    [--audit-surface drift|bloat]
                                    [--integrity FILE]

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


def aggregate_cost(execution_log_paths):
    """Sum every available action invocation without inventing missing fields."""
    runs = [extract_cost(path) for path in execution_log_paths]
    available = [run for run in runs if run["available"]]
    if not available:
        return {"available": False, "turns": None, "cost_usd": None,
                "duration_ms": None}

    def total(field):
        values = [run.get(field) for run in available]
        if any(not isinstance(value, (int, float)) or isinstance(value, bool)
               for value in values):
            return None
        return sum(values)

    return {
        "available": True,
        "turns": total("turns"),
        "cost_usd": total("cost_usd"),
        "duration_ms": total("duration_ms"),
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


def render_integrity_refusal(payload, integrity_path):
    """The gate's own verdict, rendered as this run's terminal state.

    No lineage line: the refusal is precisely the finding that the checkout
    the lineage would describe is not the one the run read.
    """
    problems = payload.get("problems") if isinstance(payload, dict) else None
    if not problems:
        # The flag was passed, so a gate ran, but its verdict cannot be read.
        # Fail closed: an unreadable gate verdict is not a passed gate.
        problems = [{
            "code": "evidence-integrity-unverifiable",
            "message": "the repository-integrity gate's verdict could not be "
                       "read, so this run cannot show that its evidence came "
                       "from the declared base commit",
            "location": integrity_path,
        }]
    lines = [
        "## Doc audit: REFUSED — repository integrity",
        "",
        "The checkout this run would have assembled its report from had "
        "changed, so no report was published. Evidence read from a mutated "
        "work tree is not evidence from the declared base commit, and the "
        "gate never repairs the tree to continue.",
        "",
        "**Problems:**",
    ]
    for problem in problems:
        where = f" ({problem.get('location')})" if problem.get("location") else ""
        lines.append(f"- `{problem.get('code')}`: {problem.get('message')}{where}")
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


def _integrity_refusal(integrity_path):
    """The gate's verdict when it refused, else None. Unreadable counts."""
    if not integrity_path:
        return None
    try:
        with open(integrity_path, encoding="utf-8") as f:
            payload = json.load(f)
    except (OSError, ValueError, UnicodeDecodeError):
        return {}
    if isinstance(payload, dict) and payload.get("status") == "verified":
        return None
    return payload


def render(report_path, cost, audit_surface="drift", integrity_path=None):
    """The full Markdown body for one audit run, as a list of lines."""
    refusal = _integrity_refusal(integrity_path)
    if refusal is not None:
        # The gate wins over any report on disk: a report assembled from a
        # checkout that failed the gate is exactly what must not be published
        # as this run's result.
        lines = render_integrity_refusal(refusal, integrity_path)
        if audit_surface == "bloat":
            lines[0] = lines[0].replace("## Doc audit:", "## Bloat audit:", 1)
        return "\n".join(lines + _cost_lines(cost)) + "\n"
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
    if audit_surface == "bloat" and lines and lines[0].startswith("## Doc audit:"):
        lines[0] = lines[0].replace("## Doc audit:", "## Bloat audit:", 1)
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
    cost.add_argument("--execution-log", required=True, action="append")
    cost.add_argument("--out", required=True)

    summary = sub.add_parser("summary")
    summary.add_argument("--report", required=True)
    summary.add_argument("--cost", default=None)
    summary.add_argument(
        "--audit-surface", choices=("drift", "bloat"), default="drift",
    )
    summary.add_argument(
        "--integrity", default=None,
        help="check-repo-integrity.py's verdict file for this run",
    )

    args = parser.parse_args()

    if args.mode == "cost":
        with open(args.out, "w", encoding="utf-8") as f:
            json.dump(aggregate_cost(args.execution_log), f)
        return 0

    cost_data = None
    if args.cost:
        try:
            with open(args.cost, encoding="utf-8") as f:
                cost_data = json.load(f)
        except (OSError, ValueError, UnicodeDecodeError):
            cost_data = {"available": False, "turns": None, "cost_usd": None,
                         "duration_ms": None}

    text = render(args.report, cost_data, audit_surface=args.audit_surface,
                  integrity_path=args.integrity)
    _write_summary(text)
    return 0


if __name__ == "__main__":
    sys.exit(main())
