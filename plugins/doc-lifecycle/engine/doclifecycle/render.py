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

# A scope that declared nothing. "Clean" is vacuously true of it, and the
# declared count three lines down is too far away to stop it reading as a
# global all-clear at a glance — so the headline itself says nothing was
# examined, rather than that nothing was found.
EMPTY_SCOPE_HEADLINE = (
    "0 documents were declared, so nothing was examined and nothing could "
    "have been found"
)

# How much of one record field to show inline. Long enough for a path, a digest,
# or a sentence; short enough that one field cannot bury the rest of the report.
FIELD_LIMIT = 240

BACKTICKS = re.compile(r"`+")

# Characters that end a line — or that a renderer may treat as ending one.
# A code span cannot contain a blank line, so a single unescaped newline is
# enough to terminate the span and turn whatever follows into block structure.
LINE_ENDING = re.compile(r"[\x00-\x1f\x7f-\x9f  ]")
NAMED_ESCAPES = {"\n": "\\n", "\r": "\\r", "\t": "\\t"}


def _escape(match):
    character = match.group()
    return NAMED_ESCAPES.get(character, f"\\u{ord(character):04x}")


def _code(text):
    """A Markdown code span holding `text`, that cannot be escaped from.

    Total by construction, because being total is the whole point: a caller
    that forgets to sanitize its argument must not be able to reopen the
    injection this closes.

    Two ways out of a code span, both shut here. A run of backticks as long as
    the fence closes it, so the fence is fitted one longer than the longest run
    inside. A line break ends it outright — CommonMark spans cannot span a
    blank line — so control characters are rendered with their escapes instead
    of reaching the document, `U+2028`/`U+2029` included.
    """
    if not text:
        # `` is two literal backticks, not an empty span. Say "the empty
        # string" the way the field values below say it.
        text = '""'
    safe = LINE_ENDING.sub(_escape, text)
    fence = "`" * (max((len(m) for m in BACKTICKS.findall(safe)), default=0) + 1)
    pad = " " if safe[:1] in ("`", " ") or safe[-1:] in ("`", " ") else ""
    return f"{fence}{pad}{safe}{pad}{fence}"


def _field_text(value):
    """One record key or value as a single safe, bounded, complete line.

    Canonical JSON, the same form the digest is taken over — so what a reader
    sees is what was hashed, strings show their quoting, and a control
    character is escaped by the encoder rather than reaching the document.
    Keys go through this too: a key is record content exactly as much as a
    value is, and the contract does not police either.
    """
    text = canonical(value)
    if len(text) <= FIELD_LIMIT:
        return _code(text)
    return (
        f"{_code(text[:FIELD_LIMIT])} … "
        f"[{len(text) - FIELD_LIMIT} more characters; whole value sha256 "
        f"{sha256_canonical(value)}]"
    )


def _detail(mapping):
    """Every field of a record or a coverage entry, beyond its own key.

    All of them: an approver binds to a digest that covers the whole thing, so
    a field this module could not render inline is marked, never dropped.
    """
    return " · ".join(
        f"{_field_text(key)}: {_field_text(value)}"
        for key, value in sorted(mapping.items())
    )


def _headline(report):
    """The one-line verdict, with what it is a verdict *about*.

    The count leads, because the state alone does not say how much it covers:
    "clean" over nothing and "clean" over the whole inventory are the same word
    for very different runs, and the reader who stops at the first line is the
    one the distinction is for.
    """
    if report.scope is None:
        return HEADLINES[report.status]
    count = len(report.scope.documents)
    if count == 0 and report.status == STATE_CLEAN:
        return EMPTY_SCOPE_HEADLINE
    return f"{count} document(s) declared — {HEADLINES[report.status]}"


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
        f"**Result: {report.status}** — {_headline(report)}.",
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

    if report.scope is not None:
        # What the run set out to examine, so "the declared scope" in the
        # headline above is a claim the reader can check rather than take.
        # Exclusions are shown next to inclusions: a document left out with a
        # reason is the visible half of a coverage claim.
        lines += [
            "",
            "## Scope",
            "",
            f"- Basis: {_code(report.scope.basis)}",
            f"- Coverage: {_code(report.scope.coverage)}",
            f"- Declared documents ({len(report.scope.documents)}): "
            + (", ".join(_code(d) for d in report.scope.documents) or "none"),
            f"- Excluded documents ({len(report.scope.excluded)}): "
            + (", ".join(
                f"{_code(e.path)} ({_code(e.code)}: {_code(e.reason)})"
                for e in report.scope.excluded
            ) or "none"),
        ]

    if report.stale_reasons:
        lines += ["", "## Lineage drift", ""]
        lines += [
            f"- {_code(reason.code)} — reported {_code(reason.reported)}, "
            f"current {_code(reason.current)}"
            for reason in report.stale_reasons
        ]

    if report.examined:
        # The positive half of coverage, shown next to the negative half below:
        # a clean run's proof of work is the only thing standing between "we
        # checked and it holds" and "nobody looked".
        lines += ["", "## Examined", ""]
        for entry in report.examined:
            detail = _detail(entry.detail)
            suffix = f" — {detail}" if detail else ""
            lines.append(f"- {_code(entry.scope)}{suffix}")

    if report.incomplete:
        lines += ["", "## Not examined", ""]
        lines += [
            f"- {_code(entry.scope)} — {_code(entry.reason)}"
            for entry in report.incomplete
        ]

    lines += ["", "## Records", ""]
    if report.records:
        for record in report.records:
            detail = _detail(record.extra)
            suffix = f" — {detail}" if detail else ""
            lines.append(f"- {_code(record.id)} {_code(record.digest)}{suffix}")
    else:
        lines.append("- none")

    return "\n".join(lines)
