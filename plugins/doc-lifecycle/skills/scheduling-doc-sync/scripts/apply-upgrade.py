#!/usr/bin/env python3
"""Deterministic wiring regeneration for the doc-sync self-upgrade pipeline.

Once the workflow YAML went version-agnostic (the Pin steps read the version from
.doc-lifecycle/installed-version at runtime), a routine upgrade has no
doc-judgment left in it: re-copy the vendored scripts, re-render the workflow
templates with the consumer's existing knobs, and bump the lockfile.
This script does exactly that — the mechanical work the headless model used to do
in upgrade mode — so the upgrade lane needs no model call (and no model auth).

It writes files only, and it is the *target release's* copy that runs, so the
lane never runs it in a job holding a credential: doc-sync-upgrade.yml's
uncredentialed `regenerate` job points --repo at a scratch copy of the install,
and the vendored stage-upgrade.py (run from the installed checkout, never from
here) is what decides which of the paths written there may be landed
(aj604/toolshed#127). The merge of the pull request that follows is what advances
installed-version. A pure version bump — a release that changed no script logic
and no template — leaves only installed-version diffing, since the re-copied
scripts and re-rendered templates come out byte-identical.

Usage:
    apply-upgrade.py --plugin-root <path> --repo <root> --target <version>

    --plugin-root  the doc-lifecycle plugin dir to pull wiring from. In the
                   workflow this is the pinned marketplace checkout
                   (<runner.temp>/toolshed-marketplace/plugins/doc-lifecycle);
                   a human forcing an upgrade passes $CLAUDE_PLUGIN_ROOT. Running
                   from the target checkout means the target version's own upgrade
                   logic applies.
    --repo         the install's repo root (defaults to cwd).
    --target       the bare semver being upgraded to (e.g. 0.9.4).

Layout (aj604/toolshed#133). Every artifact the plugin owns lives under
`.doc-lifecycle/`, in three tiers that make the ownership split legible:

    .doc-lifecycle/registry.json, audit-scope.json, drift-waivers.json,
    .doc-lifecycle/evidence-tools.json, auto-apply-policy.json
                                              consumer judgment — never rewritten
    .doc-lifecycle/installed-version        the version lockfile
    .doc-lifecycle/wiring/                  plugin-owned, regenerated wholesale
    .doc-lifecycle/state/                   what the credentialed jobs write

The workflow files stay in `.github/workflows/` because GitHub reads
workflows only from there; they are regenerated in place, never moved.

Ownership (total on wiring, idempotent on state):
    .github/workflows/doc-sync-upgrade.yml                       regenerate, knobs preserved
    .doc-lifecycle/wiring/*.py (the base scripts)                overwrite
    .doc-lifecycle/installed-version                             set to <target>
    .doc-lifecycle/state/sync-marker, .doc-lifecycle/audit-scope.json,
    .doc-lifecycle/drift-waivers.json                            never touched
    (drift-waivers.json is seeded empty when absent — pre-0.11 installs)

    An install that has been through the migration door — one holding a landed
    .doc-lifecycle/registry.json — also owns the new engine's lanes:
    .github/workflows/{doc-audit,doc-apply,doc-policy-apply}.yml regenerate, knobs preserved
    .doc-lifecycle/wiring/render-{audit,apply}-summary.py        overwrite
    .doc-lifecycle/wiring/probe-evidence-tool.py                 overwrite
    .doc-lifecycle/evidence-tools.json                           never touched
    (seeded `{"tools": []}` when absent — the audit lane's declared local tools)
    .doc-lifecycle/wiring/engine/                                replaced wholesale
    .doc-lifecycle/registry.json is consumer judgment and is never touched here;
    the migration door (scheduling-doc-sync's Migration mode) is what produces it.

Relocation. An install predating #133 keeps its wiring at `.github/doc-sync/`
with the marker loose beside it. When that directory is present and
`.doc-lifecycle/wiring/` is not, this run relocates instead of regenerating in
place: the judgment files and the lockfile are carried to the new root
byte-for-byte, the marker becomes `.doc-lifecycle/state/sync-marker`, the
scripts and the engine are written fresh under `wiring/`, and the old paths this
script named are removed. A file in the old directory that is not in that named
set is left where it is and reported — the closed-world rule, so nothing a
consumer put there is swept up by a directory the plugin no longer owns.

Exit status: 0 on success; 1 on any error (missing source/installed file, a knob
that can't be extracted, a template placeholder the script doesn't know, or a
layout the relocation would have to guess about) — fail red, never default-guess
a consumer's knob.
"""

import argparse
import pathlib
import re
import shutil
import sys

# Weekly, in the same early-morning window as the audit lane's daily 01:00 —
# seeded only for an install too old to carry a doc-sync-upgrade.yml of its own.
DEFAULT_UPGRADE_CRON = "0 2 * * 1"

# One `- cron: "..."` per scheduled workflow file, so a line-anchored match is
# unambiguous.
CRON_RE = re.compile(r'^\s*-\s*cron:\s*"([^"]*)"', re.M)

# A leftover {{ALL_CAPS}} placeholder means the new template introduced a knob this
# script doesn't handle — fail loud rather than ship a broken workflow. The lookbehind
# skips GitHub's own `${{ ... }}` expressions (dollar-prefixed, lowercase/dotted).
LEFTOVER_RE = re.compile(r"(?<!\$)\{\{[A-Z_]+\}\}")

# Which placeholders each template carries. Rendering substitutes these from the
# knobs extracted out of the currently-installed files.
TEMPLATE_PLACEHOLDERS = {
    "doc-sync-upgrade.yml": ["{{UPGRADE_CRON}}"],
}

# Vendored scripts and the skill dir each is copied from — the upgrade lane's
# own three. Mirrors scheduling-doc-sync's install step 5. The detecting
# skills' read-only tooling (plan-chunks.py, validate-bloat-output.py,
# validate-drift-output.py) is deliberately NOT vendored here: both detecting
# skills always dispatch their own scripts via ${CLAUDE_PLUGIN_ROOT}, never a
# repo-relative path, so a vendored copy would have no reader (aj604/toolshed#77
# follow-up).
SCRIPTS = {
    "upgrade-gate.py": "scheduling-doc-sync/scripts",
    "render-report.py": "scheduling-doc-sync/scripts",
    # The upgrade lane's own path authority. Vendored, unlike apply-upgrade.py,
    # precisely because the upgrade lane must run it from the *installed*
    # checkout: it is the code that decides what the target release's
    # regeneration is allowed to have written (aj604/toolshed#127).
    "stage-upgrade.py": "scheduling-doc-sync/scripts",
}

# The new engine's lanes. Held apart from the base wiring above because they are
# not installable everywhere: both are closed-world over `.doc-lifecycle/registry.json`
# and would fail on every run in a repository that has not been through the
# migration door. A landed registry is the one signal that the door was walked, so
# it is what switches these on — never a flag a caller can assert.
NEW_LANE_PLACEHOLDERS = {
    "doc-audit.yml": ["{{AUDIT_CRON}}"],
    # Manual dispatch only, so no schedule to preserve and nothing to substitute.
    "doc-apply.yml": [],
    # Audit-chained, with no consumer schedule of its own.
    "doc-policy-apply.yml": [],
}

NEW_LANE_SCRIPTS = {
    "render-audit-summary.py": "scheduling-doc-sync/scripts",
    "render-apply-summary.py": "scheduling-doc-sync/scripts",
    "probe-evidence-tool.py": "scheduling-doc-sync/scripts",
}

# Early daily, so a morning reader finds the night's report already published.
DEFAULT_AUDIT_CRON = "0 1 * * *"

# The engine is vendored wholesale rather than script-by-script: it is one package
# whose modules import each other, so a partially-refreshed tree is a version that
# was never tested. Copied from the plugin's `engine/` to
# `.doc-lifecycle/wiring/engine/`, whose `doc-lifecycle.py` is what both new lanes
# invoke.
ENGINE_DIR = "engine"

# --------------------------------------------------------------------------
# The layout (aj604/toolshed#133)
# --------------------------------------------------------------------------

# The plugin's directory in an install, and its three tiers. Spelled as path
# segments rather than joined strings so a caller builds them against whatever
# repo root it was handed.
ROOT_DIR = ".doc-lifecycle"
WIRING_DIR = "wiring"
STATE_DIR = "state"

# The consumer's own judgment, at the root of the plugin's directory where the
# files they are expected to edit are the first ones they see. Carried across a
# relocation byte-for-byte and never rewritten afterwards. `registry.json` is
# one of these too, but it is already at the new root — the new engine put it
# there — so it is not part of what relocates.
JUDGMENT_FILES = (
    "audit-scope.json",
    "drift-waivers.json",
    "evidence-tools.json",
    "auto-apply-policy.json",
)

# The lockfile: plugin-owned, but at the root rather than under `wiring/`,
# because a human reads it to answer "what version am I on".
VERSION_FILE = "installed-version"

# What the credentialed jobs write. The marker records the last-synced HEAD and
# is legacy state — no surviving lane reads it (aj604/toolshed#77 removed the
# lane that did) — so it is carried, never deleted: whose state it is decides
# that, and it is the consumer's.
MARKER_FILE = "sync-marker"

# The pre-#133 spellings. Named here, and only here, so the relocation carries a
# closed set: anything else a consumer left in the old directory is theirs.
LEGACY_ROOT = ".github/doc-sync"
LEGACY_MARKER = ".github/doc-sync-marker"

# A vendored script's filename, spelled exactly as `stage-upgrade.py`'s
# `LEGACY_REMOVE_PATTERNS` spells it. The relocation removes what matches; the
# path authority authorizes what matches; a name the two disagreed about would
# be removed and then refused, which is an install that can never upgrade again.
SCRIPT_NAME = re.compile(r"[A-Za-z0-9_-]+\.py")


def root_dir(repo):
    return repo / ROOT_DIR


def wiring_dir(repo):
    return root_dir(repo) / WIRING_DIR


def state_dir(repo):
    return root_dir(repo) / STATE_DIR


def legacy_root(repo):
    return repo / pathlib.PurePosixPath(LEGACY_ROOT)


class UpgradeError(Exception):
    """A precondition the upgrade can't proceed past — reported, never guessed around."""


def _read(path):
    if not path.is_file():
        raise UpgradeError(f"required file missing: {path}")
    return path.read_text()


def _extract(text, regex, what, path):
    m = regex.search(text)
    if not m:
        raise UpgradeError(f"could not extract {what} from installed {path}")
    return m.group(1)


def adopted_registry(repo):
    """Has this install been through the migration door?

    `.doc-lifecycle/registry.json` is the artifact that door produces and a human
    lands. The new engine's lanes are closed-world over it, so its presence — not a
    caller's assertion — is what makes them installable here.
    """
    return (repo / ".doc-lifecycle" / "registry.json").is_file()


def _wiring(base, new_lane_only, new_lane):
    """The base wiring, plus the new engine's when this install carries it."""
    wiring = dict(base)
    if new_lane:
        wiring.update(new_lane_only)
    return wiring


def scripts_for(repo):
    """The vendored scripts this install owns, base plus whatever it has adopted."""
    return _wiring(SCRIPTS, NEW_LANE_SCRIPTS, adopted_registry(repo))


def templates_for(repo):
    """The workflow templates this install owns, base plus whatever it has adopted."""
    return _wiring(TEMPLATE_PLACEHOLDERS, NEW_LANE_PLACEHOLDERS, adopted_registry(repo))


def read_knobs(repo):
    """Pull the consumer's install-time knobs out of the currently-installed workflows.

    Preserving these — never resetting to template defaults — is the whole point of
    an upgrade vs a fresh install.

    Only the surviving templates declare knobs: the upgrade lane's cron, and (on an
    install that adopted the registry) the audit lane's. A file that is present but
    holds no readable cron raises rather than defaulting — a knob that cannot be
    extracted is a consumer's choice about to be silently overwritten.
    """
    wf = repo / ".github" / "workflows"
    knobs = {}

    # An install predating self-upgrade has no doc-sync-upgrade.yml. Seed the default
    # cron and warn — the automated caller IS this file, so absence only happens on a
    # human forcing an upgrade of a very old install.
    du = wf / "doc-sync-upgrade.yml"
    if du.is_file():
        knobs["{{UPGRADE_CRON}}"] = _extract(du.read_text(), CRON_RE, "upgrade cron", du)
    else:
        print(
            f"warning: {du} absent (install predates self-upgrade); "
            f"using default upgrade cron {DEFAULT_UPGRADE_CRON!r}",
            file=sys.stderr,
        )
        knobs["{{UPGRADE_CRON}}"] = DEFAULT_UPGRADE_CRON

    # Same shape for the new engine's audit lane: an install that adopted the
    # registry contract before this lane existed has no doc-audit.yml to read a
    # schedule out of, so it is seeded rather than refused.
    if adopted_registry(repo):
        da = wf / "doc-audit.yml"
        if da.is_file():
            knobs["{{AUDIT_CRON}}"] = _extract(da.read_text(), CRON_RE, "audit cron", da)
        else:
            print(
                f"warning: {da} absent (install predates the new engine's audit "
                f"lane); using default audit cron {DEFAULT_AUDIT_CRON!r}",
                file=sys.stderr,
            )
            knobs["{{AUDIT_CRON}}"] = DEFAULT_AUDIT_CRON

    return knobs


def render_workflows(plugin_root, repo, knobs, new_lane=False):
    """Render every owned template into the install; returns the paths written."""
    src_dir = plugin_root / "skills" / "scheduling-doc-sync"
    dest_dir = repo / ".github" / "workflows"
    dest_dir.mkdir(parents=True, exist_ok=True)
    templates = _wiring(TEMPLATE_PLACEHOLDERS, NEW_LANE_PLACEHOLDERS, new_lane)
    written = []
    for name, placeholders in templates.items():
        text = _read(src_dir / name)
        for ph in placeholders:
            text = text.replace(ph, knobs[ph])
        left = LEFTOVER_RE.search(text)
        if left:
            raise UpgradeError(
                f"unrendered template placeholder {left.group()} in {name} — "
                f"a new knob the upgrade script doesn't handle; update apply-upgrade.py"
            )
        (dest_dir / name).write_text(text)
        written.append(f".github/workflows/{name}")
    return written


def copy_scripts(plugin_root, repo, new_lane=False):
    dest = wiring_dir(repo)
    dest.mkdir(parents=True, exist_ok=True)
    scripts = _wiring(SCRIPTS, NEW_LANE_SCRIPTS, new_lane)
    written = []
    for name, subdir in scripts.items():
        src = plugin_root / "skills" / pathlib.PurePosixPath(subdir) / name
        if not src.is_file():
            raise UpgradeError(f"required source script missing: {src}")
        shutil.copyfile(src, dest / name)
        written.append(f"{ROOT_DIR}/{WIRING_DIR}/{name}")
    written += prune_orphaned_scripts(dest, scripts)
    return written


def prune_orphaned_scripts(dest, scripts):
    """Delete a vendored .py file this install carries that the current
    release no longer wires up (a script dropped from SCRIPTS/NEW_LANE_SCRIPTS
    between releases — e.g. aj604/toolshed#77's sync-gate.py). Otherwise a
    consumer keeps a stale copy forever: copy_scripts only ever overwrote
    what's still in the table, never removed what left it.

    Scoped to top-level *.py files under `wiring/` only — engine/ is replaced
    wholesale by copy_engine, and nothing else lives in that directory: since
    aj604/toolshed#133 the consumer's judgment files, the lockfile and the
    marker sit outside it, at the root and under state/. Deleting by that
    wildcard is what stage-upgrade.py's `.doc-lifecycle/wiring/<name>.py`
    pattern already authorizes, deletion included, so no consumer's
    pre-upgrade copy can refuse the removal.

    A relocating install reaches this with a wiring/ directory holding exactly
    what copy_scripts just wrote, so the prune is a no-op there — the pre-#133
    orphans are removed by the relocation's own named set instead.
    """
    removed = []
    for path in sorted(dest.glob("*.py")):
        if path.name not in scripts:
            path.unlink()
            removed.append(f"{ROOT_DIR}/{WIRING_DIR}/{path.name}")
    return removed


def copy_engine(plugin_root, repo):
    """Replace the vendored engine wholesale with the plugin's own tree.

    Wholesale, not file-by-file: the package's modules import each other, so a tree
    holding this release's `applier.py` beside last release's `approval.py` is a
    version nobody tested. The destination is emptied first, so a module deleted
    upstream stops being importable here too — a leftover would shadow nothing and
    execute anything.

    Byte-for-byte, and never edited in place: `tests/scripts/install-parity_test.py`
    compares the two trees, which is what makes "the lanes run the engine this repo
    tests" a checked claim rather than a convention.

    Reported as the directory, not its members: the destination is emptied first, so
    a module deleted upstream has to be staged as a deletion, and only the directory
    pathspec covers a path that no longer exists to be listed.
    """
    src = plugin_root / ENGINE_DIR
    if not src.is_dir():
        raise UpgradeError(f"required source engine missing: {src}")
    dest = wiring_dir(repo) / ENGINE_DIR
    if dest.exists():
        shutil.rmtree(dest)
    dest.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(src, dest, ignore=shutil.ignore_patterns("__pycache__"))
    return [f"{ROOT_DIR}/{WIRING_DIR}/{ENGINE_DIR}"]


def seed_waivers(repo):
    """Seed an empty drift-waivers.json — only if absent.

    Pre-0.11 installs lack the file; the regenerated workflows reference it.
    An existing file is accumulated human judgment (accepted UNVERIFIABLE
    claims) and is never touched — same discipline as audit-scope.json.

    Returns the path only when it actually seeded one: a file it did not write is
    not a file it may stage.
    """
    path = root_dir(repo) / "drift-waivers.json"
    if path.is_file():
        return []
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text('{"waivers": []}\n')
    return [f"{ROOT_DIR}/drift-waivers.json"]


def seed_evidence_tools(repo):
    """Seed an empty evidence-tools.json — only if absent.

    The audit lane's declared local tools (probe-evidence-tool.py reads this,
    and the same list renders `drift-audit --evidence-command`). Seeded empty
    because tool-free is what a consumer opts *out* of, never something an
    upgrade hands them: an existing file is their declaration and is never
    touched, same discipline as audit-scope.json.

    Returns the path only when it actually seeded one — see seed_waivers.
    """
    path = root_dir(repo) / "evidence-tools.json"
    if path.is_file():
        return []
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text('{"tools": []}\n')
    return [f"{ROOT_DIR}/evidence-tools.json"]


def write_version(repo, target):
    # Trailing newline matches the install-time lockfile; bash `$(cat …)` strips it
    # either way, but keep the file identical so a version-only upgrade diffs cleanly.
    path = root_dir(repo) / VERSION_FILE
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(target + "\n")
    return [f"{ROOT_DIR}/{VERSION_FILE}"]


def relocating(repo):
    """Does this install still keep its wiring at the pre-#133 location?

    The old directory present and `wiring/` absent is the one shape a relocation
    reads as unambiguous. Every other combination is either already relocated or
    a question this script refuses to guess at — see `layout_problem`.
    """
    return legacy_root(repo).is_dir() and not wiring_dir(repo).is_dir()


def layout_problem(repo):
    """Why this install's layout cannot be upgraded as it stands, or None.

    Two shapes are refused rather than guessed at:

    - Both layouts present. Which of the two directories holds the live wiring
      is not knowable from the filesystem, and picking one would silently
      discard whichever half a half-finished relocation left behind.
    - `wiring/` present without the lockfile beside it. The relocation writes
      the lockfile at the new root in the same run that fills `wiring/`, so this
      is a relocation that stopped partway, and regenerating over it would leave
      the consumer's judgment files stranded in a directory nothing reads.

    A vendored script whose bytes differ from the target release's is *not* one
    of these: a consumer on an older version legitimately has different bytes
    there, and the contract overwrites those unconditionally, so reading a byte
    difference as a hand-edit would refuse every real upgrade.
    """
    if legacy_root(repo).is_dir() and wiring_dir(repo).is_dir():
        return (f"both layouts are present — {LEGACY_ROOT}/ and "
                f"{ROOT_DIR}/{WIRING_DIR}/ both exist, and which one holds the "
                f"live wiring is not something this script may guess. Move the "
                f"directory you do not want to keep out of the way, then retry.")
    if wiring_dir(repo).is_dir() and not (root_dir(repo) / VERSION_FILE).is_file():
        return (f"{ROOT_DIR}/{WIRING_DIR}/ exists but {ROOT_DIR}/{VERSION_FILE} "
                f"does not — this looks like a relocation that stopped partway. "
                f"Restore the install from its last good commit, then retry.")
    if relocating(repo):
        # One judgment file standing at both addresses is the same "both
        # layouts" question at file granularity, and the destructive one:
        # carrying refuses to overwrite what is already there, so proceeding
        # would delete the old copy without ever having read it. Which of the
        # two holds the decisions the consumer means is not knowable here.
        for rel_src, rel_dest in carried_pairs():
            if ((repo / pathlib.PurePosixPath(rel_src)).is_file()
                    and (repo / pathlib.PurePosixPath(rel_dest)).exists()):
                return (f"{rel_src} and {rel_dest} both exist — the relocation "
                        f"carries the old one to the new path, and cannot do "
                        f"that over a file already standing there. Keep "
                        f"whichever holds your decisions and remove the other, "
                        f"then retry.")
    return None


def carried_pairs():
    """(old path, new path) for everything the relocation carries byte-for-byte.

    The lockfile, the scripts and the engine are absent by design: those are
    written fresh at the new path, so they have nothing to carry.
    """
    return [(f"{LEGACY_ROOT}/{name}", f"{ROOT_DIR}/{name}")
            for name in JUDGMENT_FILES] + [
        (LEGACY_MARKER, f"{ROOT_DIR}/{STATE_DIR}/{MARKER_FILE}")]


def legacy_named_set(repo):
    """The old layout's paths this script owns, and everything else left there.

    Returns `(named, leftovers)`, both repo-relative and sorted. `named` is the
    closed set a relocation carries or removes; `leftovers` is whatever else a
    consumer put in the old directory — reported and left exactly where it is,
    because the plugin does not get to sweep a directory on its way out.

    A `.py` sitting directly in the old wiring directory counts as wiring by the
    same rule the upgrade lane's path authority uses (`stage-upgrade.py`'s
    `LEGACY_REMOVE_PATTERNS`): the confinement that matters is the directory and
    the extension, not a per-release list of script names that would leave a
    script dropped by an older version behind forever. `SCRIPT_NAME` spells that
    rule with the same character class the authority does, deliberately — a
    filename this admits and the authority refuses would be removed here and
    then rejected there, leaving the install permanently unable to upgrade.
    """
    old = legacy_root(repo)
    named, leftovers = [], []
    if (repo / LEGACY_MARKER).is_file():
        named.append(LEGACY_MARKER)
    if not old.is_dir():
        return sorted(named), leftovers
    for entry in sorted(old.iterdir()):
        rel = f"{LEGACY_ROOT}/{entry.name}"
        if entry.is_dir():
            (named if entry.name == ENGINE_DIR else leftovers).append(rel)
        elif (entry.name == VERSION_FILE or entry.name in JUDGMENT_FILES
                or SCRIPT_NAME.fullmatch(entry.name)):
            named.append(rel)
        else:
            leftovers.append(rel)
    return sorted(named), sorted(leftovers)


def relocate(repo):
    """Carry a pre-#133 install to `.doc-lifecycle/`; returns (changed, leftovers).

    Carried byte-for-byte: the consumer's judgment files, and the marker (which
    becomes `state/sync-marker`). Regenerated rather than moved: the lockfile,
    the scripts, and the engine — the caller writes those at the new paths right
    after, and the contract already overwrites them unconditionally, so moving
    them first would only copy bytes about to be replaced.

    Removed: exactly the named set. The old directory itself goes only when
    nothing unaccounted-for is left in it.
    """
    named, leftovers = legacy_named_set(repo)
    changed = []

    for rel_src, rel_dest in carried_pairs():
        src = repo / pathlib.PurePosixPath(rel_src)
        if not src.is_file():
            continue
        # `layout_problem` has already refused a destination that exists, so
        # this never writes over anything — and never has to decide not to.
        dest = repo / pathlib.PurePosixPath(rel_dest)
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(src, dest)
        changed.append(rel_dest)

    for rel in named:
        path = repo / pathlib.PurePosixPath(rel)
        if path.is_dir():
            shutil.rmtree(path)
        elif path.is_file():
            path.unlink()
        changed.append(rel)

    old = legacy_root(repo)
    if old.is_dir() and not any(old.iterdir()):
        old.rmdir()
    return changed, leftovers


def apply_upgrade(plugin_root, repo, target):
    """Regenerate the wiring; returns the repo-relative paths this run changed.

    The returned set is what the caller stages — every path written, plus every
    path a relocation removed, since a removal has to be staged to land. It is
    declared by the code that does the writing rather than discovered from
    `git status`, so a path this script never touched can never ride an upgrade
    commit — the caller stages exactly this list and refuses anything left over.
    """
    fault = layout_problem(repo)
    if fault:
        raise UpgradeError(fault)
    moved = relocating(repo)
    new_lane = adopted_registry(repo)
    knobs = read_knobs(repo)
    changed, leftovers = relocate(repo) if moved else ([], [])
    written = list(changed)
    written += render_workflows(plugin_root, repo, knobs, new_lane=new_lane)
    written += copy_scripts(plugin_root, repo, new_lane=new_lane)
    if new_lane:
        written += copy_engine(plugin_root, repo)
        written += seed_evidence_tools(repo)
    written += seed_waivers(repo)
    written += write_version(repo, target)
    workflows = len(_wiring(TEMPLATE_PLACEHOLDERS, NEW_LANE_PLACEHOLDERS, new_lane))
    scripts = len(_wiring(SCRIPTS, NEW_LANE_SCRIPTS, new_lane))
    engine = ", engine (vendored wholesale)" if new_lane else ""
    print(
        f"regenerated wiring at v{target}: {workflows} workflows (knobs "
        f"preserved), {scripts} scripts{engine}, installed-version"
    )
    if moved:
        print(f"relocated the install from {LEGACY_ROOT}/ to {ROOT_DIR}/ — "
              f"judgment files and the marker carried across unchanged")
        for rel in leftovers:
            print(f"left in place (not the plugin's to move): {rel}",
                  file=sys.stderr)
        if leftovers:
            print(f"{LEGACY_ROOT}/ still holds {len(leftovers)} file(s) this "
                  f"upgrade does not own, so the directory was kept")
    return sorted(set(written))


def write_report(path, written):
    """The changed set as `git add --pathspec-from-file=` input: one path per line.

    Sorted and newline-terminated, no quoting or magic-pathspec prefixes — every
    path this script lays down or takes away is a plain repo-relative name, and
    `git add` stages a removal from one exactly as it stages a write.
    """
    pathlib.Path(path).write_text("".join(f"{p}\n" for p in written))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--plugin-root", required=True, help="doc-lifecycle plugin dir to pull wiring from")
    parser.add_argument("--repo", default=".", help="install repo root (default: cwd)")
    parser.add_argument("--target", required=True, help="bare semver being upgraded to")
    parser.add_argument(
        "--report-written",
        help="write the changed paths here (written and removed), one per line, "
             "for `git add "
             "--pathspec-from-file=`. For a human forcing an upgrade locally; "
             "the workflow no longer reads it — a declaration by the release "
             "being landed is not evidence about that release "
             "(aj604/toolshed#127)")
    args = parser.parse_args()

    try:
        written = apply_upgrade(
            pathlib.Path(args.plugin_root), pathlib.Path(args.repo), args.target
        )
        if args.report_written:
            write_report(args.report_written, written)
    except UpgradeError as e:
        print(f"error: {e}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
