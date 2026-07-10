#!/usr/bin/env python3
"""Deterministic wiring regeneration for the doc-sync self-upgrade pipeline.

Once the workflow YAML went version-agnostic (the Pin steps read the version from
.github/doc-sync/installed-version at runtime), a routine upgrade has no
doc-judgment left in it: re-copy the seven vendored scripts, re-render the three
workflow templates with the consumer's existing knobs, and bump the lockfile.
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
    .github/workflows/{doc-sync,doc-bloat,doc-sync-upgrade}.yml  regenerate, knobs preserved
    .github/doc-sync/*.py (seven scripts)                        overwrite
    .github/doc-sync/installed-version                           set to <target>
    .github/doc-sync-marker, .github/doc-sync/audit-scope.json   never touched

Exit status: 0 on success; 1 on any error (missing source/installed file, a knob
that can't be extracted, or a template placeholder the script doesn't know) —
fail red, never default-guess a consumer's knob.
"""

import argparse
import pathlib
import re
import shutil
import sys

# Earliest of the three schedules (before doc-sync's 03:00 daily and doc-bloat's
# 04:00 Monday) so the weekly version-bump check is the first run of its day.
DEFAULT_UPGRADE_CRON = "0 2 * * 1"

# One `- cron: "..."` and (in doc-sync only) one `CAP: "..."` per workflow file,
# so a line-anchored match is unambiguous.
CRON_RE = re.compile(r'^\s*-\s*cron:\s*"([^"]*)"', re.M)
CAP_RE = re.compile(r'^\s*CAP:\s*"([^"]*)"', re.M)

# A leftover {{ALL_CAPS}} placeholder means the new template introduced a knob this
# script doesn't handle — fail loud rather than ship a broken workflow. The lookbehind
# skips GitHub's own `${{ ... }}` expressions (dollar-prefixed, lowercase/dotted).
LEFTOVER_RE = re.compile(r"(?<!\$)\{\{[A-Z_]+\}\}")

# Which placeholders each template carries. Rendering substitutes these from the
# knobs extracted out of the currently-installed files.
TEMPLATE_PLACEHOLDERS = {
    "doc-sync.yml": ["{{CRON_SCHEDULE}}", "{{BLAST_RADIUS_CAP}}"],
    "doc-bloat.yml": ["{{BLOAT_CRON}}"],
    "doc-sync-upgrade.yml": ["{{UPGRADE_CRON}}"],
}

# Vendored scripts and the skill dir each is copied from (four from this skill,
# the planner + bloat validator from detecting-doc-bloat, the drift validator from
# detecting-doc-drift). Mirror scheduling-doc-sync's install steps 3-4.
SCRIPTS = {
    "sync-gate.py": "scheduling-doc-sync/scripts",
    "upgrade-gate.py": "scheduling-doc-sync/scripts",
    "render-report.py": "scheduling-doc-sync/scripts",
    "plan-distill.py": "scheduling-doc-sync/scripts",
    "plan-chunks.py": "detecting-doc-bloat/scripts",
    "validate-bloat-output.py": "detecting-doc-bloat/scripts",
    "validate-drift-output.py": "detecting-doc-drift/scripts",
}


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


def read_knobs(repo):
    """Pull the consumer's install-time knobs out of the currently-installed workflows.

    Preserving these — never resetting to template defaults — is the whole point of
    an upgrade vs a fresh install.
    """
    wf = repo / ".github" / "workflows"
    knobs = {}

    ds = wf / "doc-sync.yml"
    ds_text = _read(ds)
    knobs["{{CRON_SCHEDULE}}"] = _extract(ds_text, CRON_RE, "cron schedule", ds)
    knobs["{{BLAST_RADIUS_CAP}}"] = _extract(ds_text, CAP_RE, "blast-radius cap", ds)

    db = wf / "doc-bloat.yml"
    knobs["{{BLOAT_CRON}}"] = _extract(_read(db), CRON_RE, "bloat cron", db)

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

    return knobs


def render_workflows(plugin_root, repo, knobs):
    src_dir = plugin_root / "skills" / "scheduling-doc-sync"
    dest_dir = repo / ".github" / "workflows"
    dest_dir.mkdir(parents=True, exist_ok=True)
    for name, placeholders in TEMPLATE_PLACEHOLDERS.items():
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


def copy_scripts(plugin_root, repo):
    dest = repo / ".github" / "doc-sync"
    dest.mkdir(parents=True, exist_ok=True)
    for name, subdir in SCRIPTS.items():
        src = plugin_root / "skills" / pathlib.PurePosixPath(subdir) / name
        if not src.is_file():
            raise UpgradeError(f"required source script missing: {src}")
        shutil.copyfile(src, dest / name)


def write_version(repo, target):
    # Trailing newline matches the install-time lockfile; bash `$(cat …)` strips it
    # either way, but keep the file identical so a version-only upgrade diffs cleanly.
    (repo / ".github" / "doc-sync" / "installed-version").write_text(target + "\n")


def apply_upgrade(plugin_root, repo, target):
    knobs = read_knobs(repo)
    render_workflows(plugin_root, repo, knobs)
    copy_scripts(plugin_root, repo)
    write_version(repo, target)
    print(
        f"regenerated wiring at v{target}: 3 workflows (knobs preserved), "
        f"{len(SCRIPTS)} scripts, installed-version"
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--plugin-root", required=True, help="doc-lifecycle plugin dir to pull wiring from")
    parser.add_argument("--repo", default=".", help="install repo root (default: cwd)")
    parser.add_argument("--target", required=True, help="bare semver being upgraded to")
    args = parser.parse_args()

    try:
        apply_upgrade(
            pathlib.Path(args.plugin_root), pathlib.Path(args.repo), args.target
        )
    except UpgradeError as e:
        print(f"error: {e}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
