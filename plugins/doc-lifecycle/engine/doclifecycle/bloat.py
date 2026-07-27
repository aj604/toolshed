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
and exactly which files a bulk scope covers. `record_verdicts()` is where the
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

from dataclasses import dataclass, field
from typing import Dict, Optional, Tuple

from . import ARTIFACT_SCHEMA_VERSION
from .cache import cache_key, get as cache_get, put as cache_put
from .context import KIND_PRECEDENCE
from .digest import sha256_canonical
from .finding import build_finding
from .inventory import DEFAULT_REGISTRY_PATH
from .registry import compile_glob
from .results import (
    STATE_CLEAN,
    STATE_FINDINGS,
    STATE_PARTIAL,
    Invalid,
    Problem,
)

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
# Verdicts that replace text, and so must carry the replacement.
PROPOSAL_VERDICTS = (CONDENSE, EXTRACT_AND_MOVE)
# Verdicts eligible for bulk expansion over a deterministic scope. Retirement
# only: a scope-wide CUT or CONDENSE would be a per-passage judgment nobody
# made, and a scope-wide move would need a per-document destination.
SCOPE_VERDICTS = (RETIRE_DOC,)

DISTILL_STATUSES = ("pending-implementation", "ready")

# A destination must be a document content can durably live in. Planning
# documents are temporary and end in distillation or retirement, so nothing is
# ever moved *into* one — the move would be undone by the target's own lifecycle.
DESTINATION_KINDS = ("living", "narrative")

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
    digest: str
    status: str = "ok"

    def to_dict(self):
        return {
            "status": self.status,
            "schema_version": ARTIFACT_SCHEMA_VERSION,
            "index_digest": self.index_digest,
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
        digest=sha256_canonical({
            "schema_version": ARTIFACT_SCHEMA_VERSION,
            "index_digest": index.digest,
            "chunks": [c.to_dict() for c in built],
        }),
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


def _claim_for(contention, destination, source):
    return next(
        (c for c in contention.get(destination, ()) if c.source == source), None
    )


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
    if not isinstance(rule, dict) or len(rule) != 1 or not set(rule) <= set(SCOPE_SELECTORS):
        return Invalid((Problem(
            code="bloat-scope-not-enumerable",
            message=(
                f"a bulk scope must be exactly one of "
                f"{list(SCOPE_SELECTORS)}, not {rule!r} — a scope nobody can "
                f"expand into a file list cannot be reviewed or applied"
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

    findings: Tuple[object, ...]
    incomplete: Tuple[dict, ...]
    index_digest: str
    status: str = "ok"

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
        lean. The state is derived from the content here for the same reason
        the contract re-derives it: a run does not get to declare a coverage it
        did not achieve.
        """
        records = [f.to_record() for f in self.findings]
        incomplete = [dict(i) for i in self.incomplete]
        if incomplete:
            status = STATE_PARTIAL
        elif records:
            status = STATE_FINDINGS
        else:
            status = STATE_CLEAN
        return {
            "status": status,
            "schema_version": ARTIFACT_SCHEMA_VERSION,
            "lineage": lineage.to_dict(),
            "records": records,
            "incomplete": incomplete,
        }

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
    """One pass over a model's verdicts, collecting every problem."""

    index: object
    lineage: object
    chunk: Optional[object] = None
    problems: list = field(default_factory=list)

    def bad(self, code, message, where=None):
        self.problems.append(Problem(code=code, message=message, location=where))


def _duplicate_search(index, units):
    """The record data that says a global search happened and what it saw.

    A bloat finding that says "this is redundant" is making a claim about the
    whole corpus, and a reader must be able to tell whether the whole corpus
    was actually consulted. This is that evidence: the index the search ran
    against, how much of the corpus it covered, and every occurrence found.
    """
    occurrences = []
    for unit in sorted(set(units)):
        occurrences.extend(index.occurrences_of(unit))
    return {
        "scope": "repository",
        "index_digest": index.digest,
        "documents_searched": len(index.documents),
        "occurrences": [o.to_dict() for o in occurrences],
        "occurrence_count": len(occurrences),
    }


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
    recorder = _Recorder(index=index, lineage=lineage, chunk=chunk)
    contention = merge_contention(index)
    in_chunk = set(chunk.documents) if chunk is not None else None
    findings, seen_ids = [], set()

    if not isinstance(verdicts, list):
        return Invalid((Problem(
            code="bloat-invalid-shape",
            message=(
                f"bloat verdicts must be a list of objects, not "
                f"{type(verdicts).__name__}"
            ),
            location="verdicts",
        ),))

    for position, raw in enumerate(verdicts):
        where = f"verdicts[{position}]"
        built = _record_one(recorder, raw, where, contention, in_chunk, seen_ids)
        if built:
            findings.extend(built)

    if recorder.problems:
        return Invalid(tuple(recorder.problems))

    return BloatResult(
        findings=tuple(findings),
        incomplete=tuple(
            {"scope": u.scope, "reason": u.reason} for u in index.unexamined
        ),
        index_digest=index.digest,
    )


def _record_one(recorder, raw, where, contention, in_chunk, seen_ids):
    """Validate one verdict and expand it into findings, or record problems."""
    index = recorder.index
    bad = recorder.bad

    if not isinstance(raw, dict):
        bad("bloat-invalid-shape", f"{where} must be an object", where)
        return ()

    unknown = sorted(set(raw) - set(VERDICT_FIELDS))
    for name in unknown:
        code = (
            "bloat-sampling-not-authority" if name in FORBIDDEN_VERDICT_FIELDS
            else "bloat-invalid-shape"
        )
        message = (
            f"{name!r} is not a field a verdict may carry — a bulk finding's "
            f"members are enumerated from the index, never asserted by the "
            f"model, so a list of files supplied here could authorize a "
            f"mutation nobody enumerated"
            if code == "bloat-sampling-not-authority" else
            f"{name!r} is not a verdict field; expected {list(VERDICT_FIELDS)}"
        )
        bad(code, message, where)

    record_id = raw.get("id")
    if not _nonempty(record_id):
        bad("bloat-invalid-shape", f"{where} needs a non-empty id", where)
    elif record_id in seen_ids:
        bad("bloat-duplicate-id",
            f"id {record_id!r} is used by more than one verdict — two records "
            f"a reviewer cannot tell apart cannot be approved apart", where)
    else:
        seen_ids.add(record_id)

    verdict = raw.get("verdict")
    if verdict not in VERDICTS:
        bad("bloat-unknown-verdict",
            f"{verdict!r} is not a bloat verdict — expected one of "
            f"{list(VERDICTS)}", where)
        return ()

    if not _nonempty(raw.get("evidence")):
        bad("bloat-missing-evidence",
            f"{where} states no evidence — a bloat verdict is a value "
            f"judgment, and one that does not say why is not reviewable", where)

    scope = raw.get("scope")
    if scope is not None:
        return _record_scope_verdict(recorder, raw, where, verdict, scope)

    return _record_document_verdict(
        recorder, raw, where, verdict, contention, in_chunk
    )


def _record_document_verdict(recorder, raw, where, verdict, contention, in_chunk):
    index, bad = recorder.index, recorder.bad
    path = raw.get("path")
    document = index.document(path) if _nonempty(path) else None

    if document is None:
        bad("bloat-unknown-document",
            f"{path!r} is not a document in this repository's index — a verdict "
            f"about a path the registry does not claim cannot be checked or "
            f"applied", where)
        return ()
    if in_chunk is not None and path not in in_chunk:
        bad("bloat-document-outside-chunk",
            f"{path} is outside this chunk's slice — a worker judges the "
            f"documents it was given, and the index answers everything else",
            where)
        return ()

    units = raw.get("units")
    if not isinstance(units, list) or not units:
        bad("bloat-invalid-shape",
            f"{where} must name at least one assertion unit", where)
        return ()
    unknown_units = [u for u in units if u not in document.units]
    for unit in unknown_units:
        bad("bloat-unknown-unit",
            f"unit {unit!r} does not occur in {path} — a verdict is about "
            f"content that is actually there", where)

    destination = _resolve_destination(recorder, raw, where, verdict, path, units)
    proposal = _check_proposal(recorder, raw, where, verdict)
    status = _check_status(recorder, raw, where, verdict)
    _reject_sample(recorder, raw, where, scoped=False)

    if recorder.problems:
        return ()

    extra = {
        "verdict": verdict,
        "evidence": raw["evidence"],
        "duplicate_search": _duplicate_search(index, units),
        "destination": destination,
        "proposal": proposal,
        "status": status,
    }
    claim = _claim_for(contention, destination["path"], path) if destination else None
    if claim is not None and len(contention[destination["path"]]) > 1:
        # More than one document folds into this destination. The complete
        # claimant list comes from the index, so both chunks record the same
        # arbitration and the same order rather than each inventing one.
        extra["contention"] = {
            "destination": destination["path"],
            "order": claim.order,
            "claimants": [c.source for c in contention[destination["path"]]],
        }
    return _build(recorder, raw["id"], verdict, path, units, extra)


def _record_scope_verdict(recorder, raw, where, verdict, scope):
    """Expand a bulk judgment into one finding per enumerated member."""
    index, bad = recorder.index, recorder.bad

    if verdict not in SCOPE_VERDICTS:
        bad("bloat-scope-verdict-ineligible",
            f"{verdict} cannot be a bulk judgment — only {list(SCOPE_VERDICTS)} "
            f"applies uniformly to every member of a scope; anything else needs "
            f"a per-document judgment nobody made", where)
        return ()
    if raw.get("path") is not None:
        bad("bloat-invalid-shape",
            f"{where} is a bulk judgment, so its subject is the scope rather "
            f"than one path", where)
    if raw.get("units") is not None:
        bad("bloat-invalid-shape",
            f"{where} is a bulk judgment, so it names no unit group of its own",
            where)
    for name in ("destination", "proposal", "status"):
        if raw.get(name) is not None:
            bad("bloat-invalid-shape",
                f"{name!r} does not apply to a bulk {verdict}", where)

    enumeration = enumerate_scope(index, scope)
    if isinstance(enumeration, Invalid):
        recorder.problems.extend(enumeration.problems)
        return ()
    _reject_sample(recorder, raw, where, scoped=True)

    if recorder.problems:
        return ()

    findings = []
    for position, member in enumerate(enumeration.members):
        document = index.document(member)
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
        built = _build(
            recorder, f"{raw['id']}.{position}", verdict, member,
            list(document.units), extra,
        )
        findings.extend(built)
    return findings


def _resolve_destination(recorder, raw, where, verdict, path, units):
    """Where content goes — decided by the index, never by the slice.

    For content the global search found elsewhere, the destination *is* the
    index's owner: a worker that proposed a different one was guessing from a
    partial view, so a mismatch is refused rather than preferred. For content
    that occurs nowhere else there is nothing to derive, so the model names a
    destination and the index checks it against the constraints a destination
    has to satisfy.
    """
    index, bad = recorder.index, recorder.bad
    proposed = raw.get("destination")

    if verdict not in DESTINATION_VERDICTS:
        if proposed is not None:
            bad("bloat-destination-forbidden",
                f"{verdict} moves nothing, so it names no destination — "
                f"only {list(DESTINATION_VERDICTS)} do", where)
        return None

    duplicated = [u for u in units if len(index.occurrences_of(u)) > 1]
    owners = {index.owner_of(u) for u in duplicated} - {path}
    derived = sorted(owners)[0] if len(owners) == 1 else None

    if derived is not None:
        if proposed is not None and proposed != derived:
            bad("bloat-destination-contradicts-index",
                f"the index owns this content at {derived}, not {proposed!r} — "
                f"a destination for duplicated content is derived from the "
                f"whole corpus, so a slice-local answer that disagrees is a "
                f"guess", where)
            return None
        return _destination_record(index, derived, "index-owner", path, recorder, where)

    if not _nonempty(proposed):
        bad("bloat-destination-required",
            f"{verdict} must name a destination, and the index found no other "
            f"occurrence of this content to derive one from", where)
        return None
    return _destination_record(index, proposed, "model-proposed", path, recorder, where)


def _destination_record(index, destination, selected_by, source, recorder, where):
    """Check a destination against every constraint, and record which held."""
    bad = recorder.bad
    document = index.document(destination)
    if document is None:
        bad("bloat-destination-not-a-document",
            f"{destination!r} is not a document in this repository's index — "
            f"content cannot be moved somewhere the registry does not claim",
            where)
        return None
    if destination == source:
        bad("bloat-destination-is-source",
            f"{destination} is the document being judged — a move to itself "
            f"changes nothing and would read as an approved edit", where)
        return None
    if document.kind not in DESTINATION_KINDS:
        bad("bloat-destination-kind-ineligible",
            f"{destination} is a {document.kind} document — content is never "
            f"moved into one, because its own lifecycle ends in distillation "
            f"or retirement and would take the moved content with it", where)
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


def _check_proposal(recorder, raw, where, verdict):
    proposal = raw.get("proposal")
    if verdict in PROPOSAL_VERDICTS:
        if not _nonempty(proposal):
            recorder.bad("bloat-proposal-required",
                         f"{verdict} replaces text, so it must carry the "
                         f"replacement", where)
            return None
        return proposal
    if proposal is not None:
        recorder.bad("bloat-proposal-forbidden",
                     f"{verdict} writes no replacement text, so it carries no "
                     f"proposal", where)
    return None


def _check_status(recorder, raw, where, verdict):
    status = raw.get("status")
    if verdict == DISTILL:
        if status not in DISTILL_STATUSES:
            recorder.bad("bloat-unknown-status",
                         f"a {DISTILL} verdict's status must be one of "
                         f"{list(DISTILL_STATUSES)}, not {status!r} — whether "
                         f"the work landed decides whether anything may be "
                         f"applied at all", where)
            return None
        return status
    if status is not None:
        recorder.bad("bloat-status-forbidden",
                     f"only {DISTILL} carries a lifecycle status", where)
    return None


def _reject_sample(recorder, raw, where, scoped):
    """A sample is review order. On anything but a bulk scope it is nothing."""
    sample = raw.get("sample")
    if sample is None:
        return
    if not scoped:
        recorder.bad("bloat-sampling-not-authority",
                     f"{where} is a judgment about one document, so a sample "
                     f"says nothing — sampling prioritizes review of a bulk "
                     f"scope and never stands in for reading the subject",
                     where)
        return
    if not (isinstance(sample, list) and all(_nonempty(s) for s in sample)):
        recorder.bad("bloat-invalid-shape",
                     f"{where}: sample must be a list of paths", where)


def _build(recorder, record_id, verdict, path, units, extra):
    finding = build_finding(
        lineage=recorder.lineage, code=verdict, path=path,
        units=units, record_id=record_id, extra=extra,
    )
    if isinstance(finding, Invalid):
        recorder.problems.extend(finding.problems)
        return ()
    return (finding,)


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
    so the corpus *is* its source evidence: `source_digest` is the context
    index's digest. Anything that could have changed the judgment — the
    document's own bytes, any other document's bytes, the registry, the audit
    configuration, the ruleset, the plugin — moves one of the two digests or a
    lineage field, and so moves the key.
    """
    return {
        path: cache_key(index.document(path).document_digest, index.digest, lineage)
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
