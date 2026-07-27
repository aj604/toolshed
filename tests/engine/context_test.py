#!/usr/bin/env python3
"""The repository-wide context index (issue #66).

Seam under test: `context.build_context_index()` as a library call, over real
repositories on disk.

Run: python3 tests/engine/context_test.py
"""

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from support import RepoTestCase  # noqa: E402  (also puts the engine on sys.path)

from doclifecycle.context import build_context_index  # noqa: E402
from doclifecycle.results import Invalid  # noqa: E402

REGISTRY = """{
  "schema_version": 1,
  "roots": ["docs"],
  "rules": [
    {"glob": "docs/*.md", "kind": "living"},
    {"glob": "docs/guides/*.md", "kind": "narrative"},
    {"glob": "docs/plans/*.md", "kind": "planning"}
  ]
}
"""

SHARED = "Fee changes require a migration note."


class WhatTheIndexHolds(RepoTestCase):
    def test_it_indexes_every_inventoried_document(self):
        repo = self.repo({
            ".doc-lifecycle/registry.json": REGISTRY,
            "docs/a.md": "# A\n\nAlpha holds.\n",
            "docs/guides/b.md": "# B\n\nBeta holds.\n",
        })

        index = build_context_index(repo)

        self.assertEqual(
            [(d.path, d.kind) for d in index.documents],
            [("docs/a.md", "living"), ("docs/guides/b.md", "narrative")],
        )

    def test_a_unit_carries_its_text_and_capability(self):
        repo = self.repo({
            ".doc-lifecycle/registry.json": REGISTRY,
            "docs/a.md": "# A\n\nAlpha holds.\n",
        })

        index = build_context_index(repo)
        by_text = {u.text: u for u in index.units}

        self.assertTrue(by_text["Alpha holds."].assertion_capable)
        self.assertFalse(by_text["A"].assertion_capable)


class GlobalDuplicateSearch(RepoTestCase):
    def test_one_sentence_in_two_documents_has_two_occurrences(self):
        repo = self.repo({
            ".doc-lifecycle/registry.json": REGISTRY,
            "docs/a.md": f"# A\n\n{SHARED}\n",
            "docs/plans/p.md": f"# P\n\n{SHARED}\n",
        })

        index = build_context_index(repo)
        digest = {u.text: u.digest for u in index.units}[SHARED]

        self.assertEqual(
            [(o.path, o.line) for o in index.occurrences_of(digest)],
            [("docs/a.md", 3), ("docs/plans/p.md", 3)],
        )

    def test_a_sentence_repeated_within_one_document_has_two_occurrences(self):
        # The constraint #63 carried forward: unit identity is content-addressed
        # and a finding's unit group is deduplicated, so N identical sentences
        # digest as one. Occurrence pointers are how a duplication finding says
        # *which* copies it is about.
        repo = self.repo({
            ".doc-lifecycle/registry.json": REGISTRY,
            "docs/a.md": f"# A\n\n{SHARED}\n\nFiller sentence.\n\n{SHARED}\n",
        })

        index = build_context_index(repo)
        digest = {u.text: u.digest for u in index.units}[SHARED]

        self.assertEqual(
            [(o.path, o.line) for o in index.occurrences_of(digest)],
            [("docs/a.md", 3), ("docs/a.md", 7)],
        )

    def test_duplicated_units_lists_only_units_occurring_more_than_once(self):
        repo = self.repo({
            ".doc-lifecycle/registry.json": REGISTRY,
            "docs/a.md": f"# A\n\n{SHARED}\n\nOnly here.\n",
            "docs/plans/p.md": f"# P\n\n{SHARED}\n",
        })

        index = build_context_index(repo)
        texts = {u.digest: u.text for u in index.units}

        self.assertEqual(
            sorted(texts[d] for d in index.duplicated_units()), [SHARED]
        )


class Ownership(RepoTestCase):
    def test_a_living_document_owns_a_claim_a_planning_document_copies(self):
        repo = self.repo({
            ".doc-lifecycle/registry.json": REGISTRY,
            "docs/plans/p.md": f"# P\n\n{SHARED}\n",
            "docs/a.md": f"# A\n\n{SHARED}\n",
        })

        index = build_context_index(repo)
        digest = {u.text: u.digest for u in index.units}[SHARED]

        self.assertEqual(index.owner_of(digest), "docs/a.md")

    def test_a_living_document_owns_a_claim_a_narrative_document_repeats(self):
        repo = self.repo({
            ".doc-lifecycle/registry.json": REGISTRY,
            "docs/guides/b.md": f"# B\n\n{SHARED}\n",
            "docs/z.md": f"# Z\n\n{SHARED}\n",
        })

        index = build_context_index(repo)
        digest = {u.text: u.digest for u in index.units}[SHARED]

        # Kind precedence decides before the path does, so the alphabetically
        # later living document still wins over the narrative one.
        self.assertEqual(index.owner_of(digest), "docs/z.md")

    def test_two_documents_of_one_kind_are_broken_by_path(self):
        repo = self.repo({
            ".doc-lifecycle/registry.json": REGISTRY,
            "docs/z.md": f"# Z\n\n{SHARED}\n",
            "docs/a.md": f"# A\n\n{SHARED}\n",
        })

        index = build_context_index(repo)
        digest = {u.text: u.digest for u in index.units}[SHARED]

        self.assertEqual(index.owner_of(digest), "docs/a.md")


class CoverageGaps(RepoTestCase):
    def test_an_unregistered_document_is_named_as_unexamined(self):
        repo = self.repo({
            ".doc-lifecycle/registry.json": REGISTRY,
            "docs/a.md": "# A\n\nAlpha holds.\n",
            "docs/notes/stray.md": "# Stray\n\nNobody classified this.\n",
        })

        index = build_context_index(repo)

        self.assertEqual(
            [(u.scope, u.code) for u in index.unexamined],
            [("docs/notes/stray.md", "unregistered-document")],
        )

    def test_an_indexable_repository_has_no_gaps(self):
        repo = self.repo({
            ".doc-lifecycle/registry.json": REGISTRY,
            "docs/a.md": "# A\n\nAlpha holds.\n",
        })

        self.assertEqual(build_context_index(repo).unexamined, ())


class Determinism(RepoTestCase):
    def test_the_same_repository_indexes_to_the_same_digest(self):
        files = {
            ".doc-lifecycle/registry.json": REGISTRY,
            "docs/a.md": f"# A\n\n{SHARED}\n",
            "docs/plans/p.md": f"# P\n\n{SHARED}\n",
        }

        first = build_context_index(self.repo(files))
        second = build_context_index(self.repo(files))

        self.assertEqual(first.digest, second.digest)

    def test_moving_a_sentence_to_another_document_re_keys_the_index(self):
        before = build_context_index(self.repo({
            ".doc-lifecycle/registry.json": REGISTRY,
            "docs/a.md": f"# A\n\n{SHARED}\n",
            "docs/plans/p.md": "# P\n\nPlan text.\n",
        }))
        after = build_context_index(self.repo({
            ".doc-lifecycle/registry.json": REGISTRY,
            "docs/a.md": "# A\n\nPlan text.\n",
            "docs/plans/p.md": f"# P\n\n{SHARED}\n",
        }))

        self.assertNotEqual(before.digest, after.digest)


class InvalidRegistry(RepoTestCase):
    def test_an_unparseable_registry_invalidates_the_index(self):
        repo = self.repo({
            ".doc-lifecycle/registry.json": "{ not json",
            "docs/a.md": "# A\n\nAlpha holds.\n",
        })

        self.assertIsInstance(build_context_index(repo), Invalid)


if __name__ == "__main__":
    unittest.main(verbosity=2)
