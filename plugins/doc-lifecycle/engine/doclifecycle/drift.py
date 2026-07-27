"""The drift audit: is what the documentation says still true of the code?

Read-only, and read-only by construction — this module opens documents, runs
`git` to ask what changed and when, and writes a report. It has no writer, and
a `fix` a verdict carries is recorded as data for the applier, never applied.

Two halves, and the line between them is the same one the document model draws.

**What to examine is deterministic.** `plan_drift_audit` derives the scope from
the registry's inventory: a full audit declares every living and narrative
document, a diff-scoped audit declares only the documents a commit range
changed or that cite a path it changed. A planning document is declared out of
scope, with its reason, rather than dropped. The plan is the basis a report's
declared scope states, so "the declared scope was examined" is a claim a reader
can re-derive rather than take.

**What is true is judged two different ways, by kind.** A *living* document's
claims are the model's to judge: `audit_drift` takes the verdicts a lane
returns and validates them hard — VERIFIED, STALE, or UNVERIFIABLE, each with
an evidence pointer, against a unit the document actually contains and can
carry a claim at all. A *narrative* document is never put through that: it must
be honestly dated, so its `> As of` anchor is checked here, deterministically,
against when the files it names last changed. A verdict offered for a narrative
document is refused outright — forcing narrative prose through claim checks is
the failure this split exists to prevent.

Coverage is never assumed. A document the lane did not return, returned as
failed, or returned verdicts that do not validate for, becomes an enumerated
entry in the report's `incomplete` list — so the result is `partial`, and
neither the payload nor any rendering of it can read as clean.

Waivers are disposition, not deletion: an accepted UNVERIFIABLE claim keeps its
record in the raw report and gains a `waived` annotation naming where the
acceptance is recorded. Nothing is ever removed from a report because someone
accepted it.
"""

import datetime
import json
import os
import re
from dataclasses import dataclass, field
from typing import Optional, Tuple

from . import ARTIFACT_SCHEMA_VERSION
from . import repository as repository_mod
from .digest import sha256_canonical
from .finding import build_finding
from .inventory import DEFAULT_REGISTRY_PATH, build_inventory
from .registry import compile_glob
from .report import (
    EvidenceBoundary,
    Lineage,
    current_lineage,
    state_from_content,
    validate_report,
)
from .results import STATUS_OK, Invalid, Problem
from .segment import segment_document

# How much of the corpus a run set out to examine. Both are report audit modes:
# `full` is the whole inventory, `incremental` is a commit range.
MODE_FULL = "full"
MODE_INCREMENTAL = "incremental"
MODES = (MODE_FULL, MODE_INCREMENTAL)

# What a document owes the drift audit, which follows from its kind and nothing
# else. A living document's claims must currently be true; a narrative document
# must be honestly dated, and is never line-verified.
OBLIGATION_ASSERTIONS = "assertions"
OBLIGATION_ANCHOR = "anchor"
KIND_OBLIGATIONS = {
    "living": OBLIGATION_ASSERTIONS,
    "narrative": OBLIGATION_ANCHOR,
}
PLANNING_REASON = (
    "a planning document carries lifecycle state rather than standing claims "
    "about the code — its obligation is distillation or retirement, not drift"
)

# The three verdicts, and nothing else. Absorbed verbatim from the legacy drift
# skill's output contract, because consumers switch on these strings.
VERDICT_VERIFIED = "VERIFIED"
VERDICT_STALE = "STALE"
VERDICT_UNVERIFIABLE = "UNVERIFIABLE"
VERDICTS = (VERDICT_VERIFIED, VERDICT_STALE, VERDICT_UNVERIFIABLE)
# The verdicts that assert someone read the code. Both must name where.
# UNVERIFIABLE is the case where there is nothing checkable to point at — that
# *is* the finding — so it may report an observation without a source.
POINTED_VERDICTS = (VERDICT_VERIFIED, VERDICT_STALE)
# The verdicts that become records. A VERIFIED claim is coverage, not a finding.
FINDING_VERDICTS = (VERDICT_STALE, VERDICT_UNVERIFIABLE)

# What kind of thing the claim asserts, and how hard it was checked. Both are
# the legacy vocabulary, unchanged: 1 static (grep), 2 shallow (read the cited
# line), 3 deep (read the implementing code).
CLAIM_KINDS = ("command", "path", "symbol", "behavior", "structure", "value")
TIERS = (1, 2, 3)

VERDICT_FIELDS = ("unit", "verdict", "kind", "tier", "evidence", "fix")
REQUIRED_VERDICT_FIELDS = ("unit", "verdict", "kind", "tier", "evidence")
EVIDENCE_FIELDS = ("source", "line", "observed")
ENTRY_FIELDS = ("path", "status", "verdicts", "reason", "chunk")
VERDICTS_FIELDS = ("schema_version", "documents")

ENTRY_OK = "ok"
ENTRY_FAILED = "failed"
ENTRY_STATUSES = (ENTRY_OK, ENTRY_FAILED)

# Anchor findings. Deterministic, engine-side, and about the anchor only: what
# the narrative prose around it says is not audited here at all.
CODE_ANCHOR_MISSING = "ANCHOR-MISSING"
CODE_ANCHOR_MALFORMED = "ANCHOR-MALFORMED"
CODE_ANCHOR_STALE = "ANCHOR-STALE"
CODE_ANCHOR_UNVERIFIABLE = "ANCHOR-UNVERIFIABLE"

# `> As of <YYYY-MM-DD> (<anchors current at writing>)`, as growing-docs writes
# it — matched against the segmenter's normalized block-quote text, where the
# `> ` marker is already gone.
ANCHOR_PREFIX = "As of"
ANCHOR = re.compile(r"^As of\s+(\S+)\s*\((.+)\)\s*$")
ISO_DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
BACKTICKED = re.compile(r"`([^`]+)`")
LINE_SUFFIX = re.compile(r":\d+$")
# A backticked token is a repository path when it names a directory or carries a
# file extension that starts with a letter. The second half is what keeps a
# version string (`v1.2`) from being opened as a file that has gone missing.
FILE_EXTENSION = re.compile(r"\.[A-Za-z][A-Za-z0-9]{0,5}$")

RECORD_ID = "DRIFT-{:03d}"

# What a run declares it was permitted to consult when the caller names nothing.
# Deliberately everything: a boundary must be honest before it is narrow, and a
# default that quietly excluded part of the repository would make every verdict
# rest on a limit nobody declared.
DEFAULT_EVIDENCE = ("**",)


def _one_line(value):
    """A non-empty single-line string — what a report field may carry."""
    return (
        isinstance(value, str)
        and value.strip() != ""
        and not any(c in value for c in "\n\r\x00")
    )


@dataclass(frozen=True)
class PlannedDocument:
    """One document the audit declared, and what its kind owes."""

    path: str
    kind: str
    obligation: str

    def to_dict(self):
        return {"path": self.path, "kind": self.kind,
                "obligation": self.obligation}


@dataclass(frozen=True)
class ExcludedDocument:
    """One document the audit deliberately did not declare, and why.

    Enumerated rather than dropped: a scope is only checkable if what it leaves
    out is visible next to what it takes in.
    """

    path: str
    kind: str
    reason: str

    def to_dict(self):
        return {"path": self.path, "kind": self.kind, "reason": self.reason}


@dataclass(frozen=True)
class DriftPlan:
    """The deterministic scope of one drift audit.

    Derived from the registry's inventory and, for a diff-scoped run, a commit
    range. No model is involved, so the same repository state always plans the
    same audit — which is what lets a report's declared scope be re-derived
    instead of trusted.
    """

    mode: str
    basis: str
    since: Optional[str]
    documents: Tuple[PlannedDocument, ...]
    excluded: Tuple[ExcludedDocument, ...]
    status: str = STATUS_OK

    def to_dict(self):
        return {
            "status": self.status,
            "schema_version": ARTIFACT_SCHEMA_VERSION,
            "mode": self.mode,
            "basis": self.basis,
            "since": self.since,
            "documents": [d.to_dict() for d in self.documents],
            "excluded": [d.to_dict() for d in self.excluded],
        }


@dataclass(frozen=True)
class _Spec:
    """One finding the audit reached, before it is numbered and digested."""

    code: str
    path: str
    units: Tuple[str, ...]
    extra: dict = field(default_factory=dict)


@dataclass(frozen=True)
class _Gap:
    """One declared document the audit did not examine, and why."""

    scope: str
    reason: str

    def to_dict(self):
        return {"scope": self.scope, "reason": self.reason}


def _document_text(repo_root, path):
    try:
        with open(os.path.join(repo_root, path), encoding="utf-8") as fh:
            return fh.read()
    except (OSError, UnicodeDecodeError):
        # Unreadable here means unexaminable later, where it becomes a coverage
        # gap. Planning errs toward declaring it, never toward skipping it.
        return None


def _affected(repo_root, path, changed):
    """Is this document in the blast radius of `changed`?

    Two ways in: the document itself changed, or its text names a path that
    changed. The second is a text search on purpose — cheap, deterministic, and
    honest about being a lower bound, which is exactly why a diff-scoped report
    declares a narrower scope rather than claiming coverage.
    """
    if path in changed:
        return True
    text = _document_text(repo_root, path)
    if text is None:
        return True
    return any(other != path and other in text for other in changed)


def plan_drift_audit(repo_root, mode=MODE_FULL, since=None,
                     registry_path=DEFAULT_REGISTRY_PATH):
    """Derive the scope of a drift audit. Returns a `DriftPlan` or `Invalid`."""
    problems = []
    if mode not in MODES:
        problems.append(Problem(
            code="drift-unknown-mode",
            message=(
                f"{mode!r} is not a drift audit mode — a report says what "
                f"'the declared scope' meant by naming one of {list(MODES)}"
            ),
            location="mode",
        ))
    elif mode == MODE_INCREMENTAL and since is None:
        problems.append(Problem(
            code="drift-missing-baseline",
            message=(
                "a diff-scoped audit needs the commit to scope against — "
                "without one there is no diff, and a run that guessed would be "
                "declaring a scope nobody can re-derive"
            ),
            location="since",
        ))
    elif mode == MODE_FULL and since is not None:
        problems.append(Problem(
            code="drift-baseline-not-applicable",
            message=(
                f"a full audit examines the whole inventory, so it cannot also "
                f"be scoped to {since!r} — run it as {MODE_INCREMENTAL!r} to "
                f"scope against a commit, and do not call the result full"
            ),
            location="since",
        ))
    if problems:
        return Invalid(tuple(problems))

    inventory = build_inventory(repo_root, registry_path)
    if isinstance(inventory, Invalid):
        return inventory

    baseline, changed = None, ()
    if mode == MODE_INCREMENTAL:
        baseline, problem = repository_mod.resolve_commit(repo_root, since)
        if problem is not None:
            return Invalid((Problem(
                code="drift-unknown-baseline",
                message=(
                    f"{since!r} is not a commit in this repository — a "
                    f"diff-scoped audit derives its scope from a commit range, "
                    f"and cannot declare one against a revision that is not "
                    f"there"
                ),
                location="since",
            ),))
        changed, problem = repository_mod.changed_paths(repo_root, baseline)
        if problem is not None:
            return Invalid((problem,))
        basis = (
            f"diff-scoped: documents changed by, or naming a path changed by, "
            f"{baseline}..HEAD — this run examined those documents and no "
            f"others"
        )
    else:
        basis = (
            "full corpus: every living and narrative document in the document "
            "inventory"
        )

    documents, excluded = [], []
    for document in sorted(inventory.documents, key=lambda d: d.path):
        obligation = KIND_OBLIGATIONS.get(document.kind)
        if obligation is None:
            excluded.append(ExcludedDocument(
                path=document.path, kind=document.kind, reason=PLANNING_REASON,
            ))
        elif mode == MODE_INCREMENTAL and not _affected(
            repo_root, document.path, changed
        ):
            excluded.append(ExcludedDocument(
                path=document.path, kind=document.kind,
                reason=(
                    f"unchanged by {baseline}..HEAD, and names no path that "
                    f"range changed"
                ),
            ))
        else:
            documents.append(PlannedDocument(
                path=document.path, kind=document.kind, obligation=obligation,
            ))

    return DriftPlan(
        mode=mode, basis=basis, since=baseline,
        documents=tuple(documents), excluded=tuple(excluded),
    )


def _load_waivers(repo_root, waivers_path):
    """(waivers, None) or ((), problem). An absent file is simply no waivers.

    A malformed one is not: a typo that silently un-waived everything would
    defeat the mechanism, so it invalidates the run instead.
    """
    if waivers_path is None:
        return (), None
    absolute = os.path.join(repo_root, waivers_path)

    def bad(detail):
        return Problem(
            code="drift-waivers-invalid",
            message=(
                f"the waivers at {waivers_path} cannot be read as "
                f"{{'waivers': [{{'file', 'claim'}}]}}: {detail}. A waivers file "
                f"nobody can parse would silently accept nothing, which is the "
                f"opposite of what it records."
            ),
            location=waivers_path,
        )

    if not os.path.exists(absolute):
        return (), None
    try:
        with open(absolute, encoding="utf-8") as fh:
            payload = json.load(fh)
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        return (), bad(str(exc))
    if not isinstance(payload, dict) or not isinstance(
        payload.get("waivers"), list
    ):
        return (), bad("it must be an object carrying a 'waivers' array")
    waivers = []
    for i, entry in enumerate(payload["waivers"]):
        if not isinstance(entry, dict) or not _one_line(entry.get("file")) or (
            not _one_line(entry.get("claim"))
        ):
            return (), bad(f"waivers[{i}] needs a 'file' and the 'claim' text "
                           f"it accepts")
        waivers.append(entry)
    return tuple(waivers), None


def _audit_config_digest(boundary):
    """The consumer configuration this audit ran under.

    What a consumer can set that could change a verdict — today, the limit of
    what the run was permitted to consult. Waivers are deliberately *not* in
    here: accepting a claim changes what a reader is asked to look at, never
    what the audit found, so it must not expire reports or re-key the findings
    an approval set selects. Detection stays pure; disposition is annotation.
    """
    return sha256_canonical({
        "schema_version": ARTIFACT_SCHEMA_VERSION,
        "audit": "drift",
        "evidence_boundary": boundary.to_dict(),
    })


def _waiver_for(waivers, waivers_path, path, claim):
    """The waiver accepting this claim, as record data, or None.

    Containment rather than equality: a waiver names the claim text a human
    read on a line, and an assertion unit is the whole sentence that line sits
    in. A waiver is therefore exactly as broad as the text it quotes.
    """
    for waiver in waivers:
        if waiver["file"] == path and waiver["claim"] in claim:
            annotation = {"claim": waiver["claim"], "source": waivers_path}
            for name in ("reason", "date"):
                if _one_line(waiver.get(name)):
                    annotation[name] = waiver[name]
            return annotation
    return None


def _within(boundary, source):
    """Is `source` inside the evidence boundary the run declared?"""
    if any(compile_glob(g).match(source) for g in boundary.excluded):
        return False
    return any(compile_glob(g).match(source) for g in boundary.sources)


def _evidence(raw, verdict, boundary, bad, where):
    """Validate one verdict's evidence. Returns (evidence, ok)."""
    if not isinstance(raw, dict) or set(raw) - set(EVIDENCE_FIELDS) or (
        not _one_line(raw.get("observed"))
    ):
        bad("drift-verdict-invalid-evidence",
            f"evidence must be an object naming the fact observed and where — "
            f"{list(EVIDENCE_FIELDS)}, 'observed' required — and it is "
            f"mandatory for every verdict, VERIFIED included: a verdict "
            f"nobody can follow is a verdict nobody can check",
            where)
        return None, False

    ok = True
    source = raw.get("source")
    if source is not None and not _one_line(source):
        bad("drift-verdict-invalid-evidence",
            "evidence.source must be a repository-relative path", where)
        ok = False
    elif source is None and verdict in POINTED_VERDICTS:
        bad("drift-verdict-invalid-evidence",
            f"a {verdict} verdict asserts that a place in the repository was "
            f"read, so evidence.source must say which one",
            where)
        ok = False
    line = raw.get("line")
    if line is not None and (
        isinstance(line, bool) or not isinstance(line, int) or line < 1
    ):
        bad("drift-verdict-invalid-evidence",
            "evidence.line must be a line number counted from 1", where)
        ok = False
    if ok and source is not None and not _within(boundary, source):
        bad("drift-evidence-outside-boundary",
            f"evidence.source {source!r} is outside the evidence boundary this "
            f"run declared ({list(boundary.sources)}) — a verdict resting on "
            f"something the report says was not consulted is not checkable",
            where)
        ok = False
    return (dict(raw) if ok else None), ok


def _validated_verdicts(segmentation, entries, boundary, path):
    """(specs, problems) for one document's verdicts.

    Exhaustive, like every other check on model output: one pass names every
    problem, so a re-prompt can address all of them. Any problem at all means
    the document was not validly examined, and the caller turns that into a
    coverage gap rather than a quietly missing finding.
    """
    problems = []

    def bad(code, message, where=None):
        problems.append(Problem(code=code, message=message, location=where))

    if not isinstance(entries, list):
        return (), (Problem(
            code="drift-verdict-invalid-shape",
            message="a document's verdicts must be a list",
            location=path,
        ),)

    capable = {u.digest for u in segmentation.units if u.assertion_capable}
    known = {u.digest: u for u in segmentation.units}
    specs, seen = [], set()

    for i, entry in enumerate(entries):
        where = f"{path}:verdicts[{i}]"
        if not isinstance(entry, dict) or set(entry) - set(VERDICT_FIELDS) or (
            not set(REQUIRED_VERDICT_FIELDS) <= set(entry)
        ):
            bad("drift-verdict-invalid-shape",
                f"a verdict is an object with {list(REQUIRED_VERDICT_FIELDS)} "
                f"and, for {VERDICT_STALE}, 'fix' — nothing else",
                where)
            continue

        unit, verdict = entry["unit"], entry["verdict"]
        valid = True
        if verdict not in VERDICTS:
            bad("drift-unknown-verdict",
                f"{verdict!r} is not a drift verdict — a claim is one of "
                f"{list(VERDICTS)}, and an unrecognized answer says nothing "
                f"about whether the documentation is still true",
                where)
            valid = False
        if entry["kind"] not in CLAIM_KINDS:
            bad("drift-verdict-unknown-kind",
                f"{entry['kind']!r} is not a claim kind — it is one of "
                f"{list(CLAIM_KINDS)}, which downstream tooling switches on",
                where)
            valid = False
        tier = entry["tier"]
        if isinstance(tier, bool) or not isinstance(tier, int) or (
            tier not in TIERS
        ):
            bad("drift-verdict-invalid-tier",
                f"tier must be one of {list(TIERS)} — how hard the claim was "
                f"checked is part of what a reviewer is being asked to trust",
                where)
            valid = False
        if unit not in known:
            bad("drift-verdict-unknown-unit",
                f"no assertion unit in {path} has digest {unit!r} — a verdict "
                f"about a unit the document does not contain describes nothing",
                where)
            valid = False
        elif unit not in capable:
            bad("drift-verdict-not-assertion-capable",
                f"a {known[unit].kind} cannot carry a claim, so it cannot be "
                f"found stale — it is structure, not prose",
                where)
            valid = False
        if unit in seen:
            bad("drift-verdict-duplicate",
                f"unit {unit!r} is judged more than once — a claim has one "
                f"verdict, and two answers is no answer",
                where)
            valid = False
        seen.add(unit)

        evidence, ok = _evidence(entry["evidence"], verdict, boundary, bad, where)
        valid = valid and ok

        fix = entry.get("fix")
        if verdict == VERDICT_STALE:
            if not _one_line(fix):
                bad("drift-verdict-invalid-fix",
                    f"a {VERDICT_STALE} verdict must carry 'fix': the complete "
                    f"replacement line, never an instruction describing one",
                    where)
                valid = False
        elif fix is not None:
            bad("drift-verdict-invalid-fix",
                f"only a {VERDICT_STALE} verdict carries a fix; {verdict!r} "
                f"proposes no edit",
                where)
            valid = False

        if not valid or verdict not in FINDING_VERDICTS:
            continue
        unit_data = known[unit]
        extra = {
            "claim": unit_data.text,
            "location": f"{path}:{unit_data.line}",
            "kind": entry["kind"],
            "tier": tier,
            "evidence": evidence,
        }
        if verdict == VERDICT_STALE:
            extra["fix"] = fix
        specs.append(_Spec(code=verdict, path=path, units=(unit,), extra=extra))

    for unit in sorted(capable - seen):
        bad("drift-verdict-missing",
            f"assertion unit {unit!r} in {path} was left unjudged — an "
            f"unjudged claim is indistinguishable from one nobody found a "
            f"problem with, so the document was not examined",
            path)

    if problems:
        return (), tuple(problems)
    return tuple(specs), ()


def _verdict_entries(payload, plan):
    """({path: entry}, problems) for the verdicts a lane returned.

    Refuses outright — the whole run, not one document — when it cannot tell
    which document an entry is about, when an entry names a document the plan
    did not declare, or when a narrative document is offered claim verdicts. A
    coverage gap is the answer for a document that was not examined; none of
    these is that.
    """
    problems = []

    def bad(code, message, where=None):
        problems.append(Problem(code=code, message=message, location=where))

    if payload is None:
        return {}, ()
    if not isinstance(payload, dict) or set(payload) - set(VERDICTS_FIELDS) or (
        "documents" not in payload
    ) or not isinstance(payload["documents"], list):
        return {}, (Problem(
            code="drift-verdicts-invalid-shape",
            message=(
                f"verdicts must be an object shaped "
                f"{{'documents': [...]}} (optionally with 'schema_version') — "
                f"one entry per document the plan declared"
            ),
            location="verdicts",
        ),)
    version = payload.get("schema_version", ARTIFACT_SCHEMA_VERSION)
    if version != ARTIFACT_SCHEMA_VERSION:
        return {}, (Problem(
            code="drift-verdicts-invalid-shape",
            message=(
                f"verdicts schema_version {version!r} is not supported; this "
                f"engine reads integer version {ARTIFACT_SCHEMA_VERSION}"
            ),
            location="verdicts.schema_version",
        ),)

    planned = {d.path: d for d in plan.documents}
    entries = {}
    for i, entry in enumerate(payload["documents"]):
        where = f"documents[{i}]"
        if not isinstance(entry, dict) or set(entry) - set(ENTRY_FIELDS) or (
            not _one_line(entry.get("path"))
        ) or entry.get("status") not in ENTRY_STATUSES:
            bad("drift-verdicts-invalid-entry",
                f"each entry names a 'path' and a 'status' of "
                f"{list(ENTRY_STATUSES)}, and carries {list(ENTRY_FIELDS)} and "
                f"nothing else",
                where)
            continue
        path, status = entry["path"], entry["status"]
        if status == ENTRY_OK and ("reason" in entry or "verdicts" not in entry):
            bad("drift-verdicts-invalid-entry",
                f"an {ENTRY_OK!r} entry carries the verdicts it reached, and no "
                f"reason for not reaching them",
                where)
            continue
        if status == ENTRY_FAILED and (
            "verdicts" in entry or not _one_line(entry.get("reason"))
        ):
            bad("drift-verdicts-invalid-entry",
                f"a {ENTRY_FAILED!r} entry must say why in 'reason' — a gap "
                f"with no reason is indistinguishable from a document nobody "
                f"thought about",
                where)
            continue
        if "chunk" in entry and not _one_line(entry["chunk"]):
            bad("drift-verdicts-invalid-entry",
                "'chunk' names the unit of work that produced the entry", where)
            continue
        if path in entries:
            bad("drift-verdict-duplicate-document",
                f"two entries report on {path} — which one describes the run "
                f"is not knowable from here",
                where)
            continue
        declared = planned.get(path)
        if declared is None:
            bad("drift-verdict-undeclared-document",
                f"{path} is not in this audit's declared scope — a report whose "
                f"scope did not name a document it examined would not describe "
                f"the run",
                where)
            continue
        if declared.obligation != OBLIGATION_ASSERTIONS:
            bad("drift-verdict-on-narrative-document",
                f"{path} is a {declared.kind} document: it must be honestly "
                f"dated, not line-verified, so its anchor is checked here and "
                f"no claim verdict about it is accepted",
                where)
            continue
        entries[path] = entry
    return entries, tuple(problems)


def _anchor_references(text):
    """The repository paths an `As of (...)` anchor names, in order.

    Backticked tokens only. An anchor writes its references in code spans, and
    reading unbackticked prose as filenames would open paths a sentence merely
    mentioned.
    """
    references = []
    for token in BACKTICKED.findall(text):
        token = LINE_SUFFIX.sub("", token.strip())
        if not token or " " in token:
            continue
        if token.startswith(("/", "~")) or ".." in token.split("/"):
            continue                       # not a repository-relative path
        if "/" not in token and not FILE_EXTENSION.search(token):
            continue                       # a commit id or a bare word
        if token not in references:
            references.append(token)
    return references


def _anchor_findings(repo_root, path, anchor, as_of, references):
    """Findings about one well-formed anchor: what has moved under it."""
    stale, unverifiable = [], []
    for reference in references:
        if not os.path.isfile(os.path.join(repo_root, reference)):
            stale.append((reference, "is no longer in the repository"))
            continue
        change, problem = repository_mod.last_change(repo_root, reference)
        if problem is not None or change is None:
            unverifiable.append((
                reference,
                "has no commit history, so the anchor cannot be checked "
                "against when it last changed",
            ))
        elif change[0] > as_of:
            stale.append((
                reference,
                f"last changed {change[0]} in {change[1]}, after the anchor's "
                f"as-of date {as_of}",
            ))

    specs = []
    for code, offenders in (
        (CODE_ANCHOR_STALE, stale), (CODE_ANCHOR_UNVERIFIABLE, unverifiable)
    ):
        if not offenders:
            continue
        offenders = sorted(offenders)
        source, detail = offenders[0]
        observed = f"{source} {detail}"
        if len(offenders) > 1:
            observed += f" (and {len(offenders) - 1} more the anchor names)"
        specs.append(_Spec(
            code=code, path=path, units=(anchor.digest,),
            extra={
                "claim": anchor.text,
                "location": f"{path}:{anchor.line}",
                "as_of": as_of,
                "references": [reference for reference, _ in offenders],
                "evidence": {"source": source, "observed": observed},
            },
        ))
    return specs


def _audit_anchor(repo_root, path, registry_path):
    """(specs, gap) for one narrative document.

    Deterministic and model-free: the obligation is honest dating, so what is
    checked is the anchor's shape and whether what it names has moved. The prose
    around it is never read as a claim.
    """
    segmentation = segment_document(repo_root, path, registry_path)
    if isinstance(segmentation, Invalid):
        return (), _Gap(scope=path, reason=_gap_reason(segmentation.problems))
    units = segmentation.units
    if not units:
        return (), _Gap(
            scope=path,
            reason="the document is empty, so it carries no anchor to check",
        )

    anchor = next(
        (u for u in units
         if u.kind == "block_quote" and u.text.startswith(ANCHOR_PREFIX)),
        None,
    )
    if anchor is None:
        return (_Spec(
            code=CODE_ANCHOR_MISSING, path=path, units=(units[0].digest,),
            extra={
                "location": f"{path}:{units[0].line}",
                "message": (
                    "a narrative document must be honestly dated: it carries no "
                    "`> As of <YYYY-MM-DD> (<anchors>)` line, so nothing says "
                    "what it was true of"
                ),
            },
        ),), None

    match = ANCHOR.match(anchor.text)
    as_of = match.group(1) if match else None
    if match and ISO_DATE.match(as_of):
        try:
            datetime.date.fromisoformat(as_of)
        except ValueError:
            match = None
    else:
        match = None
    if match is None:
        return (_Spec(
            code=CODE_ANCHOR_MALFORMED, path=path, units=(anchor.digest,),
            extra={
                "claim": anchor.text,
                "location": f"{path}:{anchor.line}",
                "message": (
                    "the anchor must read `As of <YYYY-MM-DD> (<anchors current "
                    "at writing>)` — a date nobody can compare cannot say "
                    "whether the document is honestly dated"
                ),
            },
        ),), None

    return tuple(_anchor_findings(
        repo_root, path, anchor, as_of, _anchor_references(match.group(2))
    )), None


def _gap_reason(problems):
    """One line naming why a document was not examined, without prose drift."""
    return ", ".join(sorted({problem.code for problem in problems}))


def _audit_assertions(repo_root, path, entry, boundary, registry_path):
    """(specs, gap) for one living document, given what the lane returned."""
    if entry is None:
        return (), _Gap(
            scope=path,
            reason=(
                "no verdict set was returned for this document, so none of its "
                "claims were examined"
            ),
        )
    if entry["status"] == ENTRY_FAILED:
        reason = entry["reason"]
        if "chunk" in entry:
            reason = f"{entry['chunk']}: {reason}"
        return (), _Gap(scope=path, reason=reason)

    segmentation = segment_document(repo_root, path, registry_path)
    if isinstance(segmentation, Invalid):
        return (), _Gap(scope=path, reason=_gap_reason(segmentation.problems))

    specs, problems = _validated_verdicts(
        segmentation, entry["verdicts"], boundary, path
    )
    if problems:
        return (), _Gap(
            scope=path,
            reason=(
                f"the verdicts returned for this document did not validate: "
                f"{_gap_reason(problems)}"
            ),
        )
    return specs, None


def load_verdicts(path):
    """Read a lane's verdicts file. Returns the payload, or `Invalid`.

    The file/dict split `report.load_report` and `validate_report` draw: reading
    a file is a separate failure from what the payload says, and a command must
    answer an unreadable one with a verdict rather than a traceback.
    """
    try:
        with open(path, encoding="utf-8") as fh:
            return json.load(fh)
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        return Invalid((Problem(
            code="drift-verdicts-unreadable",
            message=f"cannot read the verdicts at {path}: {exc}",
            location=path,
        ),))


def audit_drift(repo_root, mode=MODE_FULL, since=None, verdicts=None,
                waivers=None, evidence_sources=DEFAULT_EVIDENCE, evidence_excluded=(),
                registry_path=DEFAULT_REGISTRY_PATH):
    """Run a drift audit. Returns a validated `Report`, or `Invalid`.

    `verdicts` is what a model-driven lane returned for the living documents the
    plan declared — `{"documents": [{"path", "status", ...}]}`. Narrative
    documents need none: their anchors are checked here.

    The report is built and then run through `report.validate_report`, the
    landed validator rather than a parallel one, so an audit cannot emit
    something the contract would refuse.
    """
    plan = plan_drift_audit(repo_root, mode, since, registry_path)
    if isinstance(plan, Invalid):
        return plan

    accepted, problem = _load_waivers(repo_root, waivers)
    if problem is not None:
        return Invalid((problem,))

    boundary = EvidenceBoundary(tuple(evidence_sources), tuple(evidence_excluded))
    state, problems = current_lineage(
        repo_root, registry_path, _audit_config_digest(boundary)
    )
    if problems:
        return Invalid(tuple(problems))
    lineage = Lineage(audit_mode=mode, evidence_boundary=boundary, **state)

    entries, problems = _verdict_entries(verdicts, plan)
    if problems:
        return Invalid(problems)

    specs, gaps = [], []
    for document in plan.documents:
        if document.obligation == OBLIGATION_ANCHOR:
            found, gap = _audit_anchor(repo_root, document.path, registry_path)
        else:
            found, gap = _audit_assertions(
                repo_root, document.path, entries.get(document.path), boundary,
                registry_path,
            )
        specs.extend(found)
        if gap is not None:
            gaps.append(gap)

    records = []
    for number, spec in enumerate(specs, start=1):
        extra = dict(spec.extra)
        if spec.code == VERDICT_UNVERIFIABLE:
            # Disposition, never deletion: an accepted claim keeps its record
            # and says who accepted it. Waivers are not part of any digest, so
            # accepting a claim cannot re-key what an approval set selects.
            waived = _waiver_for(accepted, waivers, spec.path, extra["claim"])
            if waived is not None:
                extra["waived"] = waived
        finding = build_finding(
            lineage=lineage, code=spec.code, path=spec.path, units=spec.units,
            record_id=RECORD_ID.format(number), extra=extra,
        )
        if isinstance(finding, Invalid):
            return finding
        records.append(finding.to_record())

    incomplete = [gap.to_dict() for gap in gaps]
    return validate_report({
        "status": state_from_content(records, incomplete),
        "schema_version": ARTIFACT_SCHEMA_VERSION,
        "lineage": lineage.to_dict(),
        "records": records,
        "incomplete": incomplete,
        "scope": {
            "basis": plan.basis,
            "documents": [d.path for d in plan.documents],
        },
    }, registry_path=registry_path)
