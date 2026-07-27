#!/usr/bin/env python3
"""The command half of the segmenter contract.

Seam: `python3 -m doclifecycle segment` as a subprocess. The command must hand
back exactly what `segment_document` returns — a command and an import cannot
disagree — and two fresh interpreters must agree byte for byte, which is the
determinism criterion held across process boundaries rather than within one.

Run: python3 tests/engine/segment_cli_test.py
"""

import json
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from support import RepoTestCase, run_command  # noqa: E402

from doclifecycle.segment import segment_document  # noqa: E402

REGISTRY = json.dumps({
    "schema_version": 1,
    "roots": ["docs"],
    "rules": [{"glob": "docs/**/*.md", "kind": "living"}],
})

FILES = {
    ".doc-lifecycle/registry.json": REGISTRY,
    "docs/architecture.md": (
        "# Architecture\n\n"
        "The service charges a flat 2% fee. Refunds take a week.\n\n"
        "- Deploys run nightly.\n"
    ),
}


class SegmentCommand(RepoTestCase):
    def test_payload_equals_the_library_result(self):
        repo = self.repo(FILES)

        result = run_command("segment", "--repo", repo, "--path",
                             "docs/architecture.md")

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(
            json.loads(result.stdout),
            segment_document(repo, "docs/architecture.md").to_dict(),
        )

    def test_two_fresh_interpreters_produce_identical_bytes(self):
        repo = self.repo(FILES)

        first = run_command("segment", "--repo", repo, "--path",
                            "docs/architecture.md")
        second = run_command("segment", "--repo", repo, "--path",
                             "docs/architecture.md")

        self.assertEqual(first.stdout, second.stdout)

    def test_an_uninventoried_document_exits_one_and_says_why(self):
        repo = self.repo(FILES)

        result = run_command("segment", "--repo", repo, "--path", "docs/gone.md")

        self.assertEqual(result.returncode, 1)
        self.assertEqual(json.loads(result.stdout)["status"], "invalid")
        self.assertIn("document-not-inventoried", result.stderr)

    def test_a_missing_path_is_a_usage_error(self):
        repo = self.repo(FILES)

        result = run_command("segment", "--repo", repo)

        self.assertEqual(result.returncode, 2)


if __name__ == "__main__":
    unittest.main(verbosity=2)
