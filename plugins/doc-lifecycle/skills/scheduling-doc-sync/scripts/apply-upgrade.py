#!/usr/bin/env python3
"""Deterministic wiring regeneration for the doc-sync self-upgrade pipeline.

Once the workflow YAML went version-agnostic (the Pin steps read the version from
.github/doc-sync/installed-version at runtime), a routine upgrade has no
doc-judgment left in it: re-copy the vendored scripts, re-render the workflow
templates with the consumer's existing knobs, and bump the lockfile.
This script does exactly that — the mechanical work the headless model used to do
in upgrade mode — so the upgrade lane needs no model call (and no model auth).

It writes files only. The caller (doc-sync-upgrade.yml, or a human forcing an
upgrade) owns git: it diffs the working tree, opens the review PR, and the merge
is what advances installed-version. A pure version bump — a release that changed
no script logic and no template — leaves only installed-version diffing, since the
re-copied scripts and re-rendered templates come out byte-identical.

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

Ownership (total on wiring, idempotent on state):
    .github/workflows/doc-sync-upgrade.yml                       regenerate, knobs preserved
    .github/doc-sync/*.py (the base scripts)                     overwrite
    .github/doc-sync/installed-version                           set to <target>
    .github/doc-sync-marker, .github/doc-sync/audit-scope.json,
    .github/doc-sync/drift-waivers.json                          never touched
    (drift-waivers.json is seeded empty when absent — pre-0.11 installs)

    An install that has been through the migration door — one holding a landed
    .doc-lifecycle/registry.json — also owns the new engine's lanes:
    .github/workflows/{doc-audit,doc-apply}.yml                  regenerate, knobs preserved
    .github/doc-sync/render-{audit,apply}-summary.py             overwrite
    .github/doc-sync/probe-evidence-tool.py                      overwrite
    .github/doc-sync/evidence-tools.json                         never touched
    (seeded `{"tools": []}` when absent — the audit lane's declared local tools)
    .github/doc-sync/engine/                                     replaced wholesale
    .doc-lifecycle/registry.json is consumer judgment and is never touched here;
    the migration door (scheduling-doc-sync's Migration mode) is what produces it.

Exit status: 0 on success; 1 on any error (missing source/installed file, a knob
that can't be extracted, or a template placeholder the script doesn't know) —
fail red, never default-guess a consumer's knob.
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

# Vendored scripts and the skill dir each is copied from (the upgrade lane's two
# from this skill, the planner + bloat validator from detecting-doc-bloat, the
# drift validator from detecting-doc-drift). Mirror scheduling-doc-sync's install
# steps 5-6. The last three are the detecting skills' own read-only tooling: they
# are vendored for every install because a model running either skill reaches for
# them whichever lane invoked it.
SCRIPTS = {
    "upgrade-gate.py": "scheduling-doc-sync/scripts",
    "render-report.py": "scheduling-doc-sync/scripts",
    "plan-chunks.py": "detecting-doc-bloat/scripts",
    "validate-bloat-output.py": "detecting-doc-bloat/scripts",
    "validate-drift-output.py": "detecting-doc-drift/scripts",
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
# was never tested. Copied from the plugin's `engine/` to `.github/doc-sync/engine/`,
# whose `doc-lifecycle.py` is what both new lanes invoke.
ENGINE_DIR = "engine"


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
    dest = repo / ".github" / "doc-sync"
    dest.mkdir(parents=True, exist_ok=True)
    scripts = _wiring(SCRIPTS, NEW_LANE_SCRIPTS, new_lane)
    written = []
    for name, subdir in scripts.items():
        src = plugin_root / "skills" / pathlib.PurePosixPath(subdir) / name
        if not src.is_file():
            raise UpgradeError(f"required source script missing: {src}")
        shutil.copyfile(src, dest / name)
        written.append(f".github/doc-sync/{name}")
    return written


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
    dest = repo / ".github" / "doc-sync" / ENGINE_DIR
    if dest.exists():
        shutil.rmtree(dest)
    dest.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(src, dest, ignore=shutil.ignore_patterns("__pycache__"))
    return [f".github/doc-sync/{ENGINE_DIR}"]


def seed_waivers(repo):
    """Seed an empty drift-waivers.json — only if absent.

    Pre-0.11 installs lack the file; the regenerated workflows reference it.
    An existing file is accumulated human judgment (accepted UNVERIFIABLE
    claims) and is never touched — same discipline as audit-scope.json.

    Returns the path only when it actually seeded one: a file it did not write is
    not a file it may stage.
    """
    path = repo / ".github" / "doc-sync" / "drift-waivers.json"
    if path.is_file():
        return []
    path.write_text('{"waivers": []}\n')
    return [".github/doc-sync/drift-waivers.json"]


def seed_evidence_tools(repo):
    """Seed an empty evidence-tools.json — only if absent.

    The audit lane's declared local tools (probe-evidence-tool.py reads this,
    and the same list renders `drift-audit --evidence-command`). Seeded empty
    because tool-free is what a consumer opts *out* of, never something an
    upgrade hands them: an existing file is their declaration and is never
    touched, same discipline as audit-scope.json.

    Returns the path only when it actually seeded one — see seed_waivers.
    """
    path = repo / ".github" / "doc-sync" / "evidence-tools.json"
    if path.is_file():
        return []
    path.write_text('{"tools": []}\n')
    return [".github/doc-sync/evidence-tools.json"]


def write_version(repo, target):
    # Trailing newline matches the install-time lockfile; bash `$(cat …)` strips it
    # either way, but keep the file identical so a version-only upgrade diffs cleanly.
    (repo / ".github" / "doc-sync" / "installed-version").write_text(target + "\n")
    return [".github/doc-sync/installed-version"]


def apply_upgrade(plugin_root, repo, target):
    """Regenerate the wiring; returns the repo-relative paths this run wrote.

    The returned set is what the caller stages. It is declared by the code that
    does the writing rather than discovered from `git status`, so a path this
    script never touched can never ride an upgrade commit — the caller stages
    exactly this list and refuses anything left over.
    """
    new_lane = adopted_registry(repo)
    knobs = read_knobs(repo)
    written = render_workflows(plugin_root, repo, knobs, new_lane=new_lane)
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
    return sorted(set(written))


def write_report(path, written):
    """The written set as `git add --pathspec-from-file=` input: one path per line.

    Sorted and newline-terminated, no quoting or magic-pathspec prefixes — every
    path this script lays down is a plain repo-relative name.
    """
    pathlib.Path(path).write_text("".join(f"{p}\n" for p in written))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--plugin-root", required=True, help="doc-lifecycle plugin dir to pull wiring from")
    parser.add_argument("--repo", default=".", help="install repo root (default: cwd)")
    parser.add_argument("--target", required=True, help="bare semver being upgraded to")
    parser.add_argument(
        "--report-written",
        help="write the regenerated paths here, one per line, for `git add "
             "--pathspec-from-file=` (the caller stages this set and nothing else)")
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
