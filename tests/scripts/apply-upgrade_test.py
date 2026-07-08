#!/usr/bin/env python3
"""Black-box tests for scheduling-doc-sync's apply-upgrade.py.

Runs the script as a subprocess against a synthetic plugin-root (source wiring at
a "new" version) and a synthetic install (workflows carrying a consumer's knobs),
then asserts the regenerated files. Run: python3 tests/scripts/apply-upgrade_test.py
"""

import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPT = os.path.join(
    os.path.dirname(__file__),
    "..", "..",
    "plugins", "doc-lifecycle", "skills", "scheduling-doc-sync",
    "scripts", "apply-upgrade.py",
)

# Minimal stand-ins for the shipped templates: enough placeholders + a GitHub
# ${{ }} expression (which the leftover-placeholder guard must NOT trip on).
TPL_DOC_SYNC = (
    "name: doc-sync\n"
    "on:\n  schedule:\n    - cron: \"{{CRON_SCHEDULE}}\"\n"
    "env:\n  CAP: \"{{BLAST_RADIUS_CAP}}\"\n"
    "  GH_TOKEN: ${{ github.token }}\n"
)
TPL_DOC_BLOAT = (
    "name: doc-bloat\n"
    "on:\n  schedule:\n    - cron: \"{{BLOAT_CRON}}\"\n"
    "jobs:\n  x: ${{ github.sha }}\n"
)
TPL_DOC_UPGRADE = (
    "name: doc-sync-upgrade\n"
    "on:\n  schedule:\n    - cron: \"{{UPGRADE_CRON}}\"\n"
)

SCRIPT_SOURCES = {
    "scheduling-doc-sync/scripts": ["sync-gate.py", "upgrade-gate.py", "render-report.py"],
    "detecting-doc-bloat/scripts": ["plan-chunks.py", "validate-bloat-output.py"],
    "detecting-doc-drift/scripts": ["validate-drift-output.py"],
}


def make_plugin_root(base, version_tag="NEW"):
    """A synthetic doc-lifecycle plugin dir. Scripts carry a version marker so the
    test can prove the copy landed the source content."""
    root = base / "plugin-root"
    sds = root / "skills" / "scheduling-doc-sync"
    (sds).mkdir(parents=True)
    (sds / "doc-sync.yml").write_text(TPL_DOC_SYNC)
    (sds / "doc-bloat.yml").write_text(TPL_DOC_BLOAT)
    (sds / "doc-sync-upgrade.yml").write_text(TPL_DOC_UPGRADE)
    for subdir, names in SCRIPT_SOURCES.items():
        d = root / "skills" / subdir
        d.mkdir(parents=True, exist_ok=True)
        for n in names:
            (d / n).write_text(f"# {n} @ {version_tag}\n")
    return root


def make_install(base, upgrade_yml=True):
    """A synthetic install whose workflows carry non-default knobs, plus consumer
    state (marker, audit-scope) that must survive untouched."""
    repo = base / "repo"
    wf = repo / ".github" / "workflows"
    ds = repo / ".github" / "doc-sync"
    wf.mkdir(parents=True)
    ds.mkdir(parents=True)
    (wf / "doc-sync.yml").write_text(
        "name: doc-sync\non:\n  schedule:\n    - cron: \"15 2 * * *\"\n"
        "env:\n  CAP: \"7\"\n  GH_TOKEN: ${{ github.token }}\n"
    )
    (wf / "doc-bloat.yml").write_text(
        "name: doc-bloat\non:\n  schedule:\n    - cron: \"30 6 * * 3\"\n"
    )
    if upgrade_yml:
        (wf / "doc-sync-upgrade.yml").write_text(
            "name: doc-sync-upgrade\non:\n  schedule:\n    - cron: \"45 7 * * 4\"\n"
        )
    (ds / "installed-version").write_text("0.9.3\n")
    (repo / ".github" / "doc-sync-marker").write_text("deadbeefcafe\n")
    (ds / "audit-scope.json").write_text('{"exclude": ["keep/me"], "include": []}\n')
    # Old vendored scripts the copy must overwrite.
    for names in SCRIPT_SOURCES.values():
        for n in names:
            (ds / n).write_text(f"# {n} @ OLD\n")
    return repo


def run(plugin_root, repo, target):
    return subprocess.run(
        [sys.executable, SCRIPT, "--plugin-root", str(plugin_root),
         "--repo", str(repo), "--target", target],
        capture_output=True, text=True,
    )


class ApplyUpgrade(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.base = Path(self._tmp.name)
        self.addCleanup(self._tmp.cleanup)

    # --- happy path ---------------------------------------------------------

    def test_succeeds(self):
        pr = make_plugin_root(self.base)
        repo = make_install(self.base)
        r = run(pr, repo, "0.9.4")
        self.assertEqual(r.returncode, 0, r.stderr)

    def test_preserves_knobs_in_rendered_workflows(self):
        pr = make_plugin_root(self.base)
        repo = make_install(self.base)
        run(pr, repo, "0.9.4")
        ds = (repo / ".github/workflows/doc-sync.yml").read_text()
        self.assertIn('cron: "15 2 * * *"', ds)
        self.assertIn('CAP: "7"', ds)
        db = (repo / ".github/workflows/doc-bloat.yml").read_text()
        self.assertIn('cron: "30 6 * * 3"', db)
        du = (repo / ".github/workflows/doc-sync-upgrade.yml").read_text()
        self.assertIn('cron: "45 7 * * 4"', du)

    def test_no_placeholder_survives_and_github_expr_untouched(self):
        pr = make_plugin_root(self.base)
        repo = make_install(self.base)
        run(pr, repo, "0.9.4")
        ds = (repo / ".github/workflows/doc-sync.yml").read_text()
        self.assertNotIn("{{CRON_SCHEDULE}}", ds)
        self.assertNotIn("{{BLAST_RADIUS_CAP}}", ds)
        # The GitHub expression must be rendered verbatim, not eaten by the guard.
        self.assertIn("${{ github.token }}", ds)

    def test_bumps_installed_version_with_trailing_newline(self):
        pr = make_plugin_root(self.base)
        repo = make_install(self.base)
        run(pr, repo, "0.9.4")
        self.assertEqual(
            (repo / ".github/doc-sync/installed-version").read_text(), "0.9.4\n"
        )

    def test_overwrites_all_six_scripts_from_source(self):
        pr = make_plugin_root(self.base)
        repo = make_install(self.base)
        run(pr, repo, "0.9.4")
        ds = repo / ".github/doc-sync"
        for names in SCRIPT_SOURCES.values():
            for n in names:
                self.assertEqual((ds / n).read_text(), f"# {n} @ NEW\n", n)

    def test_never_touches_marker_or_audit_scope(self):
        pr = make_plugin_root(self.base)
        repo = make_install(self.base)
        run(pr, repo, "0.9.4")
        self.assertEqual(
            (repo / ".github/doc-sync-marker").read_text(), "deadbeefcafe\n"
        )
        self.assertEqual(
            (repo / ".github/doc-sync/audit-scope.json").read_text(),
            '{"exclude": ["keep/me"], "include": []}\n',
        )

    # --- absent upgrade.yml (pre-self-upgrade install) ----------------------

    def test_absent_upgrade_yml_uses_default_cron_and_warns(self):
        pr = make_plugin_root(self.base)
        repo = make_install(self.base, upgrade_yml=False)
        r = run(pr, repo, "0.9.4")
        self.assertEqual(r.returncode, 0, r.stderr)
        du = (repo / ".github/workflows/doc-sync-upgrade.yml").read_text()
        self.assertIn('cron: "0 2 * * 1"', du)
        self.assertIn("default upgrade cron", r.stderr)

    # --- fail loud ----------------------------------------------------------

    def test_missing_installed_doc_sync_fails(self):
        pr = make_plugin_root(self.base)
        repo = make_install(self.base)
        (repo / ".github/workflows/doc-sync.yml").unlink()
        r = run(pr, repo, "0.9.4")
        self.assertEqual(r.returncode, 1)
        self.assertIn("missing", r.stderr)

    def test_unextractable_cap_fails(self):
        pr = make_plugin_root(self.base)
        repo = make_install(self.base)
        (repo / ".github/workflows/doc-sync.yml").write_text(
            "name: doc-sync\non:\n  schedule:\n    - cron: \"15 2 * * *\"\n"
            # CAP line removed — extraction must fail, not default-guess.
        )
        r = run(pr, repo, "0.9.4")
        self.assertEqual(r.returncode, 1)
        self.assertIn("blast-radius cap", r.stderr)

    def test_unknown_template_placeholder_fails(self):
        pr = make_plugin_root(self.base)
        # A new template knob apply-upgrade.py doesn't know about.
        (pr / "skills/scheduling-doc-sync/doc-bloat.yml").write_text(
            "name: doc-bloat\non:\n  schedule:\n    - cron: \"{{BLOAT_CRON}}\"\n"
            "env:\n  NEW: \"{{BRAND_NEW_KNOB}}\"\n"
        )
        repo = make_install(self.base)
        r = run(pr, repo, "0.9.4")
        self.assertEqual(r.returncode, 1)
        self.assertIn("{{BRAND_NEW_KNOB}}", r.stderr)

    def test_missing_source_script_fails(self):
        pr = make_plugin_root(self.base)
        (pr / "skills/detecting-doc-drift/scripts/validate-drift-output.py").unlink()
        repo = make_install(self.base)
        r = run(pr, repo, "0.9.4")
        self.assertEqual(r.returncode, 1)
        self.assertIn("validate-drift-output.py", r.stderr)


if __name__ == "__main__":
    unittest.main(verbosity=2)
