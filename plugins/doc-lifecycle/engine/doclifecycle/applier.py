"""The applier: the deterministic component that writes, and nothing else does.

An **edit plan** is a separate versioned artifact: a small closed vocabulary of
operations (replace, delete, insert, create-document, retire-document,
move-with-provenance), each declaring the approved record it comes from and the
target class it is allowed to write. The plan binds to exactly one approval set
by digest, and the approval set is the sole authority the applier accepts.

The applier's whole job is refusal discipline around one small write:

- **Authority first.** The approval set is validated against the report it
  names and the repository it authorizes changes to. A lineage field that moved
  is a stale refusal naming the field, with no working-tree change; a selection
  no minter would have produced is invalid.
- **Operations are checked, not trusted.** Every operation must come from an
  approved record, write only that record's own targets, declare a declarable
  target class, spell its paths canonically (`paths.write_target_problem`, the
  same owner the approval set uses), carry an exact preimage, and overlap or
  repeat nothing.
- **The write is total or absent.** Every post-content is computed and checked
  against the plan's declared postimages before any byte lands; any problem
  leaves the tree byte-identical.
- **The whole diff is confined.** Before and after writing, the complete
  working-tree diff (index, work tree, and untracked files) is read from git
  and compared against the approval set's allowed mutation scope. An
  unaccounted change fails the run — and rolls the applier's own writes back —
  rather than riding into a commit nobody approved.
- **Reapplying is idempotent.** A plan whose every postimage is already on disk
  is a no-op, so re-running an interrupted lane is safe; the applier never
  stages and never commits — change approval (a person merging or committing)
  is the only thing that lands anything.

Model-generated content reaches this module only as data inside the plan and
report artifacts: the applier runs no shell, executes nothing it reads, and the
one external program in the whole flow is git — run read-only, behind
`repository.worktree_changes`, never from this module.
"""

import hashlib
import json
import os
from dataclasses import dataclass
from typing import Optional, Tuple

from . import ARTIFACT_SCHEMA_VERSION
from .approval import validate_approval_set
from .digest import sha256_canonical
from .inventory import DEFAULT_REGISTRY_PATH
from .paths import DECLARABLE_TARGET_CLASSES, write_target_problem
from .report import DIGEST, StaleReason
from .repository import worktree_changes
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

# The operations that name a line span in an existing document.
SPAN_OPS = (OP_REPLACE, OP_DELETE, OP_MOVE)
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

    `clean` means the plan's postimages are on disk and the complete
    working-tree diff is inside the approval set's allowed mutation scope —
    whether this run wrote them (`applied` names each operation) or found them
    already there (`already_applied`, the idempotent re-run). `stale` means the
    approval expired and nothing was touched; the reasons name every field that
    moved and say to re-run the audit and mint afresh. Anything else about the
    run is `Invalid`, never a weaker success.
    """

    status: str
    approval_digest: str
    plan_digest: str
    applied: Tuple[AppliedOperation, ...] = ()
    changed_paths: Tuple[str, ...] = ()
    already_applied: bool = False
    stale_reasons: Tuple[StaleReason, ...] = ()

    def to_dict(self):
        payload = {
            "status": self.status,
            "schema_version": ARTIFACT_SCHEMA_VERSION,
            "approval_digest": self.approval_digest,
            "plan_digest": self.plan_digest,
            "applied": [op.to_dict() for op in self.applied],
            "changed_paths": list(self.changed_paths),
            "already_applied": self.already_applied,
        }
        if self.stale_reasons:
            payload["stale_reasons"] = [r.to_dict() for r in self.stale_reasons]
        return payload


def _sha256(data):
    return hashlib.sha256(data).hexdigest()


def _reject_constant(name):
    raise ValueError(
        f"{name} is not JSON — an edit plan must survive a strict parser and "
        f"its own digest, which are taken over the same encoding"
    )


def _read_payload(path, prefix, noun):
    """A JSON payload off disk, or `Invalid` with `<prefix>-*` codes."""
    try:
        with open(path, encoding="utf-8") as fh:
            text = fh.read()
    except OSError as exc:
        return Invalid((Problem(
            code=f"{prefix}-unreadable",
            message=f"cannot read the {noun} at {path}: {exc.strerror}",
            location=path,
        ),))
    except UnicodeDecodeError as exc:
        return Invalid((Problem(
            code=f"{prefix}-unreadable",
            message=(
                f"the {noun} at {path} is not valid UTF-8 ({exc.reason} at "
                f"byte {exc.start}) — re-encode it; JSON is a text format"
            ),
            location=path,
        ),))
    try:
        return json.loads(text, parse_constant=_reject_constant)
    except (json.JSONDecodeError, ValueError, RecursionError) as exc:
        return Invalid((Problem(
            code=f"{prefix}-unparseable",
            message=f"the {noun} is not valid JSON: {exc}",
            location=path,
        ),))


def load_edit_plan(path):
    """Read an edit-plan file. Returns the payload dict, or `Invalid`.

    Reading only: validation needs the approval set the plan binds to, so it
    happens inside `apply_edit_plan`, where that authority is in hand.
    """
    return _read_payload(path, "plan", "edit plan")


def load_approval_payload(path):
    """Read an approval-set file *as data*, for handing to `apply_edit_plan`.

    Deliberately unvalidated here: the applier validates the payload itself,
    against the report and the repository, so a caller cannot accidentally
    hand it a weaker (structural-only) verdict.
    """
    return _read_payload(path, "approval", "approval set")


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
    if operation["op"] == OP_MOVE:
        if (operation["path"] != record.path
                or operation["destination"] != record.destination):
            bad("plan-target-not-record-target",
                f"operations[{i}] moves {operation['path']!r} to "
                f"{operation['destination']!r}, and record {record.record_id} "
                f"was approved for {record.path!r} to "
                f"{record.destination!r} — a move writes exactly the two "
                f"documents its record was approved for",
                where)
    elif operation["path"] not in record.targets():
        bad("plan-target-not-record-target",
            f"operations[{i}] writes {operation['path']!r}, and record "
            f"{record.record_id} was approved for {list(record.targets())} — "
            f"an operation writes only its own record's targets, so a "
            f"borrowed path is a document nobody approved this edit for",
            where)


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
        if whole and (len(entries) > 1 or path in destinations):
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

    if len(usable) == len(operations):
        _conflict_problems(operations, bad)
        _postimage_problems(payload, operations, bad)

    return Invalid(tuple(problems)) if problems else None


def _current_bytes(repo_root, path):
    """The file's bytes, or None when nothing is there.

    `lexists` first, so a symlink — even a broken one — is never read through:
    what it points at is not this repository's document. The caller treats
    "present but not a plain readable file" as a preimage that cannot match.
    """
    full = os.path.join(repo_root, path)
    if not os.path.lexists(full):
        return None
    if os.path.islink(full) or not os.path.isfile(full):
        return b""
    try:
        with open(full, "rb") as fh:
            return fh.read()
    except OSError:
        return b""


def _already_applied(repo_root, postimages):
    """True when every declared postimage is already on disk."""
    for path, digest in postimages.items():
        data = _current_bytes(repo_root, path)
        if digest is None:
            if data is not None:
                return False
        elif data is None or _sha256(data) != digest:
            return False
    return True


def _compute_postimages(repo_root, operations, problems):
    """{path: new text or None} after every operation, or None with problems.

    Deterministic order: per document, span edits apply bottom-up (so line
    numbers stay what the plan named), inserts at a boundary apply before a
    span starting on the same line, and moved text is appended to its
    destination in (source path, span) order after the destination's own span
    edits. Every preimage is compared exactly before anything is computed.
    """
    def bad(code, message, where=None):
        problems.append(Problem(code=code, message=message, location=where))

    texts = {}
    for path in sorted(_written_paths(operations)):
        data = _current_bytes(repo_root, path)
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


def _write(repo_root, new_texts):
    """Write every computed post-content. Returns (snapshots, Invalid|None).

    Snapshots are the pre-write bytes (None for a path that was absent), taken
    path by path as each is written, so any failure — mid-write or the
    post-apply confinement check — can put back exactly what was there.
    """
    snapshots = {}
    path = None
    try:
        for path in sorted(new_texts):
            full = os.path.join(repo_root, path)
            snapshots[path] = _current_bytes(repo_root, path)
            text = new_texts[path]
            if text is None:
                os.remove(full)
                continue
            parent = os.path.dirname(full)
            if parent:
                os.makedirs(parent, exist_ok=True)
            with open(full, "wb") as fh:
                fh.write(text.encode("utf-8"))
    except OSError as exc:
        _rollback(repo_root, snapshots)
        return snapshots, Invalid((Problem(
            code="apply-write-failed",
            message=(
                f"writing the plan failed at {path}: {exc.strerror} — every "
                f"write this run made has been rolled back"
            ),
            location=path,
        ),))
    return snapshots, None


def _rollback(repo_root, snapshots):
    """Best-effort restore of every path this run touched."""
    for path, data in snapshots.items():
        full = os.path.join(repo_root, path)
        try:
            if data is None:
                if os.path.lexists(full):
                    os.remove(full)
            else:
                with open(full, "wb") as fh:
                    fh.write(data)
        except OSError:
            continue


def _confinement_problem(repo_root, scope, when):
    """Every changed path in the whole tree, checked against the scope."""
    changed, problem = worktree_changes(repo_root)
    if problem is not None:
        # The diff could not be read, which certifies nothing. Fail closed.
        return None, problem
    outside = sorted(set(changed) - set(scope.paths))
    if outside:
        return None, Problem(
            code=(
                "apply-working-tree-not-confined" if when == "before"
                else "apply-unconfined-change"
            ),
            message=(
                f"the working tree differs from HEAD at {outside}, outside "
                f"the approval set's allowed mutation scope "
                f"{list(scope.paths)} — the complete diff of the change this "
                f"approval authorizes must be inside its scope, so an "
                f"unaccounted change fails the run rather than riding into a "
                f"commit"
                + (" (every write this run made has been rolled back)"
                   if when == "after" else "")
            ),
            location=outside[0],
        )
    return changed, None


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
    approval set is always checked against the repository (and the `report`,
    when supplied — supply it: a record's remedy text lives there, and without
    it the selection is not checked against the records it names).
    """
    approval = validate_approval_set(
        approval_payload, report=report, repo_root=repo_root,
        registry_path=registry_path, audit_config_digest=audit_config_digest,
        expected_digest=expected_digest,
    )
    if isinstance(approval, Invalid):
        return approval

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

    if _already_applied(repo_root, plan["postimages"]):
        changed, problem = _confinement_problem(repo_root, approval.scope, "before")
        if problem is not None:
            return Invalid((problem,))
        return ApplyResult(
            status=STATE_CLEAN,
            approval_digest=approval.digest,
            plan_digest=plan["digest"],
            changed_paths=changed,
            already_applied=True,
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

    problems = []
    operations = plan["operations"]
    new_texts = _compute_postimages(repo_root, operations, problems)
    if problems:
        return Invalid(tuple(problems))

    for path, digest in plan["postimages"].items():
        text = new_texts[path]
        if digest is None:
            continue
        if _sha256(text.encode("utf-8")) != digest:
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

    _, problem = _confinement_problem(repo_root, approval.scope, "before")
    if problem is not None:
        return Invalid((problem,))

    snapshots, failed = _write(repo_root, new_texts)
    if failed is not None:
        return failed

    changed, problem = _confinement_problem(repo_root, approval.scope, "after")
    if problem is not None:
        # An unaccounted change surfaced after the write — roll this run's own
        # writes back to the snapshotted bytes and refuse; whatever else moved
        # the tree is left exactly as found, for a human to look at.
        _rollback(repo_root, snapshots)
        return Invalid((problem,))

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
    )
