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
from typing import Optional, Tuple

from . import ARTIFACT_SCHEMA_VERSION
from .digest import sha256_canonical
from .inventory import DEFAULT_REGISTRY_PATH, load_registry
from .paths import DOCUMENTATION, authorize_path
from .reconcile import DISPOSITION_EXCLUSIVE, reconcile
from .report import DIGEST, Lineage, Report
from .results import (
    DECLARABLE_STATES,
    STATE_CLEAN,
    STATE_FINDINGS,
    STATE_PARTIAL,
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
