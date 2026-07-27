"""The migration door's command seam: `python3 -m doclifecycle migration-*`.

The interactive door is a person at a terminal, so these run the real
subprocess and assert on real exit codes and real stdout — including the
`--registry-only` form, whose whole job is to be redirected into the file the
human then reviews as a diff.
"""

import json
import os
import unittest

from migrate_test import legacy_consumer, tree_digest
from support import RepoTestCase, run_command

from doclifecycle.migrate import draft_registry


class MigrationDraftCommandTest(RepoTestCase):
    def test_prints_the_draft_payload_and_exits_zero(self):
        root = self.repo(legacy_consumer())
        result = run_command("migration-draft", "--repo", root)
        self.assertEqual(result.returncode, 0, result.stderr)
        payload = json.loads(result.stdout)
        self.assertEqual(payload["status"], "ok")
        self.assertEqual(
            [r["glob"] for r in payload["registry"]["rules"]],
            ["README.md", "docs/*.md", "docs/guides/*.md", "docs/plans/*.md"],
        )

    def test_registry_only_prints_the_file_a_human_will_review(self):
        root = self.repo(legacy_consumer())
        result = run_command("migration-draft", "--repo", root, "--registry-only")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout, draft_registry(root).registry_text)

    def test_declared_roots_override_inference(self):
        root = self.repo(legacy_consumer())
        result = run_command("migration-draft", "--repo", root, "--root", "docs")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout)["registry"]["roots"], ["docs"])

    def test_a_repository_with_no_inferable_root_exits_one_and_says_why(self):
        root = self.repo({"src/billing.py": "RATE = 0.02\n"})
        result = run_command("migration-draft", "--repo", root)
        self.assertEqual(result.returncode, 1)
        self.assertIn("migration-no-roots", result.stderr)
        self.assertEqual(json.loads(result.stdout)["status"], "invalid")


    def test_registry_only_prints_nothing_when_the_draft_is_invalid(self):
        root = self.repo({"src/billing.py": "RATE = 0.02\n"})
        result = run_command("migration-draft", "--repo", root, "--registry-only")
        self.assertEqual(result.returncode, 1)
        self.assertEqual(result.stdout, "")
        self.assertIn("migration-no-roots", result.stderr)


class MigrationDryRunCommandTest(RepoTestCase):
    def migrated(self, files=None):
        root = self.repo(files or legacy_consumer())
        draft = draft_registry(root)
        path = os.path.join(root, draft.registry_path)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(draft.registry_text)
        return root

    def test_prints_the_dry_run_payload_and_exits_zero(self):
        root = self.migrated()
        result = run_command("migration-dry-run", "--repo", root)
        self.assertEqual(result.returncode, 0, result.stderr)
        payload = json.loads(result.stdout)
        self.assertEqual(payload["migration"]["from_version"], "0.12.0")
        self.assertEqual(len(payload["obligations"]), 3)
        self.assertEqual(len(payload["waivers"]["rekeyed"]), 1)

    def test_an_unclassified_document_exits_one_and_names_the_path(self):
        root = self.migrated()
        os.makedirs(os.path.join(root, "docs/notes"))
        with open(os.path.join(root, "docs/notes/scratch.md"), "w") as fh:
            fh.write("# Notes\n\nSomething nobody classified.\n")
        result = run_command("migration-dry-run", "--repo", root)
        self.assertEqual(result.returncode, 1)
        self.assertIn("migration-unclassified-document", result.stderr)
        self.assertIn("docs/notes/scratch.md", result.stderr)

    def test_neither_command_writes_to_the_repository(self):
        root = self.migrated()
        before = tree_digest(root)
        run_command("migration-draft", "--repo", root)
        run_command("migration-dry-run", "--repo", root)
        self.assertEqual(tree_digest(root), before)


if __name__ == "__main__":
    unittest.main()
