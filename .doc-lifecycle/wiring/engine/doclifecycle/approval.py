"""The approval set: the sole authority the applier accepts.

A report is proof of examination. It authorizes nothing. What authorizes a
change is an *approval set*: an immutable artifact binding a selection of
record digests from one report to that report's lineage and to an enumerated
allowed mutation scope, minted by a named minter.

Five properties, and every one of them is what makes it worth having:

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

**A policy brand is provenance, not a label.** `mint_approval_set` is the
human door and mints for a person only: a `policy`-branded set comes from
`policy.mint_policy_approval_set` alone, which reaches the same private
construction path with the standing declaration's digest recorded in the
minter. Validation reloads that declaration from the repository, decides the
report under it again, and refuses a selection that is not exactly the one the
policy derives. Eligibility is a pure function of the policy and the report,
both of which the artifact pins, so an inexact selection is a forgery rather
than the world moving — and a minter kind anybody could type into a file is
not authority.

**It binds occurrences, not just text.** A unit digest *is* its content, so a
document containing the same sentence twice contains one identity twice. That
is right for a finding — identity is content-addressed, and stays stable when a
document is reordered — and wrong for authority: reading a record's units back
as "wherever this text is" made the approved passage the span from the first
match to the last, so approving one occurrence quietly authorized every word
between it and its twin. Each approved record therefore carries the
`occurrences` it was approved about — the assertion-unit ordinals of the
*committed baseline* the audit read, which the pinned base commit makes
reproducible whatever the working tree does. Minting derives them and refuses
rather than guessing when a unit occurs more times in the baseline than the
record approves; validation re-derives them; and the applier bounds a
positioned operation by the passages those occurrences are, never by a hull
spanning content nobody reviewed.

*Why the inventory digest is deliberately not compared.* Every other lineage
field is. The inventory digest covers document *content*, so the applier's own
writes move it — and then a second subset of one report could never be applied,
which is exactly the partial-approval case this contract exists to support. The
precise question is per-record and is asked directly: are this record's units
still present in its document? A subset whose targets were untouched validates;
one whose targets were rewritten is stale, and says which record and which
document. A deleted document fails the same check. For a whole-document bloat
record, presence is not enough: its units must equal the complete current
deterministic set, or passage authority could be amplified into deletion.
"""

import json
from dataclasses import dataclass, replace
from typing import Optional, Tuple

from .bloat import VERDICTS as BLOAT_VERDICTS
from .digest import load_strict_json, sha256_canonical
from .finding import finding_digest
from .inventory import DEFAULT_REGISTRY_PATH, load_registry
from .paths import DOCUMENTATION, authorize_path, write_target_problem
from .reconcile import DISPOSITION_EXCLUSIVE, reconcile
from . import repository as repository_mod
from .report import (
    DIGEST,
    Lineage,
    Report,
    StaleReason,
    WHOLE_DOCUMENT_RECORD_CODES,
    compare_lineage,
    current_lineage,
    lineage_digest,
    parse_lineage,
    parse_stale_reasons,
    whole_document_unit_difference,
)
from .results import (
    STATE_CLEAN,
    STATE_FINDINGS,
    STATE_PARTIAL,
    STATE_STALE,
    Invalid,
    Problem,
)
from .segment import segment_document, segment_text

# What the artifact says it is. A report also carries a lineage and a list of
# records; without a self-declared kind, one could be handed to the applier
# where the other is required and would parse far enough to be dangerous.
ARTIFACT_KIND = "approval-set"

# The approval set's own schema version, which has left the engine-wide
# `ARTIFACT_SCHEMA_VERSION` behind: policy provenance and occurrence binding are
# fields the applier's trust now rests on, and a report, a registry, or a cache
# entry did not change at all. Versioning it here is what lets an older artifact
# be *refused* rather than read under the current rules — a pre-provenance
# `policy` brand is a label nothing can be revalidated against, and a
# pre-occurrence record says which text was approved without saying which
# occurrence of it, so reading either silently is how a migration turns into an
# unnoticed grant. Each superseded version keeps its own refusal, because what a
# reader must do about it differs by what the version was missing.
SCHEMA_VERSION = 3
PRE_PROVENANCE_SCHEMA_VERSION = 1
PRE_OCCURRENCE_SCHEMA_VERSION = 2

# Who may mint. `human` is semantic approval — a person selecting record
# digests. `policy` is a standing consumer-configured auto-apply policy, named
# here so lineage records which one, and so PR review knows what it is
# reviewing. What a policy is *allowed* to mint is not decided here.
MINTER_HUMAN = "human"
MINTER_POLICY = "policy"
MINTER_KINDS = (MINTER_HUMAN, MINTER_POLICY)

# Every superseded version this engine refuses by name, with the code that names
# it and what an artifact of that version could not carry. A table rather than a
# chain of `if`s, so adding a version is one entry: a version that is neither
# current nor listed here falls through to `approval-schema-version`, which is
# the right answer for a number nothing ever minted.
SUPERSEDED_SCHEMA_VERSIONS = {
    PRE_PROVENANCE_SCHEMA_VERSION: ("approval-schema-pre-provenance", (
        f"a {MINTER_POLICY!r} brand was descriptive text there, carrying "
        f"nothing the standing declaration could be revalidated against"
    )),
    PRE_OCCURRENCE_SCHEMA_VERSION: ("approval-schema-pre-occurrence", (
        "its records name the units they approve without naming which "
        "occurrence of them was read, and a document may hold one unit "
        "identity in several places. Nothing in the artifact identifies the "
        "approved occurrence set, and the passage cannot be reconstructed by "
        "spanning the matches — that hull is precisely the authority over "
        "unreviewed text this version exists to end"
    )),
}

# The bloat verdict codes a policy minter may never select, whichever door it
# is reached through. `policy.py`'s restricted `NEVER_ELIGIBLE_CODES` is an
# alias of this tuple — one owner, so a class the eligibility table forgets to
# name and a selection built by hand around the generic minter are refused by
# the same rule. Every bloat verdict is a judgment that a passage or a whole
# document should stop existing or move; approving that is what a person is
# for, and no standing policy performs semantic review.
# *Every* bloat verdict, so this is `bloat.VERDICTS` rather than a hand-copy of
# it: a seventh verdict added there is restricted the moment it exists, where a
# re-listing would have admitted it silently and kept this guard green.
POLICY_NEVER_ELIGIBLE_CODES = BLOAT_VERDICTS

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
    "report_state", "lineage", "reconciliation_digest", "records", "skipped",
    "scope", "digest", "stale_reasons", "unchecked", "observed_report_state",
)
# Verdict-side output that reads back in only so a validated artifact can be
# round-tripped through a file. Both are re-derived on every run and the
# carried value is never consulted: they describe what one validation run was
# shown, which is a fact about that run and not about the approval set.
RUN_FIELDS = ("unchecked", "observed_report_state")
# `digest` is *required*, unlike a report's. A report is proof of examination
# and its digest is a convenience; an approval set is authority, and its digest
# is the only part of it that travels into the repository — so an approval set
# that declines to say what it hashes to is one whose trailer nothing can be
# checked against, and every tamper becomes "delete one field". `stale_reasons`
# is a validator's output that must read back in, for the same reason a
# report's do.
REQUIRED_FIELDS = tuple(
    f for f in FIELDS if f != "stale_reasons" and f not in RUN_FIELDS
)

MINTER_FIELDS = ("kind", "id", "policy_digest")
RECORD_FIELDS = (
    "digest", "id", "code", "path", "destination", "units", "occurrences",
)
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

# The stale reasons that come from somewhere other than a lineage field, and
# what a run needs in hand to have re-derived them. Named rather than spelled
# inline where a carried verdict is cleared: clearing has to be at least as
# thorough as setting, and a reason nobody listed is a reason nobody re-checks
# — which would keep it forever, or drop it unexamined.
REPOSITORY_REASON_CODES = (
    "approval-scope-changed",
    "approval-preimage-mismatch",
    "approval-preimage-unreadable",
    "approval-whole-document-units-incomplete",
)
# The occurrence codes are deliberately absent: an occurrence disagreement is
# only ever asked against the baseline the approval names, where it is a forgery
# rather than staleness, so no run produces one as a stale reason to clear.
REPORT_REASON_CODES = (
    "approval-report-changed",
    "approval-reconciliation-changed",
)
# The standing declaration a `policy` brand delegates from, re-read from the
# repository — so it belongs to the repository check, and a run without one
# cannot clear it. Listed after the two tuples above rather than inside them:
# it is neither a lineage field nor a fact about the report.
POLICY_REASON_CODES = ("approval-policy-changed",)

# The checks that need something the caller may not have supplied, and what
# each of them is the only thing that answers. A validation run names the ones
# it did *not* perform, on the artifact it returns, so `clean` from a structural
# read can never be mistaken for `clean` from a full one — the applier's whole
# trust rests on this verdict, and "I was not shown the report" and "the report
# agrees" must not print the same word.
CHECK_REPORT = "report"
CHECK_REPOSITORY = "repository"
UNCHECKED_MEANING = {
    CHECK_REPORT: (
        "no report was supplied, so the selection was not checked against the "
        "records it names: reconciliation groups, the skipped list, the move "
        "destinations, and the report's own lineage are unverified"
    ),
    CHECK_REPOSITORY: (
        "no repository was supplied, so nothing was checked against the world: "
        "base commit, rules, configuration, the allowed mutation scope, and "
        "every selected record's target text are unverified, and this verdict "
        "can never be stale"
    ),
}


@dataclass(frozen=True)
class Minter:
    """Who minted this approval set.

    `policy_digest` is the provenance of a `policy` mint: the digest of the
    standing declaration whose decisions produced the selection. It is `None`
    for a person, who is not a declaration and whose judgment nothing recomputes.
    Inside the approval digest like every other field, so re-branding a human
    mint means re-hashing the file — and then the reload below has something
    exact to disagree with.
    """

    kind: str
    id: str
    policy_digest: Optional[str] = None

    def to_dict(self):
        return {
            "kind": self.kind, "id": self.id,
            "policy_digest": self.policy_digest,
        }


@dataclass(frozen=True)
class ApprovedRecord:
    """One selected record, and every place its remedy writes.

    The target is carried, not just referenced, so the applier can check what
    it is about to edit against the approval set alone — and so a preimage
    check has something to re-derive without re-reading the report.

    `destination` is where a move puts what it takes out, or `None`. It is here
    rather than left in the report because it is the other half of the write
    set: with it, the allowed mutation scope is a *derivation* of the record
    list that any reader can recompute, and a scope naming one more document
    than the selection justifies is arithmetic, not a judgment call.

    `occurrences` is *where* those units were approved: ascending assertion-unit
    ordinals into the committed baseline's segmentation of `path`, one per
    approved unit. Units say what was approved and occurrences say which copy of
    it, which are different questions the moment a document says the same thing
    twice — and only the second one bounds an edit. Ordinals rather than line
    numbers, because a line number is a fact about a rendering and an ordinal is
    a fact about the document: both are read off the baseline the pinned base
    commit names, and the ordinal survives a re-wrap that moves every line.
    """

    digest: str
    record_id: str
    code: str
    path: str
    units: Tuple[str, ...]
    occurrences: Tuple[int, ...]
    destination: Optional[str] = None

    def targets(self):
        """Every path this record's remedy writes."""
        return (self.path,) if self.destination is None else (
            self.path, self.destination
        )

    def to_dict(self):
        return {
            "digest": self.digest,
            "id": self.record_id,
            "code": self.code,
            "path": self.path,
            "destination": self.destination,
            "units": list(self.units),
            "occurrences": list(self.occurrences),
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
    report_state: str
    lineage: Lineage
    reconciliation_digest: str
    records: Tuple[ApprovedRecord, ...]
    skipped: Tuple[SkippedRecord, ...]
    scope: MutationScope
    stale_reasons: Tuple[StaleReason, ...] = ()
    # Verdict-side, like `status`: what this particular validation run was in a
    # position to answer, never part of the artifact's identity.
    unchecked: Tuple[str, ...] = ()
    observed_report_state: Optional[str] = None

    @property
    def content(self):
        """What the approval set *says* — the part its digest is taken over.

        The status and the stale reasons are excluded, exactly as they are from
        a report's digest: they are a verdict a validator reached about the
        artifact, and an artifact must not change identity because the world
        moved under it. That is also why `digest` is derived rather than
        stored — `dataclasses.replace`-ing a verdict onto an approval set
        cannot silently re-key it, and there is no second place a digest could
        be computed from a different set of fields.
        """
        return {
            "artifact": ARTIFACT_KIND,
            "schema_version": SCHEMA_VERSION,
            "minter": self.minter.to_dict(),
            "report_digest": self.report_digest,
            # The report's own state at the moment of minting. In the content,
            # so a hand-edit is a digest mismatch: a `partial` report's absent
            # records are the unexamined ones, and reconciliation's guarantee is
            # only over the records that were present — so one of them could
            # have grouped exclusively with something approved here. The change
            # reviewer has to be able to see that from the artifact.
            "report_state": self.report_state,
            "lineage": self.lineage.to_dict(),
            "reconciliation_digest": self.reconciliation_digest,
            "records": [r.to_dict() for r in self.records],
            "skipped": [r.to_dict() for r in self.skipped],
            "scope": self.scope.to_dict(),
        }

    @property
    def digest(self):
        """The identity that travels in the change this authorizes."""
        return sha256_canonical(self.content)

    def to_dict(self):
        payload = dict(self.content)
        payload["status"] = self.status
        payload["digest"] = self.digest
        if self.stale_reasons:
            payload["stale_reasons"] = [r.to_dict() for r in self.stale_reasons]
        if self.unchecked:
            payload["unchecked"] = [
                {"check": name, "meaning": UNCHECKED_MEANING[name]}
                for name in self.unchecked
            ]
        if self.observed_report_state is not None:
            payload["observed_report_state"] = self.observed_report_state
        return payload


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


def _policy_eligibility_problems(minter, records):
    """Every selected record a policy minter may never approve.

    A pure function of the artifact's own fields — the minter's kind and each
    record's code — so unlike the reconciliation and preimage refusals above
    it needs no report and no repository, and runs identically at mint time
    and in validation's unconditional structural layer. Only a `policy`
    minter is restricted: a human approving a bloat record is exactly what
    bloat review is for.
    """
    if minter is None or minter.kind != MINTER_POLICY:
        return []
    return [
        Problem(
            code="approval-policy-ineligible-record",
            message=(
                f"a policy minter may never approve a {record.code} record — "
                f"bloat judgments are semantic review a standing policy cannot "
                f"perform; only a human approves value judgments"
            ),
            location=f"records[{i}]",
        )
        for i, record in enumerate(records)
        if record.code in POLICY_NEVER_ELIGIBLE_CODES
    ]


def _remediable_problems(records):
    """Every selected record whose finding code authorizes no operation.

    The applier's `RECORD_REMEDIES` is closed and fail-shut: it maps a finding
    code to the operations that code's approved remedy is made of, and a code
    nobody listed there authorizes nothing. Five anchor codes are deliberately
    absent — a missing, malformed, future-dated, unverifiable, or unresolvable
    anchor needs one *authored*, which is not a span edit to a passage anybody
    approved.

    Nothing filtered on that here, so such a record minted cleanly and then no
    plan could execute it: a plan omitting it is `plan-record-not-executed`,
    and a plan attaching an operation to it is
    `plan-operation-not-record-remedy` — each refusal pointing at what the
    other refuses. Asked at the mint, the dead end is legible before anyone
    authors a plan, and the operator re-selects instead of debugging a
    contradiction.

    The remedy table is imported at call time because `applier` imports this
    module; naming the remediable codes a second time here is exactly how the
    two would come apart.
    """
    from .applier import RECORD_REMEDIES

    return [
        Problem(
            code="approval-record-not-remediable",
            message=(
                f"record {record.record_id} is a {record.code} finding, and "
                f"{record.code} authorizes no remedy operation — the applier's "
                f"remedy table names, per finding code, the operations an "
                f"approval of it permits, and this code is deliberately absent "
                f"from it. Approving it would mint a mandate no edit plan can "
                f"execute; a finding like this is fixed by hand, not applied"
            ),
            location=f"records[{i}]",
        )
        for i, record in enumerate(records)
        if record.code not in RECORD_REMEDIES
    ]


def _destination(record):
    """Where a report record's remedy writes what it moves, or None.

    The lanes record a destination as the document plus what was checked about
    it; only the document is a write target. A record that moves nothing has
    none, which is most of them.
    """
    destination = record.extra.get(DESTINATION_FIELD)
    if isinstance(destination, dict):
        destination = destination.get("path")
    return destination if isinstance(destination, str) and destination else None


def _approved_units(code, units):
    """Canonical units, retaining whole-document duplicates for refusal."""
    values = units if code in WHOLE_DOCUMENT_RECORD_CODES else set(units)
    return tuple(sorted(values))


def derived_scope_paths(records):
    """The only allowed mutation scope a given selection justifies.

    A *derivation*, not a declaration, and public because both ends of the
    contract depend on it being one: minting builds the scope from here, and
    validation recomputes it and refuses an artifact whose scope says anything
    else. That is what makes "unselected findings cannot ride along" checkable
    on a file somebody may have hand-edited, rather than a property that only
    held at the moment of minting.

    A report's coverage claim is not consulted, deliberately. `whole-inventory`
    means every document is *accounted for*, which says nothing about what may
    be changed — so the strongest coverage claim a report can make authorizes
    exactly what the weakest one does.
    """
    return tuple(sorted({
        path for record in records for path in record.targets()
    }))


def _scope(records, repo_root, roots):
    """(MutationScope, problems, refused digests): the derivation, authorized."""
    problems, refused, authorized = [], set(), set()
    for record in records:
        for path in record.targets():
            if path in authorized:
                continue
            verdict = authorize_path(
                path, repo_root=repo_root, roots=roots,
                target_class=DOCUMENTATION,
            )
            if not verdict.authorized:
                problems.append(verdict.problem)
                refused.add(record.digest)
                continue
            authorized.add(verdict.path)
    scope = MutationScope(
        roots=tuple(roots), paths=tuple(sorted(authorized)),
    )
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
        whole_document_difference = whole_document_unit_difference(
            record.code, record.units, present
        )
        if (whole_document_difference is not None
                and not whole_document_difference.exact):
            problems.append(Problem(
                code="approval-whole-document-units-incomplete",
                message=(
                    f"record {record.record_id} would retire all of {path}, "
                    f"but its approved units are not the complete current "
                    f"deterministic unit set (missing "
                    f"{len(whole_document_difference.missing)}, extra "
                    f"{len(whole_document_difference.extra)}, duplicate "
                    f"{len(whole_document_difference.duplicates)}) — approve "
                    f"a fresh whole-document finding rather than amplifying "
                    f"passage authority into document deletion"
                ),
                location=path,
            ))
            continue
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


def baseline_units(repo_root, path):
    """(the committed baseline's assertion units for `path`, None), or
    (None, why the baseline cannot answer).

    HEAD, deliberately, and not through the inventory: an occurrence is a fact
    about the document the audit read, and the working tree is what an attacker
    — or an ordinary half-finished edit — can move underneath a live approval.
    The base commit is a compared lineage field, so a baseline that has moved is
    already `approval-base-commit-changed` before any occurrence is read back;
    within one approval's life these ordinals do not change.
    """
    data, problem = repository_mod.head_bytes(repo_root, path)
    if problem is not None:
        return None, problem.message
    if data is None:
        return None, f"{path} is not in the committed baseline"
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError as exc:
        return None, (
            f"{path} is not valid UTF-8 at HEAD ({exc.reason} at byte "
            f"{exc.start})"
        )
    return segment_text(text, path=path).units, None


def _derive_occurrences(units, code, approved):
    """(the baseline ordinals `approved` occupies, None), or (None, (code, why)).

    For a passage record the derivation is by count, which is what makes "which
    occurrence" a question with one answer or none. A record approving a unit
    once against a baseline holding it twice is refused rather than resolved:
    both copies are the same identity, nothing in the artifact says which one a
    reviewer read, and picking either — or spanning both — would be the engine
    deciding what was approved.

    A whole-document record is the one shape where a repeat is not a question.
    Its units must equal the document's complete identity set (that check has
    its own owner, `whole_document_unit_difference`), so *every* occurrence of
    every one of them is inside what was approved and there is nothing to
    choose between. Findings list each identity once — `finding.py` normalizes
    units to a set — so this is exactly the case the count rule would refuse
    for saying one thing twice.
    """
    ordinals = {}
    for unit in units:
        ordinals.setdefault(unit.digest, []).append(unit.ordinal)
    whole_document = code in WHOLE_DOCUMENT_RECORD_CODES
    chosen = []
    for digest in sorted(set(approved)):
        wanted = approved.count(digest)
        found = ordinals.get(digest, [])
        if len(found) < wanted:
            return None, ("approval-occurrence-unbindable", (
                f"assertion unit {digest} is approved {wanted} time(s) and the "
                f"committed baseline holds it {len(found)} — the approval "
                f"would name text the audited document does not contain"
            ))
        if len(found) > wanted and not whole_document:
            return None, ("approval-occurrence-ambiguous", (
                f"assertion unit {digest} occurs {len(found)} times in the "
                f"committed baseline and is approved {wanted} time(s), so "
                f"which occurrence was reviewed is not stated. A unit digest "
                f"is its content, and identical text in two places is one "
                f"identity in two passages — approving it here would bind "
                f"authority to whichever the applier happened to find, or to "
                f"everything between them"
            ))
        chosen.extend(found)
    return tuple(sorted(chosen)), None


def _bind_occurrences(records, repo_root):
    """(records carrying their approved occurrences, problems).

    Minting's half of the occurrence contract: the ordinals are derived here,
    once, from the baseline the report was produced against, and everything
    downstream re-derives them rather than deciding afresh what a unit digest
    reaches.
    """
    bound, problems = [], []
    for i, record in enumerate(records):
        units, why = baseline_units(repo_root, record.path)
        if units is None:
            problems.append(Problem(
                code="approval-occurrence-unbindable",
                message=(
                    f"where record {record.record_id}'s approved units are in "
                    f"the committed baseline cannot be established: {why} — an "
                    f"approval binds to the passage it was read in, so a "
                    f"baseline that cannot answer is a refusal rather than an "
                    f"approval of wherever the text turns up"
                ),
                location=f"records[{i}]",
            ))
            continue
        occurrences, failure = _derive_occurrences(
            units, record.code, record.units
        )
        if occurrences is None:
            code, reason = failure
            problems.append(Problem(
                code=code,
                message=(
                    f"record {record.record_id} cannot be bound to a unique "
                    f"passage of {record.path}: {reason}. Re-run the audit "
                    f"against a document that says it once, or approve a "
                    f"record whose units pin the passage exactly"
                ),
                location=f"records[{i}]",
            ))
            continue
        bound.append(replace(record, occurrences=occurrences))
    return tuple(bound), problems


def _occurrence_problems(records, repo_root):
    """Every selected record whose occurrences the committed baseline denies.

    Re-derivation, not belief, for the same reason the allowed mutation scope is
    recomputed: an approval set is a file, and `occurrences` is the field that
    decides how far a positioned edit may reach. A widened one would hand the
    applier a passage nobody read.
    """
    problems = []
    for record in records:
        units, why = baseline_units(repo_root, record.path)
        if units is None:
            problems.append(Problem(
                code="approval-occurrence-unbindable",
                message=(
                    f"record {record.record_id} names occurrences in "
                    f"{record.path}, and the committed baseline cannot say what "
                    f"is there: {why} — an unanswered question about the "
                    f"approved passage is a refusal"
                ),
                location=record.path,
            ))
            continue
        if any(o >= len(units) for o in record.occurrences):
            problems.append(Problem(
                code="approval-occurrence-not-derived",
                message=(
                    f"record {record.record_id} names assertion unit "
                    f"{max(record.occurrences)} of {record.path}, and the "
                    f"committed baseline segments it into {len(units)} unit(s) "
                    f"— an occurrence past the end of the document is not one a "
                    f"mint could have derived"
                ),
                location=record.path,
            ))
            continue
        found = sorted(units[o].digest for o in record.occurrences)
        # A whole-document record approves every identity in the document, so
        # each may legitimately be named at more than one ordinal and the
        # question is only whether the same identities are there. A passage
        # record approves each of its units once, so the comparison is exact:
        # a second ordinal holding an already-approved digest is the twin
        # nobody reviewed.
        expected = sorted(record.units)
        if (sorted(set(found)) != sorted(set(expected))
                if record.code in WHOLE_DOCUMENT_RECORD_CODES
                else found != expected):
            problems.append(Problem(
                code="approval-occurrence-not-derived",
                message=(
                    f"record {record.record_id}'s occurrences are not where its "
                    f"approved units are in the committed baseline of "
                    f"{record.path} — the ordinals name other text, so the "
                    f"passage this authorizes is not the passage the record "
                    f"describes"
                ),
                location=record.path,
            ))
    return problems


def occurrence_passages(repo_root, record):
    """(the passages a record's approved occurrences are, None), or (None, why).

    Each passage is a `(first line, last line)` pair over the committed
    baseline, and there is one per *run* of consecutive occurrences: units
    approved back to back are one passage, so the blank lines and list markers
    between them stay editable, and an unapproved unit between two approved ones
    ends the passage rather than being swallowed by it. That is the whole
    difference from the hull this replaced — a hull spanned from the first
    approved unit to the last and so authorized every intervening word,
    including the material separating a repeated sentence from its twin.

    The applier is the caller: bounding an edit is its job, and deciding what
    the approved passage *is* belongs here, with the field that records it.
    """
    units, why = baseline_units(repo_root, record.path)
    if units is None:
        return None, why
    if not record.occurrences or any(
        o >= len(units) for o in record.occurrences
    ):
        return None, (
            f"its approved occurrences are not units of {record.path} at HEAD"
        )
    approved = set(record.units)
    if any(units[o].digest not in approved for o in record.occurrences):
        return None, (
            f"its approved occurrences no longer hold its approved units in "
            f"{record.path} at HEAD"
        )
    passages, run = [], []
    for ordinal in record.occurrences:
        if run and ordinal != run[-1] + 1:
            passages.append((units[run[0]].line, units[run[-1]].end_line))
            run = []
        run.append(ordinal)
    passages.append((units[run[0]].line, units[run[-1]].end_line))
    return tuple(passages), None


def mint_approval_set(report, selected, *, repo_root, minter,
                      registry_path=DEFAULT_REGISTRY_PATH):
    """Mint an approval set for a person's selection of record digests.

    Returns an `ApprovalSet`, or `Invalid` naming every problem. This is the
    generic door — the caller names the records — so it is human-only: a
    caller-chosen selection credited to a standing policy would be that
    policy's authority spent on records the policy never decided about, which
    is the whole of what the eligibility table exists to prevent. A `policy`
    minter here is `approval-policy-minter-not-generic`, and
    `policy.mint_policy_approval_set` is the door that brands one, from a
    selection it derives itself.
    """
    if not isinstance(minter, Minter):
        raise TypeError(
            f"a minter is a Minter, not {type(minter).__name__} — lineage "
            f"records who approved, and an unnamed approver is not approval"
        )
    if minter.kind == MINTER_POLICY:
        return Invalid((Problem(
            code="approval-policy-minter-not-generic",
            message=(
                f"minting a {MINTER_POLICY!r}-branded approval set from a "
                f"caller-named selection is refused: a policy brand says a "
                f"standing declaration chose these records, and here a caller "
                f"did. Mint through the policy, which derives its own selection "
                f"and records the declaration it derived it from"
            ),
            location="minter",
        ),))
    return _mint_approval_set(
        report, selected, repo_root=repo_root, minter=minter,
        registry_path=registry_path,
    )


def _mint_approval_set(report, selected, *, repo_root, minter,
                       registry_path=DEFAULT_REGISTRY_PATH):
    """Construct an approval set. The one producer, whoever the minter is.

    `policy.mint_policy_approval_set` is the only other caller, and it reaches
    here rather than assembling an `ApprovalSet` of its own so that a policy
    mint and a human mint share one set of reconciliation, path-authorization,
    preimage, report-lineage, scope-derivation, and digest mechanics. A second
    construction path would be a second place each of those could be forgotten.

    A non-`Report` or a non-`Minter` is a `TypeError`: minting authority from
    something that has not been validated as a report, or crediting it to
    something that is not a minter, is a programming error in the caller, not
    malformed data.

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
    records = tuple(ApprovedRecord(
        digest=record.digest,
        record_id=record.id,
        code=record.extra["code"],
        path=record.extra["path"],
        units=_approved_units(record.extra["code"], record.extra["units"]),
        # Bound below, once the targets have authorized: reading the committed
        # baseline for a path the applier may not write would answer a question
        # about a document this selection has already been refused for.
        occurrences=(),
        destination=_destination(record),
    ) for record in chosen)

    problems = _remediable_problems(records)
    if problems:
        return Invalid(tuple(problems))

    problems = _policy_eligibility_problems(minter, records)
    if problems:
        return Invalid(tuple(problems))

    scope, problems, refused = _scope(records, repo_root, registry.roots)
    # Only records whose targets authorized: a path the applier may not write
    # has already been refused, and asking whether its text still matches would
    # answer the same refusal twice in two vocabularies.
    problems += _preimage_problems(
        [r for r in records if r.digest not in refused], repo_root, registry_path
    )
    if problems:
        return Invalid(tuple(problems))

    records, problems = _bind_occurrences(records, repo_root)
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
        report_state=report.status,
        lineage=report.lineage,
        reconciliation_digest=reconciliation.digest,
        records=records,
        skipped=skipped,
        scope=scope,
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
    provenance = raw["policy_digest"]
    if raw["kind"] == MINTER_HUMAN:
        if provenance is not None:
            bad("approval-invalid-minter",
                f"a {MINTER_HUMAN!r} minter carries no policy provenance, and "
                f"this names {provenance!r}: a person's judgment is not "
                f"delegated by a declaration and nothing recomputes it, so "
                f"provenance here would be a revalidation that never runs",
                "minter")
            return None
    elif not (isinstance(provenance, str) and DIGEST.match(provenance)):
        bad("approval-policy-provenance-missing",
            f"a {MINTER_POLICY!r}-branded approval set carries policy_digest — "
            f"the digest of the standing declaration that selected it — and "
            f"this carries {provenance!r}. The brand is what tells a change "
            f"reviewer no person read these records, so a brand nothing can be "
            f"revalidated against was never a policy mint",
            "minter")
        return None
    return Minter(
        kind=raw["kind"], id=raw["id"], policy_digest=provenance,
    )


def _path_problem(value):
    """Why `value` is not a canonical repository-relative document, or None.

    The structural layer's own path check, and it needs no repository: an
    approval set's record paths and scope paths are write targets, so `..`, a
    leading `/`, a backslash, whitespace, and a non-NFC spelling are forgeries
    rather than a repository that moved — and a forgery is `invalid`, not
    `stale`. One owner decides (`paths.repository_relative_problem`), so an
    edit target cannot mean one thing here and another to the applier.

    On top of that owner's spelling rules, one location — the git directory —
    which `paths.write_target_problem` owns, shared with the edit plan's
    operation targets so both artifacts refuse the same spellings.
    """
    return write_target_problem(value)


def _unsorted(digests, field, bad):
    """True — and refused — if `field`'s digests are not in ascending order.

    Both arrays are inside the approval digest and are read in file order, so
    an order that may vary is one selection with more than one identity, and
    the digest is what a trailer pins. Sorted is the order minting produces, so
    it is the only one that reads back: canonicality by refusal, never by
    silent reordering, which would make the file disagree with its own digest.
    """
    if list(digests) == sorted(digests):
        return False
    bad(f"approval-{field}-not-sorted",
        f"{field} must be listed in ascending digest order — the approval "
        f"digest is taken over the list as written, so an approval set that "
        f"may be reordered has more than one digest for one selection",
        field)
    return True


def _approved_records(raw, bad, lineage):
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
        canonical = _approved_units(entry["code"], units)
        occurrences = entry["occurrences"]
        if not (isinstance(occurrences, list) and occurrences and all(
            isinstance(o, int) and not isinstance(o, bool) and o >= 0
            for o in occurrences
        ) and list(occurrences) == sorted(set(occurrences))):
            bad("approval-invalid-record",
                f"records[{i}].occurrences must be a non-empty ascending list "
                f"of distinct assertion-unit ordinals — they are which "
                f"occurrence of each approved unit was read, and a repeated or "
                f"unordered one gives a passage more than one reading",
                where)
            ok = False
            continue
        # A passage record approves each of its units in one place, so the two
        # counts are the same number; a whole-document record approves the
        # document entire, where an identity it lists once may sit in several
        # places, so it owes an occurrence for each unit and may name more.
        # Either way a count *below* the units is a record that cannot say
        # where part of what it approves was read.
        whole_document = entry["code"] in WHOLE_DOCUMENT_RECORD_CODES
        if (len(occurrences) < len(canonical) if whole_document
                else len(occurrences) != len(canonical)):
            bad("approval-occurrence-not-derived",
                f"records[{i}] approves {len(canonical)} assertion unit(s) and "
                f"names {len(occurrences)} occurrence(s) — every approved unit "
                f"is approved somewhere exactly, so a count that disagrees "
                f"cannot identify the approved passage without guessing",
                where)
            ok = False
            continue
        destination = entry["destination"]
        if destination is not None and not _printable(destination):
            bad("approval-invalid-record",
                f"records[{i}].destination must be the document a move writes "
                f"to, or null — it is part of the write set, so an unreadable "
                f"one is an unreadable allowed scope",
                where)
            ok = False
            continue
        misspelled = False
        for name in ("path", "destination"):
            reason = (
                None if entry[name] is None else _path_problem(entry[name])
            )
            if reason is not None:
                bad("approval-invalid-record",
                    f"records[{i}].{name} {entry[name]!r} {reason} — every "
                    f"path in an approval set is a document the applier may "
                    f"write, and a spelling that leaves the repository is a "
                    f"forged scope, not a repository that moved",
                    where)
                misspelled = True
        if misspelled:
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
        if lineage is not None:
            # The check that makes the approved *target* mean something. Until
            # here, `code`, `path`, and `units` were shape-checked and nothing
            # more — so keeping a legitimately approved digest while rewriting
            # the document and units beneath it, and repairing `scope.paths` to
            # match, produced an artifact whose every derivation faithfully
            # computed the wrong document. A finding's digest *is* its lineage,
            # code, document, and units, so re-deriving it here binds the
            # selection to what it says it selected — the same check
            # `reconcile.py` runs over a report's records, and like that one it
            # needs no report and no repository.
            expected = finding_digest(
                lineage, entry["code"], entry["path"], units
            )
            if expected != entry["digest"]:
                bad("approval-record-digest-mismatch",
                    f"records[{i}] declares digest {entry['digest']} but its "
                    f"code, document, and units under this approval set's "
                    f"lineage digest to {expected} — the digest is what was "
                    f"approved, so a record whose target does not re-derive to "
                    f"it would point the applier at a document nobody selected",
                    where)
                ok = False
                continue
        records.append(ApprovedRecord(
            digest=entry["digest"], record_id=entry["id"], code=entry["code"],
            path=entry["path"], units=canonical,
            occurrences=tuple(occurrences), destination=destination,
        ))
    if ok and _unsorted([r.digest for r in records], "records", bad):
        ok = False
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
    if ok and _unsorted([e.digest for e in entries], "skipped", bad):
        ok = False
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
        else:
            for value in values:
                problem = _path_problem(value)
                if problem is not None:
                    bad("approval-invalid-scope",
                        f"scope.{name} entry {value!r} {problem} — the "
                        f"allowed mutation scope is the outer bound on what "
                        f"the applier writes, so a path that is not inside the "
                        f"repository is forged authority and no repository "
                        f"state could make it true",
                        f"scope.{name}")
                    ok = False
    if not ok:
        return None
    return MutationScope(roots=tuple(raw["roots"]), paths=tuple(raw["paths"]))


def _carried_stale_reasons(raw, bad, status):
    """The reasons a carried verdict names, plus the approval set's own rule."""
    reasons = parse_stale_reasons(raw, bad, "approval-invalid-stale-reason")
    if reasons is None:
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
    return [
        StaleReason(
            code=code,
            message=(
                f"the approval set was minted against {label} {reported}, and "
                f"the repository's is now {actual} — the approval was for a "
                f"state that no longer exists, so re-run the audit and approve "
                f"again"
            ),
            reported=reported,
            current=actual,
        )
        for code, label, reported, actual
        in compare_lineage(lineage, current, COMPARABLE)
    ]


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


def _preimage_reasons(problems):
    """Preimage drift, as stale reasons rather than problems.

    The problems come from the same check minting runs, read the other way
    round. At mint time a target that has already moved means the selection
    was made against text that is gone, and nothing should be minted. Here the
    artifact exists and the question is whether it still stands — which is
    `stale`: re-run the audit and approve again rather than fixing the file.
    """
    reasons = []
    for problem in problems:
        reasons.append(StaleReason(
            code=problem.code,
            message=problem.message,
            reported=problem.location,
            current="the document has changed since the approval was minted",
        ))
    return reasons


def _policy_provenance(minter, records, repo_root, policy_path, report):
    """(stale reasons, problems) for a `policy` brand against its declaration.

    Two kinds of answer again, and the split is the same one `_report_reasons`
    makes. A consumer editing their standing declaration is the world moving:
    the delegation this set was minted under no longer exists, which is
    `stale` — re-run the lane against the policy in force. A selection that is
    not the one the declaration derives is a *forgery*: eligibility is a pure
    function of the policy and the report, and this set pins the digest of
    both, so no repository state could have made an honest policy mint choose
    a different set of records.

    That is also why a changed declaration stands the recomputation down. Under
    some other policy the derived set differs as a consequence, so running the
    comparison anyway would accuse every honest re-run whose consumer narrowed
    a class of forging its own approval set.

    The import is deferred because `policy.py` imports this module: the policy
    is a narrower gate in front of this door, and this door revalidates against
    it, so the dependency has to run one way at import time and the other at
    call time.
    """
    if minter.kind != MINTER_POLICY:
        return [], []

    from .policy import (
        DEFAULT_POLICY_PATH,
        load_auto_apply_policy,
        policy_eligibility,
    )

    policy = load_auto_apply_policy(
        repo_root, DEFAULT_POLICY_PATH if policy_path is None else policy_path
    )
    if isinstance(policy, Invalid):
        return [StaleReason(
            code="approval-policy-changed",
            message=(
                f"the standing auto-apply policy this set was minted under "
                f"cannot be read from the repository, so whether it still "
                f"admits this selection is unknown: "
                f"{policy.problems[0].message}"
            ),
            reported=minter.policy_digest,
            current=policy.problems[0].code,
        )], []
    if policy.digest != minter.policy_digest:
        return [StaleReason(
            code="approval-policy-changed",
            message=(
                f"the set was minted under standing policy {minter.id!r} "
                f"declaring {minter.policy_digest}, and the repository now "
                f"declares {policy.digest} — a policy brand is authority a "
                f"declaration delegated, so a declaration that has moved is a "
                f"delegation nobody made"
            ),
            reported=minter.policy_digest,
            current=policy.digest,
        )], []

    if report is None:
        return [], []
    eligible = set(policy_eligibility(policy, report).eligible_digests)
    selected = {record.digest for record in records}
    if selected == eligible:
        return [], []
    return [], [Problem(
        code="approval-policy-selection-not-derived",
        message=(
            f"policy {policy.id!r} does not derive this selection from the "
            f"report it names: the set adds {sorted(selected - eligible)} and "
            f"omits {sorted(eligible - selected)}. A policy mint has no "
            f"parameter through which a record is named — the selection is "
            f"every record the declaration admits and nothing else — so a set "
            f"branded with a policy that would not have chosen it was produced "
            f"by something that is not that policy"
        ),
        location="records",
    )]


def validate_approval_set(payload, *, report=None, repo_root=None,
                          registry_path=DEFAULT_REGISTRY_PATH,
                          audit_config_digest=None, expected_digest=None,
                          policy_path=None):
    """Validate an approval set. Returns an `ApprovalSet` or `Invalid`.

    Structural validation is exhaustive and runs alone: an artifact that cannot
    be read has nothing to check against a report or a repository, so `invalid`
    always beats `stale`.

    Pass `report` to check the selection against the report it names, and
    `repo_root` to check it against the world. Each check is optional and each
    is honest about not having run — in both directions. Without a repository
    the verdict can never be `stale`, because this function does not guess at a
    state it was not shown; and the returned artifact's `unchecked` names every
    check that was skipped, so a caller cannot read `clean` from a structural
    pass as `clean` from a full one. An applier must supply both.

    Pass `expected_digest` — the `Doc-Lifecycle-Approval` trailer, which is the
    only part of an approval set that survives in the repository — to bind this
    file to the change that claims it. A file the trailer does not name is
    `approval-digest-unexpected`, whatever it validates to on its own.

    `policy_path` names where the repository's standing auto-apply policy
    lives, for the provenance check a `policy`-branded set gets; it defaults to
    `policy.DEFAULT_POLICY_PATH` and is read only when `repo_root` is supplied.
    A human-minted set never reads it.
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

    declared_version = payload.get("schema_version")
    if (isinstance(declared_version, int)
            and not isinstance(declared_version, bool)
            and declared_version in SUPERSEDED_SCHEMA_VERSIONS):
        # Alone, and before every other structural check: an artifact written
        # under older rules is refused rather than read under these ones, since
        # what each older version was missing is authority the current applier
        # rests on and no field can be recovered after the fact. Mint again from
        # its report, which costs a re-mint and never a silent reinterpretation.
        code, missing = SUPERSEDED_SCHEMA_VERSIONS[declared_version]
        return Invalid((Problem(
            code=code,
            message=(
                f"this approval set declares schema_version "
                f"{declared_version}, which this engine reads no longer: "
                f"{missing}. It is refused rather than read as version "
                f"{SCHEMA_VERSION} — mint again from its report"
            ),
            location="schema_version",
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
        and version == SCHEMA_VERSION
    ):
        bad("approval-schema-version",
            f"approval-set schema_version {version!r} is not supported; this "
            f"engine reads integer version {SCHEMA_VERSION}",
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

    report_state = payload.get("report_state")
    if "report_state" in payload and report_state not in APPROVABLE_STATES:
        # The minter's report-state refusal, re-run on the artifact. Minting
        # would not produce an approval set from a report in any other state,
        # and this is the read the applier actually reaches.
        bad("approval-report-not-approvable",
            f"report_state {report_state!r} is not a state a report can "
            f"authorize from — an approval set is minted from a report whose "
            f"state is one of {list(APPROVABLE_STATES)}",
            "report_state")

    minter = _minter(payload["minter"], bad) if "minter" in payload else None
    lineage = None
    if "lineage" in payload:
        lineage, lineage_problems = parse_lineage(payload["lineage"])
        problems.extend(lineage_problems)
    records = (
        _approved_records(payload["records"], bad, lineage)
        if "records" in payload else None
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
        # The scope is a derivation of the selection, so it is recomputed here
        # rather than believed. An artifact is a file: without this, a
        # hand-widened `scope.paths` would make an unselected finding's
        # document writable, which is the exact thing minting refused to do.
        derived = derived_scope_paths(records)
        if tuple(scope.paths) != derived:
            missing = sorted(set(derived) - set(scope.paths))
            extra = sorted(set(scope.paths) - set(derived))
            bad("approval-scope-not-derived",
                f"the allowed mutation scope is not what this selection "
                f"justifies: it omits {missing} and adds {extra}. The scope is "
                f"exactly the documents the selected records write — their own "
                f"and any move destination — so anything else is authority "
                f"nobody approved",
                "scope.paths")

    if minter is not None and records is not None:
        # The minter-restriction door, re-run on the artifact: the same rule
        # `mint_approval_set` applies, so a hand-edited minter field cannot
        # brand a bloat selection `policy` after the fact.
        problems.extend(_policy_eligibility_problems(minter, records))

    if problems:
        return Invalid(tuple(problems))

    carried = tuple(carried)
    approval = ApprovalSet(
        status=STATE_CLEAN,
        minter=minter,
        report_digest=payload["report_digest"],
        report_state=report_state,
        lineage=lineage,
        reconciliation_digest=payload["reconciliation_digest"],
        records=tuple(records),
        skipped=tuple(skipped),
        scope=scope,
    )
    records = approval.records
    declared = payload["digest"]
    if declared != approval.digest:
        return Invalid((Problem(
            code="approval-digest-mismatch",
            message=(
                f"the approval set declares digest {declared} but its content "
                f"digests to {approval.digest} — it has been altered since it "
                f"was minted, and its digest is what travels in the change it "
                f"authorizes"
            ),
            location="digest",
        ),))
    if expected_digest is not None and expected_digest != approval.digest:
        return Invalid((Problem(
            code="approval-digest-unexpected",
            message=(
                f"this change was authorized by approval set {expected_digest} "
                f"and the file supplied is {approval.digest} — an approval set "
                f"is untracked, so the trailer is the only record of which one "
                f"authorized the change, and a different digest is a different "
                f"approval however well-formed it is"
            ),
            location="digest",
        ),))

    reasons = []
    # Whether the report supplied is the one this set names. The policy
    # recomputation below is a fact about *that* report's records, so like
    # every other check in `_report_reasons` it has nothing to run against
    # when some other report was handed over.
    report_bound = False
    if report is not None:
        reasons, forged = _report_reasons(
            payload, records, skipped, report, lineage
        )
        if forged:
            # Not `stale`: nothing moved in the world. These are selections no
            # minter would have produced, so the artifact was never authority —
            # and `invalid` beats `stale` for the same reason it does above.
            return Invalid(tuple(forged))
        report_bound = payload["report_digest"] == report.digest
    if repo_root is not None:
        current, current_problems = current_lineage(
            repo_root, registry_path, audit_config_digest
        )
        if current_problems:
            return Invalid(tuple(current_problems))
        reasons += _lineage_reasons(lineage, current)
        reasons += _scope_reasons(scope, repo_root, registry_path)
        policy_reasons, forged_policy_brand = _policy_provenance(
            minter, records, repo_root, policy_path,
            report if report_bound else None,
        )
        if forged_policy_brand:
            return Invalid(tuple(forged_policy_brand))
        reasons += policy_reasons
        if lineage.base_commit == current.get("base_commit"):
            # Occurrences are ordinals into the baseline this set names, so they
            # are re-derivable exactly when that baseline is the one in front of
            # us — and then a disagreement cannot be the world moving, because a
            # commit pins its bytes. It is a forged passage bound, `invalid` for
            # the same reason a forged scope is. Against a *different* base
            # commit the check stands down rather than running: the move is
            # already `approval-base-commit-changed`, every occurrence
            # disagreement under it is a consequence of that move, and naming
            # them too would accuse an honest re-run of forgery — the same
            # standing-down `_report_reasons` does when handed another report.
            occurrence_problems = _occurrence_problems(records, repo_root)
            if occurrence_problems:
                return Invalid(tuple(occurrence_problems))
        preimage_problems = _preimage_problems(
            records, repo_root, registry_path
        )
        if lineage.inventory_digest == current.get("inventory_digest"):
            forged_whole_document_authority = tuple(
                problem for problem in preimage_problems
                if problem.code == "approval-whole-document-units-incomplete"
            )
            if forged_whole_document_authority:
                # With the same inventory the report was produced against,
                # no document moved after minting. A partial whole-document
                # record was never authority, so this is invalid rather than
                # stale. When the inventory differs, the same exact-set
                # mismatch remains the ordinary stale preimage lane below.
                return Invalid(forged_whole_document_authority)
        reasons += _preimage_reasons(preimage_problems)

    # A carried reason this run did not re-check still stands: clearing a
    # verdict must be at least as thorough as setting it.
    rechecked = {reason.code for reason in reasons}
    if repo_root is not None:
        rechecked |= {code for field, code, _ in COMPARABLE if field in current}
        rechecked |= set(REPOSITORY_REASON_CODES) | set(POLICY_REASON_CODES)
    if report is not None:
        rechecked |= set(REPORT_REASON_CODES)
    reasons += [r for r in carried if r.code not in rechecked]

    # The verdict is put onto the artifact, never into it: `digest` is derived
    # from the content, so replacing the status and the reasons cannot change
    # what this approval set is. `unchecked` rides along for the same reason and
    # under the same rule — it is what this run was shown, not what the approval
    # says.
    return replace(
        approval,
        status=STATE_STALE if reasons else STATE_CLEAN,
        stale_reasons=tuple(reasons),
        unchecked=tuple(
            [CHECK_REPORT] if report is None else []
        ) + tuple(
            [CHECK_REPOSITORY] if repo_root is None else []
        ),
        # The report's state *now*, alongside the state it had when this was
        # minted. Reported rather than judged: a report goes stale the moment
        # any document changes, including by the applier's own writes, so
        # turning that into a verdict here would make the second subset of one
        # report unapplyable — the exact case partial approval exists for (see
        # the module docstring). What the change reviewer needs is to see it.
        observed_report_state=None if report is None else report.status,
    )


def _report_reasons(payload, records, skipped, report, approval_lineage):
    """(stale reasons, problems) for this approval set against its report.

    Two kinds of answer, because two different things can be wrong. A *stale
    reason* means the report moved out from under a selection that was
    legitimate when it was made. A *problem* means the selection was never one
    a minter would have produced — it takes one leg of a contradictory pair,
    half of a group that is one edit or none, or hides a record the report
    carries. An approval set is an untracked file, so the minter's refusals
    have to be re-run here: this is the check the applier actually reaches.

    Every problem is a fact about the report the artifact *names*: whether a
    selection hides a record, splits a group, or invents a destination can
    only be read off that report's records. So a supplied report with a
    different digest gets the one answer it can prove — the root cause, as a
    stale reason — and every other check stands down: run against the wrong
    report they would accuse every honest re-run of forgery, turning the
    `stale → refresh and retry` lane into a refusal that names an approver
    who hid nothing. Standing down is safe because `stale` authorizes nothing
    and cannot heal — no report digests to a corrupted claim, so a forger who
    touches `report_digest` buys a verdict that only a fresh mint replaces.
    Against the named report nothing returns early: each check records what
    it finds and the run continues, so neither of the other two compared
    fields — `lineage` and `reconciliation_digest` — can relabel the
    forgeries below it as `stale`, and a check only stands down when it has
    nothing to run against.
    """
    reasons = []
    problems = []
    carried = {record.digest for record in report.records}
    selected = {record.digest for record in records}

    if payload["report_digest"] != report.digest:
        # The root cause, and the only answer worth reporting when it fires:
        # against some other report the lineage, the record lookups and the
        # grouping all differ *as a consequence*, so naming them too would
        # bury the one fact a reader can act on.
        reasons.append(StaleReason(
            code="approval-report-changed",
            message=(
                f"the approval set was minted from report "
                f"{payload['report_digest']}, and the report supplied digests "
                f"to {report.digest} — a selection is only meaningful against "
                f"the records it was made from"
            ),
            reported=payload["report_digest"],
            current=report.digest,
        ))
        return reasons, problems

    if approval_lineage != report.lineage:
        # The report digest binds the report's *records*; the lineage
        # travels beside it, and two of its fields — the audit mode and the
        # evidence boundary — describe how the run was conducted rather
        # than anything the world can be re-read for. Nothing else could
        # ever catch a divergence there, and "binds the report's lineage
        # verbatim" has to be true of the file, not just of what minting
        # wrote. Not `stale`: minting copies the named report's lineage
        # verbatim, so a copy that differs is not the world moving — it
        # describes a run that did not happen.
        problems.append(Problem(
            code="approval-lineage-not-reported",
            message=(
                "the approval set carries a lineage the report it names "
                "does not — an approval set binds one report's lineage "
                "verbatim, so a copy that differs describes a run that did "
                "not happen"
            ),
            location="lineage",
        ))

    missing = sorted(r.digest for r in records if r.digest not in carried)
    if missing:
        # Not `stale`: the report digest just matched, and a report digest
        # pins its record set, so the world cannot have moved a record out of
        # it — no mint from this report could have produced the selection.
        problems.append(Problem(
            code="approval-record-not-reported",
            message=(
                f"the approval set selects {len(missing)} record(s) the "
                f"report it names does not carry, starting with "
                f"{missing[0]} — a report digest pins its record set, so no "
                f"mint from this report could have produced the selection, "
                f"and there is nothing for the applier to look up"
            ),
            location="records",
        ))

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
        reconciliation = None
    elif reconciliation.digest != payload["reconciliation_digest"]:
        reasons.append(StaleReason(
            code="approval-reconciliation-changed",
            message=(
                "the report's records no longer group the way they did "
                "when this selection was checked against them, so the "
                "selection is not known to respect the groups"
            ),
            reported=payload["reconciliation_digest"],
            current=reconciliation.digest,
        ))

    # The group discipline is checked against the grouping that holds *now*.
    # Only an unreconcilable report leaves nothing to check it against — a
    # reconciliation whose digest the artifact misstates is still the truth
    # about how these records group, and a selection that takes one leg of a
    # contradictory pair is a forgery whichever digest the file claims.
    if reconciliation is not None:
        problems += _group_problems(selected, reconciliation)

    # A record's code, document, and units re-derive to its digest without a
    # report — but `destination` does not: it is not in the finding digest,
    # because where a move puts content is the lane's proposal and not the
    # finding's identity. So it is the one part of the write set that only the
    # report can confirm, and inventing one adds an arbitrary writable document
    # that every other derivation would faithfully accept. A record the report
    # does not carry has no reported destination to compare against — that is
    # `approval-record-not-reported` above, not a second finding here.
    by_digest = {record.digest: record for record in report.records}
    for record in records:
        if record.digest not in by_digest:
            continue
        reported = _destination(by_digest[record.digest])
        if record.destination != reported:
            problems.append(Problem(
                code="approval-destination-not-reported",
                message=(
                    f"record {record.record_id} says its remedy writes to "
                    f"{record.destination!r}, and the report says "
                    f"{reported!r} — a destination is inside the allowed "
                    f"mutation scope, so one the report never proposed is a "
                    f"document nobody approved and nobody audited"
                ),
                location=record.record_id,
            ))

    # The skipped list is a derivation too — everything the report carries that
    # this approval set did not take. A shortened one hides what the approver
    # declined, which is the half of partial approval that makes it auditable.
    expected = sorted(carried - selected)
    if sorted(record.digest for record in skipped) != expected:
        problems.append(Problem(
            code="approval-skipped-not-derived",
            message=(
                f"the approval set names {len(skipped)} skipped record(s), and "
                f"the report it binds to leaves {len(expected)} unselected — "
                f"the skipped list is every record not taken, and a short one "
                f"hides what the approver declined"
            ),
            location="skipped",
        ))
    return reasons, problems


def load_approval_set(path, *, report=None, repo_root=None,
                      registry_path=DEFAULT_REGISTRY_PATH,
                      audit_config_digest=None, expected_digest=None,
                      policy_path=None):
    """Read an approval-set file and validate it. `ApprovalSet` or `Invalid`."""
    payload, problem = load_strict_json(
        path,
        unreadable_code="approval-unreadable",
        unparseable_code="approval-unparseable",
        nesting_code="approval-nesting-too-deep",
    )
    if problem is not None:
        return Invalid((problem,))
    return validate_approval_set(
        payload, report=report, repo_root=repo_root,
        registry_path=registry_path, audit_config_digest=audit_config_digest,
        expected_digest=expected_digest, policy_path=policy_path,
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
