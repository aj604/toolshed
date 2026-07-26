"""Human-readable rendering of a validated report.

Takes a `Report` and nothing else. A dict, a JSON string, or an `Invalid` is a
`TypeError`, not a best effort: rendering is where a report reaches a PR body
or a CI summary, and unvalidated content must not be able to get that far
wearing the appearance of a verdict.

Type-checking the input is not enough on its own, because the contract
deliberately does not police record internals — those belong to the segmenter
(#63), and a record's fields carry text a model read out of repository
documents, which is attacker-influenceable. So *every* value this module
interpolates goes through `_code()`, which emits a Markdown code span nothing
can escape from. A record cannot add a heading, a link, a second `## Records`
section, or a `**Result:**` line to the rendered view that the report's digest
does not cover.

Nothing is silently withheld either: a human approving what this renders is
approving what the digest binds, so every record field is shown, and a value
too long to show in full is truncated with an explicit marker naming how much
was elided and the digest of the whole value.

Deterministic — the same report renders byte-identically every time, so a
rendered summary can itself be compared or digested.
"""

import re

from .digest import canonical, sha256_canonical
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

# How much of one record field to show inline. Long enough for a path, a digest,
# or a sentence; short enough that one field cannot bury the rest of the report.
FIELD_LIMIT = 240

BACKTICKS = re.compile(r"`+")


def _code(text):
    """A Markdown code span holding `text` exactly, that cannot be escaped from.

    CommonMark lets a code span be opened by any run of backticks and closed by
    a matching run, so a fence one longer than the longest run inside the text
    always wins. A leading or trailing backtick or space is separated by one
    space, which the renderer strips back off.
    """
    fence = "`" * (max((len(m) for m in BACKTICKS.findall(text)), default=0) + 1)
    pad = " " if text[:1] in ("`", " ") or text[-1:] in ("`", " ") else ""
    return f"{fence}{pad}{text}{pad}{fence}"


def _field_text(value):
    """One record field as a single safe line.

    Canonical JSON, the same form the digest is taken over — so what a reader
    sees is what was hashed, strings show their quoting, and a newline or a
    control character is already escaped to `\\n` by the encoder rather than
    reaching the document as a line break.
    """
    text = canonical(value)
    if len(text) <= FIELD_LIMIT:
        return _code(text)
    return (
        f"{_code(text[:FIELD_LIMIT])} … "
        f"[{len(text) - FIELD_LIMIT} more characters; whole value sha256 "
        f"{sha256_canonical(value)}]"
    )


def _record_detail(record):
    """Every field the record carries beyond the contract's own two.

    All of them: an approver binds to a digest that covers the whole record, so
    a field this module could not render inline is marked, never dropped.
    """
    return " · ".join(
        f"{_code(key)}: {_field_text(value)}"
        for key, value in sorted(record.extra.items())
    )


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
    evidence = ", ".join(_code(g) for g in boundary.sources)
    if boundary.excluded:
        excluded = ", ".join(_code(g) for g in boundary.excluded)
        evidence += f" (excluded: {excluded})"

    lines = [
        f"# Documentation audit — {report.status}",
        "",
        f"**Result: {report.status}** — {HEADLINES[report.status]}.",
        "",
        "## Lineage",
        "",
        f"- Repository: {_code(lineage.repository)}",
        f"- Base commit: {_code(lineage.base_commit)}",
        f"- Audit mode: {_code(lineage.audit_mode)}",
        f"- Inventory digest: {_code(lineage.inventory_digest)}",
        f"- Registry digest: {_code(lineage.registry_digest)}",
        f"- Audit configuration digest: {_code(lineage.audit_config_digest)}",
        f"- Ruleset version: {_code(str(lineage.ruleset_version))}",
        f"- Plugin version: {_code(lineage.plugin_version)}",
        f"- Evidence boundary: {evidence}",
        f"- Report digest: {_code(report.digest)}",
    ]

    if report.stale_reasons:
        lines += ["", "## Lineage drift", ""]
        lines += [
            f"- {_code(reason.code)} — reported {_code(reason.reported)}, "
            f"current {_code(reason.current)}"
            for reason in report.stale_reasons
        ]

    if report.incomplete:
        lines += ["", "## Not examined", ""]
        lines += [
            f"- {_code(entry.scope)} — {_code(entry.reason)}"
            for entry in report.incomplete
        ]

    lines += ["", "## Records", ""]
    if report.records:
        for record in report.records:
            detail = _record_detail(record)
            suffix = f" — {detail}" if detail else ""
            lines.append(f"- {_code(record.id)} {_code(record.digest)}{suffix}")
    else:
        lines.append("- none")

    return "\n".join(lines)
