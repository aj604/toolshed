#!/usr/bin/env python3
"""Covers the release manifest guard (aj604/toolshed#77).

Two halves. The first builds synthetic repositories in which a suite is
genuinely unwired — a `tests/engine` subdirectory with no `__init__.py`, a
name the discovery pattern misses, a directory no step reaches — and requires
the guard to say so. Those are the guard's mutation tests: a guard that cannot
be made to fail is not a guard. The second runs it against this repository,
which is where it earns its place in CI.

Run: python3 tests/scripts/release-manifest_test.py
"""

import importlib.util
import os
import shutil
import subprocess
import tempfile
import textwrap
import unittest

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
GUARD = os.path.join(ROOT, ".github", "scripts", "release-manifest.py")
RUNNER = os.path.join(ROOT, ".github", "scripts", "run-script-suites.py")


def _load(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


guard = _load(GUARD, "release_manifest")


SUITE = textwrap.dedent("""\
    import unittest


    class ASuite(unittest.TestCase):
        def test_something(self):
            pass


    if __name__ == "__main__":
        unittest.main()
    """)

HELPER = textwrap.dedent("""\
    import unittest


    class SharedBase(unittest.TestCase):
        maxDiff = None
    """)

RELEASE_YML = textwrap.dedent("""\
    name: ci
    jobs:
      ci:
        steps:
          - name: Unit tests
            run: python3 .github/scripts/run-script-suites.py --dir tests/scripts
          - name: Engine tests
            run: python3 -m unittest discover -s tests/engine -p '*_test.py' --verbose
    """)


def release_manifest_disabled_steps():
    """Any discovery step in this repo's release.yml that carries an `if:`."""
    return guard.release_discovery_steps(
        os.path.join(ROOT, ".github", "workflows", "release.yml"))["disabled"]


def _write(root, rel, text):
    path = os.path.join(root, rel)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as handle:
        handle.write(text)
    return path


class SyntheticRepo:
    """A minimal repository shaped like this one: two discovery steps in
    release.yml, the real suite runner, and a tests/ tree."""

    def __init__(self, release_yml=RELEASE_YML):
        self.root = tempfile.mkdtemp(prefix="release-manifest-")
        _write(self.root, ".github/workflows/release.yml", release_yml)
        os.makedirs(os.path.join(self.root, ".github", "scripts"))
        shutil.copy(RUNNER, os.path.join(self.root, ".github", "scripts",
                                         "run-script-suites.py"))
        _write(self.root, "tests/scripts/wired_test.py", SUITE)
        _write(self.root, "tests/engine/wired_test.py", SUITE)

    def write(self, rel, text=SUITE):
        _write(self.root, rel, text)

    def initialize_git(self):
        subprocess.run(["git", "init", "--quiet", self.root], check=True)

    def track(self, *paths):
        subprocess.run(["git", "-C", self.root, "add", *paths], check=True)

    def audit(self):
        # No manifest: these repositories exist to exercise the discovery
        # half. The manifest half has its own cases below.
        return guard.audit(self.root, manifest={})

    def cleanup(self):
        shutil.rmtree(self.root, ignore_errors=True)


class RepositoryCandidatesFollowGitIgnore(unittest.TestCase):
    """The guard judges repository candidates, not every physical file."""

    def setUp(self):
        self.repo = SyntheticRepo()
        self.repo.initialize_git()
        self.addCleanup(self.repo.cleanup)

    def test_an_ignored_nested_worktree_copy_is_not_an_unwired_suite(self):
        self.repo.write(".gitignore", "agent-worktree/\n")
        self.repo.write("agent-worktree/tests/lanes/copied_test.py")
        self.assertEqual([], self.repo.audit().unwired)

    def test_an_untracked_nonignored_orphan_suite_is_still_unwired(self):
        self.repo.write("tests/lanes/orphan_test.py")
        self.assertEqual(["tests/lanes/orphan_test.py"], self.repo.audit().unwired)

    def test_a_tracked_suite_is_still_checked_against_actual_discovery(self):
        self.repo.write("tests/engine/tracked_test.py")
        self.repo.track("tests/engine/tracked_test.py")
        report = self.repo.audit()
        self.assertIn("tests/engine/tracked_test.py", report.gate)
        self.assertEqual([], report.unwired)

    def test_a_vendored_engine_mirror_is_not_an_independent_suite(self):
        self.repo.write(".doc-lifecycle/wiring/engine/copied_test.py")
        self.repo.track(".doc-lifecycle/wiring/engine/copied_test.py")
        self.assertEqual([], self.repo.audit().unwired)

    def test_a_nonignored_malformed_candidate_is_reported(self):
        self.repo.write("tests/lanes/broken.py", BROKEN)
        self.assertEqual(["tests/lanes/broken.py"], self.repo.audit().unreadable)

    def test_a_clean_snapshot_and_ignored_worktree_checkout_agree(self):
        archive = SyntheticRepo()
        self.addCleanup(archive.cleanup)
        self.repo.write(".gitignore", "agent-worktree/\n")
        self.repo.write("agent-worktree/tests/lanes/copied_test.py")
        self.assertEqual(archive.audit().render(), self.repo.audit().render())


class AnUnwiredSuiteIsCaught(unittest.TestCase):
    """The guard's mutation tests: each of these repositories is green under
    ordinary discovery and wrong."""

    def setUp(self):
        self.repo = SyntheticRepo()
        self.addCleanup(self.repo.cleanup)

    def test_a_wired_tree_reports_nothing_unwired(self):
        self.assertEqual([], self.repo.audit().unwired)

    def test_an_engine_subdirectory_without_init_is_unwired(self):
        self.repo.write("tests/engine/lane/new_test.py")
        self.assertEqual(["tests/engine/lane/new_test.py"],
                         self.repo.audit().unwired)

    def test_the_same_subdirectory_with_init_is_wired(self):
        self.repo.write("tests/engine/lane/__init__.py", "")
        self.repo.write("tests/engine/lane/new_test.py")
        self.assertEqual([], self.repo.audit().unwired)

    def test_a_suite_the_discovery_pattern_misses_is_unwired(self):
        self.repo.write("tests/scripts/test_new.py")
        self.assertEqual(["tests/scripts/test_new.py"],
                         self.repo.audit().unwired)

    def test_a_suite_in_a_directory_no_step_reaches_is_unwired(self):
        self.repo.write("tests/lanes/new_test.py")
        self.assertEqual(["tests/lanes/new_test.py"],
                         self.repo.audit().unwired)

    def test_a_narrowed_pattern_in_release_yml_unwires_what_it_drops(self):
        narrowed = RELEASE_YML.replace("-p '*_test.py'", "-p 'scenario_*_test.py'")
        repo = SyntheticRepo(release_yml=narrowed)
        self.addCleanup(repo.cleanup)
        self.assertEqual(["tests/engine/wired_test.py"], repo.audit().unwired)

    def test_a_deleted_discovery_step_is_reported(self):
        without = "\n".join(
            line for line in RELEASE_YML.splitlines()
            if "run-script-suites" not in line and "Unit tests" not in line)
        repo = SyntheticRepo(release_yml=without + "\n")
        self.addCleanup(repo.cleanup)
        report = repo.audit()
        self.assertIn("run-script-suites.py", " ".join(report.missing_steps))
        self.assertIn("tests/scripts/wired_test.py", report.unwired)

    def test_a_helper_with_no_test_methods_is_not_a_suite(self):
        self.repo.write("tests/engine/support.py", HELPER)
        self.assertEqual([], self.repo.audit().unwired)

    def test_a_suite_named_without_the_test_suffix_is_still_a_suite(self):
        """Detection is structural, not name-based — otherwise the rename
        that hides a suite from discovery also hides it from the guard."""
        self.repo.write("tests/engine/lane/checks.py")
        self.assertEqual(["tests/engine/lane/checks.py"],
                         self.repo.audit().unwired)


class NonGateRootsAreExempt(unittest.TestCase):
    """RED/GREEN skill baselines are retained as methodology, not gate
    suites (#77's fifth criterion)."""

    def setUp(self):
        self.repo = SyntheticRepo()
        self.addCleanup(self.repo.cleanup)

    def test_a_suite_under_a_non_gate_root_is_not_required_to_be_wired(self):
        self.repo.write("tests/baselines/lane-red/probe_test.py")
        self.assertEqual([], self.repo.audit().unwired)

    def test_a_fixture_repositorys_own_tests_are_not_required_to_be_wired(self):
        self.repo.write("tests/fixtures/sample/thing_test.py")
        self.assertEqual([], self.repo.audit().unwired)


NO_MAIN_GUARD = textwrap.dedent("""\
    import unittest


    class ASuite(unittest.TestCase):
        def test_something(self):
            pass
    """)

BROKEN = "import unittest\n\nclass ASuite(unittest.TestCase)\n    pass\n"

LOCAL_MAIN_GUARD = textwrap.dedent("""\
    import unittest


    class ASuite(unittest.TestCase):
        def test_something(self):
            pass


    def main():
        print("looks legit, runs no tests")


    if __name__ == "__main__":
        main()
    """)

DOTTED_UNITTEST_IMPORT = textwrap.dedent("""\
    import unittest.mock


    class ASuite(unittest.TestCase):
        def test_something(self):
            pass


    if __name__ == "__main__":
        unittest.main()
    """)

WRAPPER_MAIN_GUARD = textwrap.dedent("""\
    import unittest


    class ASuite(unittest.TestCase):
        def test_something(self):
            pass


    def main():
        unittest.main()


    if __name__ == "__main__":
        main()
    """)


class HolesAnIndependentReviewFound(unittest.TestCase):
    """Each of these is a suite the release gate does not really run, that an
    earlier version of this guard reported as wired."""

    def setUp(self):
        self.repo = SyntheticRepo()
        self.addCleanup(self.repo.cleanup)

    def test_a_script_suite_with_no_main_guard_is_inert(self):
        """`run-script-suites.py` runs each suite as `python3 <path>`, so a
        suite that never calls unittest.main() runs zero tests and reports
        PASS — discovered, counted, and inert."""
        self.repo.write("tests/scripts/quiet_test.py", NO_MAIN_GUARD)
        self.assertEqual(["tests/scripts/quiet_test.py"],
                         self.repo.audit().inert)

    def test_a_script_suite_with_a_main_guard_is_not_inert(self):
        self.assertEqual([], self.repo.audit().inert)

    def test_a_main_guard_calling_an_unrelated_local_main_is_inert(self):
        """A __main__ block that calls a local no-op `main()` instead of
        `unittest.main()` also runs zero tests under `python3 <path>` — the
        guard must require the call resolve to unittest.main, not just any
        function literally named main."""
        self.repo.write("tests/scripts/quiet_test.py", LOCAL_MAIN_GUARD)
        self.assertEqual(["tests/scripts/quiet_test.py"],
                         self.repo.audit().inert)

    def test_a_dotted_unittest_import_still_recognizes_unittest_main(self):
        """`import unittest.mock` binds the top-level name `unittest` too
        (Python's `import a.b` binds `a`), so `unittest.main()` still runs
        the tests. The guard must not report this suite inert just because
        its only unittest import is dotted."""
        self.repo.write("tests/scripts/quiet_test.py", DOTTED_UNITTEST_IMPORT)
        self.assertEqual([], self.repo.audit().inert)

    def test_a_local_wrapper_delegating_to_unittest_main_is_not_inert(self):
        """A module-level `main()` that itself calls `unittest.main()` (setup
        before delegating) genuinely runs the tests — the guard must resolve
        one level of local-function indirection, not just the guard body."""
        self.repo.write("tests/scripts/quiet_test.py", WRAPPER_MAIN_GUARD)
        self.assertEqual([], self.repo.audit().inert)

    def test_an_engine_suite_needs_no_main_guard(self):
        """The engine suites are run by discovery, not by path."""
        self.repo.write("tests/engine/quiet_test.py", NO_MAIN_GUARD)
        report = self.repo.audit()
        self.assertEqual([], report.inert)
        self.assertEqual([], report.unwired)

    def test_a_suite_that_does_not_parse_is_reported_not_ignored(self):
        """A SyntaxError used to make a file silently 'not a suite', which
        hides it from the guard exactly when it is most broken."""
        self.repo.write("tests/scripts/broken_test.py", BROKEN)
        self.assertEqual(["tests/scripts/broken_test.py"],
                         self.repo.audit().unreadable)

    def test_a_suite_outside_tests_is_still_a_suite(self):
        self.repo.write(".github/scripts/gap_test.py")
        self.assertEqual([".github/scripts/gap_test.py"],
                         self.repo.audit().unwired)

    def test_a_discovery_step_switched_off_is_reported(self):
        """The guard reads command text, so a step gated `if: false` would
        otherwise still count as running."""
        disabled = RELEASE_YML.replace(
            "      - name: Engine tests\n",
            "      - name: Engine tests\n        if: false\n")
        self.assertIn("if: false", disabled, "the mutation did not apply")
        repo = SyntheticRepo(release_yml=disabled)
        self.addCleanup(repo.cleanup)
        report = repo.audit()
        self.assertTrue(
            any("Engine tests" in step or "unittest" in step
                for step in report.missing_steps),
            f"a disabled discovery step was not reported: {report.missing_steps}")

    def test_every_hole_fails_the_run(self):
        self.repo.write("tests/scripts/quiet_test.py", NO_MAIN_GUARD)
        self.assertFalse(self.repo.audit().ok)


class TheManifestNamesTheGateCriteria(unittest.TestCase):

    def test_a_manifest_suite_that_vanished_is_reported(self):
        repo = SyntheticRepo()
        self.addCleanup(repo.cleanup)
        report = guard.audit(repo.root,
                             manifest={"equivalence": ["tests/scripts/gone_test.py"]})
        self.assertEqual([("equivalence", "tests/scripts/gone_test.py")],
                         report.manifest_missing)

    def test_a_manifest_suite_that_exists_and_is_wired_is_not_reported(self):
        repo = SyntheticRepo()
        self.addCleanup(repo.cleanup)
        report = guard.audit(repo.root,
                             manifest={"equivalence": ["tests/scripts/wired_test.py"]})
        self.assertEqual([], report.manifest_missing)

    def test_a_manifest_suite_that_exists_but_is_unwired_is_reported(self):
        repo = SyntheticRepo()
        self.addCleanup(repo.cleanup)
        repo.write("tests/lanes/orphan_test.py")
        report = guard.audit(repo.root,
                             manifest={"equivalence": ["tests/lanes/orphan_test.py"]})
        self.assertEqual([("equivalence", "tests/lanes/orphan_test.py")],
                         report.manifest_missing)


class TheExitStatusSaysWhichWay(unittest.TestCase):

    def test_a_clean_repository_passes(self):
        repo = SyntheticRepo()
        self.addCleanup(repo.cleanup)
        self.assertTrue(repo.audit().ok)

    def test_an_unwired_suite_fails(self):
        repo = SyntheticRepo()
        self.addCleanup(repo.cleanup)
        repo.write("tests/engine/lane/new_test.py")
        self.assertFalse(repo.audit().ok)


class ThisRepositoryPassesTheGuard(unittest.TestCase):
    """Where the guard earns its place in CI."""

    @classmethod
    def setUpClass(cls):
        cls.report = guard.audit(ROOT)

    def test_every_suite_in_the_tree_is_run_by_the_release_pipeline(self):
        self.assertEqual(
            [], self.report.unwired,
            "these suites exist but no release.yml discovery step runs them: "
            f"{self.report.unwired}")

    def test_release_yml_still_runs_both_discovery_steps(self):
        self.assertEqual([], self.report.missing_steps)

    def test_every_gate_criterion_still_has_its_suites(self):
        self.assertEqual([], self.report.manifest_missing)

    def test_discovery_loads_every_suite_it_finds(self):
        self.assertEqual([], self.report.broken)

    def test_no_baseline_or_fixture_is_swept_into_the_gate(self):
        self.assertEqual([], self.report.swept)

    def test_no_suite_is_run_by_path_without_a_main_guard(self):
        self.assertEqual(
            [], self.report.inert,
            "these run as `python3 <path>` and never call unittest.main(), "
            f"so they run zero tests and pass: {self.report.inert}")

    def test_every_python_file_in_the_gate_roots_parses(self):
        self.assertEqual([], self.report.unreadable)

    def test_no_discovery_step_is_gated_off(self):
        self.assertEqual([], release_manifest_disabled_steps())


if __name__ == "__main__":
    unittest.main(verbosity=2)
