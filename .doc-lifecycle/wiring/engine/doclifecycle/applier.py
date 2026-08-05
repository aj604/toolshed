"""The applier: the deterministic component that writes, and nothing else does.

An **edit plan** is a separate versioned artifact: a small closed vocabulary of
operations (replace, delete, insert, create-document, retire-document,
move-with-provenance), each declaring the approved record it comes from and the
target class it is allowed to write. The plan binds to exactly one approval set
by digest, and the approval set is the sole authority the applier accepts.

The applier's whole job is refusal discipline around one small write:

- **Authority first.** The approval set is validated against the report it
  names and the repository it authorizes changes to — both, always: a
  validation run that skipped a check is refused before anything is read, since
  every check that does not need the report is a function of public repository
  state anyone could re-derive. A lineage field that moved is a stale refusal
  naming the field, with no working-tree change; a selection no minter would
  have produced is invalid.
- **Operations are checked, not trusted.** Every operation must come from an
  approved record, be one of the operations *that record's finding code
  approves* (`RECORD_REMEDIES`), stay inside one of the passages that record's
  approved *occurrences* are — never a hull spanning the text between two
  copies of one sentence — write only that record's own targets, declare a
  declarable target class,
  spell its paths canonically (`paths.write_target_problem`, the same owner the
  approval set uses), carry an exact preimage, and overlap or repeat nothing.
- **The write is an explicit validated transaction.** Every target's preimage
  is captured, every post-content computed from it and checked against the
  plan's declared postimages before any byte lands, every target re-read
  immediately before it is mutated, and every final target compared with its
  postimage before the run may call itself clean. A target that moved between
  the preimage and the write boundary is a typed concurrency refusal
  (`apply-write-boundary-race`) that overwrites nothing; final bytes that are
  not the computed postimage are another (`apply-postimage-not-on-disk`). Any
  problem leaves the tree byte-identical — except where a later writer has
  taken a target over, which rollback leaves alone rather than making a second
  lost update of it.
- **The whole diff is confined.** Before writing, the complete working-tree
  diff (index, work tree, and untracked files) is read from git and must be
  both inside the approval set's allowed mutation scope and empty: the applier
  applies onto the committed baseline, so nothing it did not make can ride into
  the diff it certifies. After writing it is read again, and an unaccounted
  change fails the run — rolling the applier's own writes back — rather than
  riding into a commit nobody approved.
- **Reapplying is idempotent, and that verdict is derived.** A plan is a no-op
  when applying it to HEAD reproduces exactly what is on disk, so re-running an
  interrupted lane is safe and a plan cannot declare its own way out of doing
  the work; the applier never stages and never commits — change approval (a
  person merging or committing) is the only thing that lands anything.

Model-generated content reaches this module only as data inside the plan and
report artifacts: the applier runs no shell, executes nothing it reads, and the
one external program in the whole flow is git — run read-only, behind
`repository.worktree_changes` and `repository.head_bytes`, never from this
module.
"""

import os
from dataclasses import dataclass
from typing import Optional, Tuple

from . import ARTIFACT_SCHEMA_VERSION
from .approval import (
    UNCHECKED_MEANING,
    occurrence_passages,
    validate_approval_set,
)
from .bloat import (
    CONDENSE, CUT, DISTILL, EXTRACT_AND_MOVE, MERGE_DOC, RETIRE_DOC,
    residue_destination_ineligibility,
)
from .digest import load_strict_json, sha256_bytes, sha256_canonical
from .drift import CODE_ANCHOR_STALE, VERDICT_STALE, VERDICT_UNVERIFIABLE
from .inventory import DEFAULT_REGISTRY_PATH, load_registry
from .paths import DECLARABLE_TARGET_CLASSES, write_target_problem
from .report import DIGEST, StaleReason
from .repository import head_bytes, worktree_changes
from .results import STATE_CLEAN, STATE_STALE, Invalid, Problem

# What the artifact says it is, for the same reason an approval set says so:
# a payload that does not declare itself could be handed over where the other
# is required and parse far enough to be dangerous.
ARTIFACT_KIND = "edit-plan"

OP_REPLACE = "replace"
OP_DELETE = "delete"
OP_INSERT = "insert"
OP_CREATE = "create-document"
OP_RETIRE = "retire-document"
OP_MOVE = "move-with-provenance"

# The whole vocabulary. Every operation declares the approved record it comes
# from and the target class it is allowed to write; the per-op fields are the
# smallest set that makes the edit exact.
OPERATION_FIELDS = {
    OP_REPLACE: ("op", "record", "target_class", "path",
                 "start_line", "end_line", "preimage", "text"),
    OP_DELETE: ("op", "record", "target_class", "path",
                "start_line", "end_line", "preimage"),
    OP_INSERT: ("op", "record", "target_class", "path", "after_line", "text"),
    OP_CREATE: ("op", "record", "target_class", "path", "text"),
    OP_RETIRE: ("op", "record", "target_class", "path", "preimage"),
    OP_MOVE: ("op", "record", "target_class", "path", "destination",
              "start_line", "end_line", "preimage"),
}

# Which operations each finding code's approved remedy is made of. Closed, and
# closed the fail-shut way: a code nobody listed authorizes nothing, because an
# approval is approval of a *remedy*, and letting the plan pick the operation
# would put the choice back with the model. The whole point of the auto-apply
# policy — mechanical drift fixes yes, retirements and creations never — is
# unenforceable without this table, since the policy mints records and the plan
# would otherwise attach any operation to one.
# The codes are imported from the audits that mint them rather than spelled
# here, so renaming a verdict is an import error rather than a table that
# quietly authorizes nothing.
_PASSAGE_REMEDY = (OP_REPLACE, OP_DELETE, OP_INSERT)
RECORD_REMEDIES = {
    # Drift. Both verdicts are about a passage that no longer holds; the
    # remedy rewrites, removes, or completes that passage, and nothing else.
    VERDICT_STALE: _PASSAGE_REMEDY,
    VERDICT_UNVERIFIABLE: _PASSAGE_REMEDY,
    # A narrative document's `> As of` line, overtaken by a change to what it
    # names. The remedy rewrites that one line, so it is the same span edit and
    # nothing more: an anchor record's units *are* the anchor, so the approved
    # passage already confines the edit to it. The other anchor codes are absent
    # deliberately — a missing or malformed anchor needs one authored, which is
    # not a span edit to a passage anybody approved.
    CODE_ANCHOR_STALE: _PASSAGE_REMEDY,
    # Bloat.
    CUT: (OP_DELETE,),
    CONDENSE: _PASSAGE_REMEDY,
    EXTRACT_AND_MOVE: (OP_MOVE,),
    MERGE_DOC: (OP_MOVE, OP_RETIRE),
    RETIRE_DOC: (OP_RETIRE,),
    # Distillation authors the durable residue and then retires the planning
    # artifact — the one remedy that legitimately brings a document into being.
    DISTILL: (OP_CREATE, OP_REPLACE, OP_INSERT, OP_DELETE, OP_RETIRE),
}

# Composite remedies whose legs are not substitutes for one another: a record
# whose code is a key here must see every listed operation among its own
# operations, or the plan lands a different, unapproved change (a retirement
# with no move is a deletion; a move with no retirement is a duplication).
#
# MERGE-DOC's requirement is unconditional — one move and one retirement,
# together, are the one merge a reviewer approved.
#
# DISTILL's retirement is unconditional too, and for the same reason: retiring
# the planning artifact is what a distillation *is*. A plan that edits or
# writes and never retires leaves the artifact standing — the document
# duplicated rather than distilled, and the run reporting `clean`. What is
# conditional is the *creation*, which only a record naming a destination
# proposed at all; see `DESTINATION_REQUIRED_OPERATIONS`. DISTILL's three span
# operations are never required, since which span edits a given residue needs
# is chosen per record rather than required whole.
REQUIRED_REMEDY_OPERATIONS = {
    MERGE_DOC: (OP_MOVE, OP_RETIRE),
    DISTILL: (OP_RETIRE,),
}

# Operations required *in addition* of a record that names a destination. A
# DISTILL record carrying one was approved as "author the residue there, then
# retire the planning artifact", so both legs are owed: a plan carrying only
# the retirement is the MERGE-DOC shape reached through a different code — the
# source destroyed and nothing written — while a plan carrying only the
# creation writes the residue and leaves the artifact behind. A
# destination-less DISTILL proposed no residue at all, so retiring the
# planning artifact alone remains the whole approved remedy.
DESTINATION_REQUIRED_OPERATIONS = {
    DISTILL: (OP_CREATE,),
}

# Why each composite remedy is one act, in that code's own terms — the sentence
# a `plan-remedy-incomplete` refusal ends on. A code with a requirement and no
# reason here would refuse without saying what the missing leg was for.
REMEDY_INCOMPLETE_REASON = {
    MERGE_DOC: (
        "MERGE-DOC is one composite act — a move and a retirement; either leg "
        "alone is a different, unapproved change"
    ),
    DISTILL: (
        "this distillation was approved to author its residue at "
        "{destination} and then retire the planning artifact — both legs, or "
        "it is a different change: a retirement with no creation destroys the "
        "artifact and writes nothing, and a creation with no retirement "
        "leaves the artifact standing beside its own residue"
    ),
    # The destination-less shape, whose whole remedy is the retirement — there
    # is no creation to name, so DISTILL's reason above would describe a plan
    # this record never proposed.
    (DISTILL, None): (
        "this distillation named no destination, so retiring the planning "
        "artifact is the whole remedy it was approved for; a plan that "
        "retires nothing has executed none of it"
    ),
}

# The operations that name a line span in an existing document.
SPAN_OPS = (OP_REPLACE, OP_DELETE, OP_MOVE)
# Every operation whose position in an existing document is stated, and so can
# be checked against the passage the record was approved about.
POSITIONED_OPS = SPAN_OPS + (OP_INSERT,)
# The operations that claim a whole document, and so tolerate no other
# operation touching the same path.
WHOLE_DOCUMENT_OPS = (OP_CREATE, OP_RETIRE)

FIELDS = (
    "artifact", "schema_version", "approval_digest", "operations",
    "postimages", "digest",
)

# The approval stale reasons that are answered per-target rather than by the
# world at large. They are the one kind of staleness an already-applied plan
# legitimately produces about itself — the applier's own writes moved the
# preimages — so idempotency is decided before they refuse anything.
PREIMAGE_REASON_CODES = (
    "approval-preimage-mismatch",
    "approval-preimage-unreadable",
)


@dataclass(frozen=True)
class AppliedOperation:
    """One operation that landed, with the provenance a reviewer needs."""

    op: str
    record: str
    path: str
    destination: Optional[str] = None

    def to_dict(self):
        payload = {"op": self.op, "record": self.record, "path": self.path}
        if self.destination is not None:
            payload["destination"] = self.destination
        return payload


@dataclass(frozen=True)
class ApplyResult:
    """What one apply run did, or why it refused without touching anything.

    `clean` means the plan's postimages are on disk — re-read from it and
    compared byte for byte, not inferred from having written them — and the
    complete working-tree diff is inside the approval set's allowed mutation
    scope, whether this run wrote them (`applied` names each operation) or
    found them already there (`already_applied`, the idempotent re-run — a
    narrower claim in that this run wrote nothing, but not a weaker one: the
    bytes on disk were re-derived by applying the plan to the committed
    baseline, so they are the operations' own result and not something the
    plan declared them to be). `stale` means the
    approval expired and nothing was touched; the reasons name every field that
    moved and say to re-run the audit and mint afresh. Anything else about the
    run is `Invalid`, never a weaker success.

    `postimages` is that verified manifest — each written path with the sha256
    of the bytes this run *read back* from it, `None` for one it retired — so
    a later trust boundary (a staged index, a commit tree) checks its own
    bytes against what the applier certified rather than against the plan it
    was handed. It is empty on every refusal: nothing was certified.
    """

    status: str
    approval_digest: str
    plan_digest: str
    applied: Tuple[AppliedOperation, ...] = ()
    changed_paths: Tuple[str, ...] = ()
    already_applied: bool = False
    stale_reasons: Tuple[StaleReason, ...] = ()
    postimages: Tuple[Tuple[str, Optional[str]], ...] = ()

    def to_dict(self):
        payload = {
            "status": self.status,
            "schema_version": ARTIFACT_SCHEMA_VERSION,
            "approval_digest": self.approval_digest,
            "plan_digest": self.plan_digest,
            "applied": [op.to_dict() for op in self.applied],
            "changed_paths": list(self.changed_paths),
            "already_applied": self.already_applied,
            "postimages": dict(self.postimages),
        }
        if self.stale_reasons:
            payload["stale_reasons"] = [r.to_dict() for r in self.stale_reasons]
        return payload


def _read_payload(path, prefix):
    """A JSON payload off disk, or `Invalid` with `<prefix>-*` codes."""
    payload, problem = load_strict_json(
        path,
        unreadable_code=f"{prefix}-unreadable",
        unparseable_code=f"{prefix}-unparseable",
        nesting_code=f"{prefix}-nesting-too-deep",
    )
    if problem is not None:
        return Invalid((problem,))
    return payload


def load_edit_plan(path):
    """Read an edit-plan file. Returns the payload dict, or `Invalid`.

    Reading only: validation needs the approval set the plan binds to, so it
    happens inside `apply_edit_plan`, where that authority is in hand.
    """
    return _read_payload(path, "plan")


def load_approval_payload(path):
    """Read an approval-set file *as data*, for handing to `apply_edit_plan`.

    Deliberately unvalidated here: the applier validates the payload itself,
    against the report and the repository, so a caller cannot accidentally
    hand it a weaker (structural-only) verdict.
    """
    return _read_payload(path, "approval")


def _span_position(operation):
    """Where an operation acts, for overlap checks and apply ordering.

    A span starts at its first line; an insert acts *between* lines, so it
    sits at `after_line + 0.5` — distinct from any span start, and ordered
    after a span that starts on the same line when applying bottom-up.
    """
    if operation["op"] == OP_INSERT:
        return operation["after_line"] + 0.5
    return operation["start_line"]


def _operation_shape_problems(i, operation, bad):
    """Everything structurally wrong with one operation. True if unusable."""
    where = f"operations[{i}]"
    if not isinstance(operation, dict) or not isinstance(
        operation.get("op"), str
    ) or operation.get("op") not in OPERATION_FIELDS:
        bad("plan-invalid-operation",
            f"operations[{i}] must declare 'op' as one of "
            f"{sorted(OPERATION_FIELDS)} — the vocabulary is closed, so an "
            f"operation the applier does not know is not a weaker edit, it is "
            f"no edit",
            where)
        return True
    op = operation["op"]
    expected = OPERATION_FIELDS[op]
    if set(operation) != set(expected):
        missing = sorted(set(expected) - set(operation))
        extra = sorted(set(operation) - set(expected))
        bad("plan-invalid-operation",
            f"operations[{i}] is a {op!r} and must carry exactly "
            f"{list(expected)}; it is missing {missing} and adds {extra} — "
            f"every field is load-bearing, a preimage above all",
            where)
        return True

    broken = False
    if not (isinstance(operation["record"], str)
            and DIGEST.match(operation["record"])):
        bad("plan-invalid-operation",
            f"operations[{i}].record must be the sha256 digest of the "
            f"approved record this edit comes from",
            where)
        broken = True
    for name in ("path",) + (("destination",) if op == OP_MOVE else ()):
        value = operation[name]
        reason = (
            write_target_problem(value) if isinstance(value, str) and value
            else "is not a non-empty string"
        )
        if reason is not None:
            bad("plan-invalid-operation",
                f"operations[{i}].{name} {value!r} {reason} — an edit target "
                f"is a canonical repository-relative document and nothing "
                f"else",
                where)
            broken = True
    if op in SPAN_OPS:
        start, end = operation["start_line"], operation["end_line"]
        if not all(
            isinstance(v, int) and not isinstance(v, bool) for v in (start, end)
        ) or not (1 <= start <= end):
            bad("plan-invalid-operation",
                f"operations[{i}] must name a span as 1-based line numbers "
                f"with start_line <= end_line",
                where)
            broken = True
    if op == OP_INSERT:
        after = operation["after_line"]
        if not (isinstance(after, int) and not isinstance(after, bool)
                and after >= 0):
            bad("plan-invalid-operation",
                f"operations[{i}].after_line must be a line number >= 0 "
                f"(0 inserts at the top of the document)",
                where)
            broken = True
    if "preimage" in expected and not isinstance(operation["preimage"], str):
        bad("plan-invalid-operation",
            f"operations[{i}].preimage must be the exact current text of the "
            f"span it claims — an edit without one cannot be checked against "
            f"what was approved",
            where)
        broken = True
    if "text" in expected:
        text = operation["text"]
        if not isinstance(text, str) or (
            op in (OP_INSERT, OP_CREATE) and not text
        ):
            bad("plan-invalid-operation",
                f"operations[{i}].text must be the content this edit writes"
                + (" — an empty document is not a creation"
                   if op == OP_CREATE else ""),
                where)
            broken = True
    if operation["target_class"] not in DECLARABLE_TARGET_CLASSES:
        bad("plan-forbidden-target-class",
            f"operations[{i}] declares target class "
            f"{operation['target_class']!r} — the applier writes "
            f"{list(DECLARABLE_TARGET_CLASSES)} and nothing else, and the "
            f"dangerous classes are not something a plan can opt into",
            where)
        broken = True
    return broken


def _binding_problems(i, operation, by_digest, bad):
    """The operation against the approval set: approved record, its targets."""
    where = f"operations[{i}]"
    record = by_digest.get(operation["record"])
    if record is None:
        bad("plan-record-not-approved",
            f"operations[{i}] claims record {operation['record']}, which the "
            f"approval set does not select — an edit plan executes an "
            f"approval, so an operation from outside it is authority nobody "
            f"minted",
            where)
        return
    op = operation["op"]
    allowed = RECORD_REMEDIES.get(record.code, ())
    if op not in allowed:
        bad("plan-operation-not-record-remedy",
            f"operations[{i}] is a {op!r} and record {record.record_id} was "
            f"approved as {record.code!r}, whose remedy is {list(allowed)} — "
            f"an approval approves a remedy, so a plan that picks the "
            f"operation is choosing what was approved after the fact",
            where)
        return
    if op == OP_MOVE:
        if (operation["path"] != record.path
                or operation["destination"] != record.destination):
            bad("plan-target-not-record-target",
                f"operations[{i}] moves {operation['path']!r} to "
                f"{operation['destination']!r}, and record {record.record_id} "
                f"was approved for {record.path!r} to "
                f"{record.destination!r} — a move writes exactly the two "
                f"documents its record was approved for",
                where)
        return
    # A retirement retires the document the record is about, and a creation
    # brings the document the record names as its destination into being.
    # Neither is a path the other end of the record can stand in for.
    #
    # A positioned edit is narrower still: it is bounded by the passage the
    # record's approved units are (`_approved_span_problems`), and those units
    # segment the record's own document — a destination has no such passage, so
    # a span edit there is one no reviewer could have read. Refusing it here is
    # what keeps "an approval approves a passage" true of a record that names
    # two documents.
    expected = {
        OP_RETIRE: (record.path,),
        OP_CREATE: (record.destination,) if record.destination else (),
        # `move-with-provenance` returned above; these are the rest of
        # `POSITIONED_OPS`, the ones an approved passage can and must bound.
        **{positioned: (record.path,) for positioned in _PASSAGE_REMEDY},
    }.get(op, record.targets())
    if operation["path"] not in expected:
        bad("plan-target-not-record-target",
            f"operations[{i}] writes {operation['path']!r}, and record "
            f"{record.record_id} approves a {op!r} of {list(expected)} — "
            f"an operation writes only its own record's targets, so a "
            f"borrowed path is a document nobody approved this edit for",
            where)


def _completeness_problems(usable, by_digest, bad):
    """Every approved record, against what the plan actually executes.

    `_binding_problems` checks each operation against its record; this is the
    reverse direction — each record against its operations — and it is not
    redundant with that check, since an operation can bind cleanly to every
    record it names while a *different* approved record names none at all.
    An approval set is the whole mandate: a plan that silently drops one of
    its records would let the run report work it did not do, exactly as if
    it had invented an operation the approval never saw.

    A record whose code is in `REQUIRED_REMEDY_OPERATIONS` is a composite
    remedy, and the same silent drop can happen one leg at a time: a plan can
    name the record and still execute only part of what was approved.
    MERGE-DOC is the case this closes — a retirement with no move destroys
    the source and moves nothing; a move with no retirement leaves the
    duplicate that was supposed to go away — and DISTILL is that same shape
    from both sides: retiring the planning artifact without authoring the
    residue destroys the source and writes nothing, while authoring the
    residue and never retiring leaves the artifact standing beside it. The
    retirement is owed by every DISTILL, the creation only by one that named
    a destination to write.
    """
    ops_by_record = {}
    for _, operation in usable:
        ops_by_record.setdefault(operation["record"], []).append(operation["op"])

    for digest, record in by_digest.items():
        ops = ops_by_record.get(digest)
        if not ops:
            bad("plan-record-not-executed",
                f"approved record {record.record_id} ({record.code!r} at "
                f"{record.path!r}) names no usable operation in this plan — "
                f"an approval set is the whole mandate: a plan that silently "
                f"drops an approved record would let the run report work it "
                f"did not do",
                "operations")
            continue
        required = tuple(REQUIRED_REMEDY_OPERATIONS.get(record.code, ()))
        if record.destination is not None:
            required += DESTINATION_REQUIRED_OPERATIONS.get(record.code, ())
        if not required:
            continue
        missing = [op for op in required if op not in ops]
        if missing:
            # A code whose remedy differs with and without a destination
            # explains itself per shape; everything else has one reason.
            reason = REMEDY_INCOMPLETE_REASON.get(
                (record.code, None) if record.destination is None else
                record.code,
                REMEDY_INCOMPLETE_REASON[record.code],
            )
            bad("plan-remedy-incomplete",
                f"approved record {record.record_id} ({record.code!r} at "
                f"{record.path!r}) carries {sorted(set(ops))} and is missing "
                f"{missing} — "
                + reason.format(destination=record.destination),
                "operations")


def _rendered(passages):
    """The approved passages as a reader would cite them: `12..14, 40..41`."""
    return ", ".join(f"{first}..{last}" for first, last in passages)


def _approved_span_problems(repo_root, operations, by_digest):
    """Positioned operations, checked against the passages that were approved.

    A record names its target by assertion-unit digest *and* by which occurrence
    of each unit the audit read (`approval.occurrence_passages`), and those
    occurrences are one or more *passages* of the document — so an edit that
    reaches outside them is an edit to text no reviewer read under this record.
    Consecutive approved units are one passage, so the blank lines and list
    markers between them remain editable and a remedy that removes two adjacent
    sentences legitimately removes what separated them. Units with something
    unapproved between them are two passages, and an operation must fit inside
    one of them: spanning the gap would edit the intervening material, which
    nobody approved — and where the gap separates a repeated sentence from its
    twin, spanning it is authority over a whole section obtained by approving
    one line.

    The passages are measured against the committed baseline, which is the state
    the plan's line numbers are stated in: the write path requires the tree to
    equal it, and on an idempotent re-run the approved passage is necessarily no
    longer on disk — so reading the working tree would make the bound
    unavailable in exactly the case an attacker arranges.

    Only operations on the record's *own* document reach this check, and that
    is not a gap: a record's units segment that document alone, so a
    destination has no passage to measure against — and `_binding_problems`
    refuses a positioned operation there rather than letting one through
    unbounded. What may write a destination is the whole-document operations
    and a move's append, each of which the approval covers entire.
    """
    problems = []
    bounds = {}

    def bad(message, where):
        problems.append(Problem(
            code="plan-span-outside-approved-units", message=message,
            location=where,
        ))

    for i, operation in enumerate(operations):
        if operation["op"] not in POSITIONED_OPS:
            continue
        record = by_digest[operation["record"]]
        if operation["path"] != record.path:
            continue
        if record.digest not in bounds:
            bounds[record.digest] = occurrence_passages(repo_root, record)
        passages, why = bounds[record.digest]
        if passages is None:
            bad(f"operations[{i}] edits {record.path}, and where record "
                f"{record.record_id}'s approved occurrences are cannot be "
                f"established: {why} — an unanswered question about the "
                f"target is a refusal. Re-run the audit and mint afresh",
                f"operations[{i}]")
            continue
        if operation["op"] == OP_INSERT:
            point = operation["after_line"]
            if not any(first - 1 <= point <= last for first, last in passages):
                bad(f"operations[{i}] inserts after line {point} of "
                    f"{record.path}, and record {record.record_id} was "
                    f"approved about lines {_rendered(passages)} — an edit "
                    f"outside the approved passage is an edit nobody reviewed. "
                    f"Move the insertion inside it, or mint an approval for a "
                    f"record that covers where it goes",
                    f"operations[{i}]")
            continue
        start, end = operation["start_line"], operation["end_line"]
        if not any(first <= start and end <= last for first, last in passages):
            bad(f"operations[{i}] edits lines {start}..{end} of "
                f"{record.path}, and record {record.record_id} was approved "
                f"about lines {_rendered(passages)} — an approval binds to the "
                f"passages its approved occurrences are, so a span that "
                f"reaches beyond one of them is text nobody approved a remedy "
                f"for. Narrow the operation to an approved passage, or mint an "
                f"approval that covers the rest",
                f"operations[{i}]")
    return tuple(problems)


def _residue_destination_problems(repo_root, operations, registry_path):
    """Create-document targets, re-classified against the registry at apply time.

    A `create-document` brings a new document into being, and the only finding
    whose remedy authorizes one is `DISTILL` — so every create is distilled
    residue, landing at a path a person approved as its destination. The audit
    already refuses a destination the registry does not classify as an
    eligible-kind document (`bloat-destination-unclassified` /
    `bloat-destination-kind-ineligible`), but those hold at *audit* time only:
    the record digest does not cover `destination`, so a tampered or stale
    report could repoint an approved record's create at a planning or
    unclassified path. Confinement (`authorize_path`, via the approval scope)
    and occupancy (`apply-create-exists`) are already re-answered by the
    applier elsewhere; this closes the two that were not, reusing the audit's
    own reading (`residue_destination_ineligibility`) so the two seams cannot
    diverge.

    An unreadable registry answers none of it, and an unanswered safety
    question is a refusal — the same fail-closed stance the whole module takes.
    """
    creates = [op for op in operations if op["op"] == OP_CREATE]
    if not creates:
        return ()
    registry = load_registry(repo_root, registry_path)
    if isinstance(registry, Invalid):
        # Approval validation re-loaded the registry to re-authorize the scope
        # and staled the run if it could not; only a race that unreads it
        # between there and here reaches this, and it fails closed like the
        # rest of the module.
        return (Problem(
            code="apply-destination-unclassifiable",
            message=(
                f"a create-document lands a new document, but the registry that "
                f"classifies where documents may live cannot be read "
                f"({registry.problems[0].message}) — whether the destination is "
                f"an eligible-kind document is unanswerable, and an unanswered "
                f"safety question is a refusal"
            ),
            location=registry_path,
        ),)
    problems = []
    for operation in creates:
        path = operation["path"]
        reason, rule = residue_destination_ineligibility(registry, path)
        if reason == "unclassified":
            problems.append(Problem(
                code="apply-destination-unclassified",
                message=(
                    f"create-document targets {path!r}, which no registry rule "
                    f"claims as documentation — classification is closed-world, "
                    f"so a document created at an unclassified path would be "
                    f"born outside the corpus every later audit reads. The "
                    f"audit refuses this destination; so does the applier, "
                    f"whatever report routed it here"
                ),
                location=path,
            ))
        elif reason == "kind-ineligible":
            problems.append(Problem(
                code="apply-destination-kind-ineligible",
                message=(
                    f"create-document targets {path}, which the registry "
                    f"classifies as a {rule.kind} document — residue is never "
                    f"authored into one, because its own lifecycle ends in "
                    f"distillation or retirement and would take the residue "
                    f"with it. The audit refuses this destination; so does the "
                    f"applier, whatever report routed it here"
                ),
                location=path,
            ))
    return tuple(problems)


def _conflict_problems(operations, bad):
    """Duplicates, overlapping spans, and whole-document conflicts.

    Refusal, not resolution: two operations that could contend are two
    operations whose combined result depends on order the plan did not state,
    and a deterministic applier does not pick.
    """
    seen = {}
    for i, operation in enumerate(operations):
        key = sha256_canonical(operation)
        if key in seen:
            bad("plan-duplicate-operation",
                f"operations[{i}] repeats operations[{seen[key]}] exactly — "
                f"applying one edit twice is not the same edit, and a plan is "
                f"a set of operations",
                f"operations[{i}]")
        seen[key] = i

    by_path = {}
    destinations = {}
    for i, operation in enumerate(operations):
        by_path.setdefault(operation["path"], []).append((i, operation))
        if operation["op"] == OP_MOVE:
            destinations.setdefault(
                operation["destination"], []
            ).append(i)

    for path, entries in by_path.items():
        whole = [i for i, op in entries if op["op"] in WHOLE_DOCUMENT_OPS]
        # One pairing is not a race even though it is two operations claiming
        # the same path with one of them whole: the *same approved record's*
        # own move and retirement, together — the exact shape
        # `REQUIRED_REMEDY_OPERATIONS` requires a MERGE-DOC plan to carry
        # (`RECORD_REMEDIES` makes MERGE-DOC the only code whose remedy is
        # both `OP_MOVE` and `OP_RETIRE`, so the same-record test below is
        # equivalent to, and cheaper than, re-deriving the record's code
        # here). `_compute_postimages` always lets the retirement decide this
        # path's final content, unconditionally and regardless of list order
        # — the move's only other effect is its append to a *different* path
        # (its destination) — so those two operations never race. Two
        # operations from *different* records that happen to be a move and a
        # retirement of the same path are not this shape: nothing approved
        # them as one act, so they keep the ordinary whole-document refusal
        # below (`plan-record-not-executed`/`plan-remedy-incomplete` in
        # `_completeness_problems` police the record-level MERGE-DOC
        # contract; this check polices only whether the two operations that
        # do claim the path may coexist at all).
        paired_move_and_retire = (
            len(entries) == 2 and path not in destinations
            and {op["op"] for _, op in entries} == {OP_MOVE, OP_RETIRE}
            and len({op["record"] for _, op in entries}) == 1
        )
        if whole and not paired_move_and_retire and (
            len(entries) > 1 or path in destinations
        ):
            bad("plan-conflicting-operations",
                f"operations {sorted(i for i, _ in entries)} all touch {path}, "
                f"which operations[{whole[0]}] claims whole — a created or "
                f"retired document tolerates no other edit",
                path)
            continue
        spans = sorted(
            (op["start_line"], op["end_line"], i)
            for i, op in entries if op["op"] in SPAN_OPS
        )
        for (s1, e1, i1), (s2, e2, i2) in zip(spans, spans[1:]):
            if s2 <= e1:
                bad("plan-overlapping-spans",
                    f"operations[{i1}] and operations[{i2}] both edit lines "
                    f"{s2}..{min(e1, e2)} of {path} — overlapping spans have "
                    f"no order-independent result, so the plan is ambiguous "
                    f"about what was approved",
                    path)
        points = {}
        for i, op in entries:
            if op["op"] != OP_INSERT:
                continue
            point = op["after_line"]
            if point in points:
                bad("plan-overlapping-spans",
                    f"operations[{points[point]}] and operations[{i}] both "
                    f"insert after line {point} of {path} — their order is "
                    f"not stated, so their combined result is not either",
                    path)
            points[point] = i
            for s, e, j in spans:
                if s <= point <= e - 1:
                    bad("plan-overlapping-spans",
                        f"operations[{i}] inserts inside lines {s}..{e} of "
                        f"{path}, which operations[{j}] rewrites — an insert "
                        f"into a span being replaced lands in text that is "
                        f"about to not exist",
                        path)
    return None


def _written_paths(operations):
    """Every path the plan writes, sources and move destinations alike."""
    paths = set()
    for operation in operations:
        paths.add(operation["path"])
        if operation["op"] == OP_MOVE:
            paths.add(operation["destination"])
    return paths


def _postimage_problems(payload, operations, bad):
    """The declared postimages: shape, and derivation from the operations."""
    postimages = payload.get("postimages")
    if not isinstance(postimages, dict) or not all(
        isinstance(k, str) and (
            v is None or (isinstance(v, str) and DIGEST.match(v))
        )
        for k, v in postimages.items()
    ):
        bad("plan-invalid-postimages",
            "postimages must map each written path to the sha256 of the "
            "document's bytes after the plan, or null for a retired one — "
            "they are what makes reapplying checkable",
            "postimages")
        return
    written = _written_paths(operations)
    if set(postimages) != written:
        bad("plan-postimages-not-derived",
            f"postimages must name exactly the paths the operations write: "
            f"missing {sorted(written - set(postimages))}, extra "
            f"{sorted(set(postimages) - written)}",
            "postimages")
        return
    retired = {
        op["path"] for op in operations if op["op"] == OP_RETIRE
    }
    for path, digest in postimages.items():
        if (digest is None) != (path in retired):
            bad("plan-invalid-postimages",
                f"postimages[{path!r}] must be null exactly when the plan "
                f"retires that document, and a content digest otherwise",
                "postimages")


def _validate_plan(payload, approval):
    """Every structural problem with the plan, against its approval set."""
    if not isinstance(payload, dict) or payload.get("artifact") != ARTIFACT_KIND:
        kind = payload.get("artifact") if isinstance(payload, dict) else None
        return Invalid((Problem(
            code="plan-not-an-edit-plan",
            message=(
                f"an edit plan is required here, and this is "
                f"{'an object declaring artifact %r' % (kind,) if kind else 'not one'}"
                f" — the applier executes a validated edit plan and nothing "
                f"else"
            ),
            location="artifact",
        ),))

    problems = []

    def bad(code, message, where=None):
        problems.append(Problem(code=code, message=message, location=where))

    for name in FIELDS:
        if name not in payload:
            bad("plan-missing-field", f"the edit plan is missing '{name}'", name)
    for name in payload:
        if name not in FIELDS:
            bad("plan-unknown-field",
                f"unexpected field {name!r} — an edit plan carries "
                f"{list(FIELDS)}",
                name)
    if problems:
        return Invalid(tuple(problems))

    version = payload["schema_version"]
    if not (isinstance(version, int) and not isinstance(version, bool)
            and version == ARTIFACT_SCHEMA_VERSION):
        bad("plan-schema-version",
            f"edit-plan schema_version {version!r} is not supported; this "
            f"engine reads integer version {ARTIFACT_SCHEMA_VERSION}",
            "schema_version")

    declared = payload["digest"]
    content = {k: v for k, v in payload.items() if k != "digest"}
    try:
        actual = sha256_canonical(content)
    except (TypeError, ValueError):
        bad("plan-invalid-operation",
            "the edit plan carries values no canonical JSON encoding can "
            "digest, so it cannot be checked against its own digest",
            "digest")
        return Invalid(tuple(problems))
    if declared != actual:
        bad("plan-digest-mismatch",
            f"the edit plan declares digest {declared!r} but its content "
            f"digests to {actual} — it has been altered since it was drawn "
            f"up, and its digest is what binds it to a review",
            "digest")
        return Invalid(tuple(problems))

    operations = payload["operations"]
    if not isinstance(operations, list) or not operations:
        bad("plan-empty",
            "operations must be a non-empty list — a plan that edits nothing "
            "is not a plan, and an empty one riding an approval looks like "
            "authority",
            "operations")
        return Invalid(tuple(problems))

    usable = []
    for i, operation in enumerate(operations):
        if not _operation_shape_problems(i, operation, bad):
            usable.append((i, operation))

    if payload["approval_digest"] != approval.digest:
        bad("plan-approval-mismatch",
            f"the edit plan binds to approval set "
            f"{payload['approval_digest']!r} and the approval set supplied "
            f"digests to {approval.digest} — a plan executes exactly one "
            f"approval, so a different digest is a different authority",
            "approval_digest")

    by_digest = {record.digest: record for record in approval.records}
    for i, operation in usable:
        _binding_problems(i, operation, by_digest, bad)

    _completeness_problems(usable, by_digest, bad)

    if len(usable) == len(operations):
        _conflict_problems(operations, bad)
        _postimage_problems(payload, operations, bad)

    return Invalid(tuple(problems)) if problems else None


def _current_bytes(repo_root, path):
    """(the file's bytes or None when nothing is there, problem reason or None).

    `lexists` first, so a symlink — even a broken one — is never read through:
    what it points at is not this repository's document. Present-but-not-a-
    plain-readable-file is a named refusal, never an empty read: an empty
    byte string is a value a preimage could legitimately equal, so returning
    one here would let a retire-document with an empty preimage remove a path
    nothing ever read.
    """
    full = os.path.join(repo_root, path)
    if not os.path.lexists(full):
        return None, None
    if os.path.islink(full):
        return None, "is a symlink, which is never read through or written"
    if not os.path.isfile(full):
        return None, "is not a regular file"
    try:
        with open(full, "rb") as fh:
            return fh.read(), None
    except OSError as exc:
        return None, f"cannot be read ({exc.strerror})"


def _already_applied(repo_root, operations, postimages):
    """The verified postimage manifest when this plan, applied to the committed
    baseline, is what is on disk — `None` when it is not.

    Derived, never declared. The plan is attacker-controlled by assumption, so
    a check that only asks "are the bytes the plan *names* on disk?" lets the
    plan choose what "already applied" means — it can name the unchanged
    document (an approved fix reported as landed without landing) or bytes
    somebody else put there (an unapproved diff certified as the approved one).

    So the question asked here is the one an idempotent re-run actually poses:
    take each written path as HEAD has it, apply these operations, and see
    whether the result is byte-for-byte what the working tree holds. HEAD is
    the right baseline because a moved base commit is already a stale refusal
    before this runs. The declared postimages are checked too — they are what
    a reviewer read — but they are the weaker half of the answer.

    Any question that cannot be answered — an unreadable path, a preimage that
    does not match the baseline — is a no, and the normal path then produces
    the honest refusal.

    The manifest returned on a yes is the same certified thing the write path
    returns: every digest in it was compared against the bytes read off disk
    here, so an idempotent re-run makes no weaker claim about the content than
    the run that wrote it.
    """
    baseline = {}
    for path in sorted(_written_paths(operations)):
        data, problem = head_bytes(repo_root, path)
        if problem is not None:
            return None
        try:
            baseline[path] = None if data is None else data.decode("utf-8")
        except UnicodeDecodeError:
            return None

    derived = _compute_postimages(baseline, operations, [])
    if derived is None:
        return None

    for path, digest in postimages.items():
        data, unreadable = _current_bytes(repo_root, path)
        if unreadable is not None:
            return None
        expected = derived.get(path)
        if expected is None or digest is None:
            if expected is not None or digest is not None or data is not None:
                return None
            continue
        if data is None or data.decode("utf-8", "replace") != expected:
            return None
        if sha256_bytes(data) != digest:
            return None
    return tuple(sorted(postimages.items()))


def _read_texts(repo_root, operations, problems):
    """{path: current text or None} for every path the plan writes."""
    def bad(code, message, where=None):
        problems.append(Problem(code=code, message=message, location=where))

    texts = {}
    for path in sorted(_written_paths(operations)):
        data, unreadable = _current_bytes(repo_root, path)
        if unreadable is not None:
            bad("apply-preimage-mismatch",
                f"{path} {unreadable}, so no preimage can match it and "
                f"nothing here may write it",
                path)
            continue
        if data is None:
            texts[path] = None
            continue
        try:
            texts[path] = data.decode("utf-8")
        except UnicodeDecodeError as exc:
            bad("apply-preimage-mismatch",
                f"{path} is not valid UTF-8 ({exc.reason} at byte "
                f"{exc.start}), so no preimage can match it",
                path)
    return texts


def _compute_postimages(texts, operations, problems):
    """{path: new text or None} after every operation, or None with problems.

    `texts` is the pre-state the operations are computed against — the working
    tree on the write path, the committed baseline when deciding whether the
    plan is already applied. Deterministic order: per document, span edits
    apply bottom-up (so line numbers stay what the plan named), inserts at a
    boundary apply before a span starting on the same line, and moved text is
    appended to its destination in (source path, span) order after the
    destination's own span edits. Every preimage is compared exactly before
    anything is computed.
    """
    def bad(code, message, where=None):
        problems.append(Problem(code=code, message=message, location=where))

    if problems:
        return None

    creates = [op for op in operations if op["op"] == OP_CREATE]
    for operation in creates:
        path = operation["path"]
        if texts[path] is not None:
            bad("apply-create-exists",
                f"{path} already exists, and create-document only brings a "
                f"document into being — overwriting an existing one under a "
                f"'create' is an edit nobody reviewed as one",
                path)

    span_ops = {}
    appends = []
    for operation in operations:
        op = operation["op"]
        if op in SPAN_OPS or op == OP_INSERT:
            span_ops.setdefault(operation["path"], []).append(operation)
        if op == OP_MOVE:
            appends.append(operation)

    for path, ops in span_ops.items():
        text = texts.get(path)
        if text is None:
            bad("apply-preimage-missing",
                f"{path} is not in the working tree, so the exact text this "
                f"plan edits is not there to check",
                path)
            continue
        lines = text.split("\n")
        for operation in ops:
            if operation["op"] == OP_INSERT:
                if operation["after_line"] > len(lines):
                    bad("apply-preimage-mismatch",
                        f"{path} has {len(lines)} line(s) and the plan "
                        f"inserts after line {operation['after_line']}",
                        path)
                continue
            start, end = operation["start_line"], operation["end_line"]
            if end > len(lines):
                bad("apply-preimage-mismatch",
                    f"{path} has {len(lines)} line(s) and the plan names "
                    f"lines {start}..{end} — the document is not the one the "
                    f"plan was drawn up against",
                    path)
                continue
            found = "\n".join(lines[start - 1:end])
            if found != operation["preimage"]:
                bad("apply-preimage-mismatch",
                    f"lines {start}..{end} of {path} are not the preimage the "
                    f"plan carries — the plan was drawn up against text that "
                    f"is not what is there, so nothing here was approved",
                    path)

    for operation in operations:
        if operation["op"] != OP_RETIRE:
            continue
        path = operation["path"]
        if texts.get(path) is None:
            bad("apply-preimage-missing",
                f"{path} is not in the working tree, so the document this "
                f"plan retires is not there to check",
                path)
        elif texts[path] != operation["preimage"]:
            bad("apply-preimage-mismatch",
                f"{path} is not the document the plan retires — retirement "
                f"carries the whole document as its preimage, and this one "
                f"has changed",
                path)

    if problems:
        return None

    new_texts = dict(texts)
    for path, ops in span_ops.items():
        lines = texts[path].split("\n")
        for operation in sorted(ops, key=_span_position, reverse=True):
            if operation["op"] == OP_INSERT:
                point = operation["after_line"]
                lines[point:point] = operation["text"].split("\n")
            else:
                start, end = operation["start_line"], operation["end_line"]
                replacement = (
                    operation["text"].split("\n")
                    if operation["op"] == OP_REPLACE else []
                )
                lines[start - 1:end] = replacement
        new_texts[path] = "\n".join(lines)

    for operation in sorted(
        appends, key=lambda op: (op["path"], op["start_line"])
    ):
        destination = operation["destination"]
        base = new_texts.get(destination)
        if base is None:
            bad("apply-preimage-missing",
                f"{destination} is not in the working tree, so the moved "
                f"text has nowhere approved to land",
                destination)
            continue
        if base and not base.endswith("\n"):
            base += "\n"
        new_texts[destination] = base + operation["preimage"] + "\n"

    for operation in creates:
        new_texts[operation["path"]] = operation["text"]
    for operation in operations:
        if operation["op"] == OP_RETIRE:
            new_texts[operation["path"]] = None

    return None if problems else new_texts


@dataclass(frozen=True)
class _WriteTransaction:
    """What one write found at each target, and what it left there.

    `snapshots` is the pre-write bytes of every path the write reached (None
    for one that was absent) — what rollback puts back. `written` is what this
    run left at that path (None for one it removed), recorded only once the
    write succeeded, which is what makes rollback compare-aware: a path in
    `snapshots` and not in `written` is one whose own write failed mid-flight,
    so whatever is there is this run's damage and is restored unconditionally.
    `created_dirs` are the directories a create brought into being, so a
    rolled-back one leaves no empty tree behind.
    """

    snapshots: dict
    written: dict
    created_dirs: list


def _write(repo_root, new_texts, preimages):
    """Recheck every target at the write boundary, then write it.

    The preimages were read, and the post-contents computed from them, before
    this — so between there and here another writer can have taken a target
    over, and writing then would silently overwrite work nobody in this
    transaction ever read. Each target is re-read immediately before it is
    mutated and must still be byte-for-byte the preimage this run captured; a
    target that moved is `apply-write-boundary-race`, and nothing of that
    writer's is touched.

    Returns (the transaction, Invalid|None); a refusal has already rolled this
    run's own writes back.
    """
    transaction = _WriteTransaction(snapshots={}, written={}, created_dirs=[])
    snapshots, written = transaction.snapshots, transaction.written
    created_dirs = transaction.created_dirs
    raced = None
    path = None
    try:
        for path in sorted(new_texts):
            full = os.path.join(repo_root, path)
            data, unreadable = _current_bytes(repo_root, path)
            if unreadable is not None:
                # Checked before anything was computed; only a race gets here.
                raise OSError(f"{path} {unreadable}")
            expected = preimages[path]
            if data != (None if expected is None else expected.encode("utf-8")):
                raced = path
                break
            snapshots[path] = data
            text = new_texts[path]
            if text is None:
                os.remove(full)
                written[path] = None
                continue
            parent = os.path.dirname(full)
            if parent:
                probe = parent
                while probe != repo_root and not os.path.exists(probe):
                    created_dirs.append(probe)
                    probe = os.path.dirname(probe)
                os.makedirs(parent, exist_ok=True)
            payload = text.encode("utf-8")
            with open(full, "wb") as fh:
                fh.write(payload)
            written[path] = payload
    except OSError as exc:
        return transaction, Invalid((Problem(
            code="apply-write-failed",
            message=(
                f"writing the plan failed at {path}: {exc} — "
                + _rollback_outcome(*_rollback(repo_root, transaction))
            ),
            location=path,
        ),))
    if raced is not None:
        return transaction, Invalid((Problem(
            code="apply-write-boundary-race",
            message=(
                f"{raced} is no longer the text this run read to compute the "
                f"plan's result — it changed between that read and the moment "
                f"it was to be written, so another writer holds it and the "
                f"post-content computed here is a remedy for text that is not "
                f"there. Nothing of theirs was overwritten. Commit or discard "
                f"what is there, then re-run the audit and mint afresh ("
                + _rollback_outcome(*_rollback(repo_root, transaction)) + ")"
            ),
            location=raced,
        ),))
    return transaction, None


def _rollback(repo_root, transaction):
    """Put back every path this run wrote — and only where it is still this
    run's to put back.

    Compare-aware, because an unconditional restore is a second lost update:
    a target holding something other than the bytes this transaction wrote has
    been taken over by another writer since, and overwriting it would destroy
    exactly the work the refusal exists to preserve. Such a path is left
    precisely as found and named in the outcome instead.

    Returns (paths it could not restore, paths it left to a later writer).
    """
    unrestored, foreign = [], []
    for path, data in transaction.snapshots.items():
        full = os.path.join(repo_root, path)
        if path in transaction.written:
            current, unreadable = _current_bytes(repo_root, path)
            if unreadable is not None or current != transaction.written[path]:
                foreign.append(path)
                continue
        try:
            if data is None:
                if os.path.lexists(full):
                    os.remove(full)
            else:
                with open(full, "wb") as fh:
                    fh.write(data)
        except OSError:
            unrestored.append(path)
    for full in sorted(transaction.created_dirs, key=len, reverse=True):
        try:
            os.rmdir(full)
        except OSError:
            # Not empty, or already gone — either way not this run's to force.
            continue
    return tuple(sorted(unrestored)), tuple(sorted(foreign))


def _rollback_outcome(unrestored, foreign=()):
    """The honest sentence about what the rollback achieved."""
    if not unrestored and not foreign:
        return "every write this run made has been rolled back"
    parts = []
    if unrestored:
        parts.append(
            f"rolling back failed for {list(unrestored)}, so the working tree "
            f"is NOT restored there"
        )
    if foreign:
        parts.append(
            f"{list(foreign)} no longer held the bytes this run wrote, so it "
            f"was left exactly as found rather than overwriting whoever wrote "
            f"it since"
        )
    return "; ".join(parts) + " — inspect it before trusting any diff"


def _certify(repo_root, new_texts):
    """Every written target's final bytes, against the post-content computed
    for it. Returns (the verified postimage manifest, None), or (None, problem).

    The last thing between a write and a `clean` result, and a different
    question from confinement: confinement asks which paths differ from HEAD,
    and a target whose content was replaced after this run wrote it is a path
    this plan legitimately writes, so it rides inside every path set the run
    checks. Only re-reading the bytes catches it — which is what makes `clean`
    mean the approved postimages are on disk rather than that this run once
    put them there.
    """
    manifest = []
    for path in sorted(new_texts):
        expected = new_texts[path]
        data, unreadable = _current_bytes(repo_root, path)
        if unreadable is not None:
            return None, Problem(
                code="apply-postimage-not-on-disk",
                message=(
                    f"{path} {unreadable}, so this run cannot certify that it "
                    f"holds the result the plan was approved for — something "
                    f"replaced it after the write"
                ),
                location=path,
            )
        if expected is None:
            if data is not None:
                return None, Problem(
                    code="apply-postimage-not-on-disk",
                    message=(
                        f"{path} was retired by this run and is on disk again "
                        f"— the final state of a retired document is its "
                        f"absence, and something wrote it back"
                    ),
                    location=path,
                )
            manifest.append((path, None))
            continue
        if data != expected.encode("utf-8"):
            return None, Problem(
                code="apply-postimage-not-on-disk",
                message=(
                    f"{path} does not hold the post-content this run wrote — "
                    f"it changed between the write and this certification, so "
                    f"the bytes on disk are not the ones the approval "
                    f"authorized and this run will not certify them as such"
                ),
                location=path,
            )
        manifest.append((path, sha256_bytes(data)))
    return tuple(manifest), None


def _confinement_problem(repo_root, scope, code):
    """Every changed path in the whole tree, checked against the scope."""
    changed, problem = worktree_changes(repo_root)
    if problem is not None:
        # The diff could not be read, which certifies nothing. Fail closed.
        return None, problem
    outside = sorted(set(changed) - set(scope.paths))
    if outside:
        return None, Problem(
            code=code,
            message=(
                f"the working tree differs from HEAD at {outside}, outside "
                f"the approval set's allowed mutation scope "
                f"{list(scope.paths)} — the complete diff of the change this "
                f"approval authorizes must be inside its scope, so an "
                f"unaccounted change fails the run rather than riding into a "
                f"commit"
            ),
            location=outside[0],
        )
    return changed, None


def _unaccounted_problem(paths):
    """The refusal for a difference from HEAD this plan did not make, or None.

    The applier certifies its whole diff as the approved change, so it applies
    onto the committed baseline and nothing else. The scope check above is
    path-granular; this one is not, because a change to another passage of an
    approved document is a change no record covers and no unit-level preimage
    check sees.
    """
    if not paths:
        return None
    return Problem(
        code="apply-working-tree-not-clean",
        message=(
            f"the working tree already differs from HEAD at {list(paths)}, "
            f"which this plan does not write — inside the approval set's "
            f"scope, but produced by something other than this plan, so it "
            f"would ride into the diff this run certifies. Commit or discard "
            f"what is there first"
        ),
        location=paths[0],
    )


def apply_edit_plan(repo_root, plan, approval_payload, *, report=None,
                    registry_path=DEFAULT_REGISTRY_PATH,
                    audit_config_digest=None, expected_digest=None):
    """Execute an edit plan under its approval set. The one write path.

    Returns an `ApplyResult` (`clean` — applied, or already applied — or
    `stale`, refused with every moved lineage field named), or `Invalid` with
    every problem found. Every refusal leaves the working tree byte-identical;
    nothing is ever staged or committed here — change approval is a person's.

    `plan` and `approval_payload` are data — payload dicts, exactly as read
    off disk. Validation is internal so it cannot be skipped, and so the
    approval set is always checked against the repository *and* the `report`
    it names. The report is not optional: without it, every remaining check is
    a function of public repository state, so anyone who can read the repo
    could hand over a selection nobody ever minted and have it validate.
    """
    approval = validate_approval_set(
        approval_payload, report=report, repo_root=repo_root,
        registry_path=registry_path, audit_config_digest=audit_config_digest,
        expected_digest=expected_digest,
    )
    if isinstance(approval, Invalid):
        return approval

    if approval.unchecked:
        return Invalid(tuple(
            Problem(
                code=f"approval-unchecked-{check}",
                message=(
                    f"the approval set was validated without its {check}: "
                    f"{UNCHECKED_MEANING[check]} — the applier's whole "
                    f"authority is this artifact, so a verdict that skipped a "
                    f"check is not one it may write from"
                ),
                location=check,
            )
            for check in approval.unchecked
        ))

    invalid = _validate_plan(plan, approval)
    if invalid is not None:
        return invalid

    refused = tuple(
        r for r in approval.stale_reasons
        if r.code not in PREIMAGE_REASON_CODES
    )
    if refused:
        # The world moved under the approval in a way no reapply explains:
        # refuse before reading any document, naming every field.
        return ApplyResult(
            status=STATE_STALE,
            approval_digest=approval.digest,
            plan_digest=plan["digest"],
            stale_reasons=approval.stale_reasons,
        )

    operations = plan["operations"]
    # Before idempotency, not after: the approved passage is measured against
    # the committed baseline, and an operation reaching outside it is one an
    # attacker can pre-place on disk so that nothing has to be written for the
    # run to certify it.
    spans = _approved_span_problems(
        repo_root, operations, {r.digest: r for r in approval.records}
    )
    if spans:
        return Invalid(spans)

    # A create-document's destination is re-classified against the registry
    # here, before idempotency: like the span bound, this must hold even when
    # nothing has to be written — an attacker who pre-places the file at an
    # ineligible destination would otherwise have the run certify it as
    # already applied.
    dests = _residue_destination_problems(repo_root, operations, registry_path)
    if dests:
        return Invalid(dests)

    certified = _already_applied(repo_root, operations, plan["postimages"])
    if certified is not None:
        # This plan applied to the committed baseline is exactly what is on
        # disk, and the diff is confined to the paths the plan writes. A
        # narrower fact than an apply — this run wrote nothing — but a derived
        # one: nothing here rests on what the plan declared about itself.
        changed, problem = _confinement_problem(
            repo_root, approval.scope, "apply-working-tree-not-confined"
        )
        if problem is None:
            problem = _unaccounted_problem(
                sorted(set(changed) - _written_paths(operations))
            )
        if problem is not None:
            return Invalid((problem,))
        return ApplyResult(
            status=STATE_CLEAN,
            approval_digest=approval.digest,
            plan_digest=plan["digest"],
            changed_paths=changed,
            already_applied=True,
            postimages=certified,
        )

    if approval.stale_reasons:
        # Preimage staleness that is not "already applied": the targets were
        # rewritten by something other than this plan. Same refusal as any
        # other moved field.
        return ApplyResult(
            status=STATE_STALE,
            approval_digest=approval.digest,
            plan_digest=plan["digest"],
            stale_reasons=approval.stale_reasons,
        )

    # Nothing may already differ from HEAD. The whole-diff confinement check
    # below is path-granular, so without this a change to another passage of
    # an approved document — one no record covers, and so one no unit-level
    # preimage check sees — would ride into the diff this run certifies.
    changed, problem = _confinement_problem(
        repo_root, approval.scope, "apply-working-tree-not-confined"
    )
    if problem is None:
        problem = _unaccounted_problem(changed)
    if problem is not None:
        return Invalid((problem,))

    problems = []
    texts = _read_texts(repo_root, operations, problems)
    new_texts = _compute_postimages(texts, operations, problems)
    if problems:
        return Invalid(tuple(problems))

    for path, digest in plan["postimages"].items():
        text = new_texts[path]
        if digest is None:
            continue
        if sha256_bytes(text.encode("utf-8")) != digest:
            problems.append(Problem(
                code="apply-postimage-mismatch",
                message=(
                    f"applying the plan to {path} does not produce the "
                    f"postimage it declares — the operations and the declared "
                    f"result disagree, so one of them is not what was reviewed"
                ),
                location=path,
            ))
    if problems:
        return Invalid(tuple(problems))

    transaction, failed = _write(repo_root, new_texts, texts)
    if failed is not None:
        return failed

    changed, problem = _confinement_problem(
        repo_root, approval.scope, "apply-unconfined-change"
    )
    certified = ()
    if problem is None:
        # The scope check above is path-granular against the whole approval,
        # not this plan's operations — a record with a destination puts both
        # ends in scope (`derived_scope_paths`), but not every remedy for one
        # writes both: a DISTILL record's `create-document` writes only the
        # destination, leaving its source in scope but unwritten by this
        # plan. A concurrent change landing there is inside the approval's
        # scope and so would pass the check above, then ride into the diff
        # this run certifies as its own. Same exact-path comparison the
        # already-applied branch above makes.
        problem = _unaccounted_problem(
            sorted(set(changed) - _written_paths(operations))
        )
    if problem is None:
        # Path confinement and byte binding are separate checks, and this is
        # the byte one: every target re-read and compared with the
        # post-content computed for it. A path set cannot answer it — a target
        # somebody replaced after the write is still a path this plan writes —
        # so nothing may be reported clean until this has held.
        certified, problem = _certify(repo_root, new_texts)
    if problem is not None:
        # An unaccounted change or a moved target surfaced after the write —
        # roll this run's own writes back to the snapshotted bytes and refuse;
        # whatever else moved the tree is left exactly as found, for a human to
        # look at.
        return Invalid((Problem(
            code=problem.code,
            message=(
                problem.message + " ("
                + _rollback_outcome(*_rollback(repo_root, transaction)) + ")"
            ),
            location=problem.location,
        ),))

    applied = tuple(
        AppliedOperation(
            op=operation["op"],
            record=operation["record"],
            path=operation["path"],
            destination=operation.get("destination"),
        )
        for operation in operations
    )
    return ApplyResult(
        status=STATE_CLEAN,
        approval_digest=approval.digest,
        plan_digest=plan["digest"],
        applied=applied,
        changed_paths=changed,
        postimages=certified,
    )
