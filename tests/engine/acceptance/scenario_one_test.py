#!/usr/bin/env python3
"""Scenario one (issue #61): inventory over the acceptance fixture.

Seams under test, per the engine's convention (`plugins/doc-lifecycle/engine/
README.md`): `build_inventory()` as a library call, and `python3 -m
doclifecycle` as a subprocess, over a REAL temporary git repository — no
mocked git, no mocked filesystem. This is the first slice of the deterministic
release gate the #57 re-architecture demos and gates through; later tickets
(#65 drift, #66 bloat, #67 path authorization) add their own scenarios against
the same fixture.

Run: python3 tests/engine/acceptance/scenario_one_test.py
"""

import json
import os
import subprocess
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import fixture  # noqa: E402  (the acceptance fixture builder)
from support import ENGINE  # noqa: E402  (also puts the engine on sys.path)

from doclifecycle.inventory import build_inventory  # noqa: E402


def run_cli(*argv, cwd=None):
    env = dict(os.environ, PYTHONPATH=ENGINE)
    return subprocess.run(
        [sys.executable, "-m", "doclifecycle", *argv],
        capture_output=True, text=True, env=env, cwd=cwd,
    )


class FixtureIsARealGitRepo(fixture.AcceptanceFixtureTestCase):
    """The acceptance criterion that the fixture is real git, not a stand-in:
    a bare temp-dir-of-files would pass every assertion in the other classes
    below identically, so this checks the thing they can't. This verifies the
    fixture builder itself (via `git` directly) rather than `doclifecycle` —
    it is not a third engine seam alongside `build_inventory()` and `python3
    -m doclifecycle`; every assertion about the engine's own behavior below
    still goes through only those two."""

    def test_fixture_root_is_a_real_git_working_tree(self):
        repo = self.build_fixture()

        result = subprocess.run(
            ["git", "rev-parse", "--is-inside-work-tree"],
            cwd=repo, capture_output=True, text=True,
        )

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.strip(), "true")

    def test_fixture_has_two_commits_and_a_clean_working_tree(self):
        repo = self.build_fixture()

        log = subprocess.run(
            ["git", "log", "--oneline"], cwd=repo,
            capture_output=True, text=True, check=True,
        )
        status = subprocess.run(
            ["git", "status", "--porcelain"], cwd=repo,
            capture_output=True, text=True, check=True,
        )

        self.assertEqual(len(log.stdout.strip().splitlines()), 2)
        self.assertEqual(status.stdout, "")

    def test_evidence_source_changed_between_the_two_commits(self):
        repo = self.build_fixture()

        first_commit = subprocess.run(
            ["git", "rev-list", "--max-parents=0", "HEAD"],
            cwd=repo, capture_output=True, text=True, check=True,
        ).stdout.strip()
        original = subprocess.run(
            ["git", "show", f"{first_commit}:{fixture.EVIDENCE_SOURCE}"],
            cwd=repo, capture_output=True, text=True, check=True,
        ).stdout
        with open(os.path.join(repo, fixture.EVIDENCE_SOURCE), encoding="utf-8") as fh:
            current = fh.read()

        self.assertNotEqual(original, current)
        self.assertIn("FLAT_FEE_RATE = 0.02\n", original)
        self.assertIn("FLAT_FEE_RATE = 0.025\n", current)


class InventoryOverTheFixture(fixture.AcceptanceFixtureTestCase):
    def test_classifies_every_document_kind(self):
        repo = self.build_fixture()

        result = build_inventory(repo)

        self.assertEqual(result.status, "ok")
        by_path = {d.path: d for d in result.documents}
        self.assertEqual(by_path[fixture.LIVING_DOC].kind, "living")
        self.assertEqual(by_path[fixture.NARRATIVE_DOC].kind, "narrative")
        self.assertEqual(by_path[fixture.PLANNING_DOC].kind, "planning")

    def test_excluded_subtree_is_neither_inventoried_nor_a_finding(self):
        repo = self.build_fixture()

        result = build_inventory(repo)

        paths = {d.path for d in result.documents}
        finding_paths = {f.path for f in result.findings}
        self.assertNotIn(fixture.EXCLUDED_DOC, paths)
        self.assertNotIn(fixture.EXCLUDED_DOC, finding_paths)

    def test_unregistered_document_is_the_closed_world_finding(self):
        repo = self.build_fixture()

        result = build_inventory(repo)

        self.assertEqual(
            [(f.code, f.path) for f in result.findings if f.path == fixture.STRAY_DOC],
            [("unregistered-document", fixture.STRAY_DOC)],
        )

    def test_hostile_filenames_are_classified_like_any_other_document(self):
        repo = self.build_fixture()

        result = build_inventory(repo)

        by_path = {d.path: d for d in result.documents}
        for hostile_path in fixture.HOSTILE_DOCS:
            with self.subTest(hostile_path):
                self.assertIn(hostile_path, by_path)
                self.assertEqual(by_path[hostile_path].kind, "living")

    def test_symlink_and_traversal_attempts_are_findings_never_documents(self):
        repo = self.build_fixture()

        result = build_inventory(repo)

        paths = {d.path for d in result.documents}
        findings_by_path = {f.path: f.code for f in result.findings}
        for symlink_path in fixture.SYMLINK_PATHS:
            with self.subTest(symlink_path):
                self.assertNotIn(symlink_path, paths)
                self.assertEqual(findings_by_path.get(symlink_path), "symlinked-path")

    def test_symlinked_directory_contents_are_never_walked(self):
        # docs/escape-dir -> /etc: if the walker ever followed it, /etc's
        # contents would show up as further findings or documents under that
        # path. It must not.
        repo = self.build_fixture()

        result = build_inventory(repo)

        prefix = fixture.SYMLINK_DIR + "/"
        self.assertFalse(any(d.path.startswith(prefix) for d in result.documents))
        self.assertFalse(any(f.path.startswith(prefix) for f in result.findings))

    def test_prompt_injection_content_is_present_but_inert_to_the_engine(self):
        # The fixture plants prompt injection in a doc and in source; the
        # inventory command has no model in its loop, so the correct outcome
        # is simply that it classifies these files like any other and never
        # acts on their content. Full "does a model obey this" coverage is a
        # later ticket's (#65/#66) job.
        repo = self.build_fixture()
        with open(os.path.join(repo, fixture.LIVING_DOC), encoding="utf-8") as fh:
            living_text = fh.read()
        with open(os.path.join(repo, fixture.EVIDENCE_SOURCE), encoding="utf-8") as fh:
            source_text = fh.read()

        result = build_inventory(repo)

        self.assertIn("SYSTEM:", living_text)
        self.assertIn("SYSTEM NOTE:", source_text)
        # Inert: the excluded doc the injection tells a reader to delete is
        # still on disk, and the run still completed normally.
        self.assertTrue(os.path.exists(os.path.join(repo, fixture.EXCLUDED_DOC)))
        self.assertEqual(result.status, "ok")

    def test_consumer_waiver_marker_and_recurrence_state_are_present(self):
        repo = self.build_fixture()

        with open(os.path.join(repo, fixture.MARKER_PATH), encoding="utf-8") as fh:
            marker = fh.read().strip()
        with open(os.path.join(repo, fixture.WAIVERS_PATH), encoding="utf-8") as fh:
            waivers = json.load(fh)
        with open(os.path.join(repo, fixture.PREV_STALE_PATH), encoding="utf-8") as fh:
            prev_stale = json.load(fh)

        self.assertRegex(marker, r"^[0-9a-f]{40}$")
        self.assertEqual(
            waivers["waivers"][0]["file"], fixture.LIVING_DOC
        )
        self.assertEqual(prev_stale["stales"][0]["file"], fixture.LIVING_DOC)


class InventoryCommandAgreesWithTheLibrary(fixture.AcceptanceFixtureTestCase):
    """The engine's cross-cutting contract — library call and `python3 -m
    doclifecycle` cannot disagree — held over the acceptance fixture rather
    than a synthetic one-off repo."""

    def test_cli_payload_equals_the_library_result(self):
        repo = self.build_fixture()

        result = run_cli("inventory", "--repo", repo)

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(
            json.loads(result.stdout), build_inventory(repo).to_dict()
        )

    def test_cli_closed_world_finding_is_visible_in_the_payload(self):
        repo = self.build_fixture()

        result = run_cli("inventory", "--repo", repo)

        payload = json.loads(result.stdout)
        self.assertIn(
            fixture.STRAY_DOC,
            [f["path"] for f in payload["findings"] if f["code"] == "unregistered-document"],
        )


if __name__ == "__main__":
    unittest.main(verbosity=2)
