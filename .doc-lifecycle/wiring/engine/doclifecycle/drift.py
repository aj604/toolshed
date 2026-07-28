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

Waivers are disposition, not deletion: an accepted claim keeps its record in the
raw report and gains a `waived` annotation naming where the acceptance is
recorded. Nothing is ever removed from a report because someone accepted it —
on an UNVERIFIABLE claim the annotation says a human has stopped asking, and on
a STALE one it says a human disputes the finding, which is what keeps an
auto-apply policy off it.
"""

import datetime
import json
import os
import re
from dataclasses import dataclass, field
from typing import Optional, Tuple

from . import ARTIFACT_SCHEMA_VERSION
from . import repository as repository_mod
from .digest import sha256_canonical, sha256_file
from .finding import (
    FACTUAL,
    NON_ASSERTIVE,
    build_finding,
    record_classifications,
)
from .inventory import DEFAULT_REGISTRY_PATH, build_inventory
from .paths import repository_relative_problem
from .registry import compile_glob
from .report import (
    EXCLUSION_PLANNING_KIND,
    EXCLUSION_UNAFFECTED_BY_RANGE,
    SCOPE_WHOLE_INVENTORY,
    EvidenceBoundary,
    Incomplete,
    Lineage,
    current_lineage,
    state_from_content,
    validate_report,
)
from .results import STATUS_OK, Invalid, Problem
from .segment import segment_document

# How much of the inventory a run set out to examine. Both are report audit modes:
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
# The inventory finding that means "a document, but nobody said what kind" —
# the one closed-world finding a drift audit must answer for, because it is the
# one that names something the audit was supposed to examine.
UNREGISTERED_DOCUMENT = "unregistered-document"

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

# What sort of thing the assertion is about, and how hard it was checked. Both
# are the legacy vocabulary, unchanged, because downstream tooling switches on
# them: tier 1 static (grep), 2 shallow (read the cited line), 3 deep (read the
# implementing code).
SUBJECT_KINDS = ("command", "path", "symbol", "behavior", "structure", "value")
TIERS = (1, 2, 3)

# Which classes are judged. Only `factual` carries an evidence obligation, so
# only it must be: a factual unit nobody judged is a hole in coverage.
# `non-assertive` prose connects, illustrates, or signposts — it asserts nothing
# the code could contradict, so a verdict against it is a claim nobody made.
# `normative` and `rationale` sit between: a rule or an explanation can go
# stale, but neither owes evidence, so a verdict is accepted and not required.
VERDICT_REQUIRED_CLASSES = (FACTUAL,)
VERDICT_FORBIDDEN_CLASSES = (NON_ASSERTIVE,)

VERDICT_FIELDS = ("unit", "assertion_class", "verdict", "kind", "tier",
                  "evidence", "fix")
REQUIRED_VERDICT_FIELDS = ("unit", "assertion_class")
# Owed by a unit whose class carries an evidence obligation, and refused for one
# whose class does not.
VERDICT_ONLY_FIELDS = ("verdict", "kind", "tier", "evidence")
# What a verdict may point at. `source`+`line` cite a place in the repository;
# `command` cites a local tool that was run to settle a claim no file in the
# repository can answer (#115). Exactly one of the two, because a verdict rests
# on one place a reader goes.
EVIDENCE_FIELDS = ("source", "line", "observed", "command")
EVIDENCE_CITATIONS = ("source", "command")
# What makes a cited command line more than one plain invocation: chaining,
# redirection, substitution, and escaping. A citation carrying any of them
# would be laundered by the report as a single read-only command a reader can
# re-run, which is exactly what it would not be. The engine never executes a
# citation — this is about what the report tells a reader to do. Globbing
# characters are deliberately absent: they change an argument, not what runs.
SHELL_SYNTAX = ";&|<>()$`\\"
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
CODE_ANCHOR_FUTURE_DATED = "ANCHOR-FUTURE-DATED"
CODE_ANCHOR_UNRESOLVABLE_REFERENCE = "ANCHOR-UNRESOLVABLE-REFERENCE"

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

# What bounds a waiver. Matching is containment — a waiver quotes the text a
# human read on a line, and a unit is the sentence that line sits in — so the
# fragment is the only thing deciding how far the acceptance reaches, and an
# unbounded fragment is an unbounded acceptance. `"e"` would annotate every
# assertion in a file; so would any one word.
#
# Both directions are guarded, because they fail differently. Too short is a
# fact about the waiver, knowable when it is read. Too broad is a fact about
# the run, knowable only after every record is drafted — a twelve-character
# fragment can still be the most common phrase in a document.
MIN_WAIVER_CLAIM = 12
MAX_WAIVER_UNITS = 10

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


def _is_valid_replacement_text(value, unit):
    """Complete physical replacement text for one assertion unit.

    A soft-wrapped unit may keep that shape with LF-separated physical lines.
    A single-line unit gains no authority to introduce new structure, and a
    blank line would be a paragraph boundary rather than a soft wrap. CR and
    NUL are never source-line separators in the contract.
    """
    if not isinstance(value, str) or any(c in value for c in "\r\x00"):
        return False
    lines = value.split("\n")
    return (
        all(line.strip() != "" for line in lines)
        and (len(lines) == 1 or unit.line < unit.end_line)
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
    out is visible next to what it takes in. `code` is the closed vocabulary
    `report.validate_report` cross-checks against the document's current kind
    (PR #87 review, N1); `reason` stays the prose next to it.
    """

    path: str
    kind: str
    reason: str
    code: str

    def to_dict(self):
        return {"path": self.path, "kind": self.kind, "reason": self.reason,
                "code": self.code}


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
    unclassified: Tuple[str, ...] = ()
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
            "unclassified": list(self.unclassified),
        }


@dataclass(frozen=True)
class _DraftFinding:
    """One finding the audit reached, before it is numbered and digested."""

    code: str
    path: str
    units: Tuple[str, ...]
    extra: dict = field(default_factory=dict)


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
            "full inventory: every living and narrative document the registry "
            "classifies"
        )

    documents, excluded = [], []
    for document in sorted(inventory.documents, key=lambda d: d.path):
        obligation = KIND_OBLIGATIONS.get(document.kind)
        if obligation is None:
            excluded.append(ExcludedDocument(
                path=document.path, kind=document.kind, reason=PLANNING_REASON,
                code=EXCLUSION_PLANNING_KIND,
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
                code=EXCLUSION_UNAFFECTED_BY_RANGE,
            ))
        else:
            documents.append(PlannedDocument(
                path=document.path, kind=document.kind, obligation=obligation,
            ))

    # Closed-world: a document under a declared root that no rule claims has no
    # known obligation, so the audit cannot examine it. It is neither declared
    # nor quietly skipped — it becomes a coverage gap, which is what an
    # unexaminable document in the corpus actually is. A `symlinked-path` is
    # not one: it is not a document at all, and the inventory says so.
    unclassified = tuple(
        finding.path for finding in inventory.findings
        if finding.code == UNREGISTERED_DOCUMENT
        and (mode == MODE_FULL or _affected(repo_root, finding.path, changed))
    )

    return DriftPlan(
        mode=mode, basis=basis, since=baseline,
        documents=tuple(documents), excluded=tuple(excluded),
        unclassified=unclassified,
    )


def load_waivers(repo_root, waivers_path):
    """(waivers, content digest, None) or ((), None, problem).

    An absent file is simply no waivers. A malformed one is not: a typo that
    silently un-waived everything would defeat the mechanism, so it invalidates
    the run instead.

    The digest is of the file's bytes, and it travels on every annotation the
    file produces. Without it a `waived` block names a path and nothing else,
    so nobody holding the report can tell whether the file said that — and the
    annotations are the one part of a report that is not otherwise reproducible
    from the repository. It is deliberately not in the audit-configuration
    digest: that is what freshness compares, and accepting a claim must not
    expire a prior report or re-key the findings an approval set selects.

    Public because the migration door reads the same file to work out which
    acceptances re-key onto the new contract. Two readers with two notions of
    what a waiver is would let a dry run promise the audit something else.
    """
    if waivers_path is None:
        return (), None, None
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
        return (), None, None
    try:
        with open(absolute, encoding="utf-8") as fh:
            payload = json.load(fh)
        digest = sha256_file(absolute)
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        return (), None, bad(str(exc))
    if not isinstance(payload, dict) or not isinstance(
        payload.get("waivers"), list
    ):
        return (), None, bad("it must be an object carrying a 'waivers' array")
    waivers = []
    for i, entry in enumerate(payload["waivers"]):
        if not isinstance(entry, dict) or not _one_line(entry.get("file")) or (
            not _one_line(entry.get("claim"))
        ):
            return (), None, bad(f"waivers[{i}] needs a 'file' and the 'claim' "
                                 f"text it accepts")
        if len(entry["claim"].strip()) < MIN_WAIVER_CLAIM:
            return (), None, bad(
                f"waivers[{i}] accepts {entry['claim']!r}, shorter than "
                f"{MIN_WAIVER_CLAIM} characters. A waiver is matched by "
                f"containment, so a fragment this short accepts every assertion "
                f"in the file rather than the line a human read — quote enough "
                f"of the line to name it"
            )
        waivers.append(entry)
    return tuple(waivers), digest, None


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


def _waiver_hits(waivers, specs):
    """(the waiver index accepting each spec or None, matches per waiver).

    Containment rather than equality: a waiver names the claim text a human
    read on a line, and an assertion unit is the whole sentence that line sits
    in. A waiver is therefore exactly as broad as the text it quotes — which is
    why how far it actually reached is a fact worth counting.

    Reaches every finding code, not only UNVERIFIABLE. On a STALE finding an
    acceptance is a human disputing the verdict, and a dispute a report did not
    show is one an auto-apply policy would act straight through.

    Two passes, because blast radius is a fact about the whole run: no
    annotation can honestly say how much its waiver accepted until every record
    is drafted.
    """
    hits, counts = [], [0] * len(waivers)
    for spec in specs:
        assertion = spec.extra.get("assertion")
        index = None
        if assertion is not None:
            index = next(
                (i for i, waiver in enumerate(waivers)
                 if waiver["file"] == spec.path
                 and waiver["claim"] in assertion),
                None,
            )
        if index is not None:
            counts[index] += 1
        hits.append(index)
    return hits, counts


def _breadth_problem(waivers, counts, waivers_path):
    """The first waiver that reached further than a quoted line could, or None.

    A refusal rather than a quiet over-waive, and the whole run rather than the
    one record: an acceptance this broad is operator configuration that is
    wrong, and the two ways it fails are both silent. An auto-apply policy that
    declines waiver-disputed records is switched off file-wide; one that does
    not is told a human disputed findings nobody looked at.
    """
    for waiver, count in zip(waivers, counts):
        if count > MAX_WAIVER_UNITS:
            return Problem(
                code="drift-waiver-too-broad",
                message=(
                    f"the waiver accepting {waiver['claim']!r} in "
                    f"{waiver['file']} annotates {count} findings, over the "
                    f"limit of {MAX_WAIVER_UNITS}. A waiver quotes the text a "
                    f"human read on one line; a fragment reaching this far is "
                    f"matching something else — quote more of the line, or "
                    f"write one waiver per claim accepted"
                ),
                location=waivers_path,
            )
    return None


def _waiver_annotation(waiver, waivers_path, digest, matched):
    """One record's `waived` block: who accepted what, from where, how widely.

    `matched` is the waiver's blast radius across the whole run, not this
    record's — a reader deciding what an acceptance means needs to know whether
    it named one claim or swept a document.
    """
    annotation = {
        "claim": waiver["claim"],
        "source": waivers_path,
        "source_digest": digest,
        "matched": matched,
    }
    for name in ("reason", "date"):
        if _one_line(waiver.get(name)):
            annotation[name] = waiver[name]
    return annotation


def _within(boundary, source):
    """Is `source` inside the evidence boundary the run declared?

    Only ever asked about a source `paths.repository_relative_problem` has
    already passed, and that order is the check. A glob is a string match: a
    boundary of `src/**` matches `src/../../../../etc/passwd` exactly as
    happily as it matches `src/fees.py`, so normalizing before matching is what
    makes the boundary a statement about the repository rather than about
    spelling.
    """
    if any(compile_glob(g).match(source) for g in boundary.excluded):
        return False
    return any(compile_glob(g).match(source) for g in boundary.sources)


def _command_spelling(command):
    """Why this cited command is not one command line, or None.

    Spelling before boundary, the same order a `source` is checked in and for
    the same reason: the boundary below matches the command's first token, and
    a shell program's first token says nothing about what the line would run.
    The engine never executes a citation — this is about what the report tells
    whoever checks the verdict to do.
    """
    if not _one_line(command):
        return ("evidence.command must be the single command line that settled "
                "the claim — a citation nobody can re-run is not one")
    if any(c in SHELL_SYNTAX for c in command):
        return (f"evidence.command {command!r} carries shell syntax "
                f"({SHELL_SYNTAX!r}) — chaining, redirection, substitution, or "
                f"escaping makes it a shell program, and a report must not "
                f"present one as a single read-only command a reader re-runs")
    return None


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
    cited = [name for name in EVIDENCE_CITATIONS if raw.get(name) is not None]
    if len(cited) > 1:
        # The one place this function stops at the first problem rather than
        # naming them all, and for the same reason the shape check above does:
        # which citation the rest of the checks are about is exactly what is
        # in doubt, so every one of them would be a guess.
        bad("drift-verdict-invalid-evidence",
            f"evidence cites both {list(EVIDENCE_CITATIONS)} — a verdict rests "
            f"on one place a reader goes, and two pointers leave nobody able to "
            f"say which one settled it",
            where)
        return None, False

    command = raw.get("command")
    if command is not None:
        # Every refusal below carries the command in `location`, so `_gap_reason`
        # can fold it into the coverage gap: the code alone says a citation
        # broke a rule, not which one.
        located = f"{where} command={command!r}"
        fault = _command_spelling(command)
        if fault:
            bad("drift-verdict-invalid-evidence", fault, located)
            ok = False
        if raw.get("line") is not None:
            bad("drift-verdict-invalid-evidence",
                "evidence.line points into a file, and a tool's output is not "
                "one — a command citation carries 'observed' and nothing else",
                located)
            ok = False
        if ok and command.split()[0] not in boundary.commands:
            bad("drift-evidence-outside-boundary",
                f"evidence.command {command!r} runs a tool outside the evidence "
                f"boundary this run declared ({list(boundary.commands)}) — a "
                f"verdict resting on something the report says was not "
                f"consulted is not checkable",
                located)
            ok = False
        return (dict(raw) if ok else None), ok

    source = raw.get("source")
    if source is not None:
        # Spelling before boundary: `paths.py` is the single owner of what a
        # repository-relative path is, and the boundary below is a glob match,
        # which a traversal spelling walks straight through. Refused, never
        # normalized — a pointer a reader must re-derive to follow is not one.
        fault = repository_relative_problem(source)
        if fault:
            code, reason = fault
            bad("drift-verdict-invalid-evidence",
                f"evidence.source must be a repository-relative path, and "
                f"{source!r} {reason} [{code}]",
                f"{where} source={source!r}")
            ok = False
    elif verdict in POINTED_VERDICTS:
        bad("drift-verdict-invalid-evidence",
            f"a {verdict} verdict asserts that something was actually checked, "
            f"so evidence must cite where: a repository path in "
            f"evidence.source, or the command that settled it in "
            f"evidence.command",
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
            f"{where} source={source!r}")
        ok = False
    return (dict(raw) if ok else None), ok


def _validated_verdicts(segmentation, entries, boundary, path):
    """(drafts, coverage, problems) for one document's answers.

    Two answers per unit, and the split is the document model's. *What the unit
    is* — its assertion class — is validated by `finding.record_classifications`,
    the landed owner of that rule, which also refuses a class against structure
    and names every unit nobody answered for. *Whether it is still true* is a
    verdict, and only the classes that carry an evidence obligation may have one:
    connective prose and rationale are answers in themselves, and forcing a
    verdict onto them would manufacture a claim nobody made.

    Exhaustive, like every other check on model output: one pass names every
    problem, so a re-prompt can address all of them. Any problem at all means
    the document was not validly examined, and the caller turns that into a
    coverage gap rather than a quietly missing finding.

    `coverage` is what a clean answer leaves behind. Validating the classes and
    the VERIFIED verdicts and then discarding them would make positive coverage
    rest on an absence — no record and no gap — so the class counts, the
    verdict counts, and every VERIFIED unit's evidence pointer are returned as
    reviewable data. None of it is a finding: a VERIFIED claim is proof the
    document was examined, not something to fix.
    """
    problems = []

    def bad(code, message, where=None):
        problems.append(Problem(code=code, message=message, location=where))

    if not isinstance(entries, list):
        return (), None, (Problem(
            code="drift-verdict-invalid-shape",
            message="a document's answers must be a list",
            location=path,
        ),)

    known = {u.digest: u for u in segmentation.units}
    by_ordinal = {u.ordinal: u.digest for u in segmentation.units}
    drafts, shaped, verified, judged_counts = [], [], [], {}

    for i, entry in enumerate(entries):
        where = f"{path}:verdicts[{i}]"
        if not isinstance(entry, dict) or set(entry) - set(VERDICT_FIELDS) or (
            not set(REQUIRED_VERDICT_FIELDS) <= set(entry)
        ):
            bad("drift-verdict-invalid-shape",
                f"an answer is an object with {list(REQUIRED_VERDICT_FIELDS)}, "
                f"plus {list(VERDICT_ONLY_FIELDS)} when the class carries an "
                f"evidence obligation — nothing else",
                where)
            continue
        # #116: a lane answers for a unit by the ordinal `segment` printed
        # alongside it — a small integer, never transcribed wrong the way a
        # 64-character digest is (the shadow-parity gate's G3 measurement: 39
        # of 1329 first-round answers named a digest no unit had, 36 of them
        # a real digest truncated or one/two characters off). A digest string
        # is still accepted directly, for a caller that already holds one —
        # `known`, just below, is exactly that lookup — so this only adds a
        # second, unambiguous way in: JSON's int and string are never the
        # same value, so there is no case where a well-formed answer could be
        # read either way.
        raw_unit = entry["unit"]
        if isinstance(raw_unit, int) and not isinstance(raw_unit, bool):
            if raw_unit not in by_ordinal:
                bad("drift-verdict-unknown-ordinal",
                    f"this document has no assertion unit at ordinal "
                    f"{raw_unit!r} — a verdict answers by the ordinal "
                    f"`segment` printed alongside each unit, and one outside "
                    f"that range names nothing to classify",
                    where)
                continue
            entry = dict(entry, unit=by_ordinal[raw_unit])
        shaped.append((where, entry))

    # One owner for the classification rules: unknown class, unknown unit, a
    # class against structure, one unit answered twice, and a unit nobody
    # answered for are all its verdicts, not a second set derived here.
    classified = record_classifications(segmentation, [
        {"unit": entry["unit"], "assertion_class": entry["assertion_class"]}
        for _, entry in shaped
    ])
    if isinstance(classified, Invalid):
        problems.extend(classified.problems)

    for where, entry in shaped:
        unit = entry["unit"]
        assertion_class = entry["assertion_class"]
        judged = set(VERDICT_ONLY_FIELDS) & set(entry)
        if assertion_class in VERDICT_FORBIDDEN_CLASSES:
            if judged:
                bad("drift-verdict-not-obligated",
                    f"a {assertion_class!r} unit asserts nothing the code could "
                    f"contradict, so it takes no verdict — {sorted(judged)} "
                    f"would record a claim nobody made",
                    where)
            continue
        if not judged:
            if assertion_class in VERDICT_REQUIRED_CLASSES:
                bad("drift-verdict-owed",
                    f"a {assertion_class!r} unit carries an evidence "
                    f"obligation, so it must be judged: "
                    f"{list(VERDICT_ONLY_FIELDS)} are owed for it",
                    where)
            continue
        if not set(VERDICT_ONLY_FIELDS) <= set(entry):
            bad("drift-verdict-invalid-shape",
                f"a judged unit carries all of {list(VERDICT_ONLY_FIELDS)}; "
                f"this one carries only {sorted(judged)}",
                where)
            continue

        verdict, valid = entry["verdict"], True
        if verdict not in VERDICTS:
            bad("drift-unknown-verdict",
                f"{verdict!r} is not a drift verdict — an assertion is one of "
                f"{list(VERDICTS)}, and an unrecognized answer says nothing "
                f"about whether the documentation is still true",
                where)
            valid = False
        if entry["kind"] not in SUBJECT_KINDS:
            bad("drift-verdict-unknown-kind",
                f"{entry['kind']!r} is not a subject kind — it is one of "
                f"{list(SUBJECT_KINDS)}, which downstream tooling switches on",
                where)
            valid = False
        tier = entry["tier"]
        if isinstance(tier, bool) or not isinstance(tier, int) or (
            tier not in TIERS
        ):
            bad("drift-verdict-invalid-tier",
                f"tier must be one of {list(TIERS)} — how hard the assertion "
                f"was checked is part of what a reviewer is being asked to "
                f"trust",
                where)
            valid = False

        evidence, ok = _evidence(entry["evidence"], verdict, boundary, bad, where)
        valid = valid and ok

        fix = entry.get("fix")
        if verdict == VERDICT_STALE:
            unit_data = known.get(unit)
            if unit_data is None or not _is_valid_replacement_text(fix, unit_data):
                bad("drift-verdict-invalid-fix",
                    f"a {VERDICT_STALE} verdict must carry 'fix': complete, "
                    f"non-empty replacement text with non-empty physical "
                    f"lines separated by LF and no CR or NUL. An embedded LF "
                    f"is permitted only when the approved assertion unit "
                    f"already spans more than one source line; the fix is "
                    f"never an instruction describing a replacement",
                    where)
                valid = False
        elif fix is not None:
            bad("drift-verdict-invalid-fix",
                f"only a {VERDICT_STALE} verdict carries a fix; {verdict!r} "
                f"proposes no edit",
                where)
            valid = False

        if not valid:
            continue
        judged_counts[verdict] = judged_counts.get(verdict, 0) + 1
        if unit not in known:
            continue
        unit_data = known[unit]
        if verdict not in FINDING_VERDICTS:
            # Coverage, not a finding — and coverage nobody can follow is not
            # coverage. Evidence is mandatory for VERIFIED precisely so it can
            # be checked, so the pointer is kept rather than validated and
            # dropped.
            verified.append({
                "unit": unit,
                "assertion_class": assertion_class,
                "location": f"{path}:{unit_data.line}",
                "kind": entry["kind"],
                "tier": tier,
                "evidence": evidence,
            })
            continue
        extra = {
            "assertion": unit_data.text,
            "assertion_class": assertion_class,
            "location": f"{path}:{unit_data.line}",
            "kind": entry["kind"],
            "tier": tier,
            "evidence": evidence,
        }
        if verdict == VERDICT_STALE:
            extra["fix"] = fix
        drafts.append(_DraftFinding(
            code=verdict, path=path, units=(unit,), extra=extra
        ))

    if problems:
        return (), None, tuple(problems)

    classes = {}
    for classification in classified.classifications:
        classes[classification.assertion_class] = (
            classes.get(classification.assertion_class, 0) + 1
        )
    coverage = {
        "obligation": OBLIGATION_ASSERTIONS,
        "units": len(segmentation.units),
        "classes": dict(sorted(classes.items())),
        "verdicts": dict(sorted(judged_counts.items())),
        "verified": verified,
    }
    return tuple(drafts), coverage, ()


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
    stale, unverifiable, unresolvable = [], [], []
    for reference in references:
        if not os.path.exists(os.path.join(repo_root, reference)):
            # An abbreviation and a removed target are the same observation
            # here, so neither is claimed and no prefix an earlier reference
            # established is carried forward to resolve one (#97; the engine
            # README's "Narrative documents" holds why).
            unresolvable.append((
                reference,
                "does not resolve to a path in the repository — an anchor "
                "names repository-relative paths in full, so this is either "
                "an abbreviation or a target that has moved",
            ))
            continue
        # A directory anchor's freshness is the most recent change to
        # anything beneath it — `last_change` already gets this for free,
        # since it hands the reference to git as a pathspec rather than
        # requiring it to name a single file.
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
        (CODE_ANCHOR_STALE, stale),
        (CODE_ANCHOR_UNVERIFIABLE, unverifiable),
        (CODE_ANCHOR_UNRESOLVABLE_REFERENCE, unresolvable),
    ):
        if not offenders:
            continue
        offenders = sorted(offenders)
        source, detail = offenders[0]
        observed = f"{source} {detail}"
        if len(offenders) > 1:
            observed += f" (and {len(offenders) - 1} more the anchor names)"
        specs.append(_DraftFinding(
            code=code, path=path, units=(anchor.digest,),
            extra={
                "assertion": anchor.text,
                "location": f"{path}:{anchor.line}",
                "as_of": as_of,
                "references": [reference for reference, _ in offenders],
                "evidence": {"source": source, "observed": observed},
            },
        ))
    return specs


def _audit_anchor(repo_root, path, registry_path):
    """(specs, coverage, gap) for one narrative document.

    Deterministic and model-free: the obligation is honest dating, so what is
    checked is the anchor's shape and whether what it names has moved. The prose
    around it is never read as a claim.

    Coverage says which of those things happened, because a narrative document
    that passes produces no record either — and "the anchor was read and it was
    honestly dated" is a different fact from "nobody looked".
    """
    segmentation = segment_document(repo_root, path, registry_path)
    if isinstance(segmentation, Invalid):
        return (), None, Incomplete(
            scope=path, reason=_gap_reason(segmentation.problems)
        )
    units = segmentation.units
    if not units:
        return (), None, Incomplete(
            scope=path,
            reason="the document is empty, so it carries no anchor to check",
        )

    anchor = next(
        (u for u in units
         if u.kind == "block_quote" and u.text.startswith(ANCHOR_PREFIX)),
        None,
    )
    if anchor is None:
        return (_DraftFinding(
            code=CODE_ANCHOR_MISSING, path=path, units=(units[0].digest,),
            extra={
                "location": f"{path}:{units[0].line}",
                "message": (
                    "a narrative document must be honestly dated: it carries no "
                    "`> As of <YYYY-MM-DD> (<anchors>)` line, so nothing says "
                    "what it was true of"
                ),
            },
        ),), {"obligation": OBLIGATION_ANCHOR, "anchor": "missing"}, None

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
        return (_DraftFinding(
            code=CODE_ANCHOR_MALFORMED, path=path, units=(anchor.digest,),
            extra={
                "assertion": anchor.text,
                "location": f"{path}:{anchor.line}",
                "message": (
                    "the anchor must read `As of <YYYY-MM-DD> (<anchors current "
                    "at writing>)` — a date nobody can compare cannot say "
                    "whether the document is honestly dated"
                ),
            },
        ),), {"obligation": OBLIGATION_ANCHOR, "anchor": "malformed"}, None

    # "Honestly dated" has two directions. A date the repository has not
    # reached cannot be when anything was checked, and no reference comparison
    # would catch it — every file's last change is behind such a date.
    references = _anchor_references(match.group(2))
    dated = {
        "obligation": OBLIGATION_ANCHOR,
        "anchor": "dated",
        "as_of": as_of,
        "references": references,
    }

    head, problem = repository_mod.last_change(repo_root, ".")
    if problem is None and head is not None and as_of > head[0]:
        return (_DraftFinding(
            code=CODE_ANCHOR_FUTURE_DATED, path=path, units=(anchor.digest,),
            extra={
                "assertion": anchor.text,
                "location": f"{path}:{anchor.line}",
                "as_of": as_of,
                "evidence": {
                    "source": path,
                    "observed": (
                        f"the anchor is dated {as_of}, after the repository's "
                        f"latest commit ({head[0]}, {head[1]}) — nothing could "
                        f"have been checked then"
                    ),
                },
            },
        ),), dated, None

    return tuple(_anchor_findings(
        repo_root, path, anchor, as_of, references
    )), dated, None


# Codes whose gap reason loses something specific if only the code survives:
# both name a rule an `evidence` citation broke, and the citation that broke
# it is exactly what an operator debugging the gap needs next (PR #87 review, N4 —
# the fixture's own hostile filenames are documents the audit declares and
# examines but that cannot be cited as evidence sources, and the gap this
# produced named only the code).
EVIDENCE_GAP_CODES = ("drift-verdict-invalid-evidence",
                      "drift-evidence-outside-boundary")


def _gap_reason(problems):
    """One line naming why a document was not examined.

    Codes only, by design — no prose drift — except for the two evidence
    codes above: `_evidence` records the offending citation in `location` as
    `"<where> source=<repr>"` or `"<where> command=<repr>"`, and it is folded
    back in here under its own label, because the code alone says a rule was
    broken, not which citation broke it. Split on the *first* delimiter
    (`where` never contains either substring, so it is always `_evidence`'s
    own) rather than the last, so a hostile source or command containing that
    same substring cannot truncate its own repr out of the reason.
    """
    def offenders(label):
        delimiter = f" {label}="
        return sorted({
            problem.location.split(delimiter, 1)[1]
            for problem in problems
            if problem.code in EVIDENCE_GAP_CODES
            and problem.location and delimiter in problem.location
        })

    reason = ", ".join(sorted({problem.code for problem in problems}))
    for label in EVIDENCE_CITATIONS:
        cited = offenders(label)
        if cited:
            reason += f" (offending {label}(s): " + ", ".join(cited) + ")"
    return reason


def _audit_assertions(repo_root, path, entry, boundary, registry_path):
    """(specs, coverage, gap) for one living document, given the lane's answer.

    Exactly one of `coverage` and `gap` is ever set: a document was validly
    examined or it was not, and a report that said both would be describing two
    different runs.
    """
    if entry is None:
        return (), None, Incomplete(
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
        return (), None, Incomplete(scope=path, reason=reason)

    segmentation = segment_document(repo_root, path, registry_path)
    if isinstance(segmentation, Invalid):
        return (), None, Incomplete(
            scope=path, reason=_gap_reason(segmentation.problems)
        )

    specs, coverage, problems = _validated_verdicts(
        segmentation, entry["verdicts"], boundary, path
    )
    if problems:
        return (), None, Incomplete(
            scope=path,
            reason=(
                f"the verdicts returned for this document did not validate: "
                f"{_gap_reason(problems)}"
            ),
        )
    return specs, coverage, None


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
                waivers=None, evidence_sources=DEFAULT_EVIDENCE,
                evidence_excluded=(), evidence_commands=(),
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

    accepted, waivers_digest, problem = load_waivers(repo_root, waivers)
    if problem is not None:
        return Invalid((problem,))

    boundary = EvidenceBoundary(tuple(evidence_sources), tuple(evidence_excluded),
                                tuple(evidence_commands))
    state, problems = current_lineage(
        repo_root, registry_path, _audit_config_digest(boundary)
    )
    if problems:
        return Invalid(tuple(problems))
    lineage = Lineage(audit_mode=mode, evidence_boundary=boundary, **state)

    entries, problems = _verdict_entries(verdicts, plan)
    if problems:
        return Invalid(problems)

    specs, examined, gaps = [], [], [
        Incomplete(
            scope=path,
            reason=(
                "the registry claims no rule for this document, so its "
                "obligation is unknown and it could not be examined — "
                "classify it in the registry or exclude it"
            ),
        )
        for path in plan.unclassified
    ]
    for document in plan.documents:
        if document.obligation == OBLIGATION_ANCHOR:
            found, coverage, gap = _audit_anchor(
                repo_root, document.path, registry_path
            )
        else:
            found, coverage, gap = _audit_assertions(
                repo_root, document.path, entries.get(document.path), boundary,
                registry_path,
            )
        specs.extend(found)
        if coverage is not None:
            examined.append({"scope": document.path, **coverage})
        if gap is not None:
            gaps.append(gap)

    hits, counts = _waiver_hits(accepted, specs)
    problem = _breadth_problem(accepted, counts, waivers)
    if problem is not None:
        return Invalid((problem,))

    records = []
    for number, (spec, hit) in enumerate(zip(specs, hits), start=1):
        extra = dict(spec.extra)
        if hit is not None:
            # Disposition, never deletion: an accepted claim keeps its record
            # and says who accepted it, from which file, and how far that
            # acceptance reached. Waivers are not part of any digest, so
            # accepting a claim cannot re-key what an approval set selects.
            extra["waived"] = _waiver_annotation(
                accepted[hit], waivers, waivers_digest, counts[hit]
            )
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
        "examined": examined,
        "incomplete": incomplete,
        "scope": {
            "basis": plan.basis,
            # Both modes account for the whole inventory: `plan_drift_audit`
            # partitions it, so every document is declared or excluded with a
            # reason. A diff-scoped run is narrower, not less accountable.
            "coverage": SCOPE_WHOLE_INVENTORY,
            "documents": [d.path for d in plan.documents],
            "excluded": [
                {"path": d.path, "reason": d.reason, "code": d.code}
                for d in plan.excluded
            ],
        },
    }, registry_path=registry_path)
