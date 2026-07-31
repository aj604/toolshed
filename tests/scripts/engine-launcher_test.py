#!/usr/bin/env python3
"""The checkout launcher stays identical to the engine's module command.

The engine suites test their two public seams: library functions and
`python3 -m doclifecycle`. This repository-level suite owns the extra wrapper
that skills invoke from a plugin checkout without setting PYTHONPATH.

Run: python3 tests/scripts/engine-launcher_test.py
"""

import os
import shutil
import subprocess
import sys
import tempfile
import unittest


ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
ENGINE = os.path.join(ROOT, "plugins", "doc-lifecycle", "engine")
LAUNCHER = os.path.join(ENGINE, "doc-lifecycle.py")
REGISTRY = """{
  "schema_version": 1,
  "roots": ["docs"],
  "rules": [{"glob": "docs/*.md", "kind": "living"}]
}
"""


class ChunkBudgetLauncher(unittest.TestCase):
    def setUp(self):
        self.repo = tempfile.mkdtemp(prefix="engine-launcher-")
        self.addCleanup(shutil.rmtree, self.repo, ignore_errors=True)
        os.makedirs(os.path.join(self.repo, ".doc-lifecycle"))
        os.makedirs(os.path.join(self.repo, "docs"))
        with open(os.path.join(
                self.repo, ".doc-lifecycle", "registry.json",
        ), "w", encoding="utf-8") as handle:
            handle.write(REGISTRY)
        with open(os.path.join(self.repo, "docs", "a.md"),
                  "w", encoding="utf-8") as handle:
            handle.write("# A\n\nAlpha.\n")

    def launcher(self, *argv):
        env = {key: value for key, value in os.environ.items()
               if key != "PYTHONPATH"}
        return subprocess.run(
            [sys.executable, LAUNCHER, *argv],
            capture_output=True, text=True, env=env,
        )

    def module(self, *argv):
        env = dict(os.environ, PYTHONPATH=ENGINE)
        return subprocess.run(
            [sys.executable, "-m", "doclifecycle", *argv],
            capture_output=True, text=True, env=env,
        )

    def test_invalid_chunk_budgets_retain_the_usage_exit(self):
        for flag in ("--max-documents", "--max-units"):
            for value in ("0", "-1", "true", "1.5", "many"):
                with self.subTest(flag=flag, value=value):
                    result = self.launcher(
                        "bloat-plan", "--repo", self.repo, flag, value,
                    )

                    self.assertEqual(result.returncode, 2)
                    self.assertIn("usage:", result.stderr)
                    self.assertIn("must be a positive integer", result.stderr)

    def test_positive_boundary_matches_the_module_command(self):
        argv = (
            "bloat-plan", "--repo", self.repo,
            "--max-documents", "1", "--max-units", "1",
        )

        launcher = self.launcher(*argv)
        module = self.module(*argv)

        self.assertEqual(launcher.returncode, 0, launcher.stderr)
        self.assertEqual(module.returncode, 0, module.stderr)
        self.assertEqual(launcher.stdout, module.stdout)


if __name__ == "__main__":
    unittest.main(verbosity=2)
