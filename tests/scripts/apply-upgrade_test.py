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
TPL_DOC_UPGRADE = (
    "name: doc-sync-upgrade\n"
    "on:\n  schedule:\n    - cron: \"{{UPGRADE_CRON}}\"\n"
    "jobs:\n  x: ${{ github.sha }}\n"
)

TPL_DOC_AUDIT = (
    "name: doc-audit\n"
    "on:\n  schedule:\n    - cron: \"{{AUDIT_CRON}}\"\n"
    "jobs:\n  x: ${{ github.token }}\n"
)
TPL_DOC_APPLY = "name: doc-apply\non:\n  workflow_dispatch: {}\n"

SCRIPT_SOURCES = {
    "scheduling-doc-sync/scripts": ["upgrade-gate.py", "render-report.py"],
    "detecting-doc-bloat/scripts": ["plan-chunks.py", "validate-bloat-output.py"],
    "detecting-doc-drift/scripts": ["validate-drift-output.py"],
}

# Wiring only an install that adopted `.doc-lifecycle/registry.json` receives.
NEW_LANE_SCRIPT_SOURCES = {
    "scheduling-doc-sync/scripts": ["render-audit-summary.py", "render-apply-summary.py",
                                    "probe-evidence-tool.py"],
}


def make_plugin_root(base, version_tag="NEW"):
    """A synthetic doc-lifecycle plugin dir. Scripts carry a version marker so the
    test can prove the copy landed the source content."""
    root = base / "plugin-root"
    sds = root / "skills" / "scheduling-doc-sync"
    (sds).mkdir(parents=True)
    (sds / "doc-sync-upgrade.yml").write_text(TPL_DOC_UPGRADE)
    (sds / "doc-audit.yml").write_text(TPL_DOC_AUDIT)
    (sds / "doc-apply.yml").write_text(TPL_DOC_APPLY)
    sources = dict(SCRIPT_SOURCES)
    for subdir, names in NEW_LANE_SCRIPT_SOURCES.items():
        sources[subdir] = sources.get(subdir, []) + names
    for subdir, names in sources.items():
        d = root / "skills" / subdir
        d.mkdir(parents=True, exist_ok=True)
        for n in names:
            (d / n).write_text(f"# {n} @ {version_tag}\n")
    # The engine is vendored wholesale into an install that carries a registry.
    engine = root / "engine" / "doclifecycle"
    engine.mkdir(parents=True)
    (root / "engine" / "doc-lifecycle.py").write_text(f"# entry @ {version_tag}\n")
    (engine / "__init__.py").write_text(f"# engine @ {version_tag}\n")
    return root


def make_install(base, upgrade_yml=True, registry=False):
    """A synthetic install whose workflows carry non-default knobs, plus consumer
    state (marker, audit-scope) that must survive untouched."""
    repo = base / "repo"
    wf = repo / ".github" / "workflows"
    ds = repo / ".github" / "doc-sync"
    wf.mkdir(parents=True)
    ds.mkdir(parents=True)
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
    if registry:
        # The one signal that switches the new engine's lanes on: an install
        # that has been through the migration door.
        reg = repo / ".doc-lifecycle"
        reg.mkdir(parents=True)
        (reg / "registry.json").write_text('{"roots": [], "rules": []}\n')
        (wf / "doc-audit.yml").write_text(
            "name: doc-audit\non:\n  schedule:\n    - cron: \"5 1 * * *\"\n")
    return repo


def run(plugin_root, repo, target, report=None):
    argv = [sys.executable, SCRIPT, "--plugin-root", str(plugin_root),
            "--repo", str(repo), "--target", target]
    if report is not None:
        argv += ["--report-written", str(report)]
    return subprocess.run(argv, capture_output=True, text=True)


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
        du = (repo / ".github/workflows/doc-sync-upgrade.yml").read_text()
        self.assertIn('cron: "45 7 * * 4"', du)

    def test_preserves_the_audit_lane_knob_on_a_registry_install(self):
        pr = make_plugin_root(self.base)
        repo = make_install(self.base, registry=True)
        r = run(pr, repo, "0.36.0")
        self.assertEqual(r.returncode, 0, r.stderr)
        da = (repo / ".github/workflows/doc-audit.yml").read_text()
        self.assertIn('cron: "5 1 * * *"', da)

    def test_no_placeholder_survives_and_github_expr_untouched(self):
        pr = make_plugin_root(self.base)
        repo = make_install(self.base)
        run(pr, repo, "0.9.4")
        du = (repo / ".github/workflows/doc-sync-upgrade.yml").read_text()
        self.assertNotIn("{{UPGRADE_CRON}}", du)
        # The GitHub expression must be rendered verbatim, not eaten by the guard.
        self.assertIn("${{ github.sha }}", du)

    def test_bumps_installed_version_with_trailing_newline(self):
        pr = make_plugin_root(self.base)
        repo = make_install(self.base)
        run(pr, repo, "0.9.4")
        self.assertEqual(
            (repo / ".github/doc-sync/installed-version").read_text(), "0.9.4\n"
        )

    def test_overwrites_every_vendored_script_from_source(self):
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

    def test_seeds_drift_waivers_only_if_absent(self):
        pr = make_plugin_root(self.base)
        # Pre-0.11 install: no drift-waivers.json → seeded empty.
        repo = make_install(self.base)
        run(pr, repo, "0.11.0")
        self.assertEqual(
            (repo / ".github/doc-sync/drift-waivers.json").read_text(),
            '{"waivers": []}\n',
        )
        # Existing file is accumulated human judgment → byte-identical survive.
        repo2 = make_install(self.base / "second-install")
        tuned = '{"waivers": [{"file": "README.md", "claim": "fast"}]}\n'
        (repo2 / ".github/doc-sync/drift-waivers.json").write_text(tuned)
        run(pr, repo2, "0.11.0")
        self.assertEqual(
            (repo2 / ".github/doc-sync/drift-waivers.json").read_text(), tuned
        )

    # --- the new engine's lanes (an install that adopted the registry) ------

    def test_new_lane_install_gets_the_evidence_tool_probe(self):
        pr = make_plugin_root(self.base)
        repo = make_install(self.base, registry=True)
        r = run(pr, repo, "0.36.0")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(
            (repo / ".github/doc-sync/probe-evidence-tool.py").read_text(),
            "# probe-evidence-tool.py @ NEW\n",
        )

    def test_seeds_declared_evidence_tools_empty_only_if_absent(self):
        # Tool-free is the default a consumer opts out of, never one they
        # inherit: the seeded file declares nothing, and an install that has
        # already declared a tool keeps its declaration through the upgrade.
        pr = make_plugin_root(self.base)
        repo = make_install(self.base, registry=True)
        run(pr, repo, "0.36.0")
        self.assertEqual(
            (repo / ".github/doc-sync/evidence-tools.json").read_text(),
            '{"tools": []}\n',
        )
        repo2 = make_install(self.base / "second-install", registry=True)
        declared = '{"tools": ["gh"]}\n'
        (repo2 / ".github/doc-sync/evidence-tools.json").write_text(declared)
        run(pr, repo2, "0.36.0")
        self.assertEqual(
            (repo2 / ".github/doc-sync/evidence-tools.json").read_text(),
            declared,
        )

    def test_a_registry_free_install_gets_no_evidence_tools_file(self):
        # The config is the audit lane's, and that lane is not installable in a
        # repository that has not been through the migration door.
        pr = make_plugin_root(self.base)
        repo = make_install(self.base)
        run(pr, repo, "0.36.0")
        self.assertFalse(
            (repo / ".github/doc-sync/evidence-tools.json").exists())

    # --- the declared written set (--report-written) ------------------------
    #
    # The upgrade lane stages this set by name and refuses anything left over
    # (doc-sync-upgrade.yml's "Open upgrade PR" step), so a path the run wrote
    # but did not declare would strand an uncommittable change and fail the
    # run. These assert the declaration against a real regeneration.

    def written(self, repo, registry=False, target="0.9.4"):
        pr = make_plugin_root(self.base)
        report = self.base / "written.txt"
        r = run(pr, repo, target, report=report)
        self.assertEqual(r.returncode, 0, r.stderr)
        return r, report.read_text()

    def test_reported_set_names_every_file_the_run_wrote(self):
        repo = make_install(self.base, registry=True)
        _, text = self.written(repo, target="0.36.0")
        declared = set(text.splitlines())
        expected = {".github/workflows/doc-sync-upgrade.yml",
                    ".github/workflows/doc-audit.yml",
                    ".github/workflows/doc-apply.yml",
                    ".github/doc-sync/installed-version",
                    ".github/doc-sync/engine"}
        for names in SCRIPT_SOURCES.values():
            expected |= {f".github/doc-sync/{n}" for n in names}
        for names in NEW_LANE_SCRIPT_SOURCES.values():
            expected |= {f".github/doc-sync/{n}" for n in names}
        # Both seeds fire on this install: neither file existed beforehand.
        expected |= {".github/doc-sync/drift-waivers.json",
                     ".github/doc-sync/evidence-tools.json"}
        self.assertEqual(declared, expected)

    def test_reported_set_names_the_engine_directory_not_its_members(self):
        # copy_engine rmtree's the destination, so a module deleted upstream has
        # to be staged as a deletion — only the directory pathspec covers a path
        # that no longer exists to be listed.
        repo = make_install(self.base, registry=True)
        _, text = self.written(repo, target="0.36.0")
        lines = text.splitlines()
        self.assertIn(".github/doc-sync/engine", lines)
        self.assertEqual(
            [p for p in lines if p.startswith(".github/doc-sync/engine/")], [])

    def test_a_seeded_file_is_declared_only_when_it_was_seeded(self):
        # An existing waivers file is never written, so staging it would put a
        # consumer's untouched judgment in the upgrade commit.
        repo = make_install(self.base, registry=True)
        tuned = '{"waivers": [{"file": "README.md", "claim": "fast"}]}\n'
        (repo / ".github/doc-sync/drift-waivers.json").write_text(tuned)
        _, text = self.written(repo, target="0.36.0")
        self.assertNotIn(".github/doc-sync/drift-waivers.json",
                         text.splitlines())
        self.assertEqual(
            (repo / ".github/doc-sync/drift-waivers.json").read_text(), tuned)

    def test_a_registry_free_install_declares_no_new_lane_wiring(self):
        repo = make_install(self.base)
        _, text = self.written(repo)
        declared = set(text.splitlines())
        self.assertEqual(
            declared & {".github/workflows/doc-audit.yml",
                        ".github/workflows/doc-apply.yml",
                        ".github/doc-sync/engine",
                        ".github/doc-sync/evidence-tools.json"}, set())

    def test_report_is_sorted_newline_delimited_pathspec_input(self):
        # `git add --pathspec-from-file=` reads one pathspec per line; a blank
        # line or a leading `:` would be magic-pathspec syntax, not a path.
        repo = make_install(self.base, registry=True)
        _, text = self.written(repo, target="0.36.0")
        self.assertTrue(text.endswith("\n"))
        lines = text.splitlines()
        self.assertEqual(lines, sorted(lines))
        self.assertEqual(len(lines), len(set(lines)))
        for line in lines:
            self.assertTrue(line.strip(), "blank line in the pathspec file")
            self.assertFalse(line.startswith(":"), line)
            self.assertFalse(line.startswith("/"), line)

    def test_every_declared_path_exists_after_the_run(self):
        repo = make_install(self.base, registry=True)
        _, text = self.written(repo, target="0.36.0")
        for rel in text.splitlines():
            self.assertTrue((repo / rel).exists(),
                            f"declared but not written: {rel}")

    def test_no_report_file_written_without_the_flag(self):
        pr = make_plugin_root(self.base)
        repo = make_install(self.base)
        r = run(pr, repo, "0.9.4")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertFalse((self.base / "written.txt").exists())
        # The human-readable summary is unchanged by the flag's absence.
        self.assertIn("regenerated wiring at v0.9.4", r.stdout)

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

    def test_missing_source_template_fails(self):
        pr = make_plugin_root(self.base)
        (pr / "skills/scheduling-doc-sync/doc-sync-upgrade.yml").unlink()
        repo = make_install(self.base)
        r = run(pr, repo, "0.9.4")
        self.assertEqual(r.returncode, 1)
        self.assertIn("missing", r.stderr)

    def test_unextractable_upgrade_cron_fails(self):
        pr = make_plugin_root(self.base)
        repo = make_install(self.base)
        # The file is present but carries no cron line — extraction must fail,
        # not fall back to the default reserved for an absent file.
        (repo / ".github/workflows/doc-sync-upgrade.yml").write_text(
            "name: doc-sync-upgrade\non:\n  workflow_dispatch: {}\n"
        )
        r = run(pr, repo, "0.9.4")
        self.assertEqual(r.returncode, 1)
        self.assertIn("upgrade cron", r.stderr)

    def test_unextractable_audit_cron_fails(self):
        pr = make_plugin_root(self.base)
        repo = make_install(self.base, registry=True)
        (repo / ".github/workflows/doc-audit.yml").write_text(
            "name: doc-audit\non:\n  workflow_dispatch: {}\n"
        )
        r = run(pr, repo, "0.36.0")
        self.assertEqual(r.returncode, 1)
        self.assertIn("audit cron", r.stderr)

    def test_unknown_template_placeholder_fails(self):
        pr = make_plugin_root(self.base)
        # A new template knob apply-upgrade.py doesn't know about.
        (pr / "skills/scheduling-doc-sync/doc-sync-upgrade.yml").write_text(
            "name: doc-sync-upgrade\n"
            "on:\n  schedule:\n    - cron: \"{{UPGRADE_CRON}}\"\n"
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
