"""Reconciliation: what a selection is answerable to before it can be approved.

A report is a list of records, and a person approving some of them is choosing
edits. Records are not independent, though — two of them can name the same
passage, or overlapping passages, and propose different things to do with it.
Approving one leg of such a pair applies a decision nobody made: the other leg
stays in the report, unapplied, looking as though it was merely skipped.

So approval never sees a flat list. Reconciliation runs first, deterministically,
over the *whole* report, and answers one question per pair of records: do their
targets intersect, and do they propose the same remedy?

    same target, same remedy      duplicate           -> atomic
    same target, different remedy same-target         -> exclusive
    targets overlap, same remedy  overlapping         -> atomic
    targets overlap, differ       mutually-exclusive  -> exclusive

Related records form groups (connected components), and a group's disposition is
the *selection rule* an approval must obey — structure, not advice:

- `independent` — a record related to nothing. Selectable on its own.
- `atomic` — the members describe one edit, or edits over shared text. Selecting
  part of the group would leave the rest describing text that no longer exists,
  so the group is selected whole or not at all.
- `exclusive` — some pair in the group contradicts. No member may be selected:
  the contradiction is resolved by re-running the audit or correcting the audit policy,
  not by an approver silently picking a side.

**A target is (document, unit digests).** A unit digest is content, so the same
sentence in two documents is two targets: editing one says nothing about the
other. The document is compared as a *canonical* repository-relative spelling —
`paths.repository_relative_problem` decides, the same owner an edit target
answers to — because `./docs/a.md` and `docs/a.md` are one document, and a
report that spells one leg of a contradictory pair the other way would otherwise
split the pair into two independent groups and let an approver take one leg.

**A remedy is what the record writes, and where** — the replacement text and
the destination, never the finding code. Codes are audit policy vocabulary; the
question is whether two records would put the same bytes in the same place, so
a drift `STALE` fix and a bloat `CONDENSE` proposing one replacement for one
passage reconcile as the duplicate they are. Evidence prose, display ids,
locations, and waiver annotations are not remedies at all.

*A record that records no replacement text has an* unknown *remedy, not an
empty one.* Most real records are in that state — bloat's `CUT`, `RETIRE-DOC`,
and `DISTILL` all carry no proposal, and drift emits a fix only for `STALE` —
so collapsing every one of them onto a single "writes nothing" signature would
declare a `CUT` and a `DISTILL` over one passage to be one edit described twice,
and then demand they be approved together. Unknown remedies are distinguished by
finding code instead: two unknowns under different codes are different remedies
and their group is exclusive, which is the fail-closed answer, while two under
the same code stay comparable (identical code, document, and units is one
finding by digest, so this can only ever relate *overlapping* unit sets).

One code, one document, one unit set is not two records but one finding — the
finding digest says so — so a duplicate within a report is always cross-code.
That is why the digest check below runs before any grouping: the collapse this
rests on is a property of the digest, and a record whose digest does not match
its target has stepped outside it.

Identity is checked before anything is grouped. A record that is not a finding
(no code, path, or units) says nothing about what it would change, and a record
whose digest does not commit to its own declared target would let a selection
authorize an edit somewhere else. Either one makes the whole reconciliation
unsound — the guarantee is over every pair — so both are `invalid`, never a
group quietly left out.
"""

from dataclasses import dataclass
from typing import Tuple

from . import ARTIFACT_SCHEMA_VERSION
from .digest import canonical, sha256_canonical
from .finding import finding_digest
from .paths import repository_relative_problem
from .report import DIGEST, Report
from .results import STATUS_OK, Invalid, Problem

# How two records can be related. Every pair that shares a target is one of
# these, and nothing else is a relation at all.
RELATION_DUPLICATE = "duplicate"
RELATION_SAME_TARGET = "same-target"
RELATION_OVERLAPPING = "overlapping"
RELATION_MUTUALLY_EXCLUSIVE = "mutually-exclusive"

RELATIONS = (
    RELATION_DUPLICATE,
    RELATION_SAME_TARGET,
    RELATION_OVERLAPPING,
    RELATION_MUTUALLY_EXCLUSIVE,
)

# The selection rule a group carries. Closed: an approval flow acts on these,
# so an unrecognized one would have no defined meaning.
DISPOSITION_INDEPENDENT = "independent"
DISPOSITION_ATOMIC = "atomic"
DISPOSITION_EXCLUSIVE = "exclusive"

DISPOSITIONS = (
    DISPOSITION_INDEPENDENT, DISPOSITION_ATOMIC, DISPOSITION_EXCLUSIVE,
)

# Which relations contradict. The rule is uniform: intersecting targets with
# different remedies cannot both be applied, whatever the codes happen to be.
EXCLUSIVE_RELATIONS = (RELATION_SAME_TARGET, RELATION_MUTUALLY_EXCLUSIVE)

# What a remedy *writes*, in the two field names the lanes use for it: drift's
# `fix` and bloat's `proposal`. Read as one slot, because a remedy is the bytes
# it puts in the document, not the vocabulary its audit policy uses for the verdict
# with — two lanes proposing the same replacement for one passage are one edit
# described twice, and reconciling them as a contradiction would be false.
#
# This list is the *whole* vocabulary for replacement text, and it is an
# assumption about the producers rather than something the report contract
# enforces: `report.py` deliberately does not police `extra`, so a lane that
# carried its replacement under a third key would have that text read as no
# remedy at all. Both shipped lanes have closed verdict field sets
# (`drift.VERDICT_FIELDS`, `bloat.VERDICT_FIELDS`), which is what closes it
# today; a new lane adds its slot here, and the unknown-remedy rule below is
# what keeps the failure fail-closed until it does.
WRITTEN_FIELDS = ("fix", "proposal")

# The signature slot that keeps "no recorded remedy" from meaning "the same as
# every other record with no recorded remedy" — see the module docstring.
UNRECORDED_REMEDY_FIELD = "unrecorded-remedy-code"

# Where a remedy puts content it moves. Part of the remedy for the same reason
# the replacement text is: two moves of one passage to two documents are two
# different edits, however alike their verdicts look.
DESTINATION_FIELD = "destination"

# The record fields reconciliation reads. A record without all three is not a
# finding, and cannot be reconciled at all.
TARGET_FIELDS = ("code", "path", "units")


@dataclass(frozen=True)
class Relation:
    """One reconciled pair, and why it is a pair."""

    kind: str
    left: str
    right: str
    reason: str

    def to_dict(self):
        return {
            "kind": self.kind,
            "left": self.left,
            "right": self.right,
            "reason": self.reason,
        }


@dataclass(frozen=True)
class Group:
    """Records that must be selected together, or not at all.

    `members` are record digests, sorted — the same identity an approval set
    selects by, so a selection can be checked against a group without
    re-deriving anything.
    """

    group_id: str
    disposition: str
    members: Tuple[str, ...]
    relations: Tuple[Relation, ...]

    def to_dict(self):
        return {
            "id": self.group_id,
            "disposition": self.disposition,
            "members": list(self.members),
            "relations": [r.to_dict() for r in self.relations],
        }


@dataclass(frozen=True)
class Reconciliation:
    """Every record in one report, grouped by what it would change."""

    status: str
    report_digest: str
    groups: Tuple[Group, ...]
    digest: str

    def group_of(self, record_digest):
        """The group holding `record_digest`, or None if the report lacks it."""
        for group in self.groups:
            if record_digest in group.members:
                return group
        return None

    def to_dict(self):
        return {
            "status": self.status,
            "schema_version": ARTIFACT_SCHEMA_VERSION,
            "report_digest": self.report_digest,
            "groups": [g.to_dict() for g in self.groups],
            "digest": self.digest,
        }


def _target(record):
    """(path, frozenset of unit digests) for a finding record, or None."""
    extra = record.extra
    if not all(name in extra for name in TARGET_FIELDS):
        return None
    code, path, units = extra["code"], extra["path"], extra["units"]
    if not (isinstance(code, str) and code):
        return None
    if not (isinstance(path, str) and path):
        return None
    if not (isinstance(units, list) and units):
        return None
    if not all(isinstance(u, str) and DIGEST.match(u) for u in units):
        return None
    return path, frozenset(units)


def _remedy(record):
    """The remedy signature: what the record writes, and where.

    Deliberately not the finding code. Codes are audit policy vocabulary, and the
    question a selection has to answer is whether two records would put the
    same bytes in the same place: two lanes naming one edit differently must
    not read as a contradiction, and two records writing different text to one
    passage must, whatever they are called.
    """
    extra = record.extra
    written = next(
        (extra[name] for name in WRITTEN_FIELDS if extra.get(name) is not None),
        None,
    )
    destination = extra.get(DESTINATION_FIELD)
    if isinstance(destination, dict):
        # The lanes record a destination as the document plus what was checked
        # about it; the document is the part that makes it a different edit.
        destination = destination.get("path")
    signature = {"writes": written, "destination": destination}
    if written is None:
        # Nothing was recorded, so nothing is known about the bytes — and an
        # unknown must not compare equal to another unknown. The finding code
        # is the only thing left that says what the record would do, so it
        # enters the signature here and only here: a `CUT` and a `DISTILL` over
        # one passage become different remedies, and their group is exclusive
        # rather than "one edit described twice".
        signature[UNRECORDED_REMEDY_FIELD] = extra.get("code")
    return canonical(signature)


def _relation(left, right, targets, remedies):
    """How two records are related, or None when they share no target."""
    left_path, left_units = targets[left.digest]
    right_path, right_units = targets[right.digest]
    if left_path != right_path or left_units.isdisjoint(right_units):
        return None
    same_remedy = remedies[left.digest] == remedies[right.digest]
    same_target = left_units == right_units
    if same_target:
        kind = RELATION_DUPLICATE if same_remedy else RELATION_SAME_TARGET
        overlap = (
            f"both name the same {len(left_units)} assertion unit(s) in "
            f"{left_path}"
        )
    else:
        kind = (
            RELATION_OVERLAPPING if same_remedy else RELATION_MUTUALLY_EXCLUSIVE
        )
        overlap = (
            f"their targets in {left_path} share "
            f"{len(left_units & right_units)} assertion unit(s)"
        )
    verdict = (
        "the same remedy, so they are applied together or not at all"
        if same_remedy else
        "different remedies, so applying either one decides against the other"
    )
    return Relation(
        kind=kind,
        left=min(left.digest, right.digest),
        right=max(left.digest, right.digest),
        reason=f"{left.id} and {right.id}: {overlap}, and propose {verdict}",
    )


def _components(digests, relations):
    """Connected components over the relation graph, as sorted member tuples.

    Union-find, so the answer does not depend on the order records were listed
    in: a chain A–B, B–C is one group whichever end it is walked from.
    """
    parent = {digest: digest for digest in digests}

    def find(node):
        while parent[node] != node:
            parent[node] = parent[parent[node]]
            node = parent[node]
        return node

    for relation in relations:
        left, right = find(relation.left), find(relation.right)
        if left != right:
            parent[max(left, right)] = min(left, right)

    grouped = {}
    for digest in digests:
        grouped.setdefault(find(digest), []).append(digest)
    return [tuple(sorted(members)) for members in grouped.values()]


def _disposition(members, relations):
    if len(members) == 1:
        return DISPOSITION_INDEPENDENT
    if any(r.kind in EXCLUSIVE_RELATIONS for r in relations):
        return DISPOSITION_EXCLUSIVE
    return DISPOSITION_ATOMIC


def reconcile(report):
    """Group a validated report's records by what they would change.

    Returns a `Reconciliation`, or `Invalid` naming every record that cannot be
    reconciled. A non-`Report` is a `TypeError`, not a problem: reconciling
    something that has not been validated as a report is a programming error,
    and the guarantee this module makes is only meaningful over a report whose
    records are known to be well-formed and uniquely identified.
    """
    if not isinstance(report, Report):
        raise TypeError(
            f"reconcile takes a validated Report, not {type(report).__name__} — "
            f"a selection cannot be made answerable to relationships derived "
            f"from unvalidated content"
        )

    problems, targets, remedies = [], {}, {}
    for record in report.records:
        target = _target(record)
        if target is None:
            problems.append(Problem(
                code="reconcile-record-not-a-finding",
                message=(
                    f"record {record.id!r} does not carry {list(TARGET_FIELDS)} "
                    f"— nothing says what it would change, so nothing can say "
                    f"whether it conflicts with another record, and a selection "
                    f"including it could not be checked"
                ),
                location=record.id,
            ))
            continue
        spelling = repository_relative_problem(target[0])
        if spelling is not None:
            # A target is compared by string equality, so a non-canonical
            # spelling is a *different* document to every other record — which
            # is how one leg of a contradictory pair slips out of its group and
            # becomes independently approvable. Reconciliation's guarantee is
            # over every pair, so a document it cannot compare invalidates the
            # whole reconciliation rather than quietly leaving a group out.
            problems.append(Problem(
                code="reconcile-record-path-not-canonical",
                message=(
                    f"record {record.id!r} names document {target[0]!r}, which "
                    f"{spelling[1]} — reconciliation compares targets by "
                    f"spelling, so a document written two ways is two targets, "
                    f"and a contradiction between them would never be found"
                ),
                location=record.id,
            ))
            continue
        expected = finding_digest(
            report.lineage, record.extra["code"], record.extra["path"],
            record.extra["units"],
        )
        if expected != record.digest:
            problems.append(Problem(
                code="reconcile-record-digest-mismatch",
                message=(
                    f"record {record.id!r} declares digest {record.digest} but "
                    f"its code, document, and units under this report's lineage "
                    f"digest to {expected} — an approval selects by digest, so a "
                    f"record whose digest does not commit to its own target "
                    f"would authorize an edit somewhere else"
                ),
                location=record.id,
            ))
            continue
        targets[record.digest] = target
        remedies[record.digest] = _remedy(record)

    if problems:
        return Invalid(tuple(problems))

    records = sorted(report.records, key=lambda r: r.digest)
    relations = []
    for index, left in enumerate(records):
        for right in records[index + 1:]:
            relation = _relation(left, right, targets, remedies)
            if relation is not None:
                relations.append(relation)

    groups = []
    for members in _components([r.digest for r in records], relations):
        held = tuple(
            r for r in relations if r.left in members and r.right in members
        )
        groups.append(Group(
            group_id=sha256_canonical({
                "schema_version": ARTIFACT_SCHEMA_VERSION,
                "members": list(members),
            }),
            disposition=_disposition(members, held),
            members=members,
            relations=held,
        ))
    groups.sort(key=lambda g: g.members)

    return Reconciliation(
        status=STATUS_OK,
        report_digest=report.digest,
        groups=tuple(groups),
        digest=sha256_canonical({
            "schema_version": ARTIFACT_SCHEMA_VERSION,
            "report_digest": report.digest,
            "groups": [g.to_dict() for g in groups],
        }),
    )
