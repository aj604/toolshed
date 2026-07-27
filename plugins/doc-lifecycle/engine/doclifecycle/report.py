"""The report contract: immutable proof of what was examined, pinned to lineage.

A report is not authority to change anything — it is a statement of what an
audit looked at, what it found, and under exactly which inputs. Everything that
could change a verdict travels with it as *lineage*: which repository, at which
commit, in which audit mode, over which inventory, configuration, registry,
ruleset, plugin version, artifact schema, and evidence boundary.

Validation is total and fails closed. A report missing a lineage field, or
carrying a schema version this engine does not read, is `invalid` with typed
problems and no content — never a guess at what the author meant. A report that
is structurally sound but describes a repository state that no longer exists is
`stale`: a distinct verdict, because the remedy is to re-run the audit, not to
fix the report.

`validate_report` (a dict) and `load_report` (a file) are the library seam;
`python3 -m doclifecycle validate-report` is the same functions behind argv, so
an interactive check and a CI check cannot reach different verdicts.
"""

import json
import math
import re
from dataclasses import dataclass
from typing import Optional, Tuple

from . import ARTIFACT_SCHEMA_VERSION, PLUGIN_VERSION, RULESET_VERSION
from . import repository as repository_mod
from .digest import canonical, sha256_canonical
from .inventory import DEFAULT_REGISTRY_PATH, build_inventory
from .results import (
    DECLARABLE_STATES,
    STATE_CLEAN,
    STATE_FINDINGS,
    STATE_PARTIAL,
    STATE_STALE,
    Invalid,
    Problem,
)

FIELDS = (
    "status", "schema_version", "lineage", "records", "examined", "incomplete",
    "scope", "stale_reasons", "digest",
)
REQUIRED_FIELDS = ("status", "schema_version", "lineage")

# The states a report payload may carry. A producing run declares one of
# `DECLARABLE_STATES`; `stale` additionally reads back in, because a validator
# emits it and a pipeline that persists a verdict must be able to re-check the
# file it wrote. `invalid` never appears in a report: an invalid run has no
# report to carry it.
CARRIED_STATES = DECLARABLE_STATES + (STATE_STALE,)

# The audit modes a report may declare. Closed: an unrecognized mode means the
# reader cannot know what "the declared scope" was, so nothing else it says is
# interpretable.
AUDIT_MODES = ("full", "incremental", "chunk")

REQUIRED_LINEAGE_FIELDS = (
    "repository",           # which repository the report is about
    "base_commit",          # the commit its evidence was read at
    "audit_mode",           # how much of the documentation it set out to examine
    "inventory_digest",     # the document inventory it examined
    "audit_config_digest",  # the consumer configuration it ran under
    "registry_digest",      # the classification that decided the inventory
    "ruleset_version",      # the audit policy it applied
    "plugin_version",       # the engine that applied it
    "evidence_boundary",    # what it was permitted to consult as evidence
)
# `schema_version` is lineage too — it pins the shape of everything above — but
# it lives at the report's top level, where every other engine artifact carries
# it, rather than being spelled twice in two places that could disagree.

EVIDENCE_FIELDS = ("sources", "excluded")

DIGEST = re.compile(r"^[0-9a-f]{64}$")
COMMIT = re.compile(r"^[0-9a-f]{40}([0-9a-f]{24})?$")  # sha-1 or sha-256 git

# How deeply a record may nest. Findings group assertion units and carry
# preimages; nothing legitimate approaches this. It is a stated limit rather
# than whatever the interpreter's recursion limit happens to be, so the verdict
# on a given report is the same everywhere the engine runs.
MAX_NESTING = 64

# Lineage fields the engine can compare against the world, in report order.
COMPARABLE = (
    ("repository", "lineage-repository-mismatch", "repository identity"),
    ("base_commit", "lineage-base-commit-mismatch", "base commit"),
    ("registry_digest", "lineage-registry-mismatch", "registry digest"),
    ("inventory_digest", "lineage-inventory-mismatch", "inventory digest"),
    ("audit_config_digest", "lineage-audit-config-mismatch",
     "audit configuration digest"),
    ("ruleset_version", "lineage-ruleset-mismatch", "ruleset version"),
    ("plugin_version", "lineage-plugin-mismatch", "plugin version"),
)
# Which lineage field produced a given stale reason, so a run can tell whether
# it actually re-checked a carried verdict or merely failed to look.
STALE_REASON_FIELDS = {code: field for field, code, _ in COMPARABLE}

# Stale reasons the declared scope produces rather than a lineage field. A run
# given both a repository and a scope re-checks these; one given no scope did
# not look, and a carried reason therefore stands.
SCOPE_DOCUMENT_UNKNOWN = "scope-document-unknown"
SCOPE_INVENTORY_UNACCOUNTED = "scope-inventory-unaccounted"
# PR #87 review, N1: a closed `coverage` token means nothing if what it leaves
# out is free prose — a living document moved into `excluded` with the reason
# "not relevant to this run" validated as `whole-inventory` with no stale
# reason. `scope-exclusion-kind-mismatch` is the re-derivation that closes it:
# an exclusion coded `planning-kind` must actually name a planning document,
# and a `whole-inventory` claim under a `full` audit mode cannot exclude a
# living or narrative document at all — every document such a claim covers is
# examined or the claim is false.
SCOPE_EXCLUSION_KIND_MISMATCH = "scope-exclusion-kind-mismatch"
SCOPE_REASON_CODES = (
    SCOPE_DOCUMENT_UNKNOWN, SCOPE_INVENTORY_UNACCOUNTED,
    SCOPE_EXCLUSION_KIND_MISMATCH,
)

# How much of the inventory a declared scope accounts for. Closed, because it
# is the half of a coverage claim a validator can act on: `basis` is prose for
# a reader, and prose saying "every living and narrative document" is exactly
# the sentence a scope listing one of six documents can also carry.
SCOPE_WHOLE_INVENTORY = "whole-inventory"
SCOPE_DECLARED_ONLY = "declared-only"
SCOPE_COVERAGES = (SCOPE_WHOLE_INVENTORY, SCOPE_DECLARED_ONLY)

# Why a document was left out of the declared scope, a second closed
# vocabulary beside `coverage`. `reason` stays prose for a reader; `code` is
# what a validator can act on, for the same reason `coverage` is a token
# rather than a sentence (PR #87 review, N1). `planning-kind` is a document
# excluded because a planning document is never examined for drift;
# `unaffected-by-range` is a living or narrative document an incremental
# run's commit range did not touch.
EXCLUSION_PLANNING_KIND = "planning-kind"
EXCLUSION_UNAFFECTED_BY_RANGE = "unaffected-by-range"
EXCLUSION_CODES = (EXCLUSION_PLANNING_KIND, EXCLUSION_UNAFFECTED_BY_RANGE)


@dataclass(frozen=True)
class EvidenceBoundary:
    """The declared limit of what the run was permitted to consult as evidence.

    Enumerable on purpose: a reader can tell what a verdict could and could not
    have been based on, and a later run can tell whether the boundary moved.
    """

    sources: Tuple[str, ...]
    excluded: Tuple[str, ...] = ()

    def to_dict(self):
        return {"sources": list(self.sources), "excluded": list(self.excluded)}


@dataclass(frozen=True)
class Lineage:
    repository: str
    base_commit: str
    audit_mode: str
    inventory_digest: str
    audit_config_digest: str
    registry_digest: str
    ruleset_version: int
    plugin_version: str
    evidence_boundary: EvidenceBoundary

    def to_dict(self):
        return {
            "repository": self.repository,
            "base_commit": self.base_commit,
            "audit_mode": self.audit_mode,
            "inventory_digest": self.inventory_digest,
            "audit_config_digest": self.audit_config_digest,
            "registry_digest": self.registry_digest,
            "ruleset_version": self.ruleset_version,
            "plugin_version": self.plugin_version,
            "evidence_boundary": self.evidence_boundary.to_dict(),
        }


@dataclass(frozen=True)
class Record:
    """One thing the audit found.

    The contract owns only what binds a record to approval — a display `id` and
    the `digest` an approval set selects it by. Everything else the audit
    engine or `finding.py` puts on a record travels in `extra`,
    untouched, so this module never becomes a second owner of record internals.
    """

    id: str
    digest: str
    extra: dict

    def to_dict(self):
        return {"id": self.id, "digest": self.digest, **self.extra}


@dataclass(frozen=True)
class ScopeExclusion:
    """One document the run declared out of scope, and why.

    Enumerated rather than dropped, because it is what makes a coverage claim
    checkable: a scope that accounts for every document in the inventory —
    each one either declared or excluded with a reason — is a claim a validator
    can re-derive against the repository. A scope that only lists what it took
    in leaves "and nothing else was relevant" as an assertion nobody can test.

    The claim is split in two, the same way `Scope.basis`/`coverage` is.
    `reason` is prose for a reader; `code` is the token a validator acts on —
    unconstrained prose let a living document be laundered into `excluded`
    with a reason like "not relevant to this run" and no way to catch it
    (PR #87 review, N1). Given a repository, `validate_report` checks `code`
    against the document's current kind, not just its shape.

    BREAKING, not a re-key: `code` is required, so a previously-valid report
    whose `scope.excluded` entries carry only `path`/`reason` (the shape
    before this field existed) is now `report-invalid-scope` outright, not
    merely re-keyed to a new digest. Every producer in this repository
    (`drift.audit_drift`) is updated alongside this to always emit `code`, so
    nothing this repository produces breaks — but a persisted report from
    before this change, or a consumer outside this repository holding the old
    shape, will fail validation and must be re-run.
    """

    path: str
    reason: str
    code: str

    def to_dict(self):
        return {"path": self.path, "reason": self.reason, "code": self.code}


@dataclass(frozen=True)
class Scope:
    """What the run set out to examine, enumerated.

    The result state says whether the *declared* scope completed; only this
    says what was declared. Without it a reader has to infer coverage from the
    audit mode, and "full" is exactly the claim most worth checking.

    So the claim is split in two. `basis` is prose for a reader: how the scope
    was derived. `coverage` is the token a validator acts on — `whole-inventory`
    means `documents` and `excluded` together account for every document the
    registry classifies, and `declared-only` means the scope names part of the
    inventory and says nothing about the rest. Given a repository,
    `validate_report` re-derives both against the current inventory; a scope
    that no longer describes it is `stale`.
    """

    basis: str
    coverage: str
    documents: Tuple[str, ...]
    excluded: Tuple[ScopeExclusion, ...] = ()

    def to_dict(self):
        return {
            "basis": self.basis,
            "coverage": self.coverage,
            "documents": list(self.documents),
            "excluded": [e.to_dict() for e in self.excluded],
        }


SCOPE_FIELDS = ("basis", "coverage", "documents", "excluded")


@dataclass(frozen=True)
class Incomplete:
    """One part of the declared scope the run did not examine."""

    scope: str
    reason: str

    def to_dict(self):
        return {"scope": self.scope, "reason": self.reason}


@dataclass(frozen=True)
class Examined:
    """One part of the declared scope the run did examine, and what it saw.

    The mirror of `Incomplete`, and the reason both exist: without it, positive
    coverage rests entirely on an absence. A document with no finding and no
    gap is indistinguishable from one whose clean answers were validated and
    then thrown away, and a report is supposed to be proof of examination.

    The contract owns only `scope`. What was seen travels in `detail`
    untouched, exactly as a record's fields do — the audit that looked owns
    what looking meant, and this module does not become a second owner of it.
    """

    scope: str
    detail: dict

    def to_dict(self):
        return {"scope": self.scope, **self.detail}


@dataclass(frozen=True)
class StaleReason:
    """One lineage field that no longer matches the repository.

    Carries both sides: a reader (or a cache deciding on reuse) must be able to
    see *what* moved without re-deriving it.
    """

    code: str
    message: str
    reported: str
    current: str

    def to_dict(self):
        return {
            "code": self.code,
            "message": self.message,
            "reported": self.reported,
            "current": self.current,
        }


@dataclass(frozen=True)
class Report:
    """A validated report. Rendering and application accept nothing else."""

    status: str
    lineage: Lineage
    records: Tuple[Record, ...]
    incomplete: Tuple[Incomplete, ...]
    digest: str
    stale_reasons: Tuple[StaleReason, ...] = ()
    scope: Optional[Scope] = None
    examined: Tuple[Examined, ...] = ()

    def to_dict(self):
        payload = {
            "status": self.status,
            "schema_version": ARTIFACT_SCHEMA_VERSION,
            "lineage": self.lineage.to_dict(),
            "records": [r.to_dict() for r in self.records],
            "incomplete": [i.to_dict() for i in self.incomplete],
            "digest": self.digest,
        }
        if self.examined:
            # Omitted when empty, like `scope`: an audit that records no
            # coverage says nothing about it, and reads exactly as it did
            # before the field existed.
            payload["examined"] = [e.to_dict() for e in self.examined]
        if self.scope is not None:
            payload["scope"] = self.scope.to_dict()
        if self.status == STATE_STALE:
            payload["stale_reasons"] = [r.to_dict() for r in self.stale_reasons]
        return payload


def _nonempty_str(value):
    return isinstance(value, str) and value.strip() != ""


def _printable(value):
    """A one-line string: lineage and scopes are echoed to logs and PR bodies."""
    return _nonempty_str(value) and not any(c in value for c in "\n\r\x00")


def _whole_number(value):
    """An integer, and not a bool — `True == 1` in Python, but not in a schema."""
    return isinstance(value, int) and not isinstance(value, bool)


def _scan(value):
    """(too_deep, nonfinite) for one decoded record, walked iteratively.

    Iterative, and bounded, on purpose. A report is untrusted input: a
    recursive walk of a deeply nested one dies with a `RecursionError`, a bare
    exception this result model does not permit — and the digest is taken with
    `json.dumps`, which recurses too, so an unbounded record could crash the
    engine after validation had passed it.

    `nonfinite` covers the other thing JSON will not survive: `json.loads`
    accepts `NaN` and `Infinity` by default and `json.dumps` emits them back,
    which would make the engine's own output unreadable to a strict parser.
    """
    too_deep = nonfinite = False
    pending = [(value, 1)]
    while pending:
        item, depth = pending.pop()
        if depth > MAX_NESTING:
            too_deep = True
            continue                      # refuse it rather than descend
        if isinstance(item, float) and not math.isfinite(item):
            nonfinite = True
        elif isinstance(item, dict):
            pending.extend((child, depth + 1) for child in item.values())
        elif isinstance(item, list):
            pending.extend((child, depth + 1) for child in item)
    return too_deep, nonfinite


def lineage_digest(lineage):
    """The digest of a lineage on its own, for artifacts that bind to a run.

    A report's own digest covers its records, so a record cannot use it —
    that is circular. This is the same lineage, digested alone, and it is what
    `finding.build_finding` mixes into every finding digest: a finding produced
    under a different repository state, registry, ruleset, or engine is a
    different finding, even when it groups the same units.
    """
    return sha256_canonical({
        "schema_version": ARTIFACT_SCHEMA_VERSION,
        "lineage": lineage.to_dict(),
    })


def _content_digest(lineage, records, incomplete, scope=None, examined=()):
    """The report's identity: what it says, not what a validator concluded.

    Excludes the result state and the stale reasons, so the same report keeps
    one digest whether it is read fresh or years later — approval binds to this
    digest, and a verdict changing underneath must not re-key it.

    The declared scope is *in*, because two runs finding the same records over
    different scopes are not the same report — one examined more than the
    other. Recorded coverage is *in* for the same reason: a run that verified
    twenty assertions and one that verified two are not the same report even
    when neither found anything.

    Both are omitted when a report carries neither, so one that says nothing
    about scope or coverage is digested exactly as it was before the fields
    existed — adding them re-keys nothing that did not use them.
    """
    payload = {
        "schema_version": ARTIFACT_SCHEMA_VERSION,
        "lineage": lineage.to_dict(),
        "records": [r.to_dict() for r in records],
        "incomplete": [i.to_dict() for i in incomplete],
    }
    if scope is not None:
        payload["scope"] = scope.to_dict()
    if examined:
        payload["examined"] = [e.to_dict() for e in examined]
    return sha256_canonical(payload)


def _evidence_boundary(raw, bad):
    if not isinstance(raw, dict):
        bad("report-invalid-evidence-boundary",
            "evidence_boundary must be an object declaring the sources the run "
            "was permitted to consult",
            "lineage.evidence_boundary")
        return None
    for name in raw:
        if name not in EVIDENCE_FIELDS:
            bad("report-invalid-evidence-boundary",
                f"unexpected field {name!r} — an evidence boundary declares "
                f"{list(EVIDENCE_FIELDS)}",
                "lineage.evidence_boundary")
    ok = True
    sources = raw.get("sources")
    if not isinstance(sources, list) or not sources:
        bad("report-invalid-evidence-boundary",
            "sources must be a non-empty list of repository-relative globs — a "
            "run that names no evidence boundary cannot say what its verdicts "
            "rest on",
            "lineage.evidence_boundary.sources")
        ok = False
    excluded = raw.get("excluded", [])
    if not isinstance(excluded, list):
        bad("report-invalid-evidence-boundary",
            "excluded must be a list of repository-relative globs",
            "lineage.evidence_boundary.excluded")
        ok = False
    for name, values in (("sources", sources), ("excluded", excluded)):
        if not isinstance(values, list):
            continue
        for i, value in enumerate(values):
            # Shape and log hygiene only. Path *authorization* — traversal,
            # symlinks, forbidden target classes — is issue #67's single owner;
            # a boundary is lineage here, never opened.
            if not _printable(value):
                bad("report-invalid-evidence-boundary",
                    f"{name}[{i}] must be a non-empty single-line "
                    f"repository-relative glob",
                    f"lineage.evidence_boundary.{name}[{i}]")
                ok = False
    if not ok:
        return None
    return EvidenceBoundary(tuple(sources), tuple(excluded))


def _lineage(raw, bad):
    """Parse and validate the lineage object. Returns a Lineage or None."""
    if not isinstance(raw, dict):
        bad("report-invalid-lineage",
            "lineage must be an object carrying every field that could change a "
            f"verdict: {list(REQUIRED_LINEAGE_FIELDS)}",
            "lineage")
        return None

    missing = [f for f in REQUIRED_LINEAGE_FIELDS if f not in raw]
    for field in missing:
        bad("report-missing-lineage-field",
            f"lineage is missing '{field}' — a report that cannot say {field} "
            f"cannot be checked against the repository, and guessing it would "
            f"make the report unfalsifiable",
            f"lineage.{field}")
    for field in raw:
        if field not in REQUIRED_LINEAGE_FIELDS:
            bad("report-unknown-lineage-field",
                f"unexpected lineage field {field!r} — lineage is "
                f"{list(REQUIRED_LINEAGE_FIELDS)}",
                f"lineage.{field}")

    def invalid(field, requirement):
        bad("report-invalid-lineage",
            f"lineage.{field} {requirement}", f"lineage.{field}")

    ok = not missing
    if "repository" in raw and not _printable(raw["repository"]):
        invalid("repository", "must be a non-empty single-line repository identity")
        ok = False
    if "base_commit" in raw and not (
        isinstance(raw["base_commit"], str) and COMMIT.match(raw["base_commit"])
    ):
        invalid("base_commit", "must be a full lowercase git commit id")
        ok = False
    if "audit_mode" in raw and raw["audit_mode"] not in AUDIT_MODES:
        bad("report-unknown-audit-mode",
            f"audit_mode {raw['audit_mode']!r} is not an audit mode — a reader "
            f"cannot tell what scope was declared unless it is one of "
            f"{list(AUDIT_MODES)}",
            "lineage.audit_mode")
        ok = False
    for field in ("inventory_digest", "audit_config_digest", "registry_digest"):
        if field in raw and not (
            isinstance(raw[field], str) and DIGEST.match(raw[field])
        ):
            invalid(field, "must be a sha256 digest (64 lowercase hex characters)")
            ok = False
    if "ruleset_version" in raw and not (
        _whole_number(raw["ruleset_version"]) and raw["ruleset_version"] >= 1
    ):
        invalid("ruleset_version", "must be a positive integer")
        ok = False
    if "plugin_version" in raw and not _printable(raw["plugin_version"]):
        invalid("plugin_version", "must be a non-empty version string")
        ok = False

    boundary = (
        _evidence_boundary(raw["evidence_boundary"], bad)
        if "evidence_boundary" in raw else None
    )
    if boundary is None:
        ok = False
    if not ok:
        return None
    return Lineage(
        repository=raw["repository"],
        base_commit=raw["base_commit"],
        audit_mode=raw["audit_mode"],
        inventory_digest=raw["inventory_digest"],
        audit_config_digest=raw["audit_config_digest"],
        registry_digest=raw["registry_digest"],
        ruleset_version=raw["ruleset_version"],
        plugin_version=raw["plugin_version"],
        evidence_boundary=boundary,
    )


def parse_lineage(raw):
    """Parse a lineage object on its own. Returns (`Lineage` or None, problems).

    Public because lineage has one owner. An approval set binds to the lineage
    of the report that produced it and must read it back identically — a second
    parser could only ever disagree with this one, and the disagreement would
    be an artifact that validates in one place and not the other.
    """
    problems = []
    lineage = _lineage(raw, lambda code, message, where=None: problems.append(
        Problem(code=code, message=message, location=where)
    ))
    return lineage, tuple(problems)


def _records(raw, bad):
    if not isinstance(raw, list):
        bad("report-invalid-shape", "records must be a list of record objects",
            "records")
        return None
    records, ok = [], True
    for i, entry in enumerate(raw):
        where = f"records[{i}]"
        if not isinstance(entry, dict):
            bad("report-invalid-record", f"record {i} is not an object", where)
            ok = False
            continue
        valid = True
        if not _printable(entry.get("id")):
            bad("report-invalid-record",
                f"record {i} must carry a non-empty single-line 'id'", where)
            valid = False
        digest = entry.get("digest")
        if not (isinstance(digest, str) and DIGEST.match(digest)):
            bad("report-invalid-record",
                f"record {i} must carry a sha256 'digest' — an approval set "
                f"selects records by digest, so a record without one cannot be "
                f"approved",
                where)
            valid = False
        too_deep, nonfinite = _scan(entry)
        if nonfinite:
            bad("report-nonfinite-number",
                f"record {i} carries NaN or Infinity — JSON defines neither, so "
                f"the report would not survive its own digest or a strict "
                f"parser",
                where)
            valid = False
        if too_deep:
            bad("report-nesting-too-deep",
                f"record {i} nests deeper than {MAX_NESTING} levels — a record "
                f"describes a finding, and this one cannot be digested or "
                f"rendered without exhausting the stack",
                where)
            valid = False
        if not valid:
            ok = False
            continue
        records.append(Record(
            id=entry["id"],
            digest=digest,
            extra={k: v for k, v in entry.items() if k not in ("id", "digest")},
        ))
    if not ok:
        return None
    for field in ("id", "digest"):
        seen, reported = set(), set()
        for record in records:
            value = getattr(record, field)
            if value in seen and value not in reported:
                reported.add(value)
                bad("report-duplicate-record",
                    f"two records share the {field} {value!r} — approval selects "
                    f"a record by digest, so a duplicate makes the selection "
                    f"ambiguous about what it authorized",
                    "records")
            seen.add(value)
        if reported:
            return None
    return records


def _incomplete(raw, bad):
    if not isinstance(raw, list):
        bad("report-invalid-shape",
            "incomplete must be a list naming what the run did not examine",
            "incomplete")
        return None
    entries, ok = [], True
    for i, entry in enumerate(raw):
        where = f"incomplete[{i}]"
        if not isinstance(entry, dict) or set(entry) != {"scope", "reason"}:
            bad("report-invalid-incomplete",
                f"incomplete[{i}] must be an object with exactly 'scope' and "
                f"'reason'",
                where)
            ok = False
            continue
        if not _printable(entry["scope"]) or not _printable(entry["reason"]):
            bad("report-invalid-incomplete",
                f"incomplete[{i}] must name a non-empty scope and the reason it "
                f"was not examined — a partial run that will not say what it "
                f"skipped is indistinguishable from a clean one",
                where)
            ok = False
            continue
        entries.append(Incomplete(scope=entry["scope"], reason=entry["reason"]))
    return entries if ok else None


def _scope(raw, bad):
    """Parse and validate the declared scope. Returns a Scope or None.

    Exhaustive like every other section: a scope with three things wrong says
    all three, so one round of fixes addresses them.
    """
    if not isinstance(raw, dict) or set(raw) != set(SCOPE_FIELDS):
        bad("report-invalid-scope",
            f"scope must be an object with exactly {list(SCOPE_FIELDS)} — the "
            f"basis says how the scope was derived, the coverage says how much "
            f"of the inventory it accounts for, and the documents and "
            f"exclusions enumerate it",
            "scope")
        return None
    ok = True
    if not _printable(raw["basis"]):
        bad("report-invalid-scope",
            "scope.basis must be a non-empty single-line statement of how the "
            "scope was derived — a scope nobody can re-derive is not checkable",
            "scope.basis")
        ok = False
    if raw["coverage"] not in SCOPE_COVERAGES:
        bad("report-invalid-scope",
            f"scope.coverage {raw['coverage']!r} is not a coverage claim — it "
            f"is one of {list(SCOPE_COVERAGES)}, because a validator has to be "
            f"able to act on how much of the inventory the scope accounts for, "
            f"and the prose in 'basis' is not something it can act on",
            "scope.coverage")
        ok = False
    documents = raw["documents"]
    if not isinstance(documents, list):
        bad("report-invalid-scope",
            "scope.documents must be a list of the repository-relative "
            "documents the run declared",
            "scope.documents")
        return None
    seen = set()
    for i, value in enumerate(documents):
        if not _printable(value):
            bad("report-invalid-scope",
                f"scope.documents[{i}] must be a non-empty single-line "
                f"repository-relative path",
                f"scope.documents[{i}]")
            ok = False
            continue
        if value in seen:
            bad("report-invalid-scope",
                f"scope.documents names {value!r} twice — a declared scope is a "
                f"set of documents, and a repeat makes the count of what was "
                f"examined disagree with the list of it",
                f"scope.documents[{i}]")
            ok = False
        seen.add(value)
    excluded = _scope_excluded(raw["excluded"], seen, bad)
    if excluded is None:
        ok = False
    elif raw["coverage"] == SCOPE_DECLARED_ONLY and excluded:
        # A shape contradiction adjacent to N1, not the fix for N2: the
        # reviewer's N2 probe (a `declared-only` scope over 1 of 6 documents,
        # `excluded` empty, `basis` still reading "full inventory...") stays
        # mechanically valid even after this — nothing here or elsewhere
        # parses `basis`, by design (see the README's "residual gap" note).
        # What *is* mechanical: `declared-only` means the scope "names part
        # of the inventory and claims nothing about the rest", so naming a
        # specific exclusion with a reason would be claiming something about
        # the rest — a contradiction the shape alone can catch, independent
        # of what `basis` says.
        bad("report-invalid-scope",
            f"scope.excluded names document(s) while coverage is "
            f"{SCOPE_DECLARED_ONLY!r} — {SCOPE_DECLARED_ONLY!r} claims "
            f"nothing about the rest of the inventory, so enumerating "
            f"specific exclusions would be claiming something about it; "
            f"only {SCOPE_WHOLE_INVENTORY!r} coverage accounts for what it "
            f"leaves out",
            "scope.excluded")
        ok = False
    if not ok:
        return None
    return Scope(
        basis=raw["basis"], coverage=raw["coverage"],
        documents=tuple(documents), excluded=tuple(excluded),
    )


EXCLUSION_FIELDS = {"path", "reason", "code"}


def _scope_excluded(raw, declared, bad):
    """The documents the scope deliberately left out. Returns a list or None.

    A path cannot be both declared and excluded: a scope that says it examined
    a document and also that it did not is not a scope anyone can act on.
    """
    if not isinstance(raw, list):
        bad("report-invalid-scope",
            "scope.excluded must be a list of the documents the run declared "
            "out of scope, each with the reason and the code it was left out "
            "under",
            "scope.excluded")
        return None
    entries, seen, ok = [], set(), True
    for i, entry in enumerate(raw):
        where = f"scope.excluded[{i}]"
        if not isinstance(entry, dict) or set(entry) != EXCLUSION_FIELDS:
            bad("report-invalid-scope",
                f"scope.excluded[{i}] must be an object with exactly 'path', "
                f"'reason', and 'code'",
                where)
            ok = False
            continue
        if not _printable(entry["path"]) or not _printable(entry["reason"]):
            bad("report-invalid-scope",
                f"scope.excluded[{i}] must name a document and why it was left "
                f"out — an exclusion with no reason is a document quietly "
                f"dropped, which is what enumerating them prevents",
                where)
            ok = False
            continue
        if entry["code"] not in EXCLUSION_CODES:
            bad("report-invalid-scope",
                f"scope.excluded[{i}].code {entry['code']!r} is not an "
                f"exclusion code — it is one of {list(EXCLUSION_CODES)}, "
                f"because a validator has to be able to act on why a "
                f"document was left out, and free prose like 'not relevant "
                f"to this run' is not something it can act on",
                where)
            ok = False
            continue
        path = entry["path"]
        if path in declared:
            bad("report-invalid-scope",
                f"scope.excluded names {path!r}, which scope.documents also "
                f"declares — a document is examined or it is not",
                where)
            ok = False
        elif path in seen:
            bad("report-invalid-scope",
                f"scope.excluded names {path!r} twice — an exclusion is a "
                f"document, and a repeat makes the accounting disagree with "
                f"itself",
                where)
            ok = False
        seen.add(path)
        entries.append(ScopeExclusion(
            path=path, reason=entry["reason"], code=entry["code"],
        ))
    return entries if ok else None


def _examined(raw, bad, declared):
    """Parse the coverage the run recorded. Returns a list of `Examined`.

    `declared` is the scope's document set, or None when no scope was declared.
    A report cannot claim to have examined something it never said it would
    look at — that is the same category error as a verdict for an undeclared
    document, and it is what would let recorded coverage inflate a scope.

    That containment check needs a scope to check against. PR #87 review, N3:
    with none declared it was simply skipped, so a scope-less report could
    record coverage of arbitrary paths nothing had enumerated. Requiring a
    scope whenever `examined` is non-empty is the structural fix — it needs no
    repository, unlike constraining `examined` to the current inventory would,
    and `audit_drift` always emits a scope alongside its coverage already, so
    nothing legitimate is newly refused.
    """
    if not isinstance(raw, list):
        bad("report-invalid-shape",
            "examined must be a list naming what the run did examine",
            "examined")
        return None
    if raw and declared is None:
        bad("report-invalid-examined",
            "examined records coverage of a document, but no scope was "
            "declared — recorded coverage cannot be checked against a scope "
            "that is not there, so it could name any path at all; declare a "
            "scope naming what was examined",
            "examined")
        return None
    entries, seen, ok = [], set(), True
    for i, entry in enumerate(raw):
        where = f"examined[{i}]"
        if not isinstance(entry, dict) or not _printable(entry.get("scope")):
            bad("report-invalid-examined",
                f"examined[{i}] must be an object naming the 'scope' it "
                f"covers, plus whatever the audit recorded about it",
                where)
            ok = False
            continue
        scope = entry["scope"]
        too_deep, nonfinite = _scan(entry)
        if nonfinite or too_deep:
            bad("report-invalid-examined",
                f"examined[{i}] carries a value the report cannot survive "
                f"(NaN/Infinity, or nesting deeper than {MAX_NESTING} levels)",
                where)
            ok = False
            continue
        if scope in seen:
            bad("report-invalid-examined",
                f"two examined entries cover {scope!r} — which one describes "
                f"the run is not knowable from here",
                where)
            ok = False
            continue
        if declared is not None and scope not in declared:
            bad("report-invalid-examined",
                f"examined[{i}] covers {scope!r}, which the declared scope does "
                f"not name — a run cannot record coverage of something it never "
                f"declared it would examine",
                where)
            ok = False
            continue
        seen.add(scope)
        entries.append(Examined(
            scope=scope,
            detail={k: v for k, v in entry.items() if k != "scope"},
        ))
    return entries if ok else None


def _scope_summary(paths, limit=5):
    """A bounded, one-line, injection-proof rendering of a path list.

    Canonical JSON, because these become stale-reason fields: they are read
    back by `_printable`, echoed to logs and PR bodies, and a repository path
    is content this module does not police.
    """
    text = canonical(list(paths[:limit]))
    if len(paths) > limit:
        text += f" (+{len(paths) - limit} more)"
    return text


def _exclusion_disagrees(exclusion, kind, coverage, audit_mode):
    """Does this exclusion's claimed code disagree with the document it names?

    PR #87 review, N1. Two independent ways an exclusion can lie, and either
    is enough: a `planning-kind` code naming a document that is not currently
    classified `planning`, or — regardless of what code was claimed — a
    living or narrative document excluded from a `full`-mode report that
    claims `whole-inventory` coverage. A full audit declares every living and
    narrative document (`plan_drift_audit`); nothing of that kind is ever
    legitimately excluded from one, so the second check holds even if a
    forged report picks `unaffected-by-range` instead of lying about the code.

    Deliberately mode-scoped: an incremental audit's `whole-inventory` claim
    legitimately excludes living/narrative documents the commit range did not
    touch, so the same rule applied there would refuse every diff-scoped run.
    """
    if exclusion.code == EXCLUSION_PLANNING_KIND and kind != "planning":
        return True
    if (
        audit_mode == "full" and coverage == SCOPE_WHOLE_INVENTORY
        and kind in ("living", "narrative")
    ):
        return True
    return False


def _scope_reasons(scope, kind_by_path, audit_mode):
    """Every way the declared scope no longer describes the repository.

    `stale`, not `invalid`, and the direction is deliberate. `invalid` is what
    a payload says about itself, decidable with no repository in hand; this
    check needs one, and from here a document that was deleted and a document
    that never existed are the same observation. Both mean the same thing to a
    reader — the scope claim does not describe this repository, so re-run the
    audit rather than acting on its coverage — and `stale` is what says that.
    A forged scope therefore cannot validate fresh, which is the property an
    approval set binding to a scope needs.

    `kind_by_path` is the current inventory, `{path: kind}` — its key set is
    what the document-existence checks compare against, and its values are
    what the exclusion-code checks compare against, so one map serves both
    rather than two derived from the same walk over `inventory.documents`.
    """
    inventory_paths = set(kind_by_path)
    reasons = []
    named = tuple(scope.documents) + tuple(e.path for e in scope.excluded)
    unknown = sorted(set(named) - inventory_paths)
    if unknown:
        reasons.append(StaleReason(
            code=SCOPE_DOCUMENT_UNKNOWN,
            message=(
                f"the declared scope names {len(unknown)} document(s) the "
                f"current inventory does not contain — a scope enumerating "
                f"documents that are not there describes some other repository "
                f"state, so re-run the audit rather than trusting its coverage"
            ),
            reported=_scope_summary(unknown),
            current=f"{len(inventory_paths)} document(s) in the inventory",
        ))
    if scope.coverage == SCOPE_WHOLE_INVENTORY:
        unaccounted = sorted(inventory_paths - set(named))
        if unaccounted:
            reasons.append(StaleReason(
                code=SCOPE_INVENTORY_UNACCOUNTED,
                message=(
                    f"the scope claims {SCOPE_WHOLE_INVENTORY!r} coverage but "
                    f"leaves {len(unaccounted)} document(s) neither declared "
                    f"nor excluded — a coverage claim is only true if every "
                    f"document is accounted for one way or the other"
                ),
                reported=f"{len(named)} document(s) accounted for",
                current=_scope_summary(unaccounted),
            ))
    mismatched = sorted(
        exclusion.path for exclusion in scope.excluded
        if exclusion.path in kind_by_path
        and _exclusion_disagrees(
            exclusion, kind_by_path[exclusion.path], scope.coverage, audit_mode
        )
    )
    if mismatched:
        reasons.append(StaleReason(
            code=SCOPE_EXCLUSION_KIND_MISMATCH,
            message=(
                f"the scope excludes {len(mismatched)} document(s) whose "
                f"current kind disagrees with why they were left out — a "
                f"{EXCLUSION_PLANNING_KIND!r} exclusion must name a document "
                f"the registry currently classifies planning, and a "
                f"'full'-mode {SCOPE_WHOLE_INVENTORY!r} claim cannot exclude "
                f"a living or narrative document under any code at all — "
                f"that is exactly the coverage a full audit exists to "
                f"examine"
            ),
            reported=_scope_summary(mismatched),
            current=f"{len(kind_by_path)} document(s) in the inventory",
        ))
    return tuple(reasons)


def _carried_stale_reasons(raw, bad, status):
    """The stale reasons a report payload carries from a prior verdict.

    A validator emits them, so they must read back in: a pipeline that persists
    `validate-report`'s output and re-checks the file it wrote must get the same
    verdict, not a parse failure. They are never part of the report digest, so
    carrying one does not change the report's identity.
    """
    if not isinstance(raw, list):
        bad("report-invalid-stale-reason",
            "stale_reasons must be a list of drift reasons", "stale_reasons")
        return None
    reasons, ok = [], True
    for i, entry in enumerate(raw):
        where = f"stale_reasons[{i}]"
        fields = {"code", "message", "reported", "current"}
        if not isinstance(entry, dict) or set(entry) != fields:
            bad("report-invalid-stale-reason",
                f"stale_reasons[{i}] must be an object with exactly "
                f"{sorted(fields)}",
                where)
            ok = False
            continue
        if not all(_printable(entry[f]) for f in fields):
            bad("report-invalid-stale-reason",
                f"stale_reasons[{i}] fields must each be a non-empty "
                f"single-line string",
                where)
            ok = False
            continue
        reasons.append(StaleReason(**entry))
    if not ok:
        return None
    if status == STATE_STALE and not reasons:
        bad("report-state-inconsistent",
            "a stale report must name every lineage field that drifted — "
            "'stale' without a reason is an unfalsifiable claim",
            "stale_reasons")
        return None
    if status != STATE_STALE and reasons:
        bad("report-state-inconsistent",
            f"only a stale report carries stale_reasons; this one declares "
            f"{status!r}",
            "stale_reasons")
        return None
    return reasons


def state_from_content(records, incomplete):
    """The only state the report's own content supports.

    Public because a producing run must declare the state its content supports
    and this validator re-derives it: two copies of the rule could only ever
    disagree, and the disagreement would surface as `report-state-inconsistent`
    on a report that was honest about what it did.

    Derived rather than trusted: a run cannot both leave part of its scope
    unexamined and call itself clean, and the state a reader acts on must
    follow from what the report actually contains. "Clean" is relative to the
    scope the audit mode declared — a `chunk` run that finished its chunk is
    clean about that chunk, and says so by naming the mode in lineage.
    """
    if incomplete:
        return STATE_PARTIAL
    if records:
        return STATE_FINDINGS
    return STATE_CLEAN


def current_lineage(repo_root, registry_path=DEFAULT_REGISTRY_PATH,
                    audit_config_digest=None):
    """The lineage a report about `repo_root` must carry to be fresh.

    Returns (state, problems). A producing run builds its lineage from this; a
    validator compares against it. The audit configuration digest is the
    consumer's, not the engine's, so it is only part of the state — and only
    compared — when the caller supplies one.

    Any problem means the repository state is unknown, and the state is empty:
    a freshness check that cannot read the world fails closed rather than
    certifying a report it did not check.
    """
    current, _, problems = _current_state(
        repo_root, registry_path, audit_config_digest
    )
    return current, problems


def _current_state(repo_root, registry_path, audit_config_digest):
    """(lineage state, inventory or None, problems).

    The whole answer, so the inventory is built once. `current_lineage` is the
    public half and drops the inventory; `validate_report` also needs it, to
    re-derive a declared scope against what the repository actually contains,
    and building it twice would double the cost of every checked report.
    """
    current, problems = repository_mod.lineage(repo_root)
    current = dict(current)

    inventory = build_inventory(repo_root, registry_path)
    if isinstance(inventory, Invalid):
        problems = problems + tuple(Problem(
            code="repository-state-unavailable",
            message=(
                f"the repository's current inventory cannot be computed, so a "
                f"report about it cannot be checked for freshness: {p.message}"
            ),
            location=p.location,
        ) for p in inventory.problems)
    else:
        current["inventory_digest"] = inventory.digest
        current["registry_digest"] = inventory.registry_digest

    if problems:
        return {}, None, tuple(problems)

    current["ruleset_version"] = RULESET_VERSION
    current["plugin_version"] = PLUGIN_VERSION
    if audit_config_digest is not None:
        current["audit_config_digest"] = audit_config_digest
    return current, inventory, ()


def _still_standing(carried, current, rechecked=()):
    """Carried stale reasons this run was not in a position to re-check.

    Clearing a verdict must be at least as thorough as setting it. A run that
    omits the audit-configuration digest never compares that field, so it
    cannot honestly clear a reason that field produced — otherwise a *weaker*
    check would launder a stale report clean. A reason naming a field this
    engine does not compare at all stands for the same reason.

    `rechecked` names the codes this run *did* re-derive by some route other
    than a lineage field — the scope reasons, which need a declared scope as
    well as a repository. A run that had both cleared them honestly; one that
    had only the repository did not look, so they stand.
    """
    return tuple(
        reason for reason in carried
        if reason.code not in rechecked
        and STALE_REASON_FIELDS.get(reason.code) not in current
    )


def _stale_reasons(lineage, current):
    """Every lineage field that no longer matches, not just the first."""
    reasons = []
    for field, code, label in COMPARABLE:
        if field not in current:
            continue
        reported, actual = getattr(lineage, field), current[field]
        if reported == actual:
            continue
        reasons.append(StaleReason(
            code=code,
            message=(
                f"the report's {label} ({reported}) is not the repository's "
                f"current {label} ({actual}) — re-run the audit rather than "
                f"acting on findings about a state that no longer exists"
            ),
            reported=str(reported),
            current=str(actual),
        ))
    return tuple(reasons)


def validate_report(payload, repo_root=None, registry_path=DEFAULT_REGISTRY_PATH,
                    audit_config_digest=None):
    """Validate a report payload. Returns a `Report` or `Invalid`.

    Structural validation is exhaustive: every problem the payload has is
    named, so one round of fixes can address all of them. It runs first and
    alone — an unreadable report has nothing to check against a repository, so
    `invalid` always beats `stale`.

    Pass `repo_root` to also check freshness. Without it the verdict is
    structural only and can never be `stale`: the validator does not guess at a
    repository state it was not shown.
    """
    problems = []

    def bad(code, message, where=None):
        problems.append(Problem(code=code, message=message, location=where))

    if not isinstance(payload, dict):
        return Invalid((Problem(
            code="report-invalid-shape",
            message=(
                f"a report must be a JSON object, not "
                f"{type(payload).__name__} — there is nothing to validate"
            ),
        ),))

    for name in REQUIRED_FIELDS:
        if name not in payload:
            bad("report-missing-field", f"the report is missing '{name}'", name)
    for name in payload:
        if name not in FIELDS:
            bad("report-unknown-field",
                f"unexpected field {name!r} — a report carries {list(FIELDS)}",
                name)

    version = payload.get("schema_version")
    # Type-guarded, not just compared: `True == 1` and `1.0 == 1` in Python, and
    # neither is the integer a schema version is.
    if "schema_version" in payload and not (
        _whole_number(version) and version == ARTIFACT_SCHEMA_VERSION
    ):
        bad("report-schema-version",
            f"report schema_version {version!r} is not supported; this engine "
            f"reads integer version {ARTIFACT_SCHEMA_VERSION}. Migrate the "
            f"report rather than guessing at the meaning of a shape it does "
            f"not know.",
            "schema_version")

    lineage = _lineage(payload["lineage"], bad) if "lineage" in payload else None
    records = _records(payload.get("records", []), bad)
    incomplete = _incomplete(payload.get("incomplete", []), bad)
    # Optional: a report that declares no scope says nothing about one, and is
    # read exactly as it was before the field existed.
    scope = _scope(payload["scope"], bad) if "scope" in payload else None
    examined = _examined(
        payload.get("examined", []), bad,
        set(scope.documents) if scope is not None else None,
    )

    status = payload.get("status")
    if "status" in payload and status not in CARRIED_STATES:
        bad("report-invalid-status",
            f"status {status!r} is not a state a report may carry — a producing "
            f"run declares {list(DECLARABLE_STATES)}, and a validator may have "
            f"since marked it {STATE_STALE!r}; 'invalid' is never a report, "
            f"because an invalid run has no content to report",
            "status")
    elif status in DECLARABLE_STATES and records is not None and (
        incomplete is not None
    ):
        # Derived from the raw lists, not the parsed ones: a record this
        # validator rejected is still a record the run claims to have found.
        derived = state_from_content(payload.get("records", []),
                                      payload.get("incomplete", []))
        if derived != status:
            bad("report-state-inconsistent",
                f"the report declares '{status}' but its content is '{derived}' "
                f"({len(payload.get('records', []))} record(s), "
                f"{len(payload.get('incomplete', []))} unexamined scope(s)) — "
                f"only 'clean' may mean the declared scope completed with "
                f"nothing found",
                "status")

    carried = _carried_stale_reasons(payload.get("stale_reasons", []), bad, status)

    if problems:
        return Invalid(tuple(problems))

    records, incomplete, carried = tuple(records), tuple(incomplete), tuple(carried)
    examined = tuple(examined)
    digest = _content_digest(lineage, records, incomplete, scope, examined)
    declared_digest = payload.get("digest")
    if declared_digest is not None and declared_digest != digest:
        return Invalid((Problem(
            code="report-digest-mismatch",
            message=(
                f"the report declares digest {declared_digest} but its content "
                f"digests to {digest} — the report has been altered since it was "
                f"produced, and approval binds to the digest"
            ),
            location="digest",
        ),))

    if repo_root is None:
        # Structural only: a carried stale verdict stands, because nothing here
        # can disprove it, and keeping it is the fail-closed direction.
        return Report(
            status=status, lineage=lineage, records=records,
            incomplete=incomplete, digest=digest, stale_reasons=carried,
            scope=scope, examined=examined,
        )

    current, inventory, problems = _current_state(repo_root, registry_path,
                                                  audit_config_digest)
    if problems:
        return Invalid(tuple(problems))
    reasons = _stale_reasons(lineage, current)
    # The declared scope, re-derived rather than trusted. Shape validation
    # above proves only that a scope is well-formed; this is what makes it a
    # claim about *this* repository, which is the whole reason it is in the
    # digest an approval set binds to.
    if scope is not None:
        reasons += _scope_reasons(
            scope,
            {document.path: document.kind for document in inventory.documents},
            lineage.audit_mode,
        )
    found = {reason.code for reason in reasons}
    reasons += tuple(
        reason for reason in _still_standing(
            carried, current,
            rechecked=SCOPE_REASON_CODES if scope is not None else (),
        )
        if reason.code not in found
    )
    if reasons:
        return Report(
            status=STATE_STALE, lineage=lineage, records=records,
            incomplete=incomplete, digest=digest, stale_reasons=reasons,
            scope=scope, examined=examined,
        )
    # Every comparable field matches, and every carried reason was re-checked,
    # so the verdict is cleared and the state follows from the content again.
    return Report(
        status=state_from_content(records, incomplete), lineage=lineage,
        records=records, incomplete=incomplete, digest=digest, scope=scope,
        examined=examined,
    )


def _reject_constant(name):
    raise ValueError(
        f"{name} is not JSON — a report must survive a strict parser and its "
        f"own digest, which are taken over the same encoding"
    )


def load_report(path, repo_root=None, registry_path=DEFAULT_REGISTRY_PATH,
                audit_config_digest=None):
    """Read a report file and validate it. Returns a `Report` or `Invalid`.

    The one function the `validate-report` and `render-report` commands call,
    so a file checked by hand and the same file checked in CI reach the same
    verdict.
    """
    try:
        with open(path, encoding="utf-8") as fh:
            text = fh.read()
    except OSError as exc:
        return Invalid((Problem(
            code="report-unreadable",
            message=f"cannot read the report at {path}: {exc.strerror}",
            location=path,
        ),))
    except UnicodeDecodeError as exc:
        # A `ValueError`, not an `OSError`: without this the CLI would answer a
        # malformed file with a traceback instead of a verdict.
        return Invalid((Problem(
            code="report-unreadable",
            message=(
                f"the report at {path} is not valid UTF-8 ({exc.reason} at byte "
                f"{exc.start}) — re-encode it; JSON is a text format"
            ),
            location=path,
        ),))
    try:
        # JSON has no NaN or Infinity, whatever Python's decoder will accept:
        # letting one in would make the engine's own output unparseable.
        payload = json.loads(text, parse_constant=_reject_constant)
    except (json.JSONDecodeError, ValueError) as exc:
        return Invalid((Problem(
            code="report-unparseable",
            message=f"the report is not valid JSON: {exc}",
            location=path,
        ),))
    except RecursionError:
        # The decoder recurses, and a `RecursionError` is not a `ValueError`.
        # A few kilobytes of nested brackets must be a verdict, not a traceback.
        return Invalid((Problem(
            code="report-nesting-too-deep",
            message=(
                f"the report nests too deeply to parse — a record describes a "
                f"finding, and this engine reads at most {MAX_NESTING} levels"
            ),
            location=path,
        ),))
    return validate_report(
        payload,
        repo_root=repo_root,
        registry_path=registry_path,
        audit_config_digest=audit_config_digest,
    )
