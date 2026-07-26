"""Human-readable rendering of a validated report.

Takes a `Report` and nothing else. A dict, a JSON string, or an `Invalid` is a
`TypeError`, not a best effort: rendering is where a report reaches a PR body
or a CI summary, and unvalidated content must not be able to get that far
wearing the appearance of a verdict.

Deterministic — the same report renders byte-identically every time, so a
rendered summary can itself be compared or digested.
"""

from .report import Report
from .results import (
    STATE_CLEAN,
    STATE_FINDINGS,
    STATE_PARTIAL,
    STATE_STALE,
)

HEADLINES = {
    STATE_CLEAN: "the declared scope was examined and nothing was found",
    STATE_FINDINGS: "the declared scope was examined; findings follow",
    STATE_PARTIAL: (
        "the declared scope was NOT fully examined — the absence of a finding "
        "proves nothing about what was skipped"
    ),
    STATE_STALE: (
        "the report's lineage no longer matches the repository — re-run the "
        "audit; do not act on these records"
    ),
}


def _globs(values):
    return ", ".join(f"`{value}`" for value in values)


def _record_detail(record):
    """The record's own fields, rendered without this module knowing them."""
    parts = [
        f"{key}: {value}"
        for key, value in sorted(record.extra.items())
        if isinstance(value, (str, int, float, bool))
    ]
    return " · ".join(parts)


def render_report(report):
    """Render a validated `Report` as Markdown."""
    if not isinstance(report, Report):
        raise TypeError(
            f"render_report takes a validated Report, not "
            f"{type(report).__name__} — validate it first; malformed content "
            f"must not reach rendered output"
        )

    lineage = report.lineage
    boundary = lineage.evidence_boundary
    evidence = _globs(boundary.sources)
    if boundary.excluded:
        evidence += f" (excluded: {_globs(boundary.excluded)})"

    lines = [
        f"# Documentation audit — {report.status}",
        "",
        f"**Result: {report.status}** — {HEADLINES[report.status]}.",
        "",
        "## Lineage",
        "",
        f"- Repository: `{lineage.repository}`",
        f"- Base commit: `{lineage.base_commit}`",
        f"- Audit mode: `{lineage.audit_mode}`",
        f"- Inventory digest: `{lineage.inventory_digest}`",
        f"- Registry digest: `{lineage.registry_digest}`",
        f"- Audit configuration digest: `{lineage.audit_config_digest}`",
        f"- Ruleset version: `{lineage.ruleset_version}`",
        f"- Plugin version: `{lineage.plugin_version}`",
        f"- Evidence boundary: {evidence}",
        f"- Report digest: `{report.digest}`",
    ]

    if report.stale_reasons:
        lines += ["", "## Lineage drift", ""]
        lines += [
            f"- `{reason.code}` — reported `{reason.reported}`, current "
            f"`{reason.current}`"
            for reason in report.stale_reasons
        ]

    if report.incomplete:
        lines += ["", "## Not examined", ""]
        lines += [
            f"- `{entry.scope}` — {entry.reason}" for entry in report.incomplete
        ]

    lines += ["", "## Records", ""]
    if report.records:
        for record in report.records:
            detail = _record_detail(record)
            suffix = f" — {detail}" if detail else ""
            lines.append(f"- `{record.id}` `{record.digest}`{suffix}")
    else:
        lines.append("- none")

    return "\n".join(lines)
