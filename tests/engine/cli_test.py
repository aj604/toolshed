#!/usr/bin/env python3
"""Tests for the engine's `python3 -m doclifecycle` entrypoints.

Seam: the command as a subprocess — real argv, real exit codes, real stdout.
The contract under test is that the command is a *thin* wrapper: its payload is
exactly the library result, so an interactive import and a CI command cannot
disagree.

Run: python3 tests/engine/cli_test.py
"""

import json
import os
import subprocess
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from support import ENGINE, RepoTestCase  # noqa: E402

from doclifecycle.inventory import build_inventory  # noqa: E402

REGISTRY = json.dumps({
    "schema_version": 1,
    "roots": ["docs"],
    "sets": ["adr"],
    "rules": [
        {"glob": "docs/**/*.md", "kind": "living"},
        {"glob": "docs/adr/*.md", "kind": "narrative", "set": "adr"},
    ],
})


def run(*argv, cwd=None):
    env = dict(os.environ, PYTHONPATH=ENGINE)
    return subprocess.run(
        [sys.executable, "-m", "doclifecycle", *argv],
        capture_output=True, text=True, env=env, cwd=cwd,
    )


class InventoryCommand(RepoTestCase):
    def test_payload_is_exactly_the_library_result(self):
        repo = self.repo({
            ".doc-lifecycle/registry.json": REGISTRY,
            "docs/adr/0001-use-json.md": "# ADR 1\n",
            "docs/architecture.md": "# Architecture\n",
            "docs/stray.md": "# Stray\n",
        })

        result = run("inventory", "--repo", repo)

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(
            json.loads(result.stdout), build_inventory(repo).to_dict()
        )

    def test_payload_shape(self):
        repo = self.repo({
            ".doc-lifecycle/registry.json": json.dumps({
                "schema_version": 1,
                "roots": ["docs"],
                "rules": [{"glob": "docs/*.md", "kind": "living"}],
            }),
            "docs/architecture.md": "# Architecture\n",
        })

        payload = json.loads(run("inventory", "--repo", repo).stdout)

        self.assertEqual(payload, {
            "status": "ok",
            "schema_version": 1,
            "registry": {
                "path": ".doc-lifecycle/registry.json",
                "digest": payload["registry"]["digest"],
            },
            "digest": payload["digest"],
            "documents": [{
                "path": "docs/architecture.md",
                "kind": "living",
                "set": None,
                "rule": "docs/*.md",
                "digest": (
                    "2e7cb38229f7877e569cc05dd9c8fb71b30954ad2c9978328d69f5d377f81505"
                ),
            }],
            "findings": [],
        })

    def test_defaults_to_the_current_directory(self):
        repo = self.repo({
            ".doc-lifecycle/registry.json": REGISTRY,
            "docs/architecture.md": "# Architecture\n",
        })

        result = run("inventory", cwd=repo)

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(
            [d["path"] for d in json.loads(result.stdout)["documents"]],
            ["docs/architecture.md"],
        )

    def test_registry_path_is_overridable(self):
        repo = self.repo({
            "config/registry.json": REGISTRY,
            "docs/architecture.md": "# Architecture\n",
        })

        result = run(
            "inventory", "--repo", repo, "--registry", "config/registry.json"
        )

        self.assertEqual(result.returncode, 0, result.stderr)
        payload = json.loads(result.stdout)
        self.assertEqual(payload["registry"]["path"], "config/registry.json")
        self.assertEqual(
            payload, build_inventory(repo, "config/registry.json").to_dict()
        )

    def test_closed_world_finding_is_visible_in_the_payload(self):
        repo = self.repo({
            ".doc-lifecycle/registry.json": json.dumps({
                "schema_version": 1,
                "roots": ["docs"],
                "rules": [{"glob": "docs/guides/*.md", "kind": "narrative"}],
            }),
            "docs/guides/onboarding.md": "# Onboarding\n",
            "docs/stray.md": "# Stray\n",
        })

        result = run("inventory", "--repo", repo)

        # Findings are data, not a gate: the inventory built, so exit 0.
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(
            [(f["code"], f["path"]) for f in json.loads(result.stdout)["findings"]],
            [("unregistered-document", "docs/stray.md")],
        )


class Launcher(RepoTestCase):
    """A skill or workflow invoking the engine from a plugin checkout has no
    PYTHONPATH to set: the launcher script beside the package is the entrypoint."""

    SCRIPT = os.path.join(ENGINE, "doc-lifecycle.py")

    def test_runs_without_pythonpath_and_agrees_with_the_library(self):
        repo = self.repo({
            ".doc-lifecycle/registry.json": REGISTRY,
            "docs/architecture.md": "# Architecture\n",
        })
        env = {k: v for k, v in os.environ.items() if k != "PYTHONPATH"}

        result = subprocess.run(
            [sys.executable, self.SCRIPT, "inventory", "--repo", repo],
            capture_output=True, text=True, env=env,
        )

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout), build_inventory(repo).to_dict())

    def test_reports_an_invalid_run_the_same_way(self):
        repo = self.repo({".doc-lifecycle/registry.json": "{ not json"})
        env = {k: v for k, v in os.environ.items() if k != "PYTHONPATH"}

        result = subprocess.run(
            [sys.executable, self.SCRIPT, "inventory", "--repo", repo],
            capture_output=True, text=True, env=env,
        )

        self.assertEqual(result.returncode, 1)
        self.assertIn("registry-unparseable", result.stderr)


class InvalidRuns(RepoTestCase):
    def test_invalid_registry_exits_one_with_typed_problems(self):
        repo = self.repo({
            ".doc-lifecycle/registry.json": "{ not json",
            "docs/architecture.md": "# Architecture\n",
        })

        result = run("inventory", "--repo", repo)

        self.assertEqual(result.returncode, 1)
        payload = json.loads(result.stdout)
        self.assertEqual(payload["status"], "invalid")
        self.assertEqual([p["code"] for p in payload["problems"]], ["registry-unparseable"])
        self.assertNotIn("documents", payload)
        self.assertEqual(payload, build_inventory(repo).to_dict())

    def test_invalid_run_explains_itself_on_stderr(self):
        # The run surface (CI log, terminal) states the outcome and its reason;
        # a reader must not have to parse the JSON to learn why it failed.
        repo = self.repo({"docs/architecture.md": "# Architecture\n"})

        result = run("inventory", "--repo", repo)

        self.assertEqual(result.returncode, 1)
        self.assertIn("registry-missing", result.stderr)
        self.assertIn(".doc-lifecycle/registry.json", result.stderr)

    def test_unknown_subcommand_is_a_usage_error(self):
        result = run("audit")

        self.assertEqual(result.returncode, 2)
        self.assertEqual(result.stdout, "")

    def test_no_subcommand_is_a_usage_error(self):
        result = run()

        self.assertEqual(result.returncode, 2)


if __name__ == "__main__":
    unittest.main(verbosity=2)
