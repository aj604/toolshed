"""The approval set: the sole authority the applier accepts.

A report is proof of examination. It authorizes nothing. What authorizes a
change is an *approval set*: an immutable artifact binding a selection of
record digests from one report to that report's lineage and to an enumerated
allowed mutation scope, minted by a named minter.

Four properties, and every one of them is what makes it worth having:

**It binds a selection, not a report.** Approving three of eleven findings
mints an approval set naming those three. The other eight stay in the report,
are listed as skipped, and cannot ride along: they are absent from the record
list *and* their documents are absent from the allowed scope.

**It is answerable to reconciliation.** A selection that takes half of a group
whose members share text, or one leg of a contradictory pair, is refused before
anything is minted. Reconciliation runs over the whole report — see
`reconcile.py` — so this is structural, not a warning.

**It expires honestly.** Validation compares the artifact against the world and
names every field that moved: the base commit, the report, the rules (ruleset
and registry), the configuration, the target preimage, and the allowed scope. A
stale approval set is not a weaker approval; it is not an approval.

**It is never tracked.** An expired approval set has no value, so nothing needs
to remember it — `write_approval_set` refuses to put one anywhere git would
keep it. What travels with the change is its digest and its rendered summary,
in the commit message and the PR body.

*Why the inventory digest is deliberately not compared.* Every other lineage
field is. The inventory digest covers document *content*, so the applier's own
writes move it — and then a second subset of one report could never be applied,
which is exactly the partial-approval case this contract exists to support. The
precise question is per-record and is asked directly: are this record's units
still present in its document? A subset whose targets were untouched validates;
one whose targets were rewritten is stale, and says which record and which
document. A deleted document fails the same check.
"""

import json
import os
from dataclasses import dataclass
from typing import Tuple

from . import ARTIFACT_SCHEMA_VERSION
from .digest import sha256_canonical
from .inventory import DEFAULT_REGISTRY_PATH, load_registry
from .paths import DOCUMENTATION, authorize_path
from .reconcile import DISPOSITION_EXCLUSIVE, reconcile
from .report import (
    DIGEST,
    Lineage,
    Report,
    StaleReason,
    current_lineage,
    parse_lineage,
)
from . import repository as repository_mod
from .results import (
    STATE_CLEAN,
    STATE_FINDINGS,
    STATE_PARTIAL,
    STATE_STALE,
    Invalid,
    Problem,
)
from .segment import segment_document

# What the artifact says it is. A report also carries a lineage and a list of
# records; without a self-declared kind, one could be handed to the applier
# where the other is required and would parse far enough to be dangerous.
ARTIFACT_KIND = "approval-set"

# Who may mint. `human` is semantic approval — a person selecting record
# digests. `policy` is a standing consumer-configured auto-apply policy, named
# here so lineage records which one, and so PR review knows what it is
# reviewing. What a policy is *allowed* to mint is not decided here.
MINTER_HUMAN = "human"
MINTER_POLICY = "policy"
MINTER_KINDS = (MINTER_HUMAN, MINTER_POLICY)

# The report states a selection can rest on. `clean` has nothing to approve;
# `stale` describes a repository state that no longer exists, and `invalid`
# never reaches here. `partial` does approve: a run that examined less than it
# declared still found what it found, and the records it produced are real.
APPROVABLE_STATES = (STATE_FINDINGS, STATE_PARTIAL)

# The record field naming where a move writes. Its destination is inside the
# allowed mutation scope, because the applier writes there.
DESTINATION_FIELD = "destination"

FIELDS = (
    "artifact", "schema_version", "status", "minter", "report_digest",
    "lineage", "reconciliation_digest", "records", "skipped", "scope",
    "digest", "stale_reasons",
)
# `digest` is optional on the way in, as a report's is: it is checked when
# present, and its absence changes no verdict. `stale_reasons` is a validator's
# output that must read back in, for the same reason a report's do.
REQUIRED_FIELDS = tuple(
    f for f in FIELDS if f not in ("digest", "stale_reasons")
)

MINTER_FIELDS = ("kind", "id")
RECORD_FIELDS = ("digest", "id", "code", "path", "units")
SKIPPED_FIELDS = ("digest", "id")
SCOPE_FIELDS = ("roots", "paths")

# The states an approval set may carry. `clean` is a live approval; `stale` is
# a validator's verdict that it no longer is. There is no third: `findings` and
# `partial` describe a run, and an approval set is not a run.
CARRIED_STATES = (STATE_CLEAN, STATE_STALE)

# Which lineage field a stale reason came from, so a validator that did not
# compare a field cannot clear a reason produced by it.
COMPARABLE = (
    ("repository", "approval-repository-changed", "repository identity"),
    ("base_commit", "approval-base-commit-changed", "base commit"),
    ("registry_digest", "approval-registry-changed", "registry digest"),
    ("audit_config_digest", "approval-audit-config-changed",
     "audit configuration digest"),
    ("ruleset_version", "approval-ruleset-changed", "ruleset version"),
    ("plugin_version", "approval-plugin-changed", "plugin version"),
)
# The inventory digest is deliberately absent — see the module docstring.


@dataclass(frozen=True)
class Minter:
    """Who minted this approval set."""

    kind: str
    id: str

    def to_dict(self):
        return {"kind": self.kind, "id": self.id}


@dataclass(frozen=True)
class ApprovedRecord:
    """One selected record, and the target its digest commits to.

    The target is carried, not just referenced, so the applier can check what
    it is about to edit against the approval set alone — and so a preimage
    check has something to re-derive without re-reading the report.
    """

    digest: str
    record_id: str
    code: str
    path: str
    units: Tuple[str, ...]

    def to_dict(self):
        return {
            "digest": self.digest,
            "id": self.record_id,
            "code": self.code,
            "path": self.path,
            "units": list(self.units),
        }


@dataclass(frozen=True)
class SkippedRecord:
    """One record the report carries that this approval set does not select."""

    digest: str
    record_id: str

    def to_dict(self):
        return {"digest": self.digest, "id": self.record_id}


@dataclass(frozen=True)
class MutationScope:
    """Every path the applier may write, enumerated and authorized.

    Enumerated, never a rule: a scope that has to be evaluated is a scope whose
    meaning can change with the repository. `roots` travel with it so a reader
    can see what the enumeration was authorized against.
    """

    roots: Tuple[str, ...]
    paths: Tuple[str, ...]

    def to_dict(self):
        return {"roots": list(self.roots), "paths": list(self.paths)}


@dataclass(frozen=True)
class ApprovalSet:
    """A validated approval set. The applier accepts nothing else."""

    status: str
    minter: Minter
    report_digest: str
    lineage: Lineage
    reconciliation_digest: str
    records: Tuple[ApprovedRecord, ...]
    skipped: Tuple[SkippedRecord, ...]
    scope: MutationScope
    digest: str
    stale_reasons: Tuple = ()

    def to_dict(self):
        payload = dict(_content(
            self.minter, self.report_digest, self.lineage,
            self.reconciliation_digest, self.records, self.skipped, self.scope,
        ))
        payload["status"] = self.status
        payload["digest"] = self.digest
        if self.stale_reasons:
            payload["stale_reasons"] = [r.to_dict() for r in self.stale_reasons]
        return payload


def _content(minter, report_digest, lineage, reconciliation_digest, records,
             skipped, scope):
    """What the approval set *says* — the part its digest is taken over.

    The status and the stale reasons are excluded, exactly as they are from a
    report's digest: they are a verdict a validator reached about the artifact,
    and an artifact must not change identity because the world moved under it.
    """
    return {
        "artifact": ARTIFACT_KIND,
        "schema_version": ARTIFACT_SCHEMA_VERSION,
        "minter": minter.to_dict(),
        "report_digest": report_digest,
        "lineage": lineage.to_dict(),
        "reconciliation_digest": reconciliation_digest,
        "records": [r.to_dict() for r in records],
        "skipped": [r.to_dict() for r in skipped],
        "scope": scope.to_dict(),
    }


def approval_digest(minter, report_digest, lineage, reconciliation_digest,
                    records, skipped, scope):
    """The approval set's identity — what travels in the change it authorizes."""
    return sha256_canonical(_content(
        minter, report_digest, lineage, reconciliation_digest, records,
        skipped, scope,
    ))


def _selection_problems(selected, by_digest):
    """Everything wrong with the selection itself, exhaustively."""
    problems = []
    if not selected:
        problems.append(Problem(
            code="approval-empty-selection",
            message=(
                "no record digests were selected — an approval set is a "
                "selection, and an empty one authorizes nothing while looking "
                "like authority"
            ),
            location="records",
        ))
    seen = set()
    for digest in selected:
        if digest in seen:
            problems.append(Problem(
                code="approval-duplicate-selection",
                message=(
                    f"record {digest} is selected twice — a selection is a set "
                    f"of records, and a repeat makes the count of what was "
                    f"approved disagree with the list of it"
                ),
                location=digest,
            ))
        seen.add(digest)
        if digest not in by_digest:
            problems.append(Problem(
                code="approval-unknown-record",
                message=(
                    f"the report carries no record with digest {digest} — an "
                    f"approval set binds records from one report, so a digest "
                    f"from somewhere else authorizes nothing that can be checked"
                ),
                location=digest,
            ))
    return problems


def _group_problems(selected, reconciliation):
    """Every way the selection disagrees with what reconciliation grouped.

    Two refusals, and the difference matters. An *exclusive* group cannot be
    approved at all: its members contradict, so there is no subset of it — the
    whole group included — that an applier could execute. An *atomic* group can,
    but only whole: applying part of it would leave the rest describing text
    that no longer exists.
    """
    problems = []
    for group in reconciliation.groups:
        taken = [d for d in group.members if d in selected]
        if not taken:
            continue
        if group.disposition == DISPOSITION_EXCLUSIVE:
            problems.append(Problem(
                code="approval-exclusive-group",
                message=(
                    f"records {list(group.members)} propose different remedies "
                    f"for text they share, so no selection can include any of "
                    f"them: approving one silently decides against the other, "
                    f"and approving both cannot be applied. Resolve the "
                    f"contradiction in the audit — "
                    + "; ".join(r.reason for r in group.relations)
                ),
                location=group.group_id,
            ))
            continue
        missing = [d for d in group.members if d not in selected]
        if missing:
            problems.append(Problem(
                code="approval-partial-group",
                message=(
                    f"the selection takes {len(taken)} of {len(group.members)} "
                    f"records that share text; {missing} are left out. They are "
                    f"one edit or none — applying part of the group would leave "
                    f"the rest describing text that is no longer there — "
                    + "; ".join(r.reason for r in group.relations)
                ),
                location=group.group_id,
            ))
    return problems


def _targets(record):
    """Every path a record's remedy writes: its document, and any destination."""
    paths = [record.extra["path"]]
    destination = record.extra.get(DESTINATION_FIELD)
    if isinstance(destination, dict) and isinstance(destination.get("path"), str):
        paths.append(destination["path"])
    elif isinstance(destination, str):
        paths.append(destination)
    return paths


def _scope(records, repo_root, roots):
    """(MutationScope, problems): every write target, authorized.

    Derived from the selected records and nothing else. A report's coverage
    claim is not consulted — `whole-inventory` means every document is
    *mentioned*, which an exclusion carrying prose satisfies, so a coverage
    claim cannot be allowed to widen what an approval may write.
    """
    problems, paths, refused = [], set(), set()
    for record in records:
        for path in _targets(record):
            if path in paths:
                continue
            verdict = authorize_path(
                path, repo_root=repo_root, roots=roots,
                target_class=DOCUMENTATION,
            )
            if not verdict.authorized:
                problems.append(verdict.problem)
                refused.add(record.digest)
                continue
            paths.add(verdict.path)
    scope = MutationScope(roots=tuple(roots), paths=tuple(sorted(paths)))
    return scope, problems, refused


def _preimage_problems(records, repo_root, registry_path):
    """Every selected record whose target text is not what it was written about.

    The check that makes partial approval honest. A record names its target by
    assertion-unit digest, and a unit digest *is* its content — so a unit that
    is no longer in the document is a passage that has been rewritten, moved,
    or deleted since the audit read it. Applying an edit to it would be applying
    an edit to text nobody approved.
    """
    problems = []
    for record in records:
        path = record.path
        segmentation = segment_document(repo_root, path, registry_path)
        if isinstance(segmentation, Invalid):
            problems.append(Problem(
                code="approval-preimage-unreadable",
                message=(
                    f"the target document {path} cannot be read as a document "
                    f"now ({segmentation.problems[0].message}), so whether "
                    f"record {record.record_id} still describes it is unknown — "
                    f"an unanswered question about the target is a refusal"
                ),
                location=path,
            ))
            continue
        present = {unit.digest for unit in segmentation.units}
        missing = [unit for unit in record.units if unit not in present]
        if missing:
            problems.append(Problem(
                code="approval-preimage-mismatch",
                message=(
                    f"record {record.record_id} names {len(missing)} assertion "
                    f"unit(s) that {path} no longer contains — the text it was "
                    f"written about has changed, so re-run the audit rather "
                    f"than applying an edit to text nobody approved"
                ),
                location=path,
            ))
    return problems


def mint_approval_set(report, selected, *, repo_root, minter,
                      registry_path=DEFAULT_REGISTRY_PATH):
    """Mint an approval set from a selection of one report's record digests.

    Returns an `ApprovalSet`, or `Invalid` naming every problem. A non-`Report`
    or a non-`Minter` is a `TypeError`: minting authority from something that
    has not been validated as a report, or crediting it to something that is
    not a minter, is a programming error in the caller, not malformed data.

    The phases are ordered because each rests on the one before: a selection
    that names records the report does not carry cannot be checked against
    reconciliation, and a scope cannot be authorized for records that were
    never validly selected.
    """
    if not isinstance(report, Report):
        raise TypeError(
            f"mint_approval_set takes a validated Report, not "
            f"{type(report).__name__} — an approval set binds to a report's "
            f"lineage and digest, and unvalidated content has neither"
        )
    if not isinstance(minter, Minter):
        raise TypeError(
            f"a minter is a Minter, not {type(minter).__name__} — lineage "
            f"records who approved, and an unnamed approver is not approval"
        )

    if report.status not in APPROVABLE_STATES:
        return Invalid((Problem(
            code="approval-report-not-approvable",
            message=(
                f"a {report.status!r} report cannot authorize anything: an "
                f"approval set may be minted from a report whose state is one "
                f"of {list(APPROVABLE_STATES)}. Re-run the audit."
            ),
            location="status",
        ),))

    by_digest = {record.digest: record for record in report.records}
    selected = list(selected)
    problems = _selection_problems(selected, by_digest)
    if problems:
        return Invalid(tuple(problems))

    reconciliation = reconcile(report)
    if isinstance(reconciliation, Invalid):
        return reconciliation

    problems = _group_problems(set(selected), reconciliation)
    if problems:
        return Invalid(tuple(problems))

    registry = load_registry(repo_root, registry_path)
    if isinstance(registry, Invalid):
        return registry

    chosen = sorted((by_digest[d] for d in selected), key=lambda r: r.digest)
    scope, problems, refused = _scope(chosen, repo_root, registry.roots)

    records = tuple(ApprovedRecord(
        digest=record.digest,
        record_id=record.id,
        code=record.extra["code"],
        path=record.extra["path"],
        units=tuple(sorted(set(record.extra["units"]))),
    ) for record in chosen)
    # Only records whose targets authorized: a path the applier may not write
    # has already been refused, and asking whether its text still matches would
    # answer the same refusal twice in two vocabularies.
    problems += _preimage_problems(
        [r for r in records if r.digest not in refused], repo_root, registry_path
    )
    if problems:
        return Invalid(tuple(problems))

    skipped = tuple(sorted(
        (SkippedRecord(digest=r.digest, record_id=r.id)
         for r in report.records if r.digest not in set(selected)),
        key=lambda r: r.digest,
    ))
    return ApprovalSet(
        status=STATE_CLEAN,
        minter=minter,
        report_digest=report.digest,
        lineage=report.lineage,
        reconciliation_digest=reconciliation.digest,
        records=records,
        skipped=skipped,
        scope=scope,
        digest=approval_digest(
            minter, report.digest, report.lineage, reconciliation.digest,
            records, skipped, scope,
        ),
    )


# --------------------------------------------------------------------------
# Validation
# --------------------------------------------------------------------------

def _printable(value):
    return (
        isinstance(value, str) and value.strip() != ""
        and not any(c in value for c in "\n\r\x00")
    )


def _describe(payload):
    """What the caller handed over instead of an approval set.

    Named rather than merely refused, because the mistakes are specific and a
    reader has to know which one they made: a report is proof of examination, a
    list of digests is the *input* to minting, and a branch or run id is a
    pointer to a place where something happened.
    """
    if isinstance(payload, list):
        return (
            "a list — this is a dispatch list of record digests, which is how "
            "an approval set is minted, never a substitute for one"
        )
    if isinstance(payload, str):
        return (
            "a string — a branch name, a run id, or a path is a pointer to "
            "where something happened, and authority is not a pointer"
        )
    if not isinstance(payload, dict):
        return f"a {type(payload).__name__}, which carries no authority at all"
    if "lineage" in payload and "records" in payload and "status" in payload:
        return (
            "a report — proof of what was examined, and deliberately not "
            "authority to change anything; mint an approval set from it"
        )
    kind = payload.get("artifact")
    return (
        f"an object declaring artifact {kind!r}"
        if kind is not None else
        "an object that does not say what artifact it is"
    )


def _minter(raw, bad):
    if not isinstance(raw, dict) or set(raw) != set(MINTER_FIELDS):
        bad("approval-invalid-minter",
            f"minter must be an object with exactly {list(MINTER_FIELDS)}",
            "minter")
        return None
    if raw["kind"] not in MINTER_KINDS or not _printable(raw["id"]):
        bad("approval-invalid-minter",
            f"a minter is one of {list(MINTER_KINDS)} with a non-empty id; "
            f"{raw.get('kind')!r} is neither a person nor a named auto-apply "
            f"policy, and an unattributable approval is not approval",
            "minter")
        return None
    return Minter(kind=raw["kind"], id=raw["id"])


def _approved_records(raw, bad):
    if not isinstance(raw, list) or not raw:
        bad("approval-empty-selection",
            "records must be a non-empty list of the selected records — an "
            "approval set that selects nothing authorizes nothing while "
            "looking like authority",
            "records")
        return None
    records, seen, ok = [], set(), True
    for i, entry in enumerate(raw):
        where = f"records[{i}]"
        if not isinstance(entry, dict) or set(entry) != set(RECORD_FIELDS):
            bad("approval-invalid-record",
                f"records[{i}] must be an object with exactly "
                f"{list(RECORD_FIELDS)} — the digest is what is approved, and "
                f"the rest is the target it commits to",
                where)
            ok = False
            continue
        units = entry["units"]
        if not (isinstance(entry["digest"], str) and DIGEST.match(entry["digest"])):
            bad("approval-invalid-record",
                f"records[{i}].digest must be a sha256 record digest", where)
            ok = False
            continue
        if not all(_printable(entry[f]) for f in ("id", "code", "path")):
            bad("approval-invalid-record",
                f"records[{i}] must name a single-line id, code, and document",
                where)
            ok = False
            continue
        if not (isinstance(units, list) and units and all(
            isinstance(u, str) and DIGEST.match(u) for u in units
        )):
            bad("approval-invalid-record",
                f"records[{i}].units must be a non-empty list of assertion-unit "
                f"digests — they are the preimage the approval binds to",
                where)
            ok = False
            continue
        if entry["digest"] in seen:
            bad("approval-invalid-record",
                f"records[{i}] repeats digest {entry['digest']} — a selection "
                f"is a set of records",
                where)
            ok = False
            continue
        seen.add(entry["digest"])
        records.append(ApprovedRecord(
            digest=entry["digest"], record_id=entry["id"], code=entry["code"],
            path=entry["path"], units=tuple(sorted(set(units))),
        ))
    return records if ok else None


def _skipped_records(raw, bad):
    if not isinstance(raw, list):
        bad("approval-invalid-skipped",
            "skipped must be a list of the report's records this approval set "
            "did not select — partial approval is only auditable if the part "
            "left out is named",
            "skipped")
        return None
    entries, ok = [], True
    for i, entry in enumerate(raw):
        if not isinstance(entry, dict) or set(entry) != set(SKIPPED_FIELDS):
            bad("approval-invalid-skipped",
                f"skipped[{i}] must be an object with exactly "
                f"{list(SKIPPED_FIELDS)}",
                f"skipped[{i}]")
            ok = False
            continue
        if not (isinstance(entry["digest"], str) and DIGEST.match(entry["digest"])
                and _printable(entry["id"])):
            bad("approval-invalid-skipped",
                f"skipped[{i}] must name a record digest and its display id",
                f"skipped[{i}]")
            ok = False
            continue
        entries.append(SkippedRecord(digest=entry["digest"], record_id=entry["id"]))
    return entries if ok else None


def _mutation_scope(raw, bad):
    if not isinstance(raw, dict) or set(raw) != set(SCOPE_FIELDS):
        bad("approval-invalid-scope",
            f"scope must be an object with exactly {list(SCOPE_FIELDS)} — the "
            f"roots it was authorized against, and the enumerated paths the "
            f"applier may write",
            "scope")
        return None
    ok = True
    for name in SCOPE_FIELDS:
        values = raw[name]
        if not isinstance(values, list) or not all(_printable(v) for v in values):
            bad("approval-invalid-scope",
                f"scope.{name} must be a list of single-line "
                f"repository-relative paths",
                f"scope.{name}")
            ok = False
        elif len(set(values)) != len(values):
            bad("approval-invalid-scope",
                f"scope.{name} repeats a path — an enumerated scope is a set",
                f"scope.{name}")
            ok = False
    if not ok:
        return None
    return MutationScope(roots=tuple(raw["roots"]), paths=tuple(raw["paths"]))


def _carried_stale_reasons(raw, bad, status):
    if not isinstance(raw, list):
        bad("approval-invalid-stale-reason",
            "stale_reasons must be a list of the fields that moved",
            "stale_reasons")
        return None
    fields = {"code", "message", "reported", "current"}
    reasons, ok = [], True
    for i, entry in enumerate(raw):
        if not isinstance(entry, dict) or set(entry) != fields or not all(
            _printable(entry[f]) for f in fields
        ):
            bad("approval-invalid-stale-reason",
                f"stale_reasons[{i}] must be an object with exactly "
                f"{sorted(fields)}, each a non-empty single-line string",
                f"stale_reasons[{i}]")
            ok = False
            continue
        reasons.append(StaleReason(**entry))
    if not ok:
        return None
    if (status == STATE_STALE) != bool(reasons):
        bad("approval-state-inconsistent",
            f"a {STATE_STALE!r} approval set names every field that moved, and "
            f"only a stale one carries stale reasons; this declares {status!r} "
            f"with {len(reasons)} reason(s)",
            "stale_reasons")
        return None
    return reasons


def _lineage_reasons(lineage, current):
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
                f"the approval set was minted against {label} {reported}, and "
                f"the repository's is now {actual} — the approval was for a "
                f"state that no longer exists, so re-run the audit and approve "
                f"again"
            ),
            reported=str(reported),
            current=str(actual),
        ))
    return reasons


def _scope_reasons(scope, repo_root, registry_path):
    """Every way the allowed mutation scope no longer authorizes what it names.

    Re-derived, never trusted. The scope is the outer bound on what the applier
    may write, so a path that has since become a symlink, a directory, or
    wiring is exactly the case where trusting the recorded answer would matter.
    """
    registry = load_registry(repo_root, registry_path)
    if isinstance(registry, Invalid):
        # The registry decides what is documentation at all. Unreadable, the
        # scope cannot be re-derived — and an unchecked scope stands for
        # nothing.
        return [StaleReason(
            code="approval-scope-changed",
            message=(
                f"the allowed mutation scope cannot be re-authorized: "
                f"{registry.problems[0].message}"
            ),
            reported=str(len(scope.paths)) + " path(s)",
            current="the registry cannot be read",
        )]
    reasons = []
    if tuple(registry.roots) != scope.roots:
        reasons.append(StaleReason(
            code="approval-scope-changed",
            message=(
                f"the approval set was authorized against documentation roots "
                f"{list(scope.roots)}, and the registry now declares "
                f"{list(registry.roots)} — what counts as documentation has "
                f"moved under the approval"
            ),
            reported=", ".join(scope.roots) or "none",
            current=", ".join(registry.roots) or "none",
        ))
    for path in scope.paths:
        verdict = authorize_path(
            path, repo_root=repo_root, roots=registry.roots,
            target_class=DOCUMENTATION,
        )
        if not verdict.authorized:
            reasons.append(StaleReason(
                code="approval-scope-changed",
                message=(
                    f"{path} was inside the allowed mutation scope when the "
                    f"approval was minted and no longer authorizes: "
                    f"{verdict.problem.message}"
                ),
                reported=path,
                current=verdict.problem.code,
            ))
    return reasons


def _preimage_reasons(records, repo_root, registry_path):
    """Preimage drift, as stale reasons rather than problems.

    The same check minting runs, read the other way round. At mint time a
    target that has already moved means the selection was made against text
    that is gone, and nothing should be minted. Here the artifact exists and
    the question is whether it still stands — which is `stale`: the remedy is
    to re-run the audit and approve again, not to fix the file.
    """
    reasons = []
    for problem in _preimage_problems(records, repo_root, registry_path):
        reasons.append(StaleReason(
            code=problem.code,
            message=problem.message,
            reported=problem.location,
            current="the document has changed since the approval was minted",
        ))
    return reasons


def validate_approval_set(payload, *, report=None, repo_root=None,
                          registry_path=DEFAULT_REGISTRY_PATH,
                          audit_config_digest=None):
    """Validate an approval set. Returns an `ApprovalSet` or `Invalid`.

    Structural validation is exhaustive and runs alone: an artifact that cannot
    be read has nothing to check against a report or a repository, so `invalid`
    always beats `stale`.

    Pass `report` to check the selection against the report it names, and
    `repo_root` to check it against the world. Each check is optional and each
    is honest about not having run: without a repository the verdict can never
    be `stale`, because this function does not guess at a state it was not
    shown.
    """
    if report is not None and not isinstance(report, Report):
        raise TypeError(
            f"the report an approval set is checked against is a validated "
            f"Report, not {type(report).__name__}"
        )

    if not isinstance(payload, dict) or payload.get("artifact") != ARTIFACT_KIND:
        return Invalid((Problem(
            code="approval-not-an-approval-set",
            message=(
                f"an approval set is required here, and this is "
                f"{_describe(payload)}. The applier accepts a validated "
                f"approval set and nothing else."
            ),
            location="artifact",
        ),))

    problems = []

    def bad(code, message, where=None):
        problems.append(Problem(code=code, message=message, location=where))

    for name in REQUIRED_FIELDS:
        if name not in payload:
            bad("approval-missing-field",
                f"the approval set is missing '{name}'", name)
    for name in payload:
        if name not in FIELDS:
            bad("approval-unknown-field",
                f"unexpected field {name!r} — an approval set carries "
                f"{list(FIELDS)}",
                name)

    version = payload.get("schema_version")
    if "schema_version" in payload and not (
        isinstance(version, int) and not isinstance(version, bool)
        and version == ARTIFACT_SCHEMA_VERSION
    ):
        bad("approval-schema-version",
            f"approval-set schema_version {version!r} is not supported; this "
            f"engine reads integer version {ARTIFACT_SCHEMA_VERSION}",
            "schema_version")

    status = payload.get("status")
    if "status" in payload and status not in CARRIED_STATES:
        bad("approval-invalid-status",
            f"status {status!r} is not a state an approval set carries — it is "
            f"one of {list(CARRIED_STATES)}",
            "status")

    for name in ("report_digest", "reconciliation_digest"):
        value = payload.get(name)
        if name in payload and not (
            isinstance(value, str) and DIGEST.match(value)
        ):
            bad("approval-invalid-digest",
                f"{name} must be a sha256 digest — it is what binds this "
                f"approval to one report",
                name)

    minter = _minter(payload["minter"], bad) if "minter" in payload else None
    lineage = None
    if "lineage" in payload:
        lineage, lineage_problems = parse_lineage(payload["lineage"])
        problems.extend(lineage_problems)
    records = (
        _approved_records(payload["records"], bad) if "records" in payload
        else None
    )
    skipped = (
        _skipped_records(payload["skipped"], bad) if "skipped" in payload
        else None
    )
    scope = _mutation_scope(payload["scope"], bad) if "scope" in payload else None
    carried = _carried_stale_reasons(
        payload.get("stale_reasons", []), bad, status
    )

    if records is not None and scope is not None:
        outside = sorted({
            r.path for r in records if r.path not in set(scope.paths)
        })
        if outside:
            bad("approval-record-outside-scope",
                f"the approval set selects records in {outside}, which its own "
                f"allowed mutation scope does not permit writing — the scope is "
                f"the outer bound on the selection, so the two disagreeing "
                f"means neither can be acted on",
                "scope.paths")

    if problems:
        return Invalid(tuple(problems))

    records, skipped = tuple(records), tuple(skipped)
    carried = tuple(carried)
    digest = approval_digest(
        minter, payload["report_digest"], lineage,
        payload["reconciliation_digest"], records, skipped, scope,
    )
    declared = payload.get("digest")
    if declared is not None and declared != digest:
        return Invalid((Problem(
            code="approval-digest-mismatch",
            message=(
                f"the approval set declares digest {declared} but its content "
                f"digests to {digest} — it has been altered since it was "
                f"minted, and its digest is what travels in the change it "
                f"authorizes"
            ),
            location="digest",
        ),))

    reasons = []
    if report is not None:
        reasons += _report_reasons(payload, records, report)
    if repo_root is not None:
        current, current_problems = current_lineage(
            repo_root, registry_path, audit_config_digest
        )
        if current_problems:
            return Invalid(tuple(current_problems))
        reasons += _lineage_reasons(lineage, current)
        reasons += _scope_reasons(scope, repo_root, registry_path)
        reasons += _preimage_reasons(records, repo_root, registry_path)

    # A carried reason this run did not re-check still stands: clearing a
    # verdict must be at least as thorough as setting it.
    found = {reason.code for reason in reasons}
    rechecked = set(found)
    if repo_root is not None:
        rechecked |= {code for field, code, _ in COMPARABLE if field in current}
        rechecked |= {"approval-scope-changed", "approval-preimage-mismatch",
                      "approval-preimage-unreadable"}
    if report is not None:
        rechecked |= {"approval-report-changed"}
    reasons += [r for r in carried if r.code not in rechecked]

    return ApprovalSet(
        status=STATE_STALE if reasons else STATE_CLEAN,
        minter=minter,
        report_digest=payload["report_digest"],
        lineage=lineage,
        reconciliation_digest=payload["reconciliation_digest"],
        records=records,
        skipped=skipped,
        scope=scope,
        digest=digest,
        stale_reasons=tuple(reasons),
    )


def _report_reasons(payload, records, report):
    """Whether the report this approval names is still the report it binds to."""
    if payload["report_digest"] != report.digest:
        return [StaleReason(
            code="approval-report-changed",
            message=(
                f"the approval set was minted from report "
                f"{payload['report_digest']}, and the report supplied digests "
                f"to {report.digest} — a selection is only meaningful against "
                f"the records it was made from"
            ),
            reported=payload["report_digest"],
            current=report.digest,
        )]
    reasons = []
    carried = {record.digest for record in report.records}
    missing = sorted(r.digest for r in records if r.digest not in carried)
    if missing:
        reasons.append(StaleReason(
            code="approval-report-changed",
            message=(
                f"the approval set selects {len(missing)} record(s) the report "
                f"does not carry — there is nothing for the applier to look up, "
                f"so the selection authorizes nothing"
            ),
            reported=missing[0],
            current=f"{len(carried)} record(s) in the report",
        ))
        return reasons
    reconciliation = reconcile(report)
    if isinstance(reconciliation, Invalid):
        reasons.append(StaleReason(
            code="approval-reconciliation-changed",
            message=(
                f"the report can no longer be reconciled, so whether this "
                f"selection respects its groups is unknown: "
                f"{reconciliation.problems[0].message}"
            ),
            reported=payload["reconciliation_digest"],
            current="the report cannot be reconciled",
        ))
    elif reconciliation.digest != payload["reconciliation_digest"]:
        reasons.append(StaleReason(
            code="approval-reconciliation-changed",
            message=(
                "the report's records no longer group the way they did when "
                "this selection was checked against them, so the selection is "
                "not known to respect the groups"
            ),
            reported=payload["reconciliation_digest"],
            current=reconciliation.digest,
        ))
    return reasons


def _reject_constant(name):
    raise ValueError(
        f"{name} is not JSON — an approval set must survive a strict parser "
        f"and its own digest, which are taken over the same encoding"
    )


def load_approval_set(path, *, report=None, repo_root=None,
                      registry_path=DEFAULT_REGISTRY_PATH,
                      audit_config_digest=None):
    """Read an approval-set file and validate it. `ApprovalSet` or `Invalid`."""
    try:
        with open(path, encoding="utf-8") as fh:
            text = fh.read()
    except OSError as exc:
        return Invalid((Problem(
            code="approval-unreadable",
            message=f"cannot read the approval set at {path}: {exc.strerror}",
            location=path,
        ),))
    except UnicodeDecodeError as exc:
        return Invalid((Problem(
            code="approval-unreadable",
            message=(
                f"the approval set at {path} is not valid UTF-8 ({exc.reason} "
                f"at byte {exc.start}) — re-encode it; JSON is a text format"
            ),
            location=path,
        ),))
    try:
        payload = json.loads(text, parse_constant=_reject_constant)
    except (json.JSONDecodeError, ValueError) as exc:
        return Invalid((Problem(
            code="approval-unparseable",
            message=f"the approval set is not valid JSON: {exc}",
            location=path,
        ),))
    except RecursionError:
        return Invalid((Problem(
            code="approval-unparseable",
            message=(
                "the approval set nests too deeply to parse — an approval set "
                "is a selection of digests, not a document"
            ),
            location=path,
        ),))
    return validate_approval_set(
        payload, report=report, repo_root=repo_root,
        registry_path=registry_path, audit_config_digest=audit_config_digest,
    )


def write_approval_set(approval, path):
    """Write an approval set to `path`. Returns the path, or `Invalid`.

    Refuses anywhere git would keep the file. An approval set expires with the
    change it authorizes, so a committed one is at best noise and at worst a
    stale authority somebody re-reads; what travels in the change is its digest
    and its rendered summary, not the artifact. `trackable` is refused for the
    same reason `tracked` is: an untracked file in the work tree is one
    `git add -A` away from being committed by the very run it authorizes.
    """
    if not isinstance(approval, ApprovalSet):
        raise TypeError(
            f"write_approval_set takes a validated ApprovalSet, not "
            f"{type(approval).__name__}"
        )

    state, problem = repository_mod.tracking(path)
    if problem is not None:
        return Invalid((problem,))
    if state == repository_mod.TRACKING_TRACKED:
        return Invalid((Problem(
            code="approval-set-tracked-path",
            message=(
                f"{path} is tracked in the repository — an approval set is "
                f"never written into tracked state, and this would also "
                f"overwrite a file the repository keeps"
            ),
            location=path,
        ),))
    if state == repository_mod.TRACKING_TRACKABLE:
        return Invalid((Problem(
            code="approval-set-would-be-tracked",
            message=(
                f"{path} is inside the repository's work tree and is not "
                f"ignored, so committing the change this approves would commit "
                f"the approval set with it. Write it outside the repository, "
                f"or into a git-ignored path"
            ),
            location=path,
        ),))

    with open(path, "w", encoding="utf-8") as fh:
        fh.write(json.dumps(
            approval.to_dict(), indent=2, ensure_ascii=False, allow_nan=False
        ) + "\n")
    return path
