#!/usr/bin/env python3
"""Tests for the lineage-keyed cache (issue #64): key independence,
revalidation on read, and cache-poisoning defenses.

Seam: the library functions `cache_key`, `put`, and `get`. There is no command
for this module — nothing calls it yet (the audit engine, #65/#66, is the
first caller) — so, per the engine's convention, no CLI suite is added at a
seam that does not exist.

Built on real git repositories, like `report_test.py`: staleness is a
comparison against a repository, and a mocked one would prove nothing about
the revalidation this module leans on `report.validate_report` for.

Run: python3 tests/engine/cache_test.py
"""

import dataclasses
import json
import os
import shutil
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from report_test import CONFIG_DIGEST, GitRepoTestCase  # noqa: E402

from doclifecycle import ARTIFACT_SCHEMA_VERSION  # noqa: E402
from doclifecycle import cache  # noqa: E402
from doclifecycle.report import current_lineage  # noqa: E402

DOCUMENT_DIGEST = "d" * 64
SOURCE_DIGEST = "e" * 64


class CacheTestCase(GitRepoTestCase):
    def cache_dir(self):
        root = tempfile.mkdtemp(prefix="doc-lifecycle-cache-")
        self.addCleanup(shutil.rmtree, root, ignore_errors=True)
        return root

    def fresh_key(self, repo, document_digest=DOCUMENT_DIGEST,
                 source_digest=SOURCE_DIGEST, audit_config_digest=CONFIG_DIGEST):
        state, problems = current_lineage(repo, audit_config_digest=audit_config_digest)
        self.assertEqual(problems, ())
        return cache.cache_key(document_digest, source_digest, state)

    def valid_record(self, record_id="R1", digest="a" * 64, **extra):
        return {"id": record_id, "digest": digest, **extra}

    def raw_payload_for(self, key, record, status="findings", incomplete=None,
                        repository=None, evidence_sources=("x",)):
        """Hand-build the same shape `cache.put()` writes, so a test can
        deliberately diverge from what `key` implies (a foreign repository, a
        missing record field, an incomplete scope) without going through the
        module's own writer."""
        return {
            "status": status,
            "schema_version": key.schema_version,
            "lineage": {
                "repository": repository if repository is not None else key.repository,
                "base_commit": key.base_commit,
                "audit_mode": "chunk",
                "inventory_digest": key.inventory_digest,
                "audit_config_digest": key.audit_config_digest,
                "registry_digest": key.registry_digest,
                "ruleset_version": key.ruleset_version,
                "plugin_version": key.plugin_version,
                "evidence_boundary": {
                    "sources": list(evidence_sources), "excluded": [],
                },
            },
            "records": [record] if record is not None else [],
            "incomplete": incomplete or [],
        }

    def write_raw(self, cache_dir, key, payload):
        os.makedirs(cache_dir, exist_ok=True)
        path = cache.entry_path(cache_dir, key)
        with open(path, "w", encoding="utf-8") as fh:
            json.dump(payload, fh)
        return path


class BasicHitsAndMisses(CacheTestCase):
    def test_a_fresh_entry_is_a_hit(self):
        repo = self.git_repo()
        cache_dir = self.cache_dir()
        key = self.fresh_key(repo)
        cache.put(cache_dir, key, self.valid_record())

        result = cache.get(cache_dir, key, repo_root=repo)

        self.assertTrue(result.hit)
        self.assertIsNone(result.reason)
        self.assertEqual(result.record["id"], "R1")

    def test_an_entry_that_was_never_written_is_a_miss(self):
        repo = self.git_repo()
        cache_dir = self.cache_dir()
        key = self.fresh_key(repo)

        result = cache.get(cache_dir, key, repo_root=repo)

        self.assertFalse(result.hit)
        self.assertIsNone(result.record)
        self.assertEqual(result.reason, cache.MISS_NOT_FOUND)

    def test_corrupt_json_at_the_right_path_is_a_miss(self):
        repo = self.git_repo()
        cache_dir = self.cache_dir()
        key = self.fresh_key(repo)
        os.makedirs(cache_dir, exist_ok=True)
        with open(cache.entry_path(cache_dir, key), "w", encoding="utf-8") as fh:
            fh.write("{not json")

        result = cache.get(cache_dir, key, repo_root=repo)

        self.assertFalse(result.hit)
        self.assertEqual(result.reason, cache.MISS_CORRUPT)

    def test_an_entry_that_is_not_utf_8_is_a_miss_rather_than_a_crash(self):
        # Every other corrupt-entry test writes its garbage through
        # `encoding="utf-8"`, so none of them reaches the read itself — they
        # all fail at the parser. Bytes that are not text fail one step
        # earlier, and `UnicodeDecodeError` is a `ValueError`, so the read's
        # `except OSError` never saw it (`digest.py`'s own docstring names
        # this trap). A cache is an optimization: a lookup must be able to
        # answer "no" about any file on disk, because the answer it owes the
        # caller is a re-evaluation, never a traceback out of an audit.
        repo = self.git_repo()
        cache_dir = self.cache_dir()
        key = self.fresh_key(repo)
        os.makedirs(cache_dir, exist_ok=True)
        with open(cache.entry_path(cache_dir, key), "wb") as fh:
            fh.write(b"\xff\xfe{\x00\"id\x00")

        result = cache.get(cache_dir, key, repo_root=repo)

        self.assertFalse(result.hit)
        self.assertIsNone(result.record)
        self.assertEqual(result.reason, cache.MISS_CORRUPT)

    def test_the_stored_record_carries_the_document_and_source_digests(self):
        # put() sets these from the key when the caller's record does not
        # already carry them, since the report contract's lineage has no
        # notion of "one document" — this is what a read's identity check
        # compares against.
        repo = self.git_repo()
        cache_dir = self.cache_dir()
        key = self.fresh_key(repo)
        cache.put(cache_dir, key, self.valid_record())

        result = cache.get(cache_dir, key, repo_root=repo)

        self.assertEqual(result.record["document_digest"], DOCUMENT_DIGEST)
        self.assertEqual(result.record["source_digest"], SOURCE_DIGEST)


class KeyIndependence(CacheTestCase):
    """Every one of the nine inputs the issue names must invalidate the cache
    on its own — proven by writing one entry, then showing that changing
    exactly one field of the key (holding the other eight fixed) is a miss,
    and that the untouched key is still a hit throughout."""

    def test_each_keyed_input_invalidates_the_cache_independently(self):
        repo = self.git_repo()
        cache_dir = self.cache_dir()
        base_key = self.fresh_key(repo)
        cache.put(cache_dir, base_key, self.valid_record())
        self.assertTrue(cache.get(cache_dir, base_key, repo_root=repo).hit)

        mutations = (
            ("document_digest", "f" * 64),
            ("source_digest", "f" * 64),
            ("inventory_digest", "9" * 64),
            ("audit_config_digest", "9" * 64),
            ("registry_digest", "9" * 64),
            ("ruleset_version", base_key.ruleset_version + 1),
            ("schema_version", base_key.schema_version + 1),
            ("plugin_version", "0.0.1-test"),
            ("repository", "origin:github.com/someone/else"),
            ("base_commit", "f" * 40),
        )
        self.assertEqual({m[0] for m in mutations}, set(cache.KEY_FIELDS))

        for field, value in mutations:
            with self.subTest(field=field):
                mutated_key = dataclasses.replace(base_key, **{field: value})

                result = cache.get(cache_dir, mutated_key, repo_root=repo)

                self.assertFalse(result.hit, f"{field} did not invalidate the key")
                self.assertEqual(result.reason, cache.MISS_NOT_FOUND)

        # The original, unmutated key is unaffected by any of the lookups
        # above — each mutation missed because it addressed a different slot,
        # not because the store itself was disturbed.
        self.assertTrue(cache.get(cache_dir, base_key, repo_root=repo).hit)


class CachePoisoning(CacheTestCase):
    """Payloads a legitimate `put()` would never produce, but that could
    reach the cache directory some other way (a corrupted write, a copied
    entry from elsewhere) — every one of these must fail closed as a miss."""

    def test_a_parseable_but_invalid_record_is_a_miss(self):
        repo = self.git_repo()
        cache_dir = self.cache_dir()
        key = self.fresh_key(repo)
        payload = self.raw_payload_for(key, {"id": "R1"})  # no 'digest'
        self.write_raw(cache_dir, key, payload)

        result = cache.get(cache_dir, key, repo_root=repo)

        self.assertFalse(result.hit)
        self.assertEqual(result.reason, cache.MISS_INVALID)

    def test_mismatched_chunk_identity_is_a_miss(self):
        # Everything about the lineage matches, but the record inside
        # declares a different document/source pair than the key it is
        # filed under — a mismatched chunk sitting at the right path.
        repo = self.git_repo()
        cache_dir = self.cache_dir()
        key = self.fresh_key(repo)
        record = self.valid_record(document_digest="f" * 64, source_digest=SOURCE_DIGEST)
        payload = self.raw_payload_for(key, record)
        self.write_raw(cache_dir, key, payload)

        result = cache.get(cache_dir, key, repo_root=repo)

        self.assertFalse(result.hit)
        self.assertEqual(result.reason, cache.MISS_IDENTITY)

    def test_foreign_repository_lineage_is_a_miss(self):
        # Filed at the path this repository's own key hashes to, but the
        # payload declares a different repository entirely.
        repo = self.git_repo()
        cache_dir = self.cache_dir()
        key = self.fresh_key(repo)
        payload = self.raw_payload_for(
            key, self.valid_record(), repository="origin:github.com/foreign/repo",
        )
        self.write_raw(cache_dir, key, payload)

        result = cache.get(cache_dir, key, repo_root=repo)

        self.assertFalse(result.hit)
        self.assertEqual(result.reason, cache.MISS_STALE)

    def test_an_entry_with_more_than_one_record_is_a_miss(self):
        # The report contract itself permits any number of records; a cache
        # entry describing more than one is not a shape this module ever
        # writes, and must not be trusted as "the" cached result for `key`.
        repo = self.git_repo()
        cache_dir = self.cache_dir()
        key = self.fresh_key(repo)
        first = self.valid_record(record_id="R1", digest="a" * 64)
        second = self.valid_record(record_id="R2", digest="b" * 64)
        payload = self.raw_payload_for(key, first)
        payload["records"].append(second)
        self.write_raw(cache_dir, key, payload)

        result = cache.get(cache_dir, key, repo_root=repo)

        self.assertFalse(result.hit)
        self.assertEqual(result.reason, cache.MISS_RECORD_COUNT)

    def test_an_incomplete_result_is_a_miss(self):
        repo = self.git_repo()
        cache_dir = self.cache_dir()
        key = self.fresh_key(repo)
        payload = self.raw_payload_for(
            key, None, status="partial",
            incomplete=[{"scope": "docs/huge.md", "reason": "chunk budget"}],
        )
        self.write_raw(cache_dir, key, payload)

        result = cache.get(cache_dir, key, repo_root=repo)

        self.assertFalse(result.hit)
        self.assertEqual(result.reason, cache.MISS_INCOMPLETE)

    def test_a_valid_key_with_an_invalid_payload_is_a_miss(self):
        # The key is exactly right (the entry is genuinely found), but its
        # payload is corrupted in place afterward — a hit requires both.
        repo = self.git_repo()
        cache_dir = self.cache_dir()
        key = self.fresh_key(repo)
        cache.put(cache_dir, key, self.valid_record())
        self.assertTrue(cache.get(cache_dir, key, repo_root=repo).hit)

        path = cache.entry_path(cache_dir, key)
        with open(path, encoding="utf-8") as fh:
            payload = json.load(fh)
        del payload["records"][0]["digest"]
        with open(path, "w", encoding="utf-8") as fh:
            json.dump(payload, fh)

        result = cache.get(cache_dir, key, repo_root=repo)

        self.assertFalse(result.hit)
        self.assertEqual(result.reason, cache.MISS_INVALID)


class ThePayloadDigest(CacheTestCase):
    """Issue #187: every entry declares a digest over the whole payload, and a
    read recomputes it.

    The class above proves the refusals that can be seen in the shape of a
    payload; none of them sees an entry rewritten into another *valid* one.
    These do — and note that every test above hand-builds a payload carrying
    no digest at all, which is exactly why they still answer `MISS_INVALID`,
    `MISS_STALE`, `MISS_INCOMPLETE`, `MISS_RECORD_COUNT` and `MISS_IDENTITY`:
    the two reasons added here are the last word on a payload, never the first.
    """

    def chunk_record(self, verdict="CUT", **extra):
        """A record shaped like the one the bloat lane caches: the semantic
        result is a list of findings *inside* the record, each with its own
        digest, so the interesting corruption is a nested one."""
        return self.valid_record(
            record_id="BLOAT-CHUNK:docs/a.md",
            code="bloat-chunk-result",
            path="docs/a.md",
            records=[{"id": "B-1", "digest": "b" * 64, "verdict": verdict,
                      "units": ["docs/a.md#L1-L4"]}],
            **extra,
        )

    def poison(self, cache_dir, key, mutate):
        """Rewrite a stored entry in place, restoring the digest it was
        written with — the shape every real poisoning has: the payload is
        edited, the declared digest is not."""
        path = cache.entry_path(cache_dir, key)
        with open(path, encoding="utf-8") as fh:
            payload = json.load(fh)
        declared = payload["digest"]
        mutate(payload)
        payload["digest"] = declared
        with open(path, "w", encoding="utf-8") as fh:
            json.dump(payload, fh)
        return payload

    def test_a_written_entry_declares_a_payload_digest(self):
        repo = self.git_repo()
        cache_dir = self.cache_dir()
        key = self.fresh_key(repo)

        path = cache.put(cache_dir, key, self.chunk_record())

        with open(path, encoding="utf-8") as fh:
            payload = json.load(fh)
        self.assertRegex(payload["digest"], r"\A[0-9a-f]{64}\Z")
        self.assertTrue(cache.get(cache_dir, key, repo_root=repo).hit)

    def test_a_mutated_nested_verdict_is_a_miss_with_its_own_reason(self):
        # The verdict is flipped two levels down, inside the record's own
        # list of findings, and that finding's digest is left alone — the
        # entry is a structurally perfect cache entry about this repository,
        # and every check that predates #187 passes it.
        repo = self.git_repo()
        cache_dir = self.cache_dir()
        key = self.fresh_key(repo)
        cache.put(cache_dir, key, self.chunk_record(verdict="CUT"))
        self.assertTrue(cache.get(cache_dir, key, repo_root=repo).hit)

        def flip(payload):
            payload["records"][0]["records"][0]["verdict"] = "RETIRE-DOC"

        self.poison(cache_dir, key, flip)

        result = cache.get(cache_dir, key, repo_root=repo)

        self.assertFalse(result.hit)
        self.assertIsNone(result.record)
        self.assertEqual(result.reason, cache.MISS_PAYLOAD_DIGEST)

    def test_the_document_is_re_evaluated_after_a_poisoned_entry(self):
        # A miss is the whole point: the caller re-judges the document and
        # stores what it found, and the next lookup hits that — the poisoned
        # verdict never reaches a reader, and the store recovers on its own.
        repo = self.git_repo()
        cache_dir = self.cache_dir()
        key = self.fresh_key(repo)
        cache.put(cache_dir, key, self.chunk_record(verdict="CUT"))
        self.poison(
            cache_dir, key,
            lambda payload: payload["records"][0]["records"][0].update(
                {"verdict": "RETIRE-DOC"}),
        )
        self.assertEqual(
            cache.get(cache_dir, key, repo_root=repo).reason,
            cache.MISS_PAYLOAD_DIGEST,
        )

        cache.put(cache_dir, key, self.chunk_record(verdict="CONDENSE"))

        result = cache.get(cache_dir, key, repo_root=repo)

        self.assertTrue(result.hit)
        self.assertEqual(result.record["records"][0]["verdict"], "CONDENSE")

    def test_the_digest_covers_every_field_of_the_payload(self):
        # One entry, poisoned one way at a time: the digest is over the
        # payload whole, so a semantic field of the record, a field of a
        # nested finding, the record's own identity fields, and the lineage
        # are each covered — including a field added or removed rather than
        # changed. The mutation that moves the repository would also read
        # stale, and the one that moves the record's
        # `document_digest` would also miss on identity; both answer the
        # digest instead, because an altered entry is refused before the
        # question of what it says about the world is asked at all.
        repo = self.git_repo()
        cache_dir = self.cache_dir()
        key = self.fresh_key(repo)

        mutations = {
            "a nested finding's verdict":
                lambda p: p["records"][0]["records"][0].update({"verdict": "CUT"}),
            "a nested finding's units":
                lambda p: p["records"][0]["records"][0]["units"].append("docs/a.md#L9"),
            "a nested finding removed":
                lambda p: p["records"][0]["records"].clear(),
            "a semantic field of the record":
                lambda p: p["records"][0].update({"code": "bloat-chunk-result-2"}),
            "the record's id":
                lambda p: p["records"][0].update({"id": "BLOAT-CHUNK:docs/b.md"}),
            "the record's own digest":
                lambda p: p["records"][0].update({"digest": "c" * 64}),
            "the record's document digest":
                lambda p: p["records"][0].update({"document_digest": "f" * 64}),
            "a field added to the record":
                lambda p: p["records"][0].update({"severity": "high"}),
            "a field removed from the record":
                lambda p: p["records"][0].pop("path"),
            "the lineage's evidence boundary":
                lambda p: p["lineage"]["evidence_boundary"]["sources"].append("*.md"),
            "the lineage's audit mode":
                lambda p: p["lineage"].update({"audit_mode": "full"}),
            "the lineage's repository":
                lambda p: p["lineage"].update(
                    {"repository": "origin:github.com/foreign/repo"}),
        }
        for what, mutate in mutations.items():
            with self.subTest(mutated=what):
                cache.put(cache_dir, key, self.chunk_record(verdict="RETIRE-DOC"))
                self.assertTrue(cache.get(cache_dir, key, repo_root=repo).hit)

                self.poison(cache_dir, key, mutate)

                result = cache.get(cache_dir, key, repo_root=repo)

                self.assertFalse(result.hit)
                self.assertEqual(result.reason, cache.MISS_PAYLOAD_DIGEST)

    def test_an_entry_declaring_no_digest_is_a_miss(self):
        # An entry written before the payload binding existed: valid, fresh,
        # about this very document — and unprovable, so it is a miss with its
        # own reason rather than a hit or a crash, and the caller re-evaluates.
        repo = self.git_repo()
        cache_dir = self.cache_dir()
        key = self.fresh_key(repo)
        record = self.valid_record(document_digest=DOCUMENT_DIGEST,
                                   source_digest=SOURCE_DIGEST)
        self.write_raw(cache_dir, key, self.raw_payload_for(key, record))

        result = cache.get(cache_dir, key, repo_root=repo)

        self.assertFalse(result.hit)
        self.assertIsNone(result.record)
        self.assertEqual(result.reason, cache.MISS_UNDIGESTED)

    def test_a_null_declared_digest_is_a_miss(self):
        # The one-token defeat of the whole binding, and the reason the guard
        # is on the value rather than the key: `"digest": null` leaves the
        # field present, so a presence check passes it, while the report
        # contract skips a declared digest of `None` rather than failing it.
        # An entry landing between those two would be a clean hit carrying
        # whatever the poisoner wrote. `poison()` cannot reach this — it
        # restores the digest the entry was written with — so the edit is
        # made here.
        repo = self.git_repo()
        cache_dir = self.cache_dir()
        key = self.fresh_key(repo)
        cache.put(cache_dir, key, self.chunk_record(verdict="CUT"))
        path = cache.entry_path(cache_dir, key)
        with open(path, encoding="utf-8") as fh:
            payload = json.load(fh)
        payload["records"][0]["records"][0]["verdict"] = "RETIRE-DOC"
        payload["digest"] = None
        with open(path, "w", encoding="utf-8") as fh:
            json.dump(payload, fh)

        result = cache.get(cache_dir, key, repo_root=repo)

        self.assertFalse(result.hit)
        self.assertIsNone(result.record)
        self.assertEqual(result.reason, cache.MISS_UNDIGESTED)

    def test_a_declared_digest_that_is_not_a_digest_is_a_miss(self):
        # Any other type is refused where the validator recomputes it: a
        # declared value that is not `None` never equals the digest of the
        # payload, whatever it is.
        repo = self.git_repo()
        cache_dir = self.cache_dir()
        key = self.fresh_key(repo)
        cache.put(cache_dir, key, self.chunk_record())
        path = cache.entry_path(cache_dir, key)
        with open(path, encoding="utf-8") as fh:
            payload = json.load(fh)
        payload["digest"] = 123
        with open(path, "w", encoding="utf-8") as fh:
            json.dump(payload, fh)

        result = cache.get(cache_dir, key, repo_root=repo)

        self.assertFalse(result.hit)
        self.assertEqual(result.reason, cache.MISS_PAYLOAD_DIGEST)

    def test_re_storing_an_undigested_entry_repairs_it(self):
        repo = self.git_repo()
        cache_dir = self.cache_dir()
        key = self.fresh_key(repo)
        record = self.valid_record(document_digest=DOCUMENT_DIGEST,
                                   source_digest=SOURCE_DIGEST)
        self.write_raw(cache_dir, key, self.raw_payload_for(key, record))

        cache.put(cache_dir, key, record)

        self.assertTrue(cache.get(cache_dir, key, repo_root=repo).hit)

    def test_storing_a_record_the_contract_refuses_does_not_raise(self):
        # `put()` digests through the report contract, so a record that
        # contract would refuse has no digest to declare. The write still
        # returns rather than raising in the middle of an audit, and the
        # entry reads back as the miss that record has always earned.
        repo = self.git_repo()
        cache_dir = self.cache_dir()
        key = self.fresh_key(repo)

        path = cache.put(cache_dir, key, {"id": "R1"})  # no 'digest'

        with open(path, encoding="utf-8") as fh:
            self.assertNotIn("digest", json.load(fh))
        self.assertEqual(
            cache.get(cache_dir, key, repo_root=repo).reason, cache.MISS_INVALID,
        )


class CacheKeyDigest(unittest.TestCase):
    def test_the_default_schema_version_is_the_engines_own(self):
        state = {
            "inventory_digest": "1" * 64, "audit_config_digest": CONFIG_DIGEST,
            "registry_digest": "2" * 64, "ruleset_version": 1,
            "plugin_version": "0.16.0", "repository": "root-commit:abc",
            "base_commit": "0" * 40,
        }

        key = cache.cache_key(DOCUMENT_DIGEST, SOURCE_DIGEST, state)

        self.assertEqual(key.schema_version, ARTIFACT_SCHEMA_VERSION)

    def test_reformatting_the_key_inputs_does_not_change_the_digest(self):
        state = {
            "inventory_digest": "1" * 64, "audit_config_digest": CONFIG_DIGEST,
            "registry_digest": "2" * 64, "ruleset_version": 1,
            "plugin_version": "0.16.0", "repository": "root-commit:abc",
            "base_commit": "0" * 40,
        }
        key_a = cache.cache_key(DOCUMENT_DIGEST, SOURCE_DIGEST, state)
        key_b = cache.cache_key(DOCUMENT_DIGEST, SOURCE_DIGEST, dict(reversed(state.items())))

        self.assertEqual(key_a.digest, key_b.digest)


if __name__ == "__main__":
    unittest.main(verbosity=2)
