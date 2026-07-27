#!/usr/bin/env python3
"""Scenario (issue #64): lineage-keyed cache over the acceptance fixture.

The acceptance criterion: changing only source evidence, or only
configuration/ruleset, prevents reuse of prior semantic results. Built on the
same real-git-repository fixture #61 established (extended, per that
fixture's own docstring, by each ticket that needs a scenario against it) —
not a synthetic one-off repo, so a passing test means the cache behaves
correctly against a real inventory, a real registry, and a real commit.

Seams under test: `cache.cache_key`, `cache.put`, and `cache.get` as library
calls, over `tests/engine/acceptance/fixture.py`'s repository.

Run: python3 tests/engine/acceptance/scenario_cache_test.py
"""

import os
import shutil
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import fixture  # noqa: E402  (the acceptance fixture builder)
from support import ENGINE  # noqa: E402  (also puts the engine on sys.path)

import dataclasses  # noqa: E402

from doclifecycle import cache  # noqa: E402
from doclifecycle.digest import sha256_file  # noqa: E402
from doclifecycle.report import current_lineage  # noqa: E402

CONFIG_DIGEST_A = "a" * 64
CONFIG_DIGEST_B = "b" * 64


class LineageCacheOverTheFixture(fixture.AcceptanceFixtureTestCase):
    def cache_dir(self):
        root = tempfile.mkdtemp(prefix="doc-lifecycle-cache-scenario-")
        self.addCleanup(shutil.rmtree, root, ignore_errors=True)
        return root

    def key_for(self, repo, audit_config_digest=CONFIG_DIGEST_A):
        state, problems = current_lineage(repo, audit_config_digest=audit_config_digest)
        self.assertEqual(problems, ())
        document_digest = sha256_file(os.path.join(repo, fixture.LIVING_DOC))
        source_digest = sha256_file(os.path.join(repo, fixture.EVIDENCE_SOURCE))
        return cache.cache_key(document_digest, source_digest, state)

    def test_changing_only_source_evidence_prevents_reuse(self):
        repo = self.build_fixture()
        cache_dir = self.cache_dir()
        key_before = self.key_for(repo)
        cache.put(cache_dir, key_before, {"id": "DRIFT-001", "digest": "a" * 64})
        self.assertTrue(cache.get(cache_dir, key_before, repo_root=repo).hit)

        # The evidence source is not under the registry's declared `docs`
        # root, so editing it changes nothing else lineage tracks: not the
        # inventory (it examines only registered documents), not the
        # registry, and — since this is a working-tree edit, not a commit —
        # not the repository or base commit either. Only the source's own
        # digest moves.
        with open(os.path.join(repo, fixture.EVIDENCE_SOURCE), "a", encoding="utf-8") as fh:
            fh.write("\n# a comment that changes only this file's bytes\n")

        key_after = self.key_for(repo)

        self.assertNotEqual(key_before.source_digest, key_after.source_digest)
        for field in cache.KEY_FIELDS:
            if field != "source_digest":
                with self.subTest(unchanged=field):
                    self.assertEqual(
                        getattr(key_before, field), getattr(key_after, field)
                    )
        result = cache.get(cache_dir, key_after, repo_root=repo)
        self.assertFalse(result.hit)
        self.assertEqual(result.reason, cache.MISS_NOT_FOUND)

    def test_changing_only_configuration_prevents_reuse(self):
        repo = self.build_fixture()
        cache_dir = self.cache_dir()
        key_before = self.key_for(repo, audit_config_digest=CONFIG_DIGEST_A)
        cache.put(cache_dir, key_before, {"id": "DRIFT-001", "digest": "a" * 64})
        self.assertTrue(cache.get(cache_dir, key_before, repo_root=repo).hit)

        # A re-run with a different consumer audit configuration, nothing
        # else about the repository touched at all.
        key_after = self.key_for(repo, audit_config_digest=CONFIG_DIGEST_B)

        self.assertNotEqual(key_before.audit_config_digest, key_after.audit_config_digest)
        result = cache.get(cache_dir, key_after, repo_root=repo)
        self.assertFalse(result.hit)
        self.assertEqual(result.reason, cache.MISS_NOT_FOUND)

    def test_changing_only_the_ruleset_prevents_reuse(self):
        repo = self.build_fixture()
        cache_dir = self.cache_dir()
        key_before = self.key_for(repo)
        cache.put(cache_dir, key_before, {"id": "DRIFT-001", "digest": "a" * 64})
        self.assertTrue(cache.get(cache_dir, key_before, repo_root=repo).hit)

        # A ruleset bump, nothing else about the repository touched.
        key_after = dataclasses.replace(
            key_before, ruleset_version=key_before.ruleset_version + 1
        )

        result = cache.get(cache_dir, key_after, repo_root=repo)
        self.assertFalse(result.hit)
        self.assertEqual(result.reason, cache.MISS_NOT_FOUND)


if __name__ == "__main__":
    unittest.main(verbosity=2)
