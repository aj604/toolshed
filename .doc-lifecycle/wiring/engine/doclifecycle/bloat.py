"""The bloat audit: value judgments, checked against global context (issue #66).

Drift asks whether a document is *accurate*; bloat asks whether it is *worth
its tokens*. That second question is never answerable from one document. A
passage is redundant only relative to what the rest of the corpus says; content
is misplaced only relative to which document owns the subject; a merge is safe
only relative to what every other merge is doing. The legacy skill's chunk
workers had none of that — a chunk's records could name only documents in its
own slice, there was no cross-chunk channel, and a duplicate pair split across
two chunks was invisible to both. This module is the replacement: workers keep
their bounded slices for cost, and every cross-document question is answered by
`context.ContextIndex`, built over the whole repository before any slicing.

The division of labor is the same one `finding.record_classifications()` draws.
The model supplies judgment — is this worth keeping, and what should replace it
— and nothing else. The engine supplies every fact: which documents exist, where
a unit occurs, which document owns it, who else is merging into a destination,
and exactly which files a bulk scope covers. All of it comes from the index —
including the two facts about a path holding no document at all, which the index
answers from the registry and repository it was built from
(`context.ContextIndex.registry` / `.repo_root`), because a distillation's
residue destination is a document nobody has written yet. `record_verdicts()` is where the
two meet, and it fails closed: a destination the index contradicts, a unit that
is not in the document it is claimed against, or a bulk judgment backed by a
sample rather than an enumeration is refused, exhaustively, recording nothing.

Two departures from the legacy contract, both from #57's distilled decisions.

**`POLICY` is gone.** A bulk judgment no longer rides on a hand-declared
directory whose file list the model echoes back. It declares an *enumerable
inclusion rule* — a document set, a glob, or a kind — and the engine expands it
from the index into one finding per member. Sampling survives only as review
prioritization, recorded as such and never as the member list, which is what
"sampling never authorizes mutation" has to mean mechanically.

**Destinations are resolved, not asserted.** The legacy validator checked only
that a `target` was a non-empty string; it could be a nonexistent file, the
source document itself, or prose. Here a destination is checked against the
index, and for duplicated content it is *derived* from the index — so two chunks
that never see each other reach the same answer.
"""

import json
import os
from dataclasses import dataclass, field
from typing import Dict, Optional, Tuple

from . import ARTIFACT_SCHEMA_VERSION
from .cache import cache_key, get as cache_get, put as cache_put
from .context import KIND_PRECEDENCE, LIFECYCLE_STATUSES, build_context_index
from .digest import sha256_canonical
from .finding import Finding, build_finding
from .inventory import DEFAULT_REGISTRY_PATH
from .paths import DOCUMENTATION, authorize_path
from .registry import compile_glob
from .report import (
    WHOLE_DOCUMENT_RECORD_CODES,
    EvidenceBoundary, Lineage, SCOPE_WHOLE_INVENTORY, current_lineage,
    state_from_content,
    validate_report, whole_number,
)
from .results import STATUS_OK, Invalid, Problem

# The verdicts, carried over from the skill this absorbs so a reviewer reading
# an old report and a new one is reading the same vocabulary.
CUT = "CUT"                            # restates what is self-evident; delete
CONDENSE = "CONDENSE"                  # many lines, one checkable fact
EXTRACT_AND_MOVE = "EXTRACT-AND-MOVE"  # right content, wrong document
MERGE_DOC = "MERGE-DOC"                # near-duplicate; fold into the survivor
RETIRE_DOC = "RETIRE-DOC"              # carries nothing another document lacks
DISTILL = "DISTILL"                    # planning artifact; residue, then retire

VERDICTS = (CUT, CONDENSE, EXTRACT_AND_MOVE, MERGE_DOC, RETIRE_DOC, DISTILL)

# Verdicts that move content somewhere, and so must name where. These are
# exactly the ones a worker cannot decide from its slice.
DESTINATION_VERDICTS = (EXTRACT_AND_MOVE, MERGE_DOC)
# Verdicts whose destination is a document that does not exist yet: a
# distillation authors the durable residue of a planning artifact, so its
# destination is *optional* (the residue may already have a home) and is checked
# as an unwritten path rather than looked up in the inventory, which by
# definition does not hold it.
RESIDUE_VERDICTS = (DISTILL,)
# Verdicts that replace text, and so must carry the replacement.
PROPOSAL_VERDICTS = (CONDENSE, EXTRACT_AND_MOVE)
# Verdicts eligible for bulk expansion over a deterministic scope. Retirement
# only: a scope-wide CUT or CONDENSE would be a per-passage judgment nobody
# made, and a scope-wide move would need a per-document destination.
SCOPE_VERDICTS = (RETIRE_DOC,)

# Verdicts whose remedy retires the source document. Unlike passage remedies,
# their subject is the complete current deterministic segmentation: approving
# fewer units must never authorize deletion of the units left behind.
WHOLE_DOCUMENT_VERDICTS = WHOLE_DOCUMENT_RECORD_CODES

# Owned by context.py, not repeated here: `_status()` checks a verdict's
# status *against* the planning document's own file-bound marker, so the set
# of legal values has to be the one thing both sides read, never two lists
# that could quietly disagree.
DISTILL_STATUSES = LIFECYCLE_STATUSES

# A destination must be a document content can durably live in. Planning
# documents are temporary and end in distillation or retirement, so nothing is
# ever moved *into* one — the move would be undone by the target's own lifecycle.
DESTINATION_KINDS = ("living", "narrative")


def residue_destination_ineligibility(registry, destination):
    """Why the registry refuses `destination` as distilled residue, or None.

    The single reading — closed-world classification, then kind-eligibility —
    that the audit plans a DISTILL destination against
    (`_residue_destination_record`) and the applier re-answers at
    create-document time, so the two seams cannot diverge on what the registry
    says a residue path is. Confinement (`paths.authorize_path`) and occupancy
    (a path already there) are separate owners, re-answered separately.

    Returns `(reason, rule)`: `reason` is `"unclassified"` (no rule claims the
    path as documentation, or a rule excludes it — `rule` is then None or the
    excluded rule and not to be trusted), `"kind-ineligible"` (classified, but
    of a kind residue is never authored into — `rule` is that rule), or None
    (eligible — `rule` is the classifying rule the caller records).
    """
    rule = registry.classify(destination)
    if (rule is None or not registry.is_document(destination)
            or registry.excludes(destination)):
        return "unclassified", rule
    if rule.kind not in DESTINATION_KINDS:
        return "kind-ineligible", rule
    return None, rule

VERDICT_FIELDS = (
    "id", "verdict", "path", "units", "evidence",
    "destination", "proposal", "status", "scope", "sample",
)

# Keys a model may not supply at all. `files` is the one that matters: it is
# how the legacy contract let a bulk record assert its own membership, and
# asserted membership is precisely what an enumeration replaces.
FORBIDDEN_VERDICT_FIELDS = ("files", "members", "occurrences", "contention")

SCOPE_SELECTORS = ("set", "glob", "kind")

DEFAULT_MAX_DOCUMENTS = 8
DEFAULT_MAX_UNITS = 400

COMPLETION_COMPLETE = "complete"
COMPLETION_MISSING = "missing"
COMPLETION_INVALID = "invalid"
COMPLETION_STATES = (
    COMPLETION_COMPLETE, COMPLETION_MISSING, COMPLETION_INVALID,
)


# --------------------------------------------------------------------------
# Chunk planning
# --------------------------------------------------------------------------

@dataclass(frozen=True)
class Chunk:
    """One bounded slice of the corpus, and the documents in it."""

    chunk_id: str
    documents: Tuple[str, ...]
    unit_count: int

    def to_dict(self):
        return {
            "id": self.chunk_id,
            "documents": list(self.documents),
            "unit_count": self.unit_count,
        }


@dataclass(frozen=True)
class ChunkPlan:
    """Every indexed document, partitioned into chunks exactly once."""

    chunks: Tuple[Chunk, ...]
    index_digest: str
    max_documents: int
    max_units: int
    digest: str
    status: str = STATUS_OK

    def to_dict(self):
        return {
            "status": self.status,
            "schema_version": ARTIFACT_SCHEMA_VERSION,
            "index_digest": self.index_digest,
            "max_documents": self.max_documents,
            "max_units": self.max_units,
            "digest": self.digest,
            "chunks": [c.to_dict() for c in self.chunks],
        }

    def chunk(self, chunk_id):
        return next((c for c in self.chunks if c.chunk_id == chunk_id), None)


def _chunk_id(index, paths):
    """A chunk's identity: its members and their current contents.

    Content-addressed, so an unchanged chunk keeps its id across re-plans (a
    resumed run can tell what it already did) and an edited document re-keys
    only the chunk holding it.
    """
    members = [
        {"path": path, "document_digest": index.document(path).document_digest}
        for path in paths
    ]
    return "c-" + sha256_canonical({"members": members})[:16]


def positive_chunk_budget(value, name):
    """Return one valid chunk budget, or reject it by its public name."""
    if not whole_number(value) or value < 1:
        raise ValueError(f"{name} must be a positive integer, not {value!r}")
    return value


def _chunk_budgets(max_documents, max_units):
    """Validate both public budgets once, before planning can observe them."""
    return (
        positive_chunk_budget(max_documents, "max_documents"),
        positive_chunk_budget(max_units, "max_units"),
    )


def plan_chunks(index, max_documents=DEFAULT_MAX_DOCUMENTS,
                max_units=DEFAULT_MAX_UNITS):
    """Partition the index into bounded chunks. Deterministic and total.

    Documents are grouped by directory and kind — neighbors are the documents
    most likely to duplicate each other, so a worker sees related prose — then
    packed greedily within both budgets. Every indexed document lands in
    exactly one chunk: a document dropped for being oversized would be a silent
    coverage gap, so one that exceeds the unit budget alone gets a chunk to
    itself rather than being split or skipped.
    """
    max_documents, max_units = _chunk_budgets(max_documents, max_units)
    return _plan_chunks(index, max_documents, max_units)


def _plan_chunks(index, max_documents, max_units):
    """Plan with budgets already validated by the public entrypoint."""
    groups = {}
    for document in index.documents:
        directory = document.path.rsplit("/", 1)[0] if "/" in document.path else ""
        groups.setdefault((directory, document.kind), []).append(document)

    chunks, current, current_units = [], [], 0

    def flush():
        nonlocal current, current_units
        if current:
            chunks.append((tuple(d.path for d in current), current_units))
            current, current_units = [], 0

    for key in sorted(groups):
        for document in sorted(groups[key], key=lambda d: d.path):
            size = len(document.units)
            over_documents = len(current) + 1 > max_documents
            over_units = current_units + size > max_units
            if current and (over_documents or over_units):
                flush()
            current.append(document)
            current_units += size
        flush()

    built = tuple(
        Chunk(chunk_id=_chunk_id(index, paths), documents=paths, unit_count=units)
        for paths, units in chunks
    )
    return ChunkPlan(
        chunks=built,
        index_digest=index.digest,
        max_documents=max_documents,
        max_units=max_units,
        digest=sha256_canonical({
            "schema_version": ARTIFACT_SCHEMA_VERSION,
            "index_digest": index.digest,
            "max_documents": max_documents,
            "max_units": max_units,
            "chunks": [c.to_dict() for c in built],
        }),
    )


def plan_repository_chunks(repo_root, registry_path=DEFAULT_REGISTRY_PATH,
                           max_documents=DEFAULT_MAX_DOCUMENTS,
                           max_units=DEFAULT_MAX_UNITS):
    """Index `repo_root` and plan its chunks. A `ChunkPlan`, or `Invalid`.

    The repository-level entrypoint, on `segment.segment_document()`'s pattern:
    the index-then-plan composition lives here rather than in the command, so
    the command stays a call to one library function and an import cannot
    disagree with a CI invocation. An invalid registry invalidates the run, as
    it does everywhere else.
    """
    max_documents, max_units = _chunk_budgets(max_documents, max_units)
    index = build_context_index(repo_root, registry_path)
    if isinstance(index, Invalid):
        return index
    return _plan_chunks(index, max_documents, max_units)


def chunk_plan_from_dict(raw):
    """Parse a serialized engine plan without claiming its index is current.

    Scheduler adapters use this to preserve the exact plan artifact they were
    handed.  `validate_chunk_plan` remains the authority that independently
    rebuilds it from the repository's current index before an audit can be
    called complete.
    """
    fields = {
        "status", "schema_version", "index_digest", "max_documents",
        "max_units", "digest", "chunks",
    }
    if not isinstance(raw, dict) or set(raw) != fields:
        return Invalid((Problem(
            code="bloat-completion-plan-invalid",
            message=f"completion.plan must carry exactly {sorted(fields)}",
            location="completion.plan",
        ),))
    if (raw.get("status") != STATUS_OK
            or not whole_number(raw.get("schema_version"))
            or raw["schema_version"] != ARTIFACT_SCHEMA_VERSION):
        return Invalid((Problem(
            code="bloat-completion-plan-invalid",
            message="completion.plan must be a successful current-schema plan",
            location="completion.plan",
        ),))
    max_documents, max_units = raw.get("max_documents"), raw.get("max_units")
    if not (whole_number(max_documents) and max_documents > 0
            and whole_number(max_units) and max_units > 0):
        return Invalid((Problem(
            code="bloat-completion-plan-invalid",
            message="completion.plan budgets must be positive integers",
            location="completion.plan",
        ),))
    digests = (raw.get("index_digest"), raw.get("digest"))
    if not all(isinstance(value, str) and len(value) == 64
               and all(char in "0123456789abcdef" for char in value)
               for value in digests):
        return Invalid((Problem(
            code="bloat-completion-plan-invalid",
            message="completion.plan index_digest and digest must be sha256 digests",
            location="completion.plan",
        ),))
    chunks = raw.get("chunks")
    if not isinstance(chunks, list):
        return Invalid((Problem(
            code="bloat-completion-plan-invalid",
            message="completion.plan.chunks must be a list",
            location="completion.plan.chunks",
        ),))
    built = []
    for position, chunk in enumerate(chunks):
        if (not isinstance(chunk, dict)
                or set(chunk) != {"id", "documents", "unit_count"}
                or not isinstance(chunk.get("id"), str)
                or not chunk["id"].strip()
                or not isinstance(chunk.get("documents"), list)
                or not all(isinstance(path, str) and path.strip()
                           for path in chunk["documents"])
                or not whole_number(chunk.get("unit_count"))
                or chunk["unit_count"] < 0):
            return Invalid((Problem(
                code="bloat-completion-plan-invalid",
                message=f"completion.plan.chunks[{position}] has invalid shape",
                location=f"completion.plan.chunks[{position}]",
            ),))
        built.append(Chunk(
            chunk_id=chunk["id"], documents=tuple(chunk["documents"]),
            unit_count=chunk["unit_count"],
        ))
    canonical = {
        "schema_version": raw["schema_version"],
        "index_digest": raw["index_digest"],
        "max_documents": max_documents,
        "max_units": max_units,
        "chunks": [chunk.to_dict() for chunk in built],
    }
    if raw["digest"] != sha256_canonical(canonical):
        return Invalid((Problem(
            code="bloat-completion-plan-invalid",
            message="completion.plan digest does not match its serialized contents",
            location="completion.plan.digest",
        ),))
    return ChunkPlan(
        chunks=tuple(built), index_digest=raw["index_digest"],
        max_documents=max_documents, max_units=max_units,
        digest=raw["digest"],
    )


@dataclass(frozen=True)
class ChunkOutcome:
    """What assembly received for one planned chunk."""

    chunk_id: str
    completion_state: str
    verdicts: Tuple[dict, ...] = ()
    reason: str = ""

    @classmethod
    def complete(cls, chunk_id, verdicts):
        return cls(chunk_id, COMPLETION_COMPLETE, tuple(verdicts), "")

    @classmethod
    def missing(cls, chunk_id, reason):
        return cls(chunk_id, COMPLETION_MISSING, (), reason)

    @classmethod
    def invalid(cls, chunk_id, reason):
        return cls(chunk_id, COMPLETION_INVALID, (), reason)


@dataclass(frozen=True)
class BloatAuditInput:
    """The one public artifact a completed fan-out hands to `audit_bloat`."""

    verdicts: Tuple[dict, ...]
    plan: ChunkPlan
    chunks: Tuple[dict, ...]
    digest: str

    def to_dict(self):
        return {
            "schema_version": ARTIFACT_SCHEMA_VERSION,
            "verdicts": [dict(verdict) for verdict in self.verdicts],
            "completion": {
                "plan": self.plan.to_dict(),
                "chunks": [dict(chunk) for chunk in self.chunks],
                "digest": self.digest,
            },
        }


def _completion_digest(plan_digest, chunks, verdicts):
    """Identity of the authentic plan and every received verdict byte-shape."""
    return sha256_canonical({
        "plan_digest": plan_digest,
        "chunks": chunks,
        "verdicts": verdicts,
    })


def assemble_bloat_input(plan, outcomes):
    """Bind one deterministic plan to the chunk results assembly received.

    `outcomes` is one `ChunkOutcome` per planned chunk, in plan order. The
    function owns global verdict labels, per-result content digests, and the
    completion digest so interactive and scheduler adapters cannot implement
    parallel wire contracts.
    """
    if not isinstance(plan, ChunkPlan):
        return Invalid((Problem(
            code="bloat-completion-plan-invalid",
            message="assembly requires the ChunkPlan returned by bloat planning",
            location="completion.plan",
        ),))
    if not isinstance(outcomes, (list, tuple)) or not all(
            isinstance(outcome, ChunkOutcome) for outcome in outcomes):
        return Invalid((Problem(
            code="bloat-completion-outcomes-invalid",
            message="assembly outcomes must be ChunkOutcome values",
            location="completion.chunks",
        ),))
    expected_ids = [chunk.chunk_id for chunk in plan.chunks]
    received_ids = [outcome.chunk_id for outcome in outcomes]
    if received_ids != expected_ids:
        return Invalid((Problem(
            code="bloat-completion-outcomes-mismatch",
            message=(f"assembly outcomes must follow the planned chunks exactly; "
                     f"expected {expected_ids}, received {received_ids}"),
            location="completion.chunks",
        ),))

    verdicts, completed = [], []
    for outcome in outcomes:
        if outcome.completion_state not in COMPLETION_STATES:
            return Invalid((Problem(
                code="bloat-completion-state-invalid",
                message=(f"chunk {outcome.chunk_id} completion_state must be one "
                         f"of {list(COMPLETION_STATES)}"),
                location="completion.chunks",
            ),))
        if outcome.completion_state == COMPLETION_COMPLETE:
            if (outcome.reason or not isinstance(outcome.verdicts, tuple)
                    or not all(isinstance(verdict, dict)
                               for verdict in outcome.verdicts)):
                return Invalid((Problem(
                    code="bloat-completion-outcome-invalid",
                    message="a complete chunk carries verdicts and no reason",
                    location="completion.chunks",
                ),))
            start = len(verdicts) + 1
            for verdict in outcome.verdicts:
                verdicts.append({**verdict, "id": f"B{len(verdicts) + 1}"})
            ids = [f"B{number}" for number in range(start, len(verdicts) + 1)]
            selected = verdicts[start - 1:]
            result_digest = sha256_canonical({
                "chunk": outcome.chunk_id, "verdicts": selected,
            })
        else:
            if outcome.verdicts or not _nonempty(outcome.reason):
                return Invalid((Problem(
                    code="bloat-completion-outcome-invalid",
                    message="a missing or invalid chunk carries a reason and no verdicts",
                    location="completion.chunks",
                ),))
            ids, result_digest = [], None
        completed.append({
            "id": outcome.chunk_id,
            "completion_state": outcome.completion_state,
            "verdict_ids": ids,
            "result_digest": result_digest,
            "reason": outcome.reason,
        })

    digest = _completion_digest(plan.digest, completed, verdicts)
    return BloatAuditInput(
        verdicts=tuple(verdicts), plan=plan, chunks=tuple(completed), digest=digest,
    )


# --------------------------------------------------------------------------
# The audit: verdicts in, a validated report out
# --------------------------------------------------------------------------

def load_bloat_verdicts(path):
    """Read a lane's bloat verdicts file. Returns the payload, or `Invalid`.

    The file/payload split `drift.load_verdicts` draws, and nothing else:
    reading is a separate failure from what the payload says, and this
    function does not look inside the payload at all. Shape and
    `schema_version` discipline live in `audit_bloat` — exactly the split
    drift draws between `load_verdicts` (a bare reader) and `_verdict_entries`
    (the shape check, run *inside* `audit_drift`) — so every path into
    `audit_bloat`, not only this file loader's, enforces them. A check that
    lived only here could be silently routed around by an in-process caller
    that built the envelope itself and called `audit_bloat` directly.
    """
    try:
        with open(path, encoding="utf-8") as fh:
            return json.load(fh)
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        return Invalid((Problem(
            code="bloat-verdicts-unreadable",
            message=f"cannot read the verdicts at {path}: {exc}",
            location=path,
        ),))


def _audit_input(payload):
    """(`verdicts`, `completion`, problems) from a bloat audit envelope.

    The shape check `load_bloat_verdicts` deliberately does not do: an
    object, no extra keys, carrying a `verdicts` list (optionally a
    `schema_version`, which must equal `ARTIFACT_SCHEMA_VERSION` if present).
    Called from `audit_bloat` itself, on drift's `_verdict_entries` pattern,
    so no call path into `audit_bloat` can skip it.
    """
    if (not isinstance(payload, dict)
            or set(payload) - {"schema_version", "verdicts", "completion"}
            or not {"verdicts", "completion"}.issubset(payload)
            or not isinstance(payload.get("verdicts"), list)):
        return None, None, (Problem(
            code="bloat-verdicts-invalid-shape",
            message=(
                "bloat audit input must carry verdicts and completion, with "
                "only an optional schema_version — completion is report "
                "evidence, not an optional presentation sidecar"
            ),
            location="verdicts",
        ),)

    version = payload.get("schema_version", ARTIFACT_SCHEMA_VERSION)
    # `whole_number` first: a bare `!=` accepts `True` and `1.0`, both of which
    # compare equal to `1`, so an envelope declaring either passed a check whose
    # own message says it reads an *integer* version.
    if not whole_number(version) or version != ARTIFACT_SCHEMA_VERSION:
        return None, None, (Problem(
            code="bloat-verdicts-invalid-shape",
            message=(
                f"verdicts schema_version {version!r} is not supported; this "
                f"engine reads integer version {ARTIFACT_SCHEMA_VERSION}"
            ),
            location="verdicts.schema_version",
        ),)

    return payload["verdicts"], payload["completion"], ()


def validate_chunk_plan(index, raw):
    """Re-derive an untrusted serialized chunk plan from its declared budgets."""
    parsed = chunk_plan_from_dict(raw)
    if isinstance(parsed, Invalid):
        return parsed
    expected = plan_chunks(
        index, max_documents=parsed.max_documents, max_units=parsed.max_units,
    )
    if raw != expected.to_dict():
        return Invalid((Problem(
            code="bloat-completion-plan-mismatch",
            message=("completion.plan is not the deterministic plan for the "
                     "current index and its declared budgets; re-plan and "
                     "re-run pending chunks"),
            location="completion.plan",
        ),))
    return expected


def _validate_completion(index, verdicts, raw):
    """Validate assembled completion evidence against the current index.

    The assembler is allowed to report missing or invalid worker results; those
    are coverage gaps.  The completion artifact itself is authority-shaped
    input, though, so stale, duplicated, mismatched, or edited evidence is an
    invalid run rather than a partial one.
    """
    problems = []

    def bad(code, message, location):
        problems.append(Problem(code=code, message=message, location=location))

    if not isinstance(raw, dict) or set(raw) != {"plan", "chunks", "digest"}:
        bad("bloat-completion-invalid-shape",
            "completion must carry exactly plan, chunks, and digest", "completion")
        return None, tuple(problems)

    plan = validate_chunk_plan(index, raw["plan"])
    if isinstance(plan, Invalid):
        return None, plan.problems

    chunks = raw.get("chunks")
    if not isinstance(chunks, list):
        bad("bloat-completion-invalid-shape", "completion.chunks must be a list",
            "completion.chunks")
        return None, tuple(problems)
    chunk_fields = {
        "id", "completion_state", "verdict_ids", "result_digest", "reason",
    }
    malformed = [position for position, chunk in enumerate(chunks)
                 if not isinstance(chunk, dict) or set(chunk) != chunk_fields]
    if malformed:
        for position in malformed:
            bad("bloat-completion-invalid-shape",
                f"completion.chunks[{position}] must carry exactly id, "
                "completion_state, verdict_ids, result_digest, and reason",
                f"completion.chunks[{position}]")
        return None, tuple(problems)

    assigned = []
    verdict_ids = [entry.get("id") if isinstance(entry, dict) else None
                   for entry in verdicts]
    if len(chunks) != len(plan.chunks):
        bad("bloat-completion-chunks-mismatch",
            "completion must name every planned chunk exactly once, in plan order",
            "completion.chunks")
    for position, (chunk, planned) in enumerate(zip(chunks, plan.chunks)):
        where = f"completion.chunks[{position}]"
        chunk_id = chunk["id"]
        completion_state = chunk["completion_state"]
        ids = chunk["verdict_ids"]
        result_digest = chunk["result_digest"]
        reason = chunk["reason"]
        if chunk_id != planned.chunk_id:
            bad("bloat-completion-chunks-mismatch",
                f"completion chunk {chunk_id!r} does not match planned chunk "
                f"{planned.chunk_id!r}", where + ".id")
        if completion_state not in COMPLETION_STATES:
            bad("bloat-completion-state-invalid",
                f"completion_state must be one of {list(COMPLETION_STATES)}",
                where + ".completion_state")
        if not isinstance(ids, list) or not all(_nonempty(value) for value in ids):
            bad("bloat-completion-invalid-chunk",
                "chunk verdict_ids must be a list of non-empty ids",
                where + ".verdict_ids")
            ids = []
        if completion_state == COMPLETION_COMPLETE:
            if reason != "":
                bad("bloat-completion-outcome-invalid",
                    "a complete chunk carries no failure reason", where + ".reason")
            assigned.extend(ids)
            selected = [entry for entry in verdicts
                        if isinstance(entry, dict) and entry.get("id") in ids]
            expected_result_digest = sha256_canonical({
                "chunk": chunk_id, "verdicts": selected,
            })
            if result_digest != expected_result_digest:
                bad("bloat-completion-result-mismatch",
                    "result_digest does not bind the verdict contents received "
                    "for this chunk", where + ".result_digest")
        else:
            if ids:
                bad("bloat-completion-outcome-invalid",
                    "a missing or invalid chunk cannot contribute verdicts",
                    where + ".verdict_ids")
            if not _nonempty(reason):
                bad("bloat-completion-outcome-invalid",
                    "a missing or invalid chunk must explain its coverage gap",
                    where + ".reason")
            if result_digest is not None:
                bad("bloat-completion-outcome-invalid",
                    "a missing or invalid chunk carries no result_digest",
                    where + ".result_digest")
    if assigned != verdict_ids or len(set(assigned)) != len(assigned):
        bad("bloat-completion-verdict-mismatch",
            "complete chunks must bind every supplied verdict id exactly once, "
            "in assembled order", "completion.chunks")

    expected_digest = _completion_digest(plan.digest, chunks, verdicts)
    if raw.get("digest") != expected_digest:
        bad("bloat-completion-digest-mismatch",
            "completion evidence changed after assembly", "completion.digest")

    return (plan, chunks) if not problems else None, tuple(problems)


# Every bloat verdict is checked against the whole-repository context index,
# never a document-scoped glob, so the evidence boundary a run declares is
# always "everything" — and, per the brief, no local tool: bloat cites no
# command the way drift's `--evidence-command` lets a claim be settled by one.
# `sources` is non-operative — unlike drift, nothing in the bloat lane checks
# a citation against it — and is `("**",)` rather than `()` only because
# `report.validate_report` refuses an empty `sources` list outright.
EVIDENCE_BOUNDARY = EvidenceBoundary(sources=("**",), excluded=(), commands=())


def _audit_config_digest(boundary):
    """The consumer configuration this bloat audit ran under.

    `drift.audit_config_digest`'s reasoning, carried over: what a consumer
    can set that could change a verdict. Bloat's boundary is fixed
    (`EVIDENCE_BOUNDARY`) rather than consumer-configurable, so this digest
    only has to be stable and distinct from drift's, never re-derived from
    argv the way drift's is.
    """
    return sha256_canonical({
        "schema_version": ARTIFACT_SCHEMA_VERSION,
        "audit": "bloat",
        "evidence_boundary": boundary.to_dict(),
    })


def audit_bloat(repo_root, verdicts, registry_path=DEFAULT_REGISTRY_PATH):
    """Run a bloat audit. Returns a validated `Report`, or `Invalid`.

    The repository-level entrypoint, on `plan_repository_chunks`'s pattern (the
    composition lives here rather than in the command, so the command stays a
    call to one library function): index the repository, build the lineage the
    run carries (mirroring `drift.audit_drift`'s construction), check the
    verdicts against the index, and validate what results through the same
    `report.validate_report` every other lane runs through.

    `verdicts` is the envelope a bloat lane assembled — `{"verdicts": [...],
    "completion": {...}}`, optionally with a matching `schema_version` — not
    a bare list and never a verdict-only artifact whose missing work lived in
    an optional sidecar. `_audit_input` checks its shape here, inside the
    composition, the same seam `drift.audit_drift` checks its verdicts
    payload at (`_verdict_entries`). Required — there is no planless bloat
    audit the way a drift run can leave living documents unexamined; a value
    judgment about the corpus has to have been made by someone.
    """
    index = build_context_index(repo_root, registry_path)
    if isinstance(index, Invalid):
        return index

    state, problems = current_lineage(
        repo_root, registry_path, _audit_config_digest(EVIDENCE_BOUNDARY)
    )
    if problems:
        return Invalid(tuple(problems))
    lineage = Lineage(
        audit_mode="full", evidence_boundary=EVIDENCE_BOUNDARY, **state
    )

    entries, completion, problems = _audit_input(verdicts)
    if problems:
        return Invalid(tuple(problems))

    validated_completion, problems = _validate_completion(
        index, entries, completion,
    )
    if problems:
        return Invalid(tuple(problems))
    plan, completed_chunks = validated_completion

    by_id = {entry["id"]: entry for entry in entries}
    findings, examined, incomplete = [], [], [
        {"scope": gap.scope, "reason": gap.reason} for gap in index.unexamined
    ]
    for chunk, completed in zip(plan.chunks, completed_chunks):
        if completed["completion_state"] == COMPLETION_COMPLETE:
            result = record_verdicts(
                index, lineage,
                [by_id[record_id] for record_id in completed["verdict_ids"]],
                chunk=chunk,
            )
            if isinstance(result, Invalid):
                return result
            findings.extend(result.findings)
            examined.extend({
                "scope": document,
                "chunk": completed["id"],
                "plan_digest": plan.digest,
            } for document in chunk.documents)
            continue
        code = ("bloat-chunk-missing"
                if completed["completion_state"] == COMPLETION_MISSING
                else "bloat-chunk-invalid")
        for document in chunk.documents:
            incomplete.append({
                "scope": document,
                "reason": (
                    f"{code}: planned chunk {completed['id']} did not produce "
                    f"a valid result: {completed['reason']}"
                ),
            })

    result = BloatResult(
        findings=tuple(findings), incomplete=tuple(incomplete),
        index_digest=index.digest, examined=tuple(examined),
        scope={
            "basis": (
                "the completion artifact partitions the context index into "
                "content-addressed chunks"
            ),
            "coverage": SCOPE_WHOLE_INVENTORY,
            "documents": sorted(
                [document.path for document in index.documents]
                + [gap.scope for gap in index.unexamined]
            ),
            "excluded": [],
        },
    )

    return validate_report(
        result.report_payload(lineage), registry_path=registry_path
    )


# --------------------------------------------------------------------------
# Destinations and contention
# --------------------------------------------------------------------------

@dataclass(frozen=True)
class Claimant:
    """One document whose duplicated content would fold into a destination."""

    source: str
    destination: str
    units: Tuple[str, ...]
    order: int

    def to_dict(self):
        return {
            "source": self.source,
            "destination": self.destination,
            "units": list(self.units),
            "order": self.order,
        }


def merge_contention(index):
    """Every destination in the corpus, with its complete claimant list.

    The answer to "who else is merging into this document?", computed once from
    global data. Two workers in different chunks each get the same list, in the
    same order, including claimants from slices they were never shown — which
    is what makes their independently produced findings compose instead of
    collide. Order is by source path, a property of the corpus rather than of
    which chunk ran first.
    """
    pairs = {}
    for unit in index.duplicated_units():
        owner = index.owner_of(unit)
        for place in index.occurrences_of(unit):
            if place.path != owner:
                pairs.setdefault((owner, place.path), set()).add(unit)

    contention = {}
    for destination in sorted({owner for owner, _ in pairs}):
        sources = sorted(source for owner, source in pairs if owner == destination)
        contention[destination] = tuple(
            Claimant(
                source=source,
                destination=destination,
                units=tuple(sorted(pairs[(destination, source)])),
                order=order,
            )
            for order, source in enumerate(sources)
        )
    return contention


# --------------------------------------------------------------------------
# Deterministic scopes
# --------------------------------------------------------------------------

@dataclass(frozen=True)
class ScopeEnumeration:
    """Exactly which documents an inclusion rule covers, and nothing else."""

    rule: dict
    members: Tuple[str, ...]
    digest: str

    def to_dict(self):
        return {
            "rule": dict(self.rule),
            "members": list(self.members),
            "member_count": len(self.members),
            "digest": self.digest,
        }


def enumerate_scope(index, rule):
    """Expand an inclusion rule into every document it covers.

    The rule is declarative (`{"set": ...}`, `{"glob": ...}`, or
    `{"kind": ...}`) and the membership comes from the index, so a reviewer can
    re-derive the list and an approval bound to the enumeration's digest cannot
    silently widen. A rule nobody can enumerate, and a rule that covers nothing,
    are both refused: a bulk judgment over an unknown or empty set is
    unfalsifiable.
    """
    # The selector's *value* is checked here alongside its name, not left to
    # each branch: a rule is model-supplied, and `{"glob": 123}` reached
    # `compile_glob` and raised out of a public seam — no report, no Problem, a
    # traceback. A selector naming something that is not a non-empty string
    # names no set of documents whatever the selector is, so all three read the
    # same refusal.
    if not isinstance(rule, dict) or len(rule) != 1 or not set(rule) <= set(SCOPE_SELECTORS) or not all(
            isinstance(v, str) and v != "" for v in rule.values()):
        return Invalid((Problem(
            code="bloat-scope-not-enumerable",
            message=(
                f"a bulk scope must be exactly one of "
                f"{list(SCOPE_SELECTORS)} naming a non-empty string, not "
                f"{rule!r} — a scope nobody can expand into a file list cannot "
                f"be reviewed or applied"
            ),
            location="scope",
        ),))

    selector, value = next(iter(rule.items()))
    if selector == "set":
        members = [d.path for d in index.documents if d.doc_set == value]
    elif selector == "kind":
        members = [d.path for d in index.documents if d.kind == value]
    else:
        matcher = compile_glob(value)
        members = [d.path for d in index.documents if matcher.match(d.path)]

    if not members:
        return Invalid((Problem(
            code="bloat-scope-empty",
            message=(
                f"scope {rule!r} covers no document in this repository — a bulk "
                f"judgment over nothing is not a finding"
            ),
            location="scope",
        ),))

    members = tuple(sorted(members))
    return ScopeEnumeration(
        rule=dict(rule),
        members=members,
        digest=sha256_canonical({
            "schema_version": ARTIFACT_SCHEMA_VERSION,
            "rule": dict(rule),
            "members": list(members),
        }),
    )


# --------------------------------------------------------------------------
# Recording a model's verdicts
# --------------------------------------------------------------------------

@dataclass(frozen=True)
class BloatResult:
    """Validated findings, plus the coverage gaps the run must declare."""

    findings: Tuple[Finding, ...]
    incomplete: Tuple[dict, ...]
    index_digest: str
    examined: Tuple[dict, ...] = ()
    scope: Optional[dict] = None
    status: str = STATUS_OK

    def records(self):
        return tuple(f.to_record() for f in self.findings)

    def report_payload(self, lineage):
        """This result as a report payload, for `report.validate_report`.

        The bloat lane declares coverage in the shared contract's own terms
        rather than inventing a second vocabulary for it: a scope the index
        could not examine is an `incomplete` entry, and an `incomplete` entry
        forces `partial`. So a corpus with an unregistered or symlinked path
        never reports `clean` about it, and the absence of a bloat finding for
        a document nobody read cannot be mistaken for a verdict that it is
        lean. The state comes from `report.state_from_content()` — the rule's
        one owner, the same call the validator re-derives with — because a run
        does not get to declare a coverage it did not achieve, and a second copy
        of the rule could only ever disagree with the first.
        """
        records = [f.to_record() for f in self.findings]
        incomplete = [dict(i) for i in self.incomplete]
        payload = {
            "status": state_from_content(records, incomplete),
            "schema_version": ARTIFACT_SCHEMA_VERSION,
            "lineage": lineage.to_dict(),
            "records": records,
            "incomplete": incomplete,
        }
        if self.examined:
            payload["examined"] = [dict(entry) for entry in self.examined]
        if self.scope is not None:
            payload["scope"] = dict(self.scope)
        return payload

    def to_dict(self):
        return {
            "status": self.status,
            "schema_version": ARTIFACT_SCHEMA_VERSION,
            "index_digest": self.index_digest,
            "records": [f.to_record() for f in self.findings],
            "incomplete": [dict(i) for i in self.incomplete],
        }


@dataclass
class _Recorder:
    """One pass over a model's verdicts, collecting every problem.

    Holds the two things every check needs — the index it checks against and
    the problem list it appends to — so the checks are methods rather than
    functions passing the same four arguments around.
    """

    index: object
    lineage: object
    contention: dict
    in_chunk: object = None
    problems: list = field(default_factory=list)
    seen_ids: set = field(default_factory=set)

    # -- problem bookkeeping ------------------------------------------------

    def bad(self, code, message, where=None):
        self.problems.append(Problem(code=code, message=message, location=where))

    def clean_since(self, mark):
        """Whether *this* verdict is problem-free.

        Scoped to one verdict rather than to the whole response, so an earlier
        verdict's problem never silently stops a later one from being built and
        reported on. The response as a whole still fails closed — any problem
        anywhere discards every finding — but the pass keeps collecting, which
        is what makes one re-prompt able to address all of it.
        """
        return len(self.problems) == mark

    # -- one verdict --------------------------------------------------------

    def record(self, raw, where):
        """Validate one verdict and expand it into findings, or note problems."""
        mark = len(self.problems)

        if not isinstance(raw, dict):
            self.bad("bloat-invalid-shape", f"{where} must be an object", where)
            return ()

        self._check_fields(raw, where)
        self._check_id(raw, where)

        verdict = raw.get("verdict")
        if verdict not in VERDICTS:
            self.bad("bloat-unknown-verdict",
                     f"{verdict!r} is not a bloat verdict — expected one of "
                     f"{list(VERDICTS)}", where)
            return ()

        if not _nonempty(raw.get("evidence")):
            self.bad("bloat-missing-evidence",
                     f"{where} states no evidence — a bloat verdict is a value "
                     f"judgment, and one that does not say why is not "
                     f"reviewable", where)

        if raw.get("scope") is not None:
            return self._bulk(raw, where, verdict, mark)
        return self._one_document(raw, where, verdict, mark)

    def _check_fields(self, raw, where):
        for name in sorted(set(raw) - set(VERDICT_FIELDS)):
            if name in FORBIDDEN_VERDICT_FIELDS:
                self.bad("bloat-sampling-not-authority",
                         f"{name!r} is not a field a verdict may carry — a bulk "
                         f"finding's members are enumerated from the index, "
                         f"never asserted by the model, so a list of files "
                         f"supplied here could authorize a mutation nobody "
                         f"enumerated", where)
            else:
                self.bad("bloat-invalid-shape",
                         f"{name!r} is not a verdict field; expected "
                         f"{list(VERDICT_FIELDS)}", where)

    def _check_id(self, raw, where):
        record_id = raw.get("id")
        if not _nonempty(record_id):
            self.bad("bloat-invalid-shape", f"{where} needs a non-empty id", where)
        elif record_id in self.seen_ids:
            self.bad("bloat-duplicate-id",
                     f"id {record_id!r} is used by more than one verdict — two "
                     f"records a reviewer cannot tell apart cannot be approved "
                     f"apart", where)
        else:
            self.seen_ids.add(record_id)

    # -- a verdict about one document ---------------------------------------

    def _locate(self, where, record_id, path=None):
        """A verdict's location, addressable without recounting the envelope.

        `where` alone (`verdicts[N]`) is a position in the *assembled*
        envelope — assembly renumbers every chunk worker's own id
        (`output-contract.md`'s `B1..Bn`), so the index by itself names
        neither the id a reviewer or a re-dispatched worker would recognize
        nor the document a refusal is about. Both are appended when known, on
        `drift._verdict_entries`'s `f"{where} command={command!r}"` pattern,
        so relocating the right chunk for a re-prompt needs no recount.
        """
        located = where
        if _nonempty(record_id):
            located = f"{located} id={record_id!r}"
        if _nonempty(path):
            located = f"{located} path={path!r}"
        return located

    def _one_document(self, raw, where, verdict, mark):
        path = raw.get("path")
        where = self._locate(where, raw.get("id"), path)
        document = self.index.document(path) if _nonempty(path) else None

        if document is None:
            self.bad("bloat-unknown-document",
                     f"{path!r} is not a document in this repository's index — "
                     f"a verdict about a path the registry does not claim cannot "
                     f"be checked or applied", where)
            return ()
        if self.in_chunk is not None and path not in self.in_chunk:
            self.bad("bloat-document-outside-chunk",
                     f"{path} is outside this chunk's slice — a worker judges "
                     f"the documents it was given, and the index answers "
                     f"everything else", where)
            return ()

        units = raw.get("units")
        if not isinstance(units, list) or not units:
            self.bad("bloat-invalid-shape",
                     f"{where} must name at least one assertion unit", where)
            return ()
        well_typed_units = []
        for unit in units:
            if not isinstance(unit, str) or unit not in document.units:
                self.bad("bloat-unknown-unit",
                         f"unit {unit!r} does not occur in {path} — a verdict is "
                         f"about content that is actually there", where)
            if isinstance(unit, str):
                well_typed_units.append(unit)

        if verdict in WHOLE_DOCUMENT_VERDICTS:
            if len(well_typed_units) != len(set(well_typed_units)):
                self.bad("bloat-whole-document-unit-duplicate",
                         f"{verdict} names a unit identity more than once for "
                         f"{path} — a whole-document judgment binds the current "
                         f"deterministic unit set exactly once", where)
            missing = sorted(set(document.units) - set(well_typed_units))
            if missing:
                self.bad("bloat-whole-document-units-incomplete",
                         f"{verdict} retires all of {path}, but its unit set "
                         f"omits {len(missing)} current deterministic unit(s) — "
                         f"a whole-document judgment must name every unit the "
                         f"current segmentation contains", where)

        destination = self._destination(
            raw, where, verdict, path, well_typed_units
        )
        extra = {
            "verdict": verdict,
            "evidence": raw.get("evidence"),
            "duplicate_search": self._duplicate_search(path, well_typed_units),
            "destination": destination,
            "proposal": self._proposal(raw, where, verdict),
            "status": self._status(raw, where, verdict, path, document),
        }
        self._reject_sample(raw, where, scoped=False)
        if destination is not None:
            self._note_contention(extra, destination["path"], path)

        if not self.clean_since(mark):
            return ()
        return self._build(raw["id"], verdict, path, units, extra)

    # -- a bulk judgment over a deterministic scope --------------------------

    def _bulk(self, raw, where, verdict, mark):
        """Expand a bulk judgment into one finding per enumerated member."""
        where = self._locate(where, raw.get("id"))
        scope = raw["scope"]
        if verdict not in SCOPE_VERDICTS:
            self.bad("bloat-scope-verdict-ineligible",
                     f"{verdict} cannot be a bulk judgment — only "
                     f"{list(SCOPE_VERDICTS)} applies uniformly to every member "
                     f"of a scope; anything else needs a per-document judgment "
                     f"nobody made", where)
            return ()
        for name in ("path", "units", "destination", "proposal", "status"):
            if raw.get(name) is not None:
                self.bad("bloat-invalid-shape",
                         f"{name!r} does not apply to a bulk {verdict} — its "
                         f"subject is the scope, and its members come from the "
                         f"enumeration", where)

        enumeration = enumerate_scope(self.index, scope)
        if isinstance(enumeration, Invalid):
            self.problems.extend(enumeration.problems)
            return ()
        self._reject_sample(raw, where, scoped=True, enumeration=enumeration)

        empty = [m for m in enumeration.members if not self.index.document(m).units]
        for member in empty:
            self.bad("bloat-scope-member-empty",
                     f"{member} is in scope {scope!r} but holds no assertion "
                     f"unit, so no finding can bind to it — exclude it from the "
                     f"scope or give it content, rather than retiring a set one "
                     f"of whose members no record could name", where)

        if not self.clean_since(mark):
            return ()

        findings = []
        for position, member in enumerate(enumeration.members):
            extra = {
                "verdict": verdict,
                "evidence": raw["evidence"],
                "destination": None,
                "proposal": None,
                "status": None,
                "scope": {
                    **enumeration.to_dict(),
                    "member_index": position,
                    # Recorded so a reviewer can see what was actually read, and
                    # positioned as what it is: the review order, not the mandate.
                    "sample": sorted(raw.get("sample") or ()),
                    "sample_is_not_authority": True,
                },
            }
            findings.extend(self._build(
                f"{raw['id']}.{position}", verdict, member,
                list(self.index.document(member).units), extra,
            ))
        return findings

    # -- destinations -------------------------------------------------------

    def _destination(self, raw, where, verdict, path, units):
        """Where content goes — decided by the index, never by the slice.

        For content the global search found elsewhere, the destination *is* the
        index's owner: a worker that proposed a different one was guessing from
        a partial view, so a mismatch is refused rather than preferred. For
        content that occurs nowhere else there is nothing to derive, so the
        model names a destination and the index checks it against the
        constraints a destination has to satisfy.
        """
        proposed = raw.get("destination")

        if verdict in RESIDUE_VERDICTS:
            if proposed is None:
                # Retire-only distillation: nothing is authored, so nothing is
                # named. Legal, and lossy only if residue was never landed
                # under its own record — a judgment for the person approving.
                return None
            if not _nonempty(proposed):
                self.bad("bloat-invalid-shape",
                         f"{verdict}'s destination must be the path of the "
                         f"residue document, or absent", where)
                return None
            return self._residue_destination_record(proposed, path, where)

        if verdict not in DESTINATION_VERDICTS:
            if proposed is not None:
                self.bad("bloat-destination-forbidden",
                         f"{verdict} moves nothing, so it names no destination — "
                         f"only {list(DESTINATION_VERDICTS + RESIDUE_VERDICTS)} "
                         f"do", where)
            return None

        owners_including_self = {
            self.index.owner_of(unit) for unit in units
            if len(self.index.occurrences_of(unit)) > 1
        }

        if owners_including_self == {path}:
            # Every duplicated unit in this group is owned by the document
            # being judged — it is the original the other occurrence(s) point
            # at, not a copy of one. There is no other document to fold into,
            # regardless of what was proposed: accepting a model-proposed
            # destination here would bypass the index guard this whole
            # function exists to enforce.
            self.bad("bloat-destination-self-owner",
                     f"the index owns this content at {path} itself — this "
                     f"document is not a duplicate, it is the original the "
                     f"other occurrence(s) point back at, so there is no "
                     f"other document for {verdict} to fold it into; naming "
                     f"a destination here asserts a merge the index does "
                     f"not support", where)
            return None

        owners = owners_including_self - {path}

        if len(owners) > 1:
            # The group's content is owned in more than one place, so no single
            # destination is right for it. Falling back to whatever the worker
            # proposed would be exactly the slice-local guess the index exists
            # to prevent, so the grouping is refused instead.
            self.bad("bloat-destination-ambiguous",
                     f"this group's units are owned by {sorted(owners)} — one "
                     f"destination cannot be right for all of them; split the "
                     f"verdict so each group has one owner", where)
            return None

        if owners:
            derived = owners.pop()
            if proposed is not None and proposed != derived:
                self.bad("bloat-destination-contradicts-index",
                         f"the index owns this content at {derived}, not "
                         f"{proposed!r} — a destination for duplicated content "
                         f"is derived from the whole corpus, so a slice-local "
                         f"answer that disagrees is a guess", where)
                return None
            return self._destination_record(derived, "index-owner", path, where)

        if not _nonempty(proposed):
            self.bad("bloat-destination-required",
                     f"{verdict} must name a destination, and the index found no "
                     f"other occurrence of this content to derive one from",
                     where)
            return None
        return self._destination_record(proposed, "model-proposed", path, where)

    def _residue_destination_record(self, destination, source, where):
        """Check a destination that must name a document nobody has written yet.

        A residue destination is create-only, and that is a *bound on authority*,
        not a limitation. `RECORD_REMEDIES[DISTILL]` includes the span edits — an
        approved distillation legitimately rewrites the artifact it retires — and
        the applier bounds a positioned edit to the hull of the record's approved
        units only on the record's *own* document. A record's units segment that
        document alone, so a destination that already existed would take
        `replace`/`insert`/`delete` at any line of it, with no passage anyone
        reviewed: naming a decision log as the destination would authorize
        deleting an unrelated sentence from it. An unwritten path cannot: its
        whole content is the `create-document` text the approval covers, and the
        applier refuses a creation over a document that is there
        (`apply-create-exists`).

        So the inventory not vouching for this path is the requirement, not an
        obstacle to work around — and residue belonging in a document that does
        exist stays what it was before this route existed: unplaceable under this
        record, needing its own record and its own approval.

        Confinement is not re-derived here: `paths.authorize_path` is the single
        owner of path safety, and it already reasons about unwritten
        create-document targets (canonical spelling, containment in a declared
        root, no symlinked component, no case-folded collision, documentation
        class). The approval set authorizes the same path through the same
        function before an applier ever sees it; this is the audit-time half, so
        a record that could never be applied is never minted in the first place.

        The rest are the registry's and the repository's: the registry
        classifies the path — closed-world, so a path no rule claims is refused
        rather than assumed living — the kind it assigns must be one content
        durably lives in, and the path must be free both in the index and *on
        disk*, since a file the inventory does not claim is still a file a
        creation would land on and the index may predate it.
        """
        repo_root, registry = self.index.repo_root, self.index.registry
        if repo_root is None or registry is None:
            self.bad("bloat-destination-uncheckable",
                     f"this index is missing the repository it was built from "
                     f"or its registry, so whether {destination!r} could hold a "
                     f"new document is unanswerable — and an unanswered safety "
                     f"question is a refusal", where)
            return None

        if destination == source:
            self.bad("bloat-destination-is-source",
                     f"{destination} is the planning artifact being distilled — "
                     f"its residue cannot be the document the same record "
                     f"retires", where)
            return None

        authorization = authorize_path(
            destination, repo_root=repo_root, roots=registry.roots,
            target_class=DOCUMENTATION,
        )
        if not authorization.authorized:
            self.bad("bloat-destination-unauthorized",
                     f"{destination!r} cannot be a residue document: "
                     f"{authorization.problem.message}", where)
            return None

        reason, rule = residue_destination_ineligibility(registry, destination)
        if reason == "unclassified":
            self.bad("bloat-destination-unclassified",
                     f"no registry rule claims {destination!r} as documentation "
                     f"— classification is closed-world, so a residue document "
                     f"at an unclassified path would be born outside the corpus "
                     f"every later audit reads", where)
            return None
        if reason == "kind-ineligible":
            self.bad("bloat-destination-kind-ineligible",
                     f"the registry classifies {destination} as a {rule.kind} "
                     f"document — residue is never authored into one, because "
                     f"its own lifecycle ends in distillation or retirement and "
                     f"would take the residue with it", where)
            return None

        if (self.index.document(destination) is not None
                or os.path.lexists(os.path.join(repo_root, destination))):
            self.bad("bloat-destination-occupied",
                     f"{destination} already exists — a residue destination is "
                     f"a document this distillation *authors*, so an occupied "
                     f"path would either be overwritten or take span edits "
                     f"nobody reviewed a passage of; land the residue there "
                     f"under its own record instead", where)
            return None

        return {
            "path": destination,
            "kind": rule.kind,
            "set": rule.doc_set,
            "selected_by": "model-proposed-residue",
            "constraints": {
                "is_inventoried_document": False,
                "is_authorized_new_document": True,
                "differs_from_source": True,
                "kind_accepts_content": True,
                "eligible_kinds": list(DESTINATION_KINDS),
                "registry_rule": rule.glob,
            },
        }

    def _destination_record(self, destination, selected_by, source, where):
        """Check a destination against every constraint, and record which held."""
        document = self.index.document(destination)
        if document is None:
            self.bad("bloat-destination-not-a-document",
                     f"{destination!r} is not a document in this repository's "
                     f"index — content cannot be moved somewhere the registry "
                     f"does not claim", where)
            return None
        if destination == source:
            self.bad("bloat-destination-is-source",
                     f"{destination} is the document being judged — a move to "
                     f"itself changes nothing and would read as an approved "
                     f"edit", where)
            return None
        if document.kind not in DESTINATION_KINDS:
            self.bad("bloat-destination-kind-ineligible",
                     f"{destination} is a {document.kind} document — content is "
                     f"never moved into one, because its own lifecycle ends in "
                     f"distillation or retirement and would take the moved "
                     f"content with it", where)
            return None
        return {
            "path": destination,
            "kind": document.kind,
            "set": document.doc_set,
            "selected_by": selected_by,
            "constraints": {
                "is_inventoried_document": True,
                "differs_from_source": True,
                "kind_accepts_content": True,
                "eligible_kinds": list(DESTINATION_KINDS),
            },
        }

    def _note_contention(self, extra, destination, source):
        """Record the arbitration when more than one document folds into one.

        The claimant list comes from the index, so every chunk records the same
        arbitration and the same order rather than each inventing one.
        """
        claimants = self.contention.get(destination, ())
        claim = next((c for c in claimants if c.source == source), None)
        if claim is not None and len(claimants) > 1:
            extra["contention"] = {
                "destination": destination,
                "order": claim.order,
                "claimants": [c.source for c in claimants],
            }

    # -- the rest of the record ----------------------------------------------

    def _duplicate_search(self, path, units):
        """The record data saying a global search happened and what it saw.

        A finding that says "this is redundant" is making a claim about the
        whole corpus, and a reader must be able to tell whether the whole corpus
        was actually consulted. The occurrences are split by side, because that
        is the question the unit group cannot answer: the group is a
        deduplicated set of content digests, so `here` is what a reviewer needs
        to know which copies in *this* document the finding is about, and
        `elsewhere` is what makes the redundancy claim checkable.
        """
        here, elsewhere = [], []
        for unit in sorted(set(units)):
            for place in self.index.occurrences_of(unit):
                (here if place.path == path else elsewhere).append(place.to_dict())
        return {
            "scope": "repository",
            "index_digest": self.index.digest,
            "documents_searched": len(self.index.documents),
            "here": here,
            "elsewhere": elsewhere,
            "occurrence_count": len(here) + len(elsewhere),
        }

    def _proposal(self, raw, where, verdict):
        proposal = raw.get("proposal")
        if verdict in PROPOSAL_VERDICTS:
            if not _nonempty(proposal):
                self.bad("bloat-proposal-required",
                         f"{verdict} replaces text, so it must carry the "
                         f"replacement", where)
                return None
            return proposal
        if proposal is not None:
            self.bad("bloat-proposal-forbidden",
                     f"{verdict} writes no replacement text, so it carries no "
                     f"proposal", where)
        return None

    def _status(self, raw, where, verdict, path, document):
        status = raw.get("status")
        if verdict == DISTILL:
            if document.kind != "planning":
                self.bad("bloat-distill-not-planning",
                         f"{DISTILL} classifies a planning document, and "
                         f"{path} is registered as {document.kind!r} — a "
                         f"lifecycle status is not a fact about any other "
                         f"kind", where)
                return None
            if status not in DISTILL_STATUSES:
                self.bad("bloat-unknown-status",
                         f"a {DISTILL} verdict's status must be one of "
                         f"{list(DISTILL_STATUSES)}, not {status!r} — whether the "
                         f"work landed decides whether anything may be applied "
                         f"at all", where)
                return None
            file_status = self.index.lifecycle_status(path)
            if status != file_status:
                self.bad("bloat-status-not-file-bound",
                         f"the planning document's own marker says "
                         f"{file_status!r} — lifecycle state lives in the file "
                         f"(the registry owns classification; content-coupled "
                         f"facts like lifecycle state stay in the document — "
                         f"engine/README.md, \"The registry\"), and a verdict "
                         f"may report it, never assert it",
                         where)
                return None
            return status
        if status is not None:
            self.bad("bloat-status-forbidden",
                     f"only {DISTILL} carries a lifecycle status", where)
        return None

    def _reject_sample(self, raw, where, scoped, enumeration=None):
        """A sample is review order. On anything but a bulk scope it is nothing."""
        sample = raw.get("sample")
        if sample is None:
            return
        if not scoped:
            self.bad("bloat-sampling-not-authority",
                     f"{where} is a judgment about one document, so a sample "
                     f"says nothing — sampling prioritizes review of a bulk "
                     f"scope and never stands in for reading the subject", where)
            return
        if not (isinstance(sample, list) and all(_nonempty(s) for s in sample)):
            self.bad("bloat-invalid-shape",
                     f"{where}: sample must be a list of paths", where)
            return
        outside = sorted(set(sample) - set(enumeration.members))
        if outside:
            self.bad("bloat-sample-outside-scope",
                     f"{outside} are not in scope {enumeration.rule!r} — a sample "
                     f"is the part of the scope that was read, so a path outside "
                     f"it describes review of something this judgment does not "
                     f"cover", where)

    def _build(self, record_id, verdict, path, units, extra):
        finding = build_finding(
            lineage=self.lineage, code=verdict, path=path,
            units=units, record_id=record_id, extra=extra,
        )
        if isinstance(finding, Invalid):
            self.problems.extend(finding.problems)
            return ()
        return (finding,)


def record_verdicts(index, lineage, verdicts, chunk=None):
    """Validate a model's bloat verdicts against the index; build findings.

    Returns a `BloatResult`, or `Invalid` naming every problem in the whole
    response so one re-prompt can address all of it. Fails closed: any problem
    records nothing, because a half-trusted set of deletion proposals is one
    nobody can tell the trustworthy half of.

    `chunk`, when supplied, is the slice the verdicts came from; a verdict about
    a document outside it is refused. Destinations are deliberately *not* bound
    that way — a destination outside the slice is the normal case, and the whole
    reason the index exists.
    """
    if not isinstance(verdicts, list):
        return Invalid((Problem(
            code="bloat-invalid-shape",
            message=(
                f"bloat verdicts must be a list of objects, not "
                f"{type(verdicts).__name__}"
            ),
            location="verdicts",
        ),))

    recorder = _Recorder(
        index=index,
        lineage=lineage,
        contention=merge_contention(index),
        in_chunk=set(chunk.documents) if chunk is not None else None,
    )

    findings = []
    for position, raw in enumerate(verdicts):
        findings.extend(recorder.record(raw, f"verdicts[{position}]"))

    if recorder.problems:
        return Invalid(tuple(recorder.problems))

    return BloatResult(
        findings=tuple(findings),
        incomplete=tuple(
            {"scope": u.scope, "reason": u.reason} for u in index.unexamined
        ),
        index_digest=index.digest,
    )


def _nonempty(value):
    return isinstance(value, str) and value.strip() != ""


# --------------------------------------------------------------------------
# The chunk cache seam
# --------------------------------------------------------------------------

@dataclass(frozen=True)
class ChunkCache:
    """What a chunk can reuse, and what it must still be asked about."""

    hits: Dict[str, tuple]
    misses: Tuple[str, ...]
    reasons: Dict[str, str]

    def to_dict(self):
        return {
            "hits": {path: list(records) for path, records in sorted(self.hits.items())},
            "misses": list(self.misses),
            "reasons": dict(sorted(self.reasons.items())),
        }


def chunk_cache_keys(index, lineage, chunk):
    """One cache key per document in the chunk.

    A bloat verdict about a document is checked against the rest of the corpus,
    so the corpus *is* its source evidence: `source_digest` is
    `index.context_digest(path)` — the part of the corpus that bears on this
    document, rather than the whole index. Anything that could have changed the
    judgment moves it or a lineage field, and so moves the key.

    Note that #64's lineage already carries `inventory_digest`, which moves on
    any corpus edit at all, so today the narrower digest buys no extra hits. It
    is still the honest description of what a cached bloat verdict was judged
    against — a cache entry that names a different context slice is
    `MISS_IDENTITY` rather than a false hit — and it is what a later slice would
    need in order to narrow the lineage without re-deriving this rule.
    """
    return {
        path: cache_key(
            index.document(path).document_digest, index.context_digest(path), lineage
        )
        for path in chunk.documents
    }


def load_chunk(cache_dir, repo_root, index, lineage, chunk,
               registry_path=DEFAULT_REGISTRY_PATH):
    """Split a chunk into what is already known and what must be re-judged."""
    hits, misses, reasons = {}, [], {}
    for path, key in chunk_cache_keys(index, lineage, chunk).items():
        result = cache_get(cache_dir, key, repo_root=repo_root,
                           registry_path=registry_path)
        if result.hit:
            hits[path] = tuple(result.record.get("records", ()))
        else:
            misses.append(path)
            reasons[path] = result.reason
    return ChunkCache(hits=hits, misses=tuple(sorted(misses)), reasons=reasons)


def store_chunk(cache_dir, index, lineage, chunk, results):
    """Store one chunk's per-document results.

    `results` maps each document in the chunk to the finding records produced
    for it — an empty list is a real answer ("judged, nothing found") and is
    stored as such, so a clean document is not re-judged on every run. A
    document outside the chunk is refused: its result was produced under a
    different slice, and storing it here would key it to the wrong evidence.
    """
    keys = chunk_cache_keys(index, lineage, chunk)
    outside = sorted(set(results) - set(keys))
    if outside:
        raise ValueError(
            f"{outside} are not in chunk {chunk.chunk_id} — a chunk stores only "
            f"the documents it was given"
        )
    written = {}
    for path, records in sorted(results.items()):
        records = list(records)
        written[path] = cache_put(cache_dir, keys[path], {
            "id": f"BLOAT-CHUNK:{path}",
            "digest": sha256_canonical({
                "schema_version": ARTIFACT_SCHEMA_VERSION,
                "path": path,
                "records": records,
            }),
            "code": "bloat-chunk-result",
            "path": path,
            "records": records,
        }, evidence_sources=("context-index",))
    return written
