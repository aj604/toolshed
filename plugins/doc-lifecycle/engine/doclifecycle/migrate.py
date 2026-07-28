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

An install keeps that state at one of two addresses — the pre-registry
`.github/doc-sync/`, or `.doc-lifecycle/`, where aj604/toolshed#133 centralized
it — so the door looks at both and reports which one it read. That is a fact
about the install, not about the migration: the contract is the same either
way, because neither layout had a registry. It is reported beside a second
fact it does not imply, whether a registry is already landed, so "pre-registry,
never relocated", "relocated, still pre-door", and "relocated, already through
the door" are three answers rather than one. State standing under *both*
layouts is refused, never merged: with two rival copies of the audit scope,
whichever the door read could be the wrong half of the consumer's judgment.
"""

import json
import os
import posixpath
from dataclasses import dataclass
from typing import Optional, Tuple

from . import ARTIFACT_SCHEMA_VERSION, PLUGIN_VERSION
from . import registry as registry_mod
from . import repository
from .digest import sha256_file
from .drift import (
    ANCHOR_PREFIX,
    KIND_OBLIGATIONS,
    OBLIGATION_ASSERTIONS,
    PLANNING_REASON,
    UNREGISTERED_DOCUMENT,
    load_waivers,
)
from .drift import MAX_WAIVER_UNITS
from .inventory import DEFAULT_REGISTRY_PATH, build_inventory, walk_root
from .paths import repository_relative_problem
from .registry import KINDS
from .results import STATUS_OK, Invalid, Problem
from .segment import segment_document

# The migration this door performs, named so a dry run states which contract it
# is a dry run *of*. One contract, spanning every pre-registry install to this
# engine: the shape of the change is the same for all of them, because none of
# them had a registry.
MIGRATION_CONTRACT = "legacy-doc-sync-to-registry"

SCOPE_RECORD_PATH = "docs/doc-scope.md"

# What happens to each consumer file the contract carries across. Everything
# else the install's state directory holds is an artifact of the old contract,
# and the door says so rather than leaving a reader to guess which files still
# mean anything. `installed-version` is accounted for too — it is not left
# alone, but it is not discarded either, and a table that showed neither would
# hide the one consumer file the migration does move.
UNCHANGED = "unchanged"
SET_TO_TARGET = "set-to-target"


@dataclass(frozen=True)
class Layout:
    """One set of addresses for the four things this door infers from.

    There are two, because aj604/toolshed#133 moved an install's artifacts out
    of `.github/` into `.doc-lifecycle/`. The inputs did not change — same
    files, same bytes, same meaning — so the layout is an address book and
    nothing else, and the door reads whichever one an install presents.
    """

    name: str
    audit_scope: str
    waivers: str
    installed_version: str
    marker: str
    # The directory whose contents the dry run scans closed-world, and the
    # names in it the contract accounts for. Everything else there is an
    # artifact of the old world.
    state_root: str
    accounted: Tuple[str, ...]

    @property
    def inputs(self):
        """The four addresses whose presence says an install lives here."""
        return (self.audit_scope, self.waivers, self.installed_version,
                self.marker)

    @property
    def preserved(self):
        return (
            (self.audit_scope, UNCHANGED),
            (self.waivers, UNCHANGED),
            (self.marker, UNCHANGED),
            (self.installed_version, SET_TO_TARGET),
        )


# The current addresses (aj604/toolshed#133). `registry.json` and
# `evidence-tools.json` are accounted for without being carried by this
# contract: they belong to the new layout, so a closed-world scan that reported
# them as old-world leftovers would tell a consumer to delete the registry the
# migration exists to land.
CENTRALIZED_LAYOUT = Layout(
    name="centralized",
    audit_scope=".doc-lifecycle/audit-scope.json",
    waivers=".doc-lifecycle/drift-waivers.json",
    installed_version=".doc-lifecycle/installed-version",
    marker=".doc-lifecycle/state/sync-marker",
    state_root=".doc-lifecycle",
    accounted=("audit-scope.json", "drift-waivers.json", "evidence-tools.json",
               "installed-version", "registry.json"),
)

# The pre-#133 addresses. Kept beside the current ones rather than replaced:
# this door exists for consumers arriving from a genuinely pre-registry
# install, and most of those have never run the relocating upgrade. The marker
# sits outside the state root here, which is exactly the scattering #133 ended.
LEGACY_LAYOUT = Layout(
    name="legacy",
    audit_scope=".github/doc-sync/audit-scope.json",
    waivers=".github/doc-sync/drift-waivers.json",
    installed_version=".github/doc-sync/installed-version",
    marker=".github/doc-sync-marker",
    state_root=".github/doc-sync",
    accounted=("audit-scope.json", "drift-waivers.json", "installed-version"),
)

# Current spelling first, so a payload that lists both reads newest-first.
LAYOUTS = (CENTRALIZED_LAYOUT, LEGACY_LAYOUT)

# Whether a registry file stands at the registry path. Deliberately separate
# from the layout: relocating an install and adopting the registry contract are
# two different events, in either order, and one enum over the pair would fuse
# two questions that have different answers and different remedies.
REGISTRY_PRESENT = "present"
REGISTRY_ABSENT = "absent"

# Working files the legacy workflows write into the repository root. Named
# rather than swept, because the root is not a directory this contract owns —
# these are the artifacts most likely to be sitting in a tree at migration
# time, and the ones a reader is most tempted to keep.
LEGACY_WORKING_FILES = (
    "drift-report.json", "bloat-report.json",
    "manifest.json", "distill-manifest.json",
)

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

# How many left-behind paths the coverage note names. The count is exact; the
# paths are an example, because this note is read in a PR body and a terminal
# and a repository with five thousand unclaimed markdown files must not emit
# five thousand lines of them.
COVERAGE_SAMPLE = 10

# What a planning document owes. The drift audit has no obligation for it —
# `KIND_OBLIGATIONS` covers living and narrative only, because a planning
# document is out of drift's scope — but a migration must still tell a reader
# what the kind commits them to, so the third row is named here.
OBLIGATION_LIFECYCLE = "lifecycle"
# Total over the document kinds, deliberately not a defaulting lookup: a fourth
# kind must be given an obligation here rather than silently inheriting one.
OBLIGATION_BY_KIND = {**KIND_OBLIGATIONS, "planning": OBLIGATION_LIFECYCLE}


@dataclass(frozen=True)
class Source:
    """One legacy input, whether it was there, and what it said."""

    path: str
    present: bool
    digest: Optional[str]

    def to_dict(self):
        return {"path": self.path, "present": self.present, "digest": self.digest}


@dataclass(frozen=True)
class Install:
    """What the door is looking at, as two facts that do not imply each other.

    `layout` is where this install keeps its state — `legacy` for the pre-#133
    addresses, `centralized` for the current ones, and `null` when there is no
    install state at either (a repository that never ran doc-sync at all, which
    the door still drafts for, from conventions and markers alone).

    `registry` is whether a file stands at the registry path. That is the fact
    that separates an install still waiting to go through this door from one
    that has already been through it — and it is orthogonal to the layout, so
    "relocated, pre-door" and "relocated, post-door" are told apart here rather
    than guessed at from where the state sits.
    """

    layout: Optional[str]
    registry: str

    def to_dict(self):
        return {"layout": self.layout, "registry": self.registry}


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
            "override": self.override,
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
    install: Install
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
            "install": self.install.to_dict(),
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


def _resolve_layout(repo_root):
    """(layout to read this install at, the layout found or None, problem).

    Both layouts are looked at, never one. An install that has run the
    relocating upgrade keeps its judgment somewhere the pre-#133 addresses
    cannot see, and a door that read only those would draft a registry without
    the consumer's exclusions or waivers and be reviewed as if it had them.

    State standing under *both* layouts is refused rather than merged or
    picked. Which copy holds the decisions the consumer means is not knowable
    from the filesystem, and the cost of guessing is silently dropping half of
    them — the same question `apply-upgrade.py` refuses to answer when it finds
    both layouts, refused here for the same reason.

    Nothing at either address is not a refusal: a fresh install has none of
    these files, and the door infers from conventions and markers alone. It
    claims no layout in that case, and reads at the current addresses, because
    a file that is not there is not evidence of an old install.
    """
    found = {
        layout.name: tuple(
            path for path in layout.inputs
            if os.path.isfile(os.path.join(repo_root, path))
        )
        for layout in LAYOUTS
    }
    occupied = [layout for layout in LAYOUTS if found[layout.name]]
    if len(occupied) > 1:
        where = "; ".join(
            f"{layout.name} ({', '.join(found[layout.name])})"
            for layout in occupied
        )
        return None, None, Problem(
            code="migration-split-install",
            message=(
                f"this install's state stands under both layouts — {where}. "
                f"Which copy holds the decisions you mean is not knowable from "
                f"the filesystem, and reading either one would silently drop "
                f"the exclusions or acceptances in the other. Keep whichever "
                f"is current, remove the rest, then re-run."
            ),
        )
    if occupied:
        return occupied[0], occupied[0].name, None
    return CENTRALIZED_LAYOUT, None, None


def _source_paths():
    """Every address the door consults, both layouts, in a fixed order.

    Both are listed whichever one an install turned out to occupy, so the
    payload shows what was looked for as well as what was found — a table of
    only the layout that was read cannot tell a reader whether the other was
    ever checked, which is the question aj604/toolshed#137 was filed about.
    """
    return tuple(
        path for layout in LAYOUTS for path in layout.inputs
    ) + (SCOPE_RECORD_PATH,)


def _install(repo_root, found, registry_path):
    return Install(
        layout=found,
        registry=(
            REGISTRY_PRESENT
            if os.path.isfile(os.path.join(repo_root, registry_path))
            else REGISTRY_ABSENT
        ),
    )


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
    """The first segment of `path`, or None if it is not a path in this repo.

    Path safety has one owner, so a spelling `paths.repository_relative_problem`
    refuses — absolute, `..`, a backslash separator, a control character — is
    not evidence of anything and contributes no root. Trimming the string by
    hand here is how a waiver naming `../elsewhere/x.md` would end up declaring
    a root outside the repository.
    """
    if not isinstance(path, str) or repository_relative_problem(path) is not None:
        return None
    return path.split("/")[0] or None


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

    # A trailing `/` is the obvious spelling of a directory prefix, and the
    # canonical-path rule refuses it, so it is repaired before the check rather
    # than costing the consumer a root they plainly declared.
    declared = (
        [w["file"] for w in waivers]
        + list(audit_scope.get("policy_scope", []))
        + list(audit_scope.get("include", []))
    )
    candidates = [posixpath.dirname(scope_record)]
    candidates += [_top_segment(value.rstrip("/")) for value in declared]
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
    """(kind, basis, note or None) for one document, from written-down evidence.

    Precedence follows the legacy bloat planner's: an anchored document is
    narrative wherever it sits, then a declared policy scope or a planning
    directory makes it planning, and everything else is living. Living last is
    the safe default — it is the kind that owes the most, so a misclassification
    here over-audits rather than quietly exempting a document.

    A document this cannot read still gets a kind, from its location, because
    refusing the whole draft over one unreadable file would block a migration
    on something the audit will refuse anyway. But it is never silent: the
    reader is told which evidence was unavailable, so the classification is
    reviewed rather than trusted.
    """
    note = None
    text, reason = _read(repo_root, path)
    if reason is not None:
        note = Note(
            code="migration-unreadable-document",
            message=(
                f"{path} could not be read ({reason}), so its kind is inferred "
                f"from its location alone — no narrative marker could be "
                f"checked. Confirm the rule that claims it."
            ),
            location=path,
        )
    if text is not None and _anchored(text):
        return "narrative", BASIS_NARRATIVE_ANCHOR, note
    directory = posixpath.dirname(path)
    for prefix in policy_scopes:
        trimmed = prefix.rstrip("/")
        if directory == trimmed or directory.startswith(f"{trimmed}/"):
            return "planning", BASIS_POLICY_SCOPE, note
    if any(segment in PLANNING_SEGMENTS for segment in directory.split("/")):
        return "planning", BASIS_PLANNING_LOCATION, note
    return "living", BASIS_LIVING_DEFAULT, note


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
    """(rules, what each rule claims about each document it was written for).

    Turns classified documents into glob rules, broad first, overrides after.

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

    rules = tuple(sorted(
        rules, key=lambda r: (r.glob.count("/"), r.override, r.glob)
    ))
    # What the draft asserts about each document, so the caller can check the
    # parsed registry actually says it rather than assume the globs behave.
    claimed = {
        path: (rule.kind, rule.doc_set) for rule in rules for path in rule.documents
    }
    return rules, claimed


def _unclaimed(paths, roots, extension):
    """The documents among `paths` that no root claims, sorted.

    A root is a file or a subtree, so it claims a path by being it or by being
    a prefix of it. Exclusions do not enter into it, and the asymmetry that
    produces is the intended one: an exclusion *inside* a root leaves the path
    claimed and unreported, because the draft prints that exclusion in its own
    `exclude` for the reviewer to read, while a subtree named only in `exclude`
    is under no root at all — an exclusion is not root evidence — and is
    reported like any other omission.
    """
    return tuple(sorted(
        path for path in paths
        if path.endswith(extension)
        and not any(path == root or path.startswith(f"{root}/") for root in roots)
    ))


def _coverage_note(repo_root, roots, extension):
    """What these roots leave behind that the legacy drift lane reached, or None.

    Every source the roots are inferred from — the audit scope, the scope
    record, the waivers, the policy scope — describes the legacy *bloat* corpus
    or narrower. The legacy *drift* lane had no root concept at all: it was
    diff-scoped over the whole repository, and the audit scope reached it only
    as a write-authorization filter. So a drafted registry all but always
    narrows drift coverage, and a draft that did not say so would be ratified as
    if it changed nothing.

    A note, never a refusal, and never an inferred root. The narrowing is
    usually correct — vendored, generated, and third-party markdown is exactly
    what a corpus should not carry — so the reviewer decides, with `--root` as
    the instrument. Refusing here would block every repository with a vendored
    tree; sweeping the tree into the roots would make the decision for them.

    Enumeration is what the repository tracks, so generated and ignored files
    are not counted; the legacy lane never saw those either. Failing to
    enumerate is reported rather than passed over — silence reads as "nothing
    was left behind", which is the one conclusion this note exists to prevent.
    That report is a note and not a problem downgraded into one: the draft does
    not need this answer to be a draft, so what cannot be established is the
    coverage statement, not the registry.
    """
    tracked, problem = repository.tracked_files(repo_root)
    if tracked is None:
        return Note(
            code="migration-coverage-unchecked",
            message=(
                f"whether these roots narrow what is audited could not be "
                f"checked: {problem.message}. The legacy drift lane was "
                f"diff-scoped over the whole repository and had no roots, so a "
                f"drafted root set can leave documents behind — compare the "
                f"roots against the tree by hand before landing this."
            ),
        )

    left = _unclaimed(tracked, roots, extension)
    if not left:
        return None
    sample = left[:COVERAGE_SAMPLE]
    if len(left) == 1:
        counted = f"1 tracked {extension} file is"
        instruction = "Add it with --root if it is documentation (it is)"
    else:
        counted = f"{len(left)} tracked {extension} files are"
        listing = (f"the first {len(sample)}, sorted" if len(left) > len(sample)
                   else "they are")
        instruction = f"Add them with --root if they are documentation ({listing})"
    return Note(
        code="migration-coverage-narrowed",
        message=(
            f"{counted} under no drafted root, so this registry narrows what is "
            f"audited. The legacy drift lane had no roots at all — it was "
            f"diff-scoped over the whole repository — so everything counted "
            f"here was inside its scope, while these roots come from evidence "
            f"describing the legacy bloat corpus or narrower. Dropping "
            f"vendored and generated markdown is usually the right call, but "
            f"it is a narrowing to ratify, not a gap in the inference. "
            f"{instruction}: {', '.join(sample)}"
        ),
    )


def draft_registry(repo_root, roots=None, registry_path=DEFAULT_REGISTRY_PATH,
                   scope_record=SCOPE_RECORD_PATH, audit_scope=None,
                   waivers=None):
    """Infer a reviewable draft registry from a pre-registry install.

    Writes nothing. Returns a `Draft`, or `Invalid` when the install's state
    cannot be read well enough to infer from — a draft built on a config the
    door could not parse, or on one of two rival copies of it, would propose
    the wrong corpus and be reviewed as if it had not.

    `audit_scope` and `waivers` default to the addresses of whichever layout
    the install occupies; passing either names a file directly instead.

    `roots` overrides inference outright: a consumer whose documentation does
    not sit where the conventions put it declares it, rather than editing a
    draft that started from the wrong tree.
    """
    layout, found, problem = _resolve_layout(repo_root)
    if problem is not None:
        return Invalid((problem,))
    if audit_scope is None:
        audit_scope = layout.audit_scope
    if waivers is None:
        waivers = layout.waivers

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

    # Checked before anything is walked. `registry.parse` would refuse an
    # unsafe root at the end, but by then the door would already have listed a
    # directory outside the repository — and a declared root that simply is not
    # there would drift past it as an empty walk, drafting a registry
    # `build_inventory` then refuses with `registry-missing-root`.
    root_problems = []
    for root in roots:
        reason = repository_relative_problem(root)
        if reason is not None:
            root_problems.append(Problem(
                code="migration-unsafe-root",
                message=(
                    f"declared root {root!r} {reason[1]} — a root names a "
                    f"documentation subtree of this repository"
                ),
                location=root,
            ))
        elif not os.path.exists(os.path.join(repo_root, root)):
            root_problems.append(Problem(
                code="migration-missing-root",
                message=(
                    f"declared root {root!r} does not exist — drafting rules "
                    f"for a tree that is not there would produce a registry the "
                    f"inventory refuses"
                ),
                location=root,
            ))
    if root_problems:
        return Invalid(tuple(root_problems))

    exclude = tuple(scope.get("exclude", []))
    extension = registry_mod.DEFAULT_EXTENSIONS[0]
    walker = registry_mod.without_rules(roots, exclude)

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
            kind, basis, note = _classify(
                repo_root, rel, scope.get("policy_scope", [])
            )
            if note is not None:
                notes.append(note)
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

    coverage = _coverage_note(repo_root, roots, extension)
    if coverage is not None:
        notes.append(coverage)

    install = _install(repo_root, found, registry_path)
    if install.registry == REGISTRY_PRESENT:
        # The door's own instructions redirect `--registry-only` into this
        # path, and its dry-run loop is edit-then-re-run for exactly this
        # reason: a second draft is inference from the install's state again,
        # and knows nothing about the rules a reviewer edited into the file.
        notes.append(Note(
            code="migration-registry-already-landed",
            message=(
                f"a registry already stands at {registry_path} — this draft "
                f"re-infers one from the install's state and would overwrite "
                f"it, edits included, if redirected there again. Fix the "
                f"landed registry and re-run the dry run instead."
            ),
            location=registry_path,
        ))

    rules, claimed = _group_rules(documents, extension)
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

    # Nor a draft that classifies something other than what it claims to. Every
    # rule is a *glob*, including the per-file overrides, so a document whose
    # name contains `*` or `?` emits a rule that also claims its neighbours —
    # and overrides sort last, so it would win silently. Re-deriving the
    # classification through the parsed registry is the only check that catches
    # it, because parsing cannot: the file is perfectly well formed.
    inconsistent = []
    for path, expected in sorted(claimed.items()):
        winner = parsed.classify(path)
        actual = (winner.kind, winner.doc_set) if winner else (None, None)
        if actual != expected:
            inconsistent.append(Problem(
                code="migration-draft-inconsistent",
                message=(
                    f"the drafted rules classify {path} as {actual[0]}, but it "
                    f"was inferred as {expected[0]} — a rule's glob is claiming "
                    f"a document it was not written for, which a `*` or `?` in "
                    f"a filename does. Rename the file, or write the registry's "
                    f"rules by hand."
                ),
                location=path,
            ))
    if inconsistent:
        return Invalid(tuple(inconsistent))

    return Draft(
        status=STATUS_OK,
        install=install,
        registry_path=registry_path,
        registry=payload,
        registry_text=text,
        registry_digest=parsed.digest,
        rules=rules,
        sources=_sources(repo_root, _source_paths()),
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
    """A waiver whose acceptance lands on determinate units of the new corpus.

    `matched` is its blast radius, the same fact the audit's own `waived`
    annotation reports, so a reader can see whether an acceptance named one
    claim or swept a document before deciding to keep it.
    """

    file: str
    claim: str
    units: Tuple[Tuple[str, str], ...]

    def to_dict(self):
        return {
            "file": self.file,
            "claim": self.claim,
            "matched": len(self.units),
            "units": [{"digest": d, "text": t} for d, t in self.units],
        }


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
        return {"class": self.name, "carried": False, "reason": self.reason,
                "regenerate": self.regenerate, "found": list(self.found)}


@dataclass(frozen=True)
class Preserved:
    """One consumer file the contract accounts for, and what happens to it."""

    path: str
    present: bool
    digest: Optional[str]
    disposition: str

    def to_dict(self):
        return {"path": self.path, "present": self.present,
                "digest": self.digest, "disposition": self.disposition}


def _preserved(repo_root, layout):
    """The consumer files this install carries, at the addresses it uses.

    One layout's addresses, not both: this table is a statement about what
    happens to *these* files, and a row for a path the install does not have
    would be a claim about nothing.
    """
    preserved = layout.preserved
    return tuple(Preserved(
        path=source.path, present=source.present, digest=source.digest,
        disposition=disposition,
    ) for source, (_, disposition) in zip(
        _sources(repo_root, [path for path, _ in preserved]), preserved
    ))


@dataclass(frozen=True)
class DryRun:
    """What adopting this registry would cost. A report, never a migration."""

    status: str
    install: Install
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
    preserved: Tuple[Preserved, ...]
    sources: Tuple[Source, ...]

    def to_dict(self):
        return {
            "status": self.status,
            "schema_version": ARTIFACT_SCHEMA_VERSION,
            "install": self.install.to_dict(),
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
        obligation=OBLIGATION_BY_KIND[kind],
        documents=tuple(sorted(by_kind[kind])),
        reason=PLANNING_REASON if kind == "planning" else None,
    ) for kind in KINDS)


def _rekey(repo_root, inventory, waivers, registry_path):
    """Which acceptances survive the move onto assertion-unit identity.

    A legacy waiver names a file and quotes claim text; the new contract keys a
    finding to a document and a *group of assertion units*, identified by
    content digest. An acceptance therefore re-keys cleanly when its quoted
    text lands on determinate units, and needs re-waiving when it lands on
    none, on a document that no longer carries assertions, or on more units
    than the audit itself will accept.

    That last bound is the audit's, not this module's: `drift` annotates a
    waiver reaching up to `MAX_WAIVER_UNITS` findings and refuses the run past
    it. Calling anything above one unit "ambiguous" here would report waivers
    as broken that will in fact keep working, which overstates the very cost
    this dry run exists to state accurately.

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
        elif len(matched) > MAX_WAIVER_UNITS:
            blocked(waiver, "waiver-claim-too-broad", (
                f"{claim!r} appears in {len(matched)} assertion units of {path}, "
                f"over the audit's limit of {MAX_WAIVER_UNITS}, so the run it is "
                f"read into would be refused. Quote more of the line, or write "
                f"one waiver per claim accepted."
            ))
        else:
            rekeyed.append(Rekeyed(
                file=path, claim=claim, units=tuple(matched),
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


def _artifacts(repo_root, layout):
    """Every old artifact found, by class, with what to do instead of keeping it.

    Closed-world over this install's state directory: rather than hunting a
    list of known filenames, anything in it that the contract does not account
    for and that is not a vendored script is an artifact of the old world.
    Which names *are* accounted for is the layout's, because the current one
    holds files the pre-#133 one never had — the registry among them, and
    reporting that as a leftover would tell a consumer to delete the file this
    migration exists to land.
    Subdirectories are left alone — a vendored engine tree is wiring, not state.
    The repository root is not a directory this contract owns, so there the
    scan is the named list of files the legacy workflows write into it.

    Every class reports `carried: false` whether or not an instance was found:
    the disposition is the contract, and a reader must be able to see that
    approvals do not survive the move without having to leave one lying around
    to be told so.
    """
    found = {name: [] for name in ARTIFACT_CLASSES}
    for name in LEGACY_WORKING_FILES:
        if os.path.isfile(os.path.join(repo_root, name)):
            found[_artifact_class(name)].append(name)

    state_root = os.path.join(repo_root, layout.state_root)
    if os.path.isdir(state_root):
        for name in sorted(os.listdir(state_root)):
            if name in layout.accounted:
                continue
            if name.endswith(".py") or not os.path.isfile(
                os.path.join(state_root, name)
            ):
                continue
            found[_artifact_class(name)].append(f"{layout.state_root}/{name}")

    return tuple(ArtifactClass(
        name=name,
        reason=ARTIFACT_CLASSES[name][0],
        regenerate=ARTIFACT_CLASSES[name][1],
        found=tuple(sorted(found[name])),
    ) for name in sorted(ARTIFACT_CLASSES))


def dry_run_migration(repo_root, registry_path=DEFAULT_REGISTRY_PATH,
                      waivers=None, installed_version=None):
    """What adopting the landed registry costs. Reads only; writes nothing.

    Returns a `DryRun`, or `Invalid` naming every reason the migration is
    blocked — the version it cannot place, every document under a declared root
    that no rule claims, and a waivers file it cannot parse. The unclassified
    case is the one that matters most: there is no bucket for it, because a
    bucket is how a corpus quietly stops being audited, so the paths are named
    and the upgrade stops.

    `waivers` and `installed_version` default to the addresses of whichever
    layout the install occupies. State standing under both is refused on its
    own, before anything else is read: with two rival copies of the waivers,
    every acceptance this run reports on could be the wrong half.
    """
    layout, found, problem = _resolve_layout(repo_root)
    if problem is not None:
        return Invalid((problem,))
    if waivers is None:
        waivers = layout.waivers
    if installed_version is None:
        installed_version = layout.installed_version

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
        install=_install(repo_root, found, registry_path),
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
        artifacts=_artifacts(repo_root, layout),
        preserved=_preserved(repo_root, layout),
        sources=_sources(repo_root, _source_paths()),
    )
