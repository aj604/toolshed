#!/usr/bin/env python3
"""Scenario (issue #66): the bloat audit over the acceptance fixture.

One class per acceptance criterion, against the real-git repository #61
established — real commits, real symlinks, real prompt-injection content — so a
pass means the bloat lane behaves correctly against a real inventory, a real
registry, and a real corpus rather than a synthetic one.

The fixture's shape is what makes these criteria non-trivial: the living
document that owns the fee policy (`fixture.POLICY_DOC`) is a *different*
document from the two planning artifacts that copy its claims, so a chunk plan
puts the copies and their destination in different chunks. Any answer a worker
could reach from its own slice would be wrong.

Seams under test: `context.build_context_index()`, `bloat.plan_chunks()`,
`bloat.record_verdicts()`, `bloat.load_chunk()` / `bloat.store_chunk()`, and
`report.validate_report()` / `render.render_report()` over the produced report.

Run: python3 tests/engine/acceptance/scenario_bloat_test.py
"""

import os
import shutil
import subprocess
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import fixture  # noqa: E402  (the acceptance fixture builder)
from support import ENGINE  # noqa: E402  (also puts the engine on sys.path)

import json  # noqa: E402

from doclifecycle import bloat  # noqa: E402
from doclifecycle.context import build_context_index  # noqa: E402
from doclifecycle.render import render_report  # noqa: E402
from doclifecycle.report import (  # noqa: E402
    EvidenceBoundary,
    Lineage,
    current_lineage,
    validate_report,
)
from doclifecycle.results import STATE_PARTIAL, Invalid  # noqa: E402

CONFIG_DIGEST = "c" * 64


def run_cli(*argv):
    env = dict(os.environ, PYTHONPATH=ENGINE)
    return subprocess.run(
        [sys.executable, "-m", "doclifecycle", *argv],
        capture_output=True, text=True, env=env,
    )


class BloatScenario(fixture.AcceptanceFixtureTestCase):
    """A fixture repository, its context index, and a lineage read from git."""

    def setUp(self):
        self.repo = self.build_fixture()
        self.index = build_context_index(self.repo)
        self.assertNotIsInstance(self.index, Invalid)
        current, problems = current_lineage(
            self.repo, audit_config_digest=CONFIG_DIGEST
        )
        self.assertEqual(problems, ())
        self.state = dict(current)
        self.lineage = Lineage(
            audit_mode="chunk",
            evidence_boundary=EvidenceBoundary(("docs/**",)),
            **current,
        )

    def unit(self, path, text):
        """The digest of `text` as it appears in `path`."""
        digest = {u.text: u.digest for u in self.index.units}[text]
        self.assertIn(digest, self.index.document(path).units)
        return digest

    def all_units(self, path):
        return list(dict.fromkeys(self.index.document(path).units))

    def chunk_holding(self, path):
        plan = bloat.plan_chunks(self.index, max_documents=2)
        chunk = next(c for c in plan.chunks if path in c.documents)
        return chunk

    def record(self, verdicts, chunk=None):
        result = bloat.record_verdicts(
            self.index, self.lineage, verdicts, chunk=chunk
        )
        self.assertNotIsInstance(
            result, Invalid, getattr(result, "problems", None)
        )
        return result


class TheDuplicateDestinationOutsideTheSlice(BloatScenario):
    """AC1 — the legitimate destination is found and named, from global data."""

    def test_the_destination_really_is_outside_the_workers_slice(self):
        chunk = self.chunk_holding(fixture.FEE_TIERS_PLAN)

        self.assertNotIn(fixture.POLICY_DOC, chunk.documents)

    def test_the_finding_names_the_living_document_that_owns_the_claim(self):
        chunk = self.chunk_holding(fixture.FEE_TIERS_PLAN)

        result = self.record([{
            "id": "BLOAT-001",
            "verdict": bloat.MERGE_DOC,
            "path": fixture.FEE_TIERS_PLAN,
            "units": self.all_units(fixture.FEE_TIERS_PLAN),
            "evidence": "The fee policy already states this; the plan restates it.",
        }], chunk=chunk)

        destination = result.records()[0]["destination"]
        self.assertEqual(destination["path"], fixture.POLICY_DOC)
        self.assertEqual(destination["kind"], "living")
        self.assertEqual(destination["selected_by"], "index-owner")

    def test_the_finding_carries_a_pointer_to_every_copy(self):
        # Unit identity is content-addressed and the finding's unit group is
        # deduplicated, so the group alone cannot say which of the plan's two
        # identical sentences is meant. The occurrence pointers can.
        result = self.record([{
            "id": "BLOAT-001",
            "verdict": bloat.CUT,
            "path": fixture.FEE_TIERS_PLAN,
            "units": [self.unit(fixture.FEE_TIERS_PLAN, fixture.DUPLICATED_ASSERTION)],
            "evidence": "The fee policy already states this.",
        }])

        search = result.records()[0]["duplicate_search"]
        # One deduplicated unit in the group, but two copies in this document
        # — `here` is what says which copies the finding is about, and
        # `elsewhere` is what makes the redundancy claim checkable.
        self.assertEqual(len(result.records()[0]["units"]), 1)
        self.assertEqual(
            [(o["path"], o["line"]) for o in search["here"]],
            [(fixture.FEE_TIERS_PLAN, 5), (fixture.FEE_TIERS_PLAN, 9)],
        )
        self.assertEqual(
            [(o["path"], o["line"]) for o in search["elsewhere"]],
            [(fixture.POLICY_DOC, 3)],
        )

    def test_the_search_that_informed_it_covered_the_whole_corpus(self):
        result = self.record([{
            "id": "BLOAT-001",
            "verdict": bloat.MERGE_DOC,
            "path": fixture.FEE_TIERS_PLAN,
            "units": self.all_units(fixture.FEE_TIERS_PLAN),
            "evidence": "The fee policy already states this.",
        }])

        search = result.records()[0]["duplicate_search"]
        self.assertEqual(search["scope"], "repository")
        self.assertEqual(search["index_digest"], self.index.digest)
        self.assertEqual(search["documents_searched"], len(self.index.documents))

    def test_a_slice_local_guess_at_the_destination_is_refused(self):
        chunk = self.chunk_holding(fixture.FEE_TIERS_PLAN)

        result = bloat.record_verdicts(self.index, self.lineage, [{
            "id": "BLOAT-001",
            "verdict": bloat.MERGE_DOC,
            "path": fixture.FEE_TIERS_PLAN,
            "units": self.all_units(fixture.FEE_TIERS_PLAN),
            "evidence": "Guessed a destination inside my own slice.",
            "destination": fixture.PLANNING_DOC,
        }], chunk=chunk)

        self.assertIsInstance(result, Invalid)
        self.assertEqual(
            [p.code for p in result.problems],
            ["bloat-destination-contradicts-index"],
        )


class TwoChunksCompetingForOneMoveTarget(BloatScenario):
    """AC2 — passage moves resolve globally, independently of each worker."""

    def move_from(self, path, text):
        chunk = self.chunk_holding(path)
        result = self.record([{
            "id": f"BLOAT-{path}",
            "verdict": bloat.EXTRACT_AND_MOVE,
            "path": path,
            "units": [self.unit(path, text)],
            "evidence": "The living fee policy already owns this claim.",
            "proposal": text,
        }], chunk=chunk)
        return result.records()[0]

    def test_the_two_claimants_are_in_different_chunks(self):
        tiers = self.chunk_holding(fixture.FEE_TIERS_PLAN)
        rollout = self.chunk_holding(fixture.FEE_ROLLOUT_PLAN)

        self.assertNotEqual(tiers.chunk_id, rollout.chunk_id)

    def test_both_chunks_resolve_to_the_same_move_target(self):
        tiers = self.move_from(fixture.FEE_TIERS_PLAN, fixture.DUPLICATED_ASSERTION)
        rollout = self.move_from(fixture.FEE_ROLLOUT_PLAN, fixture.CONTENDED_ASSERTION)

        self.assertEqual(tiers["destination"]["path"], fixture.POLICY_DOC)
        self.assertEqual(rollout["destination"]["path"], fixture.POLICY_DOC)

    def test_each_chunk_sees_the_complete_claimant_list_and_its_own_rank(self):
        tiers = self.move_from(fixture.FEE_TIERS_PLAN, fixture.DUPLICATED_ASSERTION)
        rollout = self.move_from(fixture.FEE_ROLLOUT_PLAN, fixture.CONTENDED_ASSERTION)

        claimants = [fixture.FEE_TIERS_PLAN, fixture.FEE_ROLLOUT_PLAN]
        self.assertEqual(tiers["contention"]["claimants"], claimants)
        self.assertEqual(rollout["contention"]["claimants"], claimants)
        self.assertEqual(tiers["contention"]["order"], 0)
        self.assertEqual(rollout["contention"]["order"], 1)

    def test_the_order_the_chunks_are_audited_in_changes_no_answer(self):
        forward = [
            self.move_from(fixture.FEE_TIERS_PLAN, fixture.DUPLICATED_ASSERTION),
            self.move_from(fixture.FEE_ROLLOUT_PLAN, fixture.CONTENDED_ASSERTION),
        ]
        backward = [
            self.move_from(fixture.FEE_ROLLOUT_PLAN, fixture.CONTENDED_ASSERTION),
            self.move_from(fixture.FEE_TIERS_PLAN, fixture.DUPLICATED_ASSERTION),
        ]

        self.assertEqual(forward, list(reversed(backward)))

    def test_one_chunk_audited_alone_reaches_the_same_answer(self):
        alone = self.move_from(fixture.FEE_TIERS_PLAN, fixture.DUPLICATED_ASSERTION)
        self.move_from(fixture.FEE_ROLLOUT_PLAN, fixture.CONTENDED_ASSERTION)
        together = self.move_from(fixture.FEE_TIERS_PLAN, fixture.DUPLICATED_ASSERTION)

        self.assertEqual(alone, together)


class ChunkResultsFlowThroughTheCache(BloatScenario):
    """AC3 — cached and invalidated through the lineage-keyed cache."""

    def cache_dir(self):
        root = tempfile.mkdtemp(prefix="doc-lifecycle-bloat-cache-")
        self.addCleanup(shutil.rmtree, root, ignore_errors=True)
        return root

    def stored(self, cache_dir, chunk, state):
        result = self.record([{
            "id": "BLOAT-001",
            "verdict": bloat.MERGE_DOC,
            "path": fixture.FEE_TIERS_PLAN,
            "units": self.all_units(fixture.FEE_TIERS_PLAN),
            "evidence": "The fee policy already states this.",
        }], chunk=chunk)
        results = {path: [] for path in chunk.documents}
        results[fixture.FEE_TIERS_PLAN] = list(result.records())
        bloat.store_chunk(cache_dir, self.index, state, chunk, results)

    def test_a_stored_chunk_result_is_reused_on_the_next_run(self):
        cache_dir = self.cache_dir()
        chunk = self.chunk_holding(fixture.FEE_TIERS_PLAN)
        self.stored(cache_dir, chunk, self.state)

        cached = bloat.load_chunk(
            cache_dir, self.repo, self.index, self.state, chunk
        )

        self.assertEqual(cached.misses, ())
        self.assertEqual(
            cached.hits[fixture.FEE_TIERS_PLAN][0]["destination"]["path"],
            fixture.POLICY_DOC,
        )

    def test_a_configuration_change_reruns_the_chunk(self):
        cache_dir = self.cache_dir()
        chunk = self.chunk_holding(fixture.FEE_TIERS_PLAN)
        self.stored(cache_dir, chunk, self.state)

        moved, problems = current_lineage(self.repo, audit_config_digest="d" * 64)
        self.assertEqual(problems, ())
        cached = bloat.load_chunk(cache_dir, self.repo, self.index, moved, chunk)

        self.assertEqual(cached.misses, chunk.documents)

    def test_a_ruleset_change_reruns_the_chunk(self):
        cache_dir = self.cache_dir()
        chunk = self.chunk_holding(fixture.FEE_TIERS_PLAN)
        self.stored(cache_dir, chunk, self.state)

        bumped = dict(self.state, ruleset_version=self.state["ruleset_version"] + 1)
        cached = bloat.load_chunk(cache_dir, self.repo, self.index, bumped, chunk)

        self.assertEqual(cached.misses, chunk.documents)

    def test_an_edit_to_the_destination_document_reruns_the_chunk(self):
        # `docs/plans/...`'s own bytes never change, but the corpus it was
        # judged against does: the claim it duplicates is gone from the living
        # document, so "this is already stated elsewhere" is no longer true.
        cache_dir = self.cache_dir()
        chunk = self.chunk_holding(fixture.FEE_TIERS_PLAN)
        self.stored(cache_dir, chunk, self.state)

        path = os.path.join(self.repo, fixture.POLICY_DOC)
        with open(path, encoding="utf-8") as fh:
            text = fh.read()
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(text.replace(fixture.DUPLICATED_ASSERTION, "Rewritten."))

        moved_index = build_context_index(self.repo)
        moved, problems = current_lineage(
            self.repo, audit_config_digest=CONFIG_DIGEST
        )
        self.assertEqual(problems, ())
        cached = bloat.load_chunk(
            cache_dir, self.repo, moved_index, moved, chunk
        )

        self.assertIn(fixture.FEE_TIERS_PLAN, cached.misses)


class BulkRetirementIsEnumerated(BloatScenario):
    """AC4 — every affected file enumerated; sampling is never authority."""

    def bulk(self, **overrides):
        entry = {
            "id": "BLOAT-BULK",
            "verdict": bloat.RETIRE_DOC,
            "evidence": "Spent planning artifacts; the fee work has landed.",
            "scope": {"set": fixture.PLANS_SET},
        }
        entry.update(overrides)
        return bloat.record_verdicts(self.index, self.lineage, [entry])

    def test_one_judgment_produces_one_finding_per_affected_file(self):
        result = self.bulk()

        self.assertEqual(
            [r["path"] for r in result.records()],
            sorted(fixture.PLANS_SET_MEMBERS),
        )

    def test_the_enumeration_is_re_derivable_from_the_index(self):
        result = self.bulk()

        scope = result.records()[0]["scope"]
        enumeration = bloat.enumerate_scope(
            self.index, {"set": fixture.PLANS_SET}
        )
        self.assertEqual(scope["digest"], enumeration.digest)
        self.assertEqual(scope["members"], sorted(fixture.PLANS_SET_MEMBERS))

    def test_reading_only_a_sample_still_names_every_file(self):
        result = self.bulk(sample=[fixture.FEE_TIERS_PLAN])

        self.assertEqual(len(result.records()), len(fixture.PLANS_SET_MEMBERS))
        scope = result.records()[0]["scope"]
        self.assertEqual(scope["sample"], [fixture.FEE_TIERS_PLAN])
        self.assertTrue(scope["sample_is_not_authority"])

    def test_a_model_supplied_file_list_cannot_stand_in_for_the_enumeration(self):
        result = self.bulk(files=[fixture.FEE_TIERS_PLAN, fixture.FEE_ROLLOUT_PLAN])

        self.assertIsInstance(result, Invalid)
        self.assertEqual(
            [p.code for p in result.problems], ["bloat-sampling-not-authority"]
        )

    def test_adding_a_planning_document_re_keys_the_enumeration(self):
        before = self.bulk().records()[0]["scope"]["digest"]

        with open(os.path.join(self.repo, "docs/plans/2026-07-23-late.md"),
                  "w", encoding="utf-8") as fh:
            fh.write("# Late plan\n\n**Status:** draft.\n")
        self.index = build_context_index(self.repo)

        self.assertNotEqual(self.bulk().records()[0]["scope"]["digest"], before)


class CoverageRendersTruthfully(BloatScenario):
    """AC5 — gaps and partial states in the shared report contract's terms."""

    def test_the_index_names_what_it_could_not_examine(self):
        gaps = {u.scope: u.code for u in self.index.unexamined}

        self.assertEqual(gaps[fixture.STRAY_DOC], "unregistered-document")
        for symlink in fixture.SYMLINK_PATHS:
            with self.subTest(symlink):
                self.assertEqual(gaps[symlink], "symlinked-path")

    def test_a_run_with_an_unexamined_scope_reports_partial(self):
        result = bloat.record_verdicts(self.index, self.lineage, [])

        report = validate_report(result.report_payload(self.lineage))

        self.assertEqual(report.status, STATE_PARTIAL)

    def test_the_report_names_every_scope_it_did_not_examine(self):
        result = bloat.record_verdicts(self.index, self.lineage, [])

        report = validate_report(result.report_payload(self.lineage))

        self.assertEqual(
            sorted(entry.scope for entry in report.incomplete),
            sorted([fixture.STRAY_DOC, *fixture.SYMLINK_PATHS]),
        )

    def test_a_clean_document_is_never_implied_by_an_unexamined_one(self):
        result = bloat.record_verdicts(self.index, self.lineage, [])

        rendered = render_report(
            validate_report(result.report_payload(self.lineage))
        )

        self.assertIn("partial", rendered.lower())
        self.assertIn(fixture.STRAY_DOC, rendered)

    def test_the_findings_and_the_gaps_travel_in_one_report(self):
        result = self.record([{
            "id": "BLOAT-001",
            "verdict": bloat.MERGE_DOC,
            "path": fixture.FEE_TIERS_PLAN,
            "units": self.all_units(fixture.FEE_TIERS_PLAN),
            "evidence": "The fee policy already states this.",
        }])

        report = validate_report(result.report_payload(self.lineage))

        self.assertEqual(report.status, STATE_PARTIAL)
        self.assertEqual([r.id for r in report.records], ["BLOAT-001"])

    def test_the_injected_instructions_never_become_a_verdict(self):
        # The fixture's living document carries a prompt-injection attempt in
        # an HTML comment. It is indexed as content like anything else, and
        # naming it in a verdict is not how it gains authority — nothing in the
        # index or the recorder reads it as an instruction.
        injected = [
            u for u in self.index.units if "ignore all previous instructions" in u.text
        ]

        self.assertEqual(len(injected), 1)
        self.assertFalse(injected[0].assertion_capable)


class TheCommandsOverTheFixture(BloatScenario):
    def test_the_context_index_command_agrees_with_the_library(self):
        result = run_cli("context-index", "--repo", self.repo)

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout), self.index.to_dict())

    def test_the_chunk_plan_covers_every_indexed_document(self):
        result = run_cli("bloat-plan", "--repo", self.repo, "--max-documents", "2")

        self.assertEqual(result.returncode, 0, result.stderr)
        placed = [p for c in json.loads(result.stdout)["chunks"] for p in c["documents"]]
        self.assertEqual(sorted(placed), [d.path for d in self.index.documents])


if __name__ == "__main__":
    unittest.main(verbosity=2)
