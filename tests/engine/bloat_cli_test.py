#!/usr/bin/env python3
"""The `context-index` and `bloat-plan` commands (issue #66).

Seam under test: `python3 -m doclifecycle` as a subprocess. Each command must
equal the library result it wraps and add nothing, so an interactive import and
a CI invocation cannot disagree.

Run: python3 tests/engine/bloat_cli_test.py
"""

import json
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from support import (  # noqa: E402  (also puts the engine on sys.path)
    CORPUS_REGISTRY as REGISTRY,
    SHARED_SENTENCE as SHARED,
    RepoTestCase,
    run_command,
)

from doclifecycle import bloat  # noqa: E402
from doclifecycle.context import build_context_index  # noqa: E402




class ContextIndexCommand(RepoTestCase):
    def corpus(self):
        return self.repo({
            ".doc-lifecycle/registry.json": REGISTRY,
            "docs/a.md": f"# A\n\n{SHARED}\n",
            "docs/plans/p.md": f"# P\n\n{SHARED}\n",
        })

    def test_the_command_agrees_with_the_library(self):
        repo = self.corpus()

        result = run_command("context-index", "--repo", repo)

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(
            json.loads(result.stdout), build_context_index(repo).to_dict()
        )

    def test_it_reports_every_occurrence_of_a_duplicated_unit(self):
        repo = self.corpus()

        payload = json.loads(run_command("context-index", "--repo", repo).stdout)

        duplicated = [
            places for places in payload["occurrences"].values() if len(places) > 1
        ]
        self.assertEqual(
            [(p["path"], p["line"]) for p in duplicated[0]],
            [("docs/a.md", 3), ("docs/plans/p.md", 3)],
        )

    def test_an_invalid_registry_exits_one_and_explains_itself(self):
        repo = self.repo({
            ".doc-lifecycle/registry.json": "{ not json",
            "docs/a.md": "# A\n\nAlpha.\n",
        })

        result = run_command("context-index", "--repo", repo)

        self.assertEqual(result.returncode, 1)
        self.assertEqual(json.loads(result.stdout)["status"], "invalid")
        self.assertIn("registry", result.stderr)

    def test_two_runs_produce_byte_identical_output(self):
        repo = self.corpus()

        first = run_command("context-index", "--repo", repo)
        second = run_command("context-index", "--repo", repo)

        self.assertEqual(first.stdout, second.stdout)


class BloatPlanCommand(RepoTestCase):
    def corpus(self):
        return self.repo({
            ".doc-lifecycle/registry.json": REGISTRY,
            "docs/a.md": "# A\n\nAlpha.\n",
            "docs/b.md": "# B\n\nBeta.\n",
            "docs/plans/p.md": "# P\n\nDelta.\n",
        })

    def test_the_command_agrees_with_the_library(self):
        repo = self.corpus()

        result = run_command("bloat-plan", "--repo", repo, "--max-documents", "2")

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(
            json.loads(result.stdout),
            bloat.plan_repository_chunks(repo, max_documents=2).to_dict(),
        )

    def test_every_document_appears_in_exactly_one_chunk(self):
        repo = self.corpus()

        payload = json.loads(
            run_command("bloat-plan", "--repo", repo, "--max-documents", "1").stdout
        )

        placed = [p for c in payload["chunks"] for p in c["documents"]]
        self.assertEqual(
            sorted(placed), ["docs/a.md", "docs/b.md", "docs/plans/p.md"]
        )

    def test_an_invalid_registry_exits_one(self):
        repo = self.repo({
            ".doc-lifecycle/registry.json": "{ not json",
            "docs/a.md": "# A\n\nAlpha.\n",
        })

        result = run_command("bloat-plan", "--repo", repo)

        self.assertEqual(result.returncode, 1)
        self.assertEqual(json.loads(result.stdout)["status"], "invalid")

    def test_a_non_positive_budget_is_a_usage_error(self):
        result = run_command("bloat-plan", "--repo", self.corpus(),
                             "--max-documents", "0")

        self.assertEqual(result.returncode, 2)


if __name__ == "__main__":
    unittest.main(verbosity=2)
