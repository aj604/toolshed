"""The migration door: adopting the registry contract without a per-file slog.

A consumer arriving from a pre-registry doc-sync install has classification
knowledge already — spread across `audit-scope.json`'s exclusions, the
`> As of` markers on its narrative docs, its `docs/plans/` directory, and the
files its waivers name. None of it is a registry. This module reads that state
and does two things, neither of which writes anything:

**Draft.** `draft_registry` infers a registry and emits it as *glob rules* —
one rule per directory, with a per-file override only where a directory is not
uniform. The point is the review: a human reads a dozen globs in a normal PR
diff and knows whether the classification is right, instead of approving a
list of every markdown file in the repository. Every rule carries the basis it
was inferred from and the documents it claims, so a wrong rule is traceable to
the evidence that produced it.

**Dry run.** `dry_run_migration` reads the registry the human landed and states
what adopting it costs: the audit obligation each document kind takes on, which
waivers re-key cleanly onto the new identity and which need re-waiving, which
old artifacts are not carried across, and which consumer files are preserved
untouched. It is a report about a migration, never a migration.

Fail closed in both directions. A document under a declared root that no rule
claims blocks the run and is named — there is no unclassified bucket, because a
bucket is how a corpus quietly stops being audited. Legacy artifacts are
rejected with instructions for regenerating them, never coerced into the new
shape: a report with no lineage cannot be given one after the fact.

Migration is version-to-version. The contract names the versions it spans, and
the door refuses an install whose version it cannot read or that is already
ahead of this engine, rather than guessing what state it is looking at.
"""

import json
import os
import posixpath
from dataclasses import dataclass, field
from typing import Optional, Tuple

from . import ARTIFACT_SCHEMA_VERSION, PLUGIN_VERSION
from . import registry as registry_mod
from .digest import sha256_file
from .drift import (
    ANCHOR_PREFIX,
    KIND_OBLIGATIONS,
    OBLIGATION_ASSERTIONS,
    PLANNING_REASON,
    UNREGISTERED_DOCUMENT,
    load_waivers,
)
from .inventory import DEFAULT_REGISTRY_PATH, build_inventory, walk_root
from .registry import KINDS
from .results import STATUS_OK, Invalid, Problem
from .segment import segment_document

# The migration this door performs, named so a dry run states which contract it
# is a dry run *of*. One contract, spanning every pre-registry install to this
# engine: the shape of the change is the same for all of them, because none of
# them had a registry.
MIGRATION_CONTRACT = "legacy-doc-sync-to-registry"

# Where a legacy install keeps the things this door reads. All optional: a
# fresh install (the bootstrapping path) has none of them, and the door infers
# from directory conventions and markers alone.
LEGACY_ROOT = ".github/doc-sync"
AUDIT_SCOPE_PATH = f"{LEGACY_ROOT}/audit-scope.json"
WAIVERS_PATH = f"{LEGACY_ROOT}/drift-waivers.json"
INSTALLED_VERSION_PATH = f"{LEGACY_ROOT}/installed-version"
MARKER_PATH = ".github/doc-sync-marker"
SCOPE_RECORD_PATH = "docs/doc-scope.md"
LEGACY_SOURCES = (
    AUDIT_SCOPE_PATH, WAIVERS_PATH, INSTALLED_VERSION_PATH, MARKER_PATH,
    SCOPE_RECORD_PATH,
)

# The consumer files the contract carries across untouched. Everything else the
# legacy state directory holds is an artifact of the old contract, and the door
# says so rather than leaving a reader to guess which files still mean anything.
PRESERVED = (AUDIT_SCOPE_PATH, WAIVERS_PATH, MARKER_PATH)

# Reports the legacy workflows write into the working tree. Named here because
# they are the artifacts most likely to be sitting in a tree at migration time,
# and the ones a reader is most tempted to keep.
LEGACY_REPORTS = ("drift-report.json", "bloat-report.json")

# Why each artifact class cannot cross the contract boundary, and what to do
# instead. Regeneration is always cheap; coercion never is, because none of
# these artifacts carry the lineage the new contract binds identity to.
ARTIFACT_CLASSES = {
    "report": (
        "a legacy report predates report lineage, so nothing can say which "
        "repository state, registry, or ruleset produced it",
        "delete it and re-run the audit: "
        "`python3 -m doclifecycle drift-audit --repo . --verdicts <file>`",
    ),
    "approval": (
        "an approval set binds record digests to one report's lineage, and "
        "under this contract it is never tracked in the repository",
        "delete it and mint a fresh approval set from a current report",
    ),
    "cache": (
        "a cached or carried-over result is keyed to inputs the registry "
        "contract changes, so it can no longer be revalidated",
        "delete it; the next audit repopulates what it needs",
    ),
}

# How a document's kind was inferred, recorded per rule so a human reviewing
# the draft can check the evidence rather than the conclusion.
BASIS_NARRATIVE_ANCHOR = "narrative-anchor"
BASIS_POLICY_SCOPE = "policy-scope"
BASIS_PLANNING_LOCATION = "planning-location"
BASIS_LIVING_DEFAULT = "living-default"

# The first line of a narrative document under the growing-docs convention.
# Built from the drift audit's own anchor prefix so the door and the audit
# cannot disagree about what marks a document narrative.
ANCHOR_LINE = f"> {ANCHOR_PREFIX}"
# How far into a file the marker may sit: a title, a blank line, and slack.
ANCHOR_HEAD_LINES = 6

# Directory names the legacy bloat planner reads as planning artifacts.
PLANNING_SEGMENTS = ("plans", "specs")

# What a planning document owes, stated for symmetry with the drift
# obligations: it is out of drift's scope, and this is the reason the audit
# gives for leaving it out.
OBLIGATION_LIFECYCLE = "lifecycle"


@dataclass(frozen=True)
class Source:
    """One legacy input, whether it was there, and what it said."""

    path: str
    present: bool
    digest: Optional[str]

    def to_dict(self):
        return {"path": self.path, "present": self.present, "digest": self.digest}


@dataclass(frozen=True)
class DraftRule:
    """One proposed glob rule, and the evidence behind it."""

    glob: str
    kind: str
    doc_set: Optional[str]
    basis: str
    documents: Tuple[str, ...]
    override: bool = False

    def to_dict(self):
        return {
            "glob": self.glob,
            "kind": self.kind,
            "set": self.doc_set,
            "basis": self.basis,
            "documents": list(self.documents),
        }


@dataclass(frozen=True)
class Note:
    """Something a reviewer should know that does not invalidate the draft."""

    code: str
    message: str
    location: Optional[str] = None

    def to_dict(self):
        return {"code": self.code, "message": self.message,
                "location": self.location}


@dataclass(frozen=True)
class Draft:
    """An inferred registry, ready to be reviewed as a diff of glob rules."""

    status: str
    registry_path: str
    registry: dict
    registry_text: str
    registry_digest: str
    rules: Tuple[DraftRule, ...]
    sources: Tuple[Source, ...]
    notes: Tuple[Note, ...]

    def to_dict(self):
        return {
            "status": self.status,
            "schema_version": ARTIFACT_SCHEMA_VERSION,
            "registry_path": self.registry_path,
            "registry": self.registry,
            "registry_digest": self.registry_digest,
            "rules": [r.to_dict() for r in self.rules],
            "sources": [s.to_dict() for s in self.sources],
            "notes": [n.to_dict() for n in self.notes],
        }


def _read(repo_root, path):
    """(text, None) or (None, OSError-ish reason). Absent is not a failure."""
    absolute = os.path.join(repo_root, path)
    if not os.path.isfile(absolute):
        return None, None
    try:
        with open(absolute, encoding="utf-8") as fh:
            return fh.read(), None
    except (OSError, UnicodeDecodeError) as exc:
        return None, str(exc)


def _sources(repo_root, paths):
    out = []
    for path in paths:
        absolute = os.path.join(repo_root, path)
        present = os.path.isfile(absolute)
        out.append(Source(
            path=path,
            present=present,
            digest=sha256_file(absolute) if present else None,
        ))
    return tuple(out)


def _load_audit_scope(repo_root, path):
    """(config, problem). A legacy audit scope, or the reason it is unusable.

    Refused rather than defaulted: the exclusions in this file are the only
    record of which subtrees a consumer deliberately kept out of the audit, and
    a draft that silently lost them proposes auditing vendored documentation.
    """
    text, reason = _read(repo_root, path)
    if text is None and reason is None:
        return {}, None

    def bad(detail):
        return Problem(
            code="migration-audit-scope-invalid",
            message=(
                f"the legacy audit scope at {path} cannot be read as an object "
                f"of glob lists: {detail}. Its exclusions are the only record "
                f"of what the consumer kept out of the audit, so a draft "
                f"inferred without them would propose auditing it."
            ),
            location=path,
        )

    if text is None:
        return {}, bad(reason)
    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        return {}, bad(str(exc))
    if not isinstance(data, dict):
        return {}, bad("it must be a JSON object")
    config = {}
    for name in ("exclude", "include", "policy_scope"):
        value = data.get(name, [])
        if not isinstance(value, list) or not all(
            isinstance(v, str) and v.strip() for v in value
        ):
            return {}, bad(f"'{name}' must be a list of non-empty globs")
        config[name] = [v.strip() for v in value]
    return config, None


def _top_segment(path):
    """The first path segment of a repo-relative path, or None if it has one."""
    head = path.strip().lstrip("./").split("/")[0]
    return head or None


def _infer_roots(repo_root, audit_scope, waivers, scope_record):
    """The documentation roots a legacy install evidences.

    Three kinds of evidence, all of them things the consumer already wrote
    down: every markdown file at the top of the repository is documentation by
    position; the directory holding the scope record is a documentation tree by
    construction; and any directory the consumer's own waivers, policy scopes,
    or audit-scope inclusions reach into holds documents it was already
    auditing. Exclusions are deliberately *not* evidence — naming a subtree to
    keep it out is not a declaration that it is a root.
    """
    roots = set()
    try:
        entries = sorted(os.listdir(repo_root))
    except OSError:
        entries = []
    for name in entries:
        absolute = os.path.join(repo_root, name)
        if name.endswith(".md") and os.path.isfile(absolute) and not os.path.islink(
            absolute
        ):
            roots.add(name)

    candidates = [posixpath.dirname(scope_record)]
    candidates += [_top_segment(w["file"]) for w in waivers]
    candidates += [_top_segment(p) for p in audit_scope.get("policy_scope", [])]
    candidates += [_top_segment(p) for p in audit_scope.get("include", [])]
    for candidate in candidates:
        if not candidate:
            continue
        absolute = os.path.join(repo_root, candidate)
        if os.path.isdir(absolute) and not os.path.islink(absolute):
            roots.add(candidate)

    # A root inside another root would inventory its documents twice, which the
    # registry refuses outright. The outer one wins: it is the broader claim,
    # and the narrower one adds nothing the walk would not already reach.
    return tuple(sorted(
        root for root in roots
        if not any(root.startswith(f"{other}/") for other in roots if other != root)
    ))


def _anchored(text):
    """Does this document carry the growing-docs narrative marker up top?

    The marker may be the first line, or sit under a title — both spellings are
    in use, and the legacy bloat planner accepts both, so the door does too.
    """
    head = [line.lstrip() for line in text.splitlines()[:ANCHOR_HEAD_LINES]]
    if not head:
        return False
    if head[0].startswith(ANCHOR_LINE):
        return True
    if head[0].startswith("#"):
        for line in head[1:]:
            if line.strip():
                return line.startswith(ANCHOR_LINE)
    return False


def _classify(repo_root, path, policy_scopes):
    """(kind, basis) for one document, from evidence the consumer already wrote.

    Precedence follows the legacy bloat planner's: an anchored document is
    narrative wherever it sits, then a declared policy scope or a planning
    directory makes it planning, and everything else is living. Living last is
    the safe default — it is the kind that owes the most, so a misclassification
    here over-audits rather than quietly exempting a document.
    """
    text, _ = _read(repo_root, path)
    if text is not None and _anchored(text):
        return "narrative", BASIS_NARRATIVE_ANCHOR
    directory = posixpath.dirname(path)
    for prefix in policy_scopes:
        trimmed = prefix.rstrip("/")
        if directory == trimmed or directory.startswith(f"{trimmed}/"):
            return "planning", BASIS_POLICY_SCOPE
    if any(segment in PLANNING_SEGMENTS for segment in directory.split("/")):
        return "planning", BASIS_PLANNING_LOCATION
    return "living", BASIS_LIVING_DEFAULT


def _set_for(directory, basis):
    """The set a directory forms, or None.

    Only planning directories: a `docs/plans/` or a declared policy scope is a
    grouping the consumer already treats as one thing, with shared retirement
    rules. A directory that merely happens to hold living documents is not a
    set, and inventing one would put a convention in the registry that nobody
    agreed to.
    """
    if basis not in (BASIS_PLANNING_LOCATION, BASIS_POLICY_SCOPE):
        return None
    return posixpath.basename(directory) or None


def _group_rules(documents, extension):
    """Turn classified documents into glob rules, broad first, overrides after.

    One rule per directory, carrying that directory's dominant classification,
    plus a per-file rule for each document that disagrees with it. Precedence is
    rule order — the last match wins — so the overrides sit after the directory
    rule they correct, and deeper directories sit after shallower ones.

    This is the whole point of the door: a reviewer reads the directory rules to
    check the shape of the corpus and the overrides to check the exceptions,
    rather than a line per file.
    """
    by_directory = {}
    for path, kind, basis in documents:
        by_directory.setdefault(posixpath.dirname(path), []).append(
            (path, kind, basis)
        )

    rules = []
    for directory, members in by_directory.items():
        if not directory:
            # A markdown file at the top of the repository is its own root, so
            # it gets a literal rule: `*.md` at the top level would claim files
            # in no declared root at all.
            for path, kind, basis in sorted(members):
                rules.append(DraftRule(
                    glob=path, kind=kind, doc_set=None, basis=basis,
                    documents=(path,),
                ))
            continue
        counts = {}
        for path, kind, basis in members:
            key = (kind, basis)
            counts.setdefault(key, []).append(path)
        # Ties are broken by document-kind order, then by basis name, so the
        # same corpus always drafts the same directory rule.
        dominant = sorted(
            counts, key=lambda k: (-len(counts[k]), KINDS.index(k[0]), k[1])
        )[0]
        kind, basis = dominant
        rules.append(DraftRule(
            glob=f"{directory}/*{extension}",
            kind=kind,
            doc_set=_set_for(directory, basis),
            basis=basis,
            documents=tuple(sorted(counts[dominant])),
        ))
        for key in sorted(counts, key=lambda k: (KINDS.index(k[0]), k[1])):
            if key == dominant:
                continue
            for path in sorted(counts[key]):
                rules.append(DraftRule(
                    glob=path, kind=key[0], doc_set=_set_for(directory, key[1]),
                    basis=key[1], documents=(path,), override=True,
                ))

    return tuple(sorted(
        rules, key=lambda r: (r.glob.count("/"), r.override, r.glob)
    ))


def draft_registry(repo_root, roots=None, registry_path=DEFAULT_REGISTRY_PATH,
                   scope_record=SCOPE_RECORD_PATH, audit_scope=AUDIT_SCOPE_PATH,
                   waivers=WAIVERS_PATH):
    """Infer a reviewable draft registry from a legacy install. Writes nothing.

    Returns a `Draft`, or `Invalid` when the legacy state cannot be read well
    enough to infer from — a draft built on a config the door could not parse
    would propose the wrong corpus, and be reviewed as if it had.

    `roots` overrides inference outright: a consumer whose documentation does
    not sit where the conventions put it declares it, rather than editing a
    draft that started from the wrong tree.
    """
    scope, problem = _load_audit_scope(repo_root, audit_scope)
    if problem is not None:
        return Invalid((problem,))
    accepted, _, waiver_problem = load_waivers(repo_root, waivers)
    if waiver_problem is not None:
        return Invalid((waiver_problem,))

    if roots is None:
        roots = _infer_roots(repo_root, scope, accepted, scope_record)
    else:
        roots = tuple(roots)
    if not roots:
        return Invalid((Problem(
            code="migration-no-roots",
            message=(
                "no documentation root could be inferred: this repository has "
                "no markdown file at its top level, no scope record, and no "
                "waiver or audit-scope entry naming a directory. Declare the "
                "roots explicitly rather than migrating a corpus nobody named."
            ),
        ),))

    exclude = tuple(scope.get("exclude", []))
    extension = registry_mod.DEFAULT_EXTENSIONS[0]
    walker = registry_mod.unclassified(roots, exclude)

    notes = []
    documents = []
    for root in roots:
        for rel, is_symlink in walk_root(repo_root, root, walker):
            if is_symlink:
                notes.append(Note(
                    code="migration-symlinked-path",
                    message=(
                        f"{rel} is a symlink, so it is not a document and no "
                        f"rule claims it — the inventory reports it the same way"
                    ),
                    location=rel,
                ))
                continue
            kind, basis = _classify(repo_root, rel, scope.get("policy_scope", []))
            documents.append((rel, kind, basis))

    for pattern in scope.get("include", []):
        if pattern.endswith(extension) or pattern.endswith("*"):
            continue
        notes.append(Note(
            code="migration-non-markdown-include",
            message=(
                f"the legacy audit scope re-admitted {pattern!r}, which is not "
                f"{extension} — the draft declares {extension} only, so add the "
                f"extension to the registry if those files are documentation"
            ),
            location=audit_scope,
        ))

    rules = _group_rules(documents, extension)
    sets = sorted({r.doc_set for r in rules if r.doc_set})
    payload = {
        "schema_version": registry_mod.SCHEMA_VERSION,
        "roots": list(roots),
        "exclude": list(exclude),
        "sets": sets,
        "extensions": [extension],
        "rules": [
            {"glob": r.glob, "kind": r.kind, **({"set": r.doc_set} if r.doc_set
                                                else {})}
            for r in rules
        ],
    }
    text = json.dumps(payload, indent=2, ensure_ascii=False) + "\n"

    # The door must never hand a human a draft the engine would reject: the
    # review is of glob rules, not of whether the file parses.
    parsed, problems = registry_mod.parse(text, location=registry_path)
    if problems:
        return Invalid(tuple(problems))

    return Draft(
        status=STATUS_OK,
        registry_path=registry_path,
        registry=payload,
        registry_text=text,
        registry_digest=parsed.digest,
        rules=rules,
        sources=_sources(repo_root, LEGACY_SOURCES),
        notes=tuple(notes),
    )


@dataclass(frozen=True)
class Obligation:
    """What one document kind owes the audit, and which documents owe it."""

    kind: str
    obligation: str
    documents: Tuple[str, ...]
    reason: Optional[str] = None

    def to_dict(self):
        return {
            "kind": self.kind,
            "obligation": self.obligation,
            "count": len(self.documents),
            "documents": list(self.documents),
            "reason": self.reason,
        }


@dataclass(frozen=True)
class Rekeyed:
    """A waiver whose acceptance lands on exactly one unit of the new corpus."""

    file: str
    claim: str
    unit: str
    unit_text: str

    def to_dict(self):
        return {"file": self.file, "claim": self.claim, "unit": self.unit,
                "unit_text": self.unit_text}


@dataclass(frozen=True)
class Rewaive:
    """A waiver that does not survive the move, and why."""

    file: str
    claim: str
    code: str
    message: str

    def to_dict(self):
        return {"file": self.file, "claim": self.claim, "code": self.code,
                "message": self.message}


@dataclass(frozen=True)
class ArtifactClass:
    """One class of old artifact, why it stops here, and what to do instead."""

    name: str
    reason: str
    regenerate: str
    found: Tuple[str, ...]

    def to_dict(self):
        return {"class": self.name, "reason": self.reason,
                "regenerate": self.regenerate, "found": list(self.found)}


@dataclass(frozen=True)
class DryRun:
    """What adopting this registry would cost. A report, never a migration."""

    status: str
    contract: str
    from_version: Optional[str]
    to_version: str
    registry_path: str
    registry_digest: str
    inventory_digest: str
    obligations: Tuple[Obligation, ...]
    waivers_source: Optional[str]
    waivers_digest: Optional[str]
    rekeyed: Tuple[Rekeyed, ...]
    needs_rewaiving: Tuple[Rewaive, ...]
    artifacts: Tuple[ArtifactClass, ...]
    preserved: Tuple[Source, ...]
    sources: Tuple[Source, ...]

    def to_dict(self):
        return {
            "status": self.status,
            "schema_version": ARTIFACT_SCHEMA_VERSION,
            "migration": {
                "contract": self.contract,
                "from_version": self.from_version,
                "to_version": self.to_version,
            },
            "registry": {"path": self.registry_path,
                         "digest": self.registry_digest},
            "inventory_digest": self.inventory_digest,
            "obligations": [o.to_dict() for o in self.obligations],
            "waivers": {
                "source": self.waivers_source,
                "source_digest": self.waivers_digest,
                "rekeyed": [r.to_dict() for r in self.rekeyed],
                "needs_rewaiving": [r.to_dict() for r in self.needs_rewaiving],
            },
            "artifacts": [a.to_dict() for a in self.artifacts],
            "preserved": [p.to_dict() for p in self.preserved],
            "sources": [s.to_dict() for s in self.sources],
        }


def _parse_version(text):
    """`X.Y.Z` as an int triple, or None. A `v` prefix is tolerated.

    Numeric, not lexical, so 0.9.0 precedes 0.10.0 — the same comparison the
    upgrade lane's gate makes, because the two must agree about which install
    is older.
    """
    trimmed = text.strip()
    if trimmed.startswith("v"):
        trimmed = trimmed[1:]
    parts = trimmed.split(".")
    if len(parts) != 3 or not all(p.isdigit() for p in parts):
        return None
    return tuple(int(p) for p in parts)


def _version_problems(repo_root, path):
    """(declared version or None, problems). Absent means a fresh install.

    A migration spans two named versions, so an install whose version this door
    cannot place is refused rather than migrated on a guess — and one already
    ahead of this engine is refused for the same reason the upgrade gate
    refuses a downgrade: the door does not know what it is looking at.
    """
    text, reason = _read(repo_root, path)
    if text is None and reason is None:
        return None, ()
    if text is None:
        return None, (Problem(
            code="migration-version-unreadable",
            message=f"cannot read the installed version at {path}: {reason}",
            location=path,
        ),)
    declared = _parse_version(text)
    if declared is None:
        return None, (Problem(
            code="migration-version-unreadable",
            message=(
                f"the installed version at {path} reads {text.strip()!r}, which "
                f"is not an X.Y.Z version. A migration spans two named versions; "
                f"repair the lockfile rather than migrating from an unknown one."
            ),
            location=path,
        ),)
    if declared > _parse_version(PLUGIN_VERSION):
        return None, (Problem(
            code="migration-version-ahead",
            message=(
                f"the install at {path} declares {text.strip()}, ahead of this "
                f"engine's {PLUGIN_VERSION}. This door migrates forward only — "
                f"run it from the newer plugin checkout."
            ),
            location=path,
        ),)
    return text.strip(), ()


def _obligations(inventory):
    """The audit obligation each kind takes on, all three kinds always listed.

    A kind with no documents is still a row: the table is what the registry
    commits the consumer to, and "nothing here is narrative" is part of that.
    """
    by_kind = {kind: [] for kind in KINDS}
    for document in inventory.documents:
        by_kind[document.kind].append(document.path)
    return tuple(Obligation(
        kind=kind,
        obligation=KIND_OBLIGATIONS.get(kind, OBLIGATION_LIFECYCLE),
        documents=tuple(sorted(by_kind[kind])),
        reason=PLANNING_REASON if kind == "planning" else None,
    ) for kind in KINDS)


def _rekey(repo_root, inventory, waivers, registry_path):
    """Which acceptances survive the move onto assertion-unit identity.

    A legacy waiver names a file and quotes claim text; the new contract keys a
    finding to a document and a *group of assertion units*, identified by
    content digest. An acceptance therefore re-keys cleanly exactly when its
    quoted text lands on one determinate unit — and needs re-waiving whenever
    it lands on none, on several, or on a document that no longer carries
    assertions at all.

    The half of the new identity this can resolve is the document-and-unit
    half; the lineage and finding code that complete a finding digest are bound
    when an audit runs, and inventing them here would be a promise about a run
    nobody has made. So a cleanly re-keyed waiver reports the unit its
    acceptance now names, which is the part that has to be stable.
    """
    by_path = {d.path: d for d in inventory.documents}
    rekeyed, stuck, segmentations = [], [], {}

    def blocked(waiver, code, message):
        stuck.append(Rewaive(
            file=waiver["file"], claim=waiver["claim"], code=code, message=message,
        ))

    for waiver in waivers:
        path, claim = waiver["file"], waiver["claim"]
        document = by_path.get(path)
        if document is None:
            blocked(waiver, "waiver-document-not-inventoried", (
                f"{path} is not a document in the new inventory — it is outside "
                f"the declared roots, excluded, or gone. Classify it in the "
                f"registry, or drop the waiver along with the document."
            ))
            continue
        if KIND_OBLIGATIONS.get(document.kind) != OBLIGATION_ASSERTIONS:
            blocked(waiver, "waiver-document-carries-no-assertions", (
                f"{path} is a {document.kind} document, which is never "
                f"line-verified, so there is no assertion for this acceptance to "
                f"attach to. Re-waive against a living document, or drop it."
            ))
            continue
        if path not in segmentations:
            segmentations[path] = segment_document(repo_root, path, registry_path)
        segmentation = segmentations[path]
        if isinstance(segmentation, Invalid):
            blocked(waiver, "waiver-document-unreadable", (
                f"{path} cannot be segmented, so nothing can say which unit this "
                f"acceptance names: "
                f"{'; '.join(p.message for p in segmentation.problems)}"
            ))
            continue
        matched = sorted({
            (unit.digest, unit.text) for unit in segmentation.units
            if unit.assertion_capable and claim in unit.text
        })
        if not matched:
            blocked(waiver, "waiver-claim-not-found", (
                f"no assertion unit in {path} contains {claim!r}. The text was "
                f"edited or removed, so the acceptance names nothing — re-read "
                f"the document and waive what it says now."
            ))
        elif len(matched) > 1:
            blocked(waiver, "waiver-claim-ambiguous", (
                f"{claim!r} appears in {len(matched)} assertion units of {path}, "
                f"so it names no one finding to key an acceptance to. Quote more "
                f"of the line, or write one waiver per unit accepted."
            ))
        else:
            rekeyed.append(Rekeyed(
                file=path, claim=claim, unit=matched[0][0], unit_text=matched[0][1],
            ))
    return tuple(rekeyed), tuple(stuck)


def _artifact_class(name):
    """Which class an uncarried artifact belongs to, from what it is called.

    A name is weak evidence, which is why the classes share one disposition:
    every one of them is rejected with instructions. The class only decides
    which instruction the reader is given.
    """
    lowered = name.lower()
    if "approval" in lowered:
        return "approval"
    if "report" in lowered:
        return "report"
    return "cache"


def _artifacts(repo_root):
    """Every old artifact found, by class, with what to do instead of keeping it.

    Closed-world over the legacy state directory: rather than hunting a list of
    known filenames, anything in it that the contract does not carry across and
    that is not a vendored script is an artifact of the old world.
    Subdirectories are left alone — a vendored engine tree is wiring, not state.
    The two report names the legacy workflows write into the working tree are
    checked at the repository root as well.
    """
    found = {name: [] for name in ARTIFACT_CLASSES}
    for name in LEGACY_REPORTS:
        if os.path.isfile(os.path.join(repo_root, name)):
            found["report"].append(name)

    legacy = os.path.join(repo_root, LEGACY_ROOT)
    if os.path.isdir(legacy):
        for name in sorted(os.listdir(legacy)):
            rel = f"{LEGACY_ROOT}/{name}"
            if rel in PRESERVED or rel == INSTALLED_VERSION_PATH:
                continue
            if name.endswith(".py") or not os.path.isfile(
                os.path.join(legacy, name)
            ):
                continue
            found[_artifact_class(name)].append(rel)

    return tuple(ArtifactClass(
        name=name,
        reason=ARTIFACT_CLASSES[name][0],
        regenerate=ARTIFACT_CLASSES[name][1],
        found=tuple(sorted(found[name])),
    ) for name in sorted(ARTIFACT_CLASSES))


def dry_run_migration(repo_root, registry_path=DEFAULT_REGISTRY_PATH,
                      waivers=WAIVERS_PATH,
                      installed_version=INSTALLED_VERSION_PATH):
    """What adopting the landed registry costs. Reads only; writes nothing.

    Returns a `DryRun`, or `Invalid` naming every reason the migration is
    blocked — the version it cannot place, every document under a declared root
    that no rule claims, and a waivers file it cannot parse. The unclassified
    case is the one that matters most: there is no bucket for it, because a
    bucket is how a corpus quietly stops being audited, so the paths are named
    and the upgrade stops.
    """
    inventory = build_inventory(repo_root, registry_path)
    if isinstance(inventory, Invalid):
        return inventory

    declared, version_problems = _version_problems(repo_root, installed_version)
    problems = list(version_problems)
    problems.extend(Problem(
        code="migration-unclassified-document",
        message=(
            f"{finding.path} is under a declared documentation root but no "
            f"registry rule claims it. Classification is closed-world and has no "
            f"unclassified bucket: add a rule, or exclude the path, then re-run "
            f"the dry run."
        ),
        location=finding.path,
    ) for finding in inventory.findings if finding.code == UNREGISTERED_DOCUMENT)

    accepted, waivers_digest, waiver_problem = load_waivers(repo_root, waivers)
    if waiver_problem is not None:
        problems.append(waiver_problem)
    if problems:
        return Invalid(tuple(problems))

    rekeyed, stuck = _rekey(repo_root, inventory, accepted, registry_path)
    return DryRun(
        status=STATUS_OK,
        contract=MIGRATION_CONTRACT,
        from_version=declared,
        to_version=PLUGIN_VERSION,
        registry_path=registry_path,
        registry_digest=inventory.registry_digest,
        inventory_digest=inventory.digest,
        obligations=_obligations(inventory),
        waivers_source=waivers if waivers_digest else None,
        waivers_digest=waivers_digest,
        rekeyed=rekeyed,
        needs_rewaiving=stuck,
        artifacts=_artifacts(repo_root),
        preserved=_sources(repo_root, PRESERVED),
        sources=_sources(repo_root, LEGACY_SOURCES),
    )
