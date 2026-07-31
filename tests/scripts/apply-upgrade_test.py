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
TPL_DOC_POLICY_APPLY = (
    "name: doc-policy-apply\n"
    "on:\n  workflow_run:\n    workflows: [\"doc-audit\"]\n"
)

SCRIPT_SOURCES = {
    "scheduling-doc-sync/scripts": ["upgrade-gate.py", "render-report.py",
                                   "stage-upgrade.py"],
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
    (sds / "doc-policy-apply.yml").write_text(TPL_DOC_POLICY_APPLY)
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


MARKER = "deadbeefcafe\n"
AUDIT_SCOPE = '{"exclude": ["keep/me"], "include": []}\n'
WAIVERS = '{"waivers": [{"file": "README.md", "claim": "fast"}]}\n'
AUTO_APPLY_POLICY = (
    '{"artifact":"auto-apply-policy","schema_version":1,'
    '"id":"nightly-doc-sync"}\n'
)


def _workflows(repo, upgrade_yml, registry):
    wf = repo / ".github" / "workflows"
    wf.mkdir(parents=True, exist_ok=True)
    if upgrade_yml:
        (wf / "doc-sync-upgrade.yml").write_text(
            "name: doc-sync-upgrade\non:\n  schedule:\n    - cron: \"45 7 * * 4\"\n"
        )
    if registry:
        (wf / "doc-audit.yml").write_text(
            "name: doc-audit\non:\n  schedule:\n    - cron: \"5 1 * * *\"\n")


def make_install(base, upgrade_yml=True, registry=False, name="repo"):
    """A synthetic install on the current layout: workflows carrying non-default
    knobs, judgment files at `.doc-lifecycle/`, wiring under `wiring/`, and the
    marker under `state/` — all of which must survive an upgrade untouched."""
    repo = base / name
    root = repo / ".doc-lifecycle"
    wiring = root / "wiring"
    wiring.mkdir(parents=True)
    _workflows(repo, upgrade_yml, registry)
    (root / "installed-version").write_text("0.9.3\n")
    (root / "state").mkdir()
    (root / "state" / "sync-marker").write_text(MARKER)
    (root / "audit-scope.json").write_text(AUDIT_SCOPE)
    # Old vendored scripts the copy must overwrite.
    for names in SCRIPT_SOURCES.values():
        for n in names:
            (wiring / n).write_text(f"# {n} @ OLD\n")
    if registry:
        # The one signal that switches the new engine's lanes on: an install
        # that has been through the migration door.
        (root / "registry.json").write_text('{"roots": [], "rules": []}\n')
    return repo


def make_legacy_install(base, registry=False, name="repo", extras=()):
    """The same install before aj604/toolshed#133 moved it: wiring at
    `.github/doc-sync/`, the marker loose beside it, nothing under
    `.doc-lifecycle/` but the registry an adopting install already had.

    `extras` are files a consumer put in the old directory themselves — the
    relocation must leave every one of them exactly where it is.
    """
    repo = base / name
    ds = repo / ".github" / "doc-sync"
    ds.mkdir(parents=True)
    _workflows(repo, True, registry)
    (ds / "installed-version").write_text("0.9.3\n")
    (repo / ".github" / "doc-sync-marker").write_text(MARKER)
    (ds / "audit-scope.json").write_text(AUDIT_SCOPE)
    (ds / "drift-waivers.json").write_text(WAIVERS)
    for names in SCRIPT_SOURCES.values():
        for n in names:
            (ds / n).write_text(f"# {n} @ OLD\n")
    if registry:
        engine = ds / "engine" / "doclifecycle"
        engine.mkdir(parents=True)
        (engine / "__init__.py").write_text("# engine @ OLD\n")
        for names in NEW_LANE_SCRIPT_SOURCES.values():
            for n in names:
                (ds / n).write_text(f"# {n} @ OLD\n")
        (ds / "evidence-tools.json").write_text('{"tools": ["gh"]}\n')
        (ds / "auto-apply-policy.json").write_text(AUTO_APPLY_POLICY)
        reg = repo / ".doc-lifecycle"
        reg.mkdir(parents=True)
        (reg / "registry.json").write_text('{"roots": [], "rules": []}\n')
    for rel, text in extras:
        path = ds / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text)
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
            (repo / ".doc-lifecycle/installed-version").read_text(), "0.9.4\n"
        )

    def test_overwrites_every_vendored_script_from_source(self):
        pr = make_plugin_root(self.base)
        repo = make_install(self.base)
        run(pr, repo, "0.9.4")
        ds = repo / ".doc-lifecycle/wiring"
        for names in SCRIPT_SOURCES.values():
            for n in names:
                self.assertEqual((ds / n).read_text(), f"# {n} @ NEW\n", n)

    def test_never_touches_marker_or_audit_scope(self):
        pr = make_plugin_root(self.base)
        repo = make_install(self.base)
        run(pr, repo, "0.9.4")
        self.assertEqual(
            (repo / ".doc-lifecycle/state/sync-marker").read_text(), "deadbeefcafe\n"
        )
        self.assertEqual(
            (repo / ".doc-lifecycle/audit-scope.json").read_text(),
            '{"exclude": ["keep/me"], "include": []}\n',
        )

    def test_seeds_drift_waivers_only_if_absent(self):
        pr = make_plugin_root(self.base)
        # Pre-0.11 install: no drift-waivers.json → seeded empty.
        repo = make_install(self.base)
        run(pr, repo, "0.11.0")
        self.assertEqual(
            (repo / ".doc-lifecycle/drift-waivers.json").read_text(),
            '{"waivers": []}\n',
        )
        # Existing file is accumulated human judgment → byte-identical survive.
        repo2 = make_install(self.base, name="second-install")
        tuned = '{"waivers": [{"file": "README.md", "claim": "fast"}]}\n'
        (repo2 / ".doc-lifecycle/drift-waivers.json").write_text(tuned)
        run(pr, repo2, "0.11.0")
        self.assertEqual(
            (repo2 / ".doc-lifecycle/drift-waivers.json").read_text(), tuned
        )

    # --- the new engine's lanes (an install that adopted the registry) ------

    def test_new_lane_install_gets_the_evidence_tool_probe(self):
        pr = make_plugin_root(self.base)
        repo = make_install(self.base, registry=True)
        r = run(pr, repo, "0.36.0")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(
            (repo / ".doc-lifecycle/wiring/probe-evidence-tool.py").read_text(),
            "# probe-evidence-tool.py @ NEW\n",
        )

    def test_new_lane_install_gets_the_policy_apply_workflow(self):
        pr = make_plugin_root(self.base)
        repo = make_install(self.base, registry=True)
        r = run(pr, repo, "0.36.0")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(
            (repo / ".github/workflows/doc-policy-apply.yml").read_text(),
            TPL_DOC_POLICY_APPLY,
        )

    def test_an_upgrade_never_opts_a_consumer_into_auto_apply(self):
        pr = make_plugin_root(self.base)
        repo = make_install(self.base, registry=True)
        run(pr, repo, "0.36.0")
        policy = repo / ".doc-lifecycle/auto-apply-policy.json"
        self.assertFalse(policy.exists())

        repo2 = make_install(self.base, registry=True, name="configured")
        policy2 = repo2 / ".doc-lifecycle/auto-apply-policy.json"
        policy2.write_text(AUTO_APPLY_POLICY)
        run(pr, repo2, "0.36.0")
        self.assertEqual(policy2.read_text(), AUTO_APPLY_POLICY)

    def test_seeds_declared_evidence_tools_empty_only_if_absent(self):
        # Tool-free is the default a consumer opts out of, never one they
        # inherit: the seeded file declares nothing, and an install that has
        # already declared a tool keeps its declaration through the upgrade.
        pr = make_plugin_root(self.base)
        repo = make_install(self.base, registry=True)
        run(pr, repo, "0.36.0")
        self.assertEqual(
            (repo / ".doc-lifecycle/evidence-tools.json").read_text(),
            '{"tools": []}\n',
        )
        repo2 = make_install(self.base, registry=True, name="second-install")
        declared = '{"tools": ["gh"]}\n'
        (repo2 / ".doc-lifecycle/evidence-tools.json").write_text(declared)
        run(pr, repo2, "0.36.0")
        self.assertEqual(
            (repo2 / ".doc-lifecycle/evidence-tools.json").read_text(),
            declared,
        )

    def test_a_registry_free_install_gets_no_evidence_tools_file(self):
        # The config is the audit lane's, and that lane is not installable in a
        # repository that has not been through the migration door.
        pr = make_plugin_root(self.base)
        repo = make_install(self.base)
        run(pr, repo, "0.36.0")
        self.assertFalse(
            (repo / ".doc-lifecycle/evidence-tools.json").exists())

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
                    ".github/workflows/doc-policy-apply.yml",
                    ".doc-lifecycle/installed-version",
                    ".doc-lifecycle/wiring/engine"}
        for names in SCRIPT_SOURCES.values():
            expected |= {f".doc-lifecycle/wiring/{n}" for n in names}
        for names in NEW_LANE_SCRIPT_SOURCES.values():
            expected |= {f".doc-lifecycle/wiring/{n}" for n in names}
        # Both seeds fire on this install: neither file existed beforehand.
        expected |= {".doc-lifecycle/drift-waivers.json",
                     ".doc-lifecycle/evidence-tools.json"}
        self.assertEqual(declared, expected)

    def test_reported_set_names_the_engine_directory_not_its_members(self):
        # copy_engine rmtree's the destination, so a module deleted upstream has
        # to be staged as a deletion — only the directory pathspec covers a path
        # that no longer exists to be listed.
        repo = make_install(self.base, registry=True)
        _, text = self.written(repo, target="0.36.0")
        lines = text.splitlines()
        self.assertIn(".doc-lifecycle/wiring/engine", lines)
        self.assertEqual(
            [p for p in lines if p.startswith(".doc-lifecycle/wiring/engine/")], [])

    def test_a_seeded_file_is_declared_only_when_it_was_seeded(self):
        # An existing waivers file is never written, so staging it would put a
        # consumer's untouched judgment in the upgrade commit.
        repo = make_install(self.base, registry=True)
        tuned = '{"waivers": [{"file": "README.md", "claim": "fast"}]}\n'
        (repo / ".doc-lifecycle/drift-waivers.json").write_text(tuned)
        _, text = self.written(repo, target="0.36.0")
        self.assertNotIn(".doc-lifecycle/drift-waivers.json",
                         text.splitlines())
        self.assertEqual(
            (repo / ".doc-lifecycle/drift-waivers.json").read_text(), tuned)

    def test_a_registry_free_install_declares_no_new_lane_wiring(self):
        repo = make_install(self.base)
        _, text = self.written(repo)
        declared = set(text.splitlines())
        self.assertEqual(
            declared & {".github/workflows/doc-audit.yml",
                        ".github/workflows/doc-apply.yml",
                        ".github/workflows/doc-policy-apply.yml",
                        ".doc-lifecycle/wiring/engine",
                        ".doc-lifecycle/evidence-tools.json"}, set())

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

    # --- orphaned vendored scripts (left the SCRIPTS/NEW_LANE_SCRIPTS table) -
    #
    # copy_scripts only ever overwrote what's still in the table; a script
    # dropped from a later release (e.g. aj604/toolshed#77's sync-gate.py,
    # authorize-paths.py, plan-distill.py, and the follow-up's plan-chunks.py,
    # validate-bloat-output.py, validate-drift-output.py) used to strand a
    # stale copy in every consumer that had already vendored it. These pin
    # the fix: a .py file directly under .doc-lifecycle/wiring/ that isn't in
    # the current wiring gets deleted, declared in the written set (so the
    # upgrade lane's undeclared-paths refusal doesn't choke on it), and
    # nothing else in the install is touched.
    #
    # The pre-#133 spellings of these same orphans are removed by the
    # relocation's own named set instead, not by this prune — see the
    # relocation tests.

    def test_orphaned_scripts_are_deleted(self):
        pr = make_plugin_root(self.base)
        repo = make_install(self.base)
        wiring = repo / ".doc-lifecycle" / "wiring"
        stale = ["plan-chunks.py", "validate-bloat-output.py",
                 "validate-drift-output.py", "sync-gate.py",
                 "authorize-paths.py", "plan-distill.py"]
        for name in stale:
            (wiring / name).write_text(f"# stale {name}\n")
        r = run(pr, repo, "0.9.4")
        self.assertEqual(r.returncode, 0, r.stderr)
        for name in stale:
            self.assertFalse((wiring / name).exists(), name)

    def test_orphan_deletion_leaves_current_scripts_and_state_alone(self):
        pr = make_plugin_root(self.base)
        repo = make_install(self.base, registry=True)
        root = repo / ".doc-lifecycle"
        wiring = root / "wiring"
        (wiring / "plan-chunks.py").write_text("# stale\n")
        r = run(pr, repo, "0.36.0")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertTrue((wiring / "render-report.py").is_file())
        self.assertTrue((wiring / "upgrade-gate.py").is_file())
        self.assertTrue((wiring / "stage-upgrade.py").is_file())
        self.assertTrue((wiring / "render-audit-summary.py").is_file())
        self.assertTrue((wiring / "engine").is_dir())
        self.assertTrue((wiring / "engine" / "doclifecycle").is_dir())
        # The tiers the prune must never reach into: judgment at the root,
        # machine-written state under state/.
        self.assertEqual((root / "audit-scope.json").read_text(), AUDIT_SCOPE)
        self.assertTrue((root / "installed-version").is_file())
        self.assertEqual((root / "state" / "sync-marker").read_text(), MARKER)

    def test_orphan_deletions_are_declared_in_the_written_set(self):
        repo = make_install(self.base)
        wiring = repo / ".doc-lifecycle" / "wiring"
        (wiring / "plan-chunks.py").write_text("# stale\n")
        _, text = self.written(repo)
        self.assertIn(".doc-lifecycle/wiring/plan-chunks.py", text.splitlines())
        self.assertFalse((wiring / "plan-chunks.py").exists())

    def test_no_orphans_declares_no_deletions(self):
        repo = make_install(self.base)
        _, text = self.written(repo)
        expected = {".github/workflows/doc-sync-upgrade.yml",
                    ".doc-lifecycle/installed-version",
                    ".doc-lifecycle/drift-waivers.json"}
        for names in SCRIPT_SOURCES.values():
            expected |= {f".doc-lifecycle/wiring/{n}" for n in names}
        self.assertEqual(set(text.splitlines()), expected)

    def test_a_relocating_install_prunes_nothing_of_its_own(self):
        """The new wiring/ holds exactly what copy_scripts just wrote, so the
        prune has nothing to find — the old directory's orphans leave with the
        relocation's named set, and never as a prune of a path that was never
        under `wiring/`."""
        pr = make_plugin_root(self.base)
        repo = make_legacy_install(self.base)
        (repo / ".github" / "doc-sync" / "sync-gate.py").write_text("# stale\n")
        report = self.base / "written.txt"
        r = run(pr, repo, "0.9.4", report=report)
        self.assertEqual(r.returncode, 0, r.stderr)
        declared = set(report.read_text().splitlines())
        self.assertIn(".github/doc-sync/sync-gate.py", declared)
        self.assertFalse(
            [p for p in declared
             if p.startswith(".doc-lifecycle/wiring/")
             and not (repo / p).exists()])

    # --- absent upgrade.yml (pre-self-upgrade install) ----------------------

    def test_absent_upgrade_yml_uses_default_cron_and_warns(self):
        pr = make_plugin_root(self.base)
        repo = make_install(self.base, upgrade_yml=False)
        r = run(pr, repo, "0.9.4")
        self.assertEqual(r.returncode, 0, r.stderr)
        du = (repo / ".github/workflows/doc-sync-upgrade.yml").read_text()
        self.assertIn('cron: "0 2 * * 1"', du)
        self.assertIn("default upgrade cron", r.stderr)

    # --- the relocation (aj604/toolshed#133) --------------------------------
    #
    # Black-box at the same seam as everything above: given a pre-#133 install
    # on disk, what tree comes out and what does the run say. The relocation is
    # entirely observable there — nothing here reaches into the module.

    def relocate(self, registry=True, extras=(), target="0.36.0"):
        self.plugin_root = make_plugin_root(self.base)
        repo = make_legacy_install(self.base, registry=registry, extras=extras)
        r = run(self.plugin_root, repo, target)
        self.assertEqual(r.returncode, 0, r.stderr)
        return repo, r

    def test_it_carries_the_judgment_files_byte_for_byte(self):
        repo, _ = self.relocate()
        self.assertEqual((repo / ".doc-lifecycle/audit-scope.json").read_text(),
                         AUDIT_SCOPE)
        self.assertEqual(
            (repo / ".doc-lifecycle/evidence-tools.json").read_text(),
            '{"tools": ["gh"]}\n')
        self.assertEqual(
            (repo / ".doc-lifecycle/auto-apply-policy.json").read_text(),
            AUTO_APPLY_POLICY)
        # Carried, so the seeder never fires over it.
        self.assertEqual(
            (repo / ".doc-lifecycle/drift-waivers.json").read_text(), WAIVERS)
        # Already at the new root before the move, and no business of the move.
        self.assertEqual((repo / ".doc-lifecycle/registry.json").read_text(),
                         '{"roots": [], "rules": []}\n')

    def test_the_marker_lands_under_state_with_its_bytes_intact(self):
        repo, _ = self.relocate()
        self.assertEqual(
            (repo / ".doc-lifecycle/state/sync-marker").read_text(), MARKER)

    def test_the_wiring_and_the_engine_are_written_fresh_under_wiring(self):
        repo, _ = self.relocate()
        for names in SCRIPT_SOURCES.values():
            for n in names:
                self.assertEqual(
                    (repo / ".doc-lifecycle/wiring" / n).read_text(),
                    f"# {n} @ NEW\n", n)
        self.assertEqual(
            (repo / ".doc-lifecycle/wiring/engine/doclifecycle/__init__.py"
             ).read_text(), "# engine @ NEW\n")
        self.assertEqual((repo / ".doc-lifecycle/installed-version").read_text(),
                         "0.36.0\n")

    def test_the_workflows_are_regenerated_with_the_knobs_preserved(self):
        repo, _ = self.relocate()
        self.assertIn('cron: "45 7 * * 4"',
                      (repo / ".github/workflows/doc-sync-upgrade.yml").read_text())
        self.assertIn('cron: "5 1 * * *"',
                      (repo / ".github/workflows/doc-audit.yml").read_text())

    def test_the_old_layout_is_gone(self):
        repo, _ = self.relocate()
        self.assertFalse((repo / ".github/doc-sync").exists())
        self.assertFalse((repo / ".github/doc-sync-marker").exists())

    def test_an_unrecognized_file_is_left_where_it_is_and_named(self):
        repo, r = self.relocate(extras=[("notes.md", "mine\n"),
                                        ("scratch/data.csv", "1,2\n")])
        old = repo / ".github/doc-sync"
        self.assertEqual((old / "notes.md").read_text(), "mine\n")
        self.assertEqual((old / "scratch/data.csv").read_text(), "1,2\n")
        self.assertIn(".github/doc-sync/notes.md", r.stderr)
        self.assertIn(".github/doc-sync/scratch", r.stderr)
        self.assertIn("does not own", r.stdout)
        # Everything the plugin did own still left.
        self.assertFalse((old / "installed-version").exists())
        self.assertFalse((old / "render-report.py").exists())

    def test_a_registry_free_install_relocates_too(self):
        repo, _ = self.relocate(registry=False, target="0.12.0")
        self.assertFalse((repo / ".github/doc-sync").exists())
        self.assertEqual((repo / ".doc-lifecycle/audit-scope.json").read_text(),
                         AUDIT_SCOPE)
        # The audit lane is still not installable here, so its config is not
        # seeded on the way past.
        self.assertFalse((repo / ".doc-lifecycle/evidence-tools.json").exists())

    def test_the_reported_set_carries_the_removals_too(self):
        # `git add` stages a removal exactly as it stages a write, and a patch
        # of deletions with no creations would not be applicable.
        pr = make_plugin_root(self.base)
        repo = make_legacy_install(self.base, registry=True)
        report = self.base / "written.txt"
        r = run(pr, repo, "0.36.0", report=report)
        self.assertEqual(r.returncode, 0, r.stderr)
        declared = set(report.read_text().splitlines())
        self.assertIn(".github/doc-sync-marker", declared)
        self.assertIn(".github/doc-sync/installed-version", declared)
        self.assertIn(".github/doc-sync/audit-scope.json", declared)
        self.assertIn(".github/doc-sync/engine", declared)
        self.assertIn(".doc-lifecycle/state/sync-marker", declared)
        self.assertIn(".doc-lifecycle/audit-scope.json", declared)
        self.assertIn(".doc-lifecycle/wiring/engine", declared)

    def test_a_second_run_is_a_routine_upgrade(self):
        repo, _ = self.relocate()
        r = run(self.plugin_root, repo, "0.37.0")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertNotIn("relocated the install", r.stdout)
        self.assertEqual((repo / ".doc-lifecycle/audit-scope.json").read_text(),
                         AUDIT_SCOPE)
        self.assertEqual(
            (repo / ".doc-lifecycle/state/sync-marker").read_text(), MARKER)

    # --- refuses rather than guesses ----------------------------------------

    def test_both_layouts_present_is_refused(self):
        pr = make_plugin_root(self.base)
        repo = make_legacy_install(self.base, registry=True)
        (repo / ".doc-lifecycle" / "wiring").mkdir(parents=True)
        r = run(pr, repo, "0.36.0")
        self.assertEqual(r.returncode, 1)
        self.assertIn("both layouts", r.stderr)
        # Nothing moved: a refusal is not a half-relocation.
        self.assertTrue((repo / ".github/doc-sync/installed-version").is_file())

    def test_a_judgment_file_standing_at_both_addresses_is_refused(self):
        # The destructive shape: carrying will not write over what is already
        # there, so without this refusal the old copy would be deleted without
        # ever having been read. Which one holds the consumer's decisions is
        # not knowable from the filesystem.
        for name in ("audit-scope.json", "drift-waivers.json",
                     "evidence-tools.json", "auto-apply-policy.json"):
            with self.subTest(name=name):
                base = self.base / f"collide-{name}"
                pr = make_plugin_root(base)
                repo = make_legacy_install(base, registry=True)
                kept = '{"mine": true}\n'
                (repo / ".doc-lifecycle" / name).write_text(kept)
                r = run(pr, repo, "0.36.0")
                self.assertEqual(r.returncode, 1, r.stdout)
                self.assertIn(name, r.stderr)
                self.assertIn("both exist", r.stderr)
                # Neither copy was touched.
                self.assertEqual((repo / ".doc-lifecycle" / name).read_text(),
                                 kept)
                self.assertTrue((repo / ".github/doc-sync" / name).is_file())

    def test_a_marker_standing_at_both_addresses_is_refused(self):
        pr = make_plugin_root(self.base)
        repo = make_legacy_install(self.base, registry=True)
        state = repo / ".doc-lifecycle" / "state"
        state.mkdir(parents=True)
        (state / "sync-marker").write_text("newer\n")
        r = run(pr, repo, "0.36.0")
        self.assertEqual(r.returncode, 1, r.stdout)
        self.assertIn("sync-marker", r.stderr)
        self.assertEqual((repo / ".github/doc-sync-marker").read_text(), MARKER)

    def test_a_py_name_the_path_authority_would_refuse_is_left_alone(self):
        # apply-upgrade and stage-upgrade must agree on what counts as a
        # vendored script. A name only one of them admits would be removed here
        # and then rejected there, stranding the install.
        repo, r = self.relocate(extras=[("render.v2.py", "# theirs\n")])
        self.assertTrue((repo / ".github/doc-sync/render.v2.py").is_file())
        self.assertIn(".github/doc-sync/render.v2.py", r.stderr)

    def test_a_half_relocated_install_is_refused(self):
        pr = make_plugin_root(self.base)
        repo = make_install(self.base, registry=True)
        (repo / ".doc-lifecycle/installed-version").unlink()
        r = run(pr, repo, "0.36.0")
        self.assertEqual(r.returncode, 1)
        self.assertIn("stopped partway", r.stderr)

    def test_a_modified_vendored_script_is_not_a_refusal(self):
        # A consumer on an older version legitimately has different bytes
        # there, and the contract overwrites them anyway.
        pr = make_plugin_root(self.base)
        repo = make_legacy_install(self.base, registry=True)
        (repo / ".github/doc-sync/render-report.py").write_text("# hand-edited\n")
        r = run(pr, repo, "0.36.0")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(
            (repo / ".doc-lifecycle/wiring/render-report.py").read_text(),
            "# render-report.py @ NEW\n")

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
        (pr / "skills/scheduling-doc-sync/scripts/stage-upgrade.py").unlink()
        repo = make_install(self.base)
        r = run(pr, repo, "0.9.4")
        self.assertEqual(r.returncode, 1)
        self.assertIn("stage-upgrade.py", r.stderr)


if __name__ == "__main__":
    unittest.main(verbosity=2)
