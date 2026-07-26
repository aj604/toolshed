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
import re
from dataclasses import dataclass
from typing import Optional, Tuple

from . import ARTIFACT_SCHEMA_VERSION, PLUGIN_VERSION, RULESET_VERSION
from . import repository as repository_mod
from .digest import sha256_canonical
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

FIELDS = ("status", "schema_version", "lineage", "records", "incomplete", "digest")
REQUIRED_FIELDS = ("status", "schema_version", "lineage")

# The audit modes a report may declare. Closed: an unrecognized mode means the
# reader cannot know what "the declared scope" was, so nothing else it says is
# interpretable.
AUDIT_MODES = ("full", "incremental", "chunk")

REQUIRED_LINEAGE_FIELDS = (
    "repository",           # which repository the report is about
    "base_commit",          # the commit its evidence was read at
    "audit_mode",           # how much of the corpus the run set out to examine
    "inventory_digest",     # the corpus it examined
    "audit_config_digest",  # the consumer configuration it ran under
    "registry_digest",      # the classification that decided the corpus
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
    the `digest` an approval set selects it by. Everything else a detector or
    the segmenter (#63) puts on a record travels in `extra`, untouched, so this
    module never becomes a second owner of record internals.
    """

    id: str
    digest: str
    extra: dict

    def to_dict(self):
        return {"id": self.id, "digest": self.digest, **self.extra}


@dataclass(frozen=True)
class Incomplete:
    """One part of the declared scope the run did not examine."""

    scope: str
    reason: str

    def to_dict(self):
        return {"scope": self.scope, "reason": self.reason}


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

    def to_dict(self):
        payload = {
            "status": self.status,
            "schema_version": ARTIFACT_SCHEMA_VERSION,
            "lineage": self.lineage.to_dict(),
            "records": [r.to_dict() for r in self.records],
            "incomplete": [i.to_dict() for i in self.incomplete],
            "digest": self.digest,
        }
        if self.status == STATE_STALE:
            payload["stale_reasons"] = [r.to_dict() for r in self.stale_reasons]
        return payload


def _nonempty_str(value):
    return isinstance(value, str) and value.strip() != ""


def _printable(value):
    """A one-line string: lineage and scopes are echoed to logs and PR bodies."""
    return _nonempty_str(value) and not any(c in value for c in "\n\r\x00")


def _content_digest(lineage, records, incomplete):
    """The report's identity: what it says, not what a validator concluded.

    Excludes the result state and the stale reasons, so the same report keeps
    one digest whether it is read fresh or years later — approval binds to this
    digest, and a verdict changing underneath must not re-key it.
    """
    return sha256_canonical({
        "schema_version": ARTIFACT_SCHEMA_VERSION,
        "lineage": lineage.to_dict(),
        "records": [r.to_dict() for r in records],
        "incomplete": [i.to_dict() for i in incomplete],
    })


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
        isinstance(raw["ruleset_version"], int)
        and not isinstance(raw["ruleset_version"], bool)
        and raw["ruleset_version"] >= 1
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
        if not _printable(entry.get("id")):
            bad("report-invalid-record",
                f"record {i} must carry a non-empty single-line 'id'", where)
            ok = False
        digest = entry.get("digest")
        if not (isinstance(digest, str) and DIGEST.match(digest)):
            bad("report-invalid-record",
                f"record {i} must carry a sha256 'digest' — an approval set "
                f"selects records by digest, so a record without one cannot be "
                f"approved",
                where)
            ok = False
        if ok:
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


def _declared_state(records, incomplete):
    """The only state the report's own content supports.

    Derived rather than trusted: a run cannot both leave part of its scope
    unexamined and call itself clean, and the state a reader acts on must
    follow from what the report actually contains.
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
    state, problems = repository_mod.state(repo_root)
    state = dict(state)

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
        state["inventory_digest"] = inventory.digest
        state["registry_digest"] = inventory.registry_digest

    if problems:
        return {}, tuple(problems)

    state["ruleset_version"] = RULESET_VERSION
    state["plugin_version"] = PLUGIN_VERSION
    if audit_config_digest is not None:
        state["audit_config_digest"] = audit_config_digest
    return state, ()


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
    if "schema_version" in payload and version != ARTIFACT_SCHEMA_VERSION:
        bad("report-schema-version",
            f"report schema_version {version!r} is not supported; this engine "
            f"reads version {ARTIFACT_SCHEMA_VERSION}. Migrate the report rather "
            f"than guessing at the meaning of a shape it does not know.",
            "schema_version")

    lineage = _lineage(payload["lineage"], bad) if "lineage" in payload else None
    records = _records(payload.get("records", []), bad)
    incomplete = _incomplete(payload.get("incomplete", []), bad)

    status = payload.get("status")
    if "status" in payload and status not in DECLARABLE_STATES:
        bad("report-invalid-status",
            f"status {status!r} is not a state a run may declare — a producing "
            f"run is {list(DECLARABLE_STATES)}; 'stale' and 'invalid' are "
            f"verdicts a validator reaches about a report, not self-assessments",
            "status")
    elif status in DECLARABLE_STATES and records is not None and (
        incomplete is not None
    ):
        derived = _declared_state(payload.get("records", []),
                                  payload.get("incomplete", []))
        if derived != status:
            bad("report-state-inconsistent",
                f"the report declares '{status}' but its content is '{derived}' "
                f"({len(payload.get('records', []))} record(s), "
                f"{len(payload.get('incomplete', []))} unexamined scope(s)) — "
                f"only 'clean' may mean the declared scope completed with "
                f"nothing found",
                "status")

    if problems:
        return Invalid(tuple(problems))

    records, incomplete = tuple(records), tuple(incomplete)
    digest = _content_digest(lineage, records, incomplete)
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

    report = Report(
        status=status, lineage=lineage, records=records,
        incomplete=incomplete, digest=digest,
    )
    if repo_root is None:
        return report

    current, problems = current_lineage(repo_root, registry_path,
                                        audit_config_digest)
    if problems:
        return Invalid(tuple(problems))
    reasons = _stale_reasons(lineage, current)
    if not reasons:
        return report
    return Report(
        status=STATE_STALE, lineage=lineage, records=records,
        incomplete=incomplete, digest=digest, stale_reasons=reasons,
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
    try:
        payload = json.loads(text)
    except json.JSONDecodeError as exc:
        return Invalid((Problem(
            code="report-unparseable",
            message=f"the report is not valid JSON: {exc}",
            location=path,
        ),))
    return validate_report(
        payload,
        repo_root=repo_root,
        registry_path=registry_path,
        audit_config_digest=audit_config_digest,
    )
