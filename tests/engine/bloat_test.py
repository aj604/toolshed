#!/usr/bin/env python3
"""The bloat lane's deterministic machinery (issue #66).

Seams under test: `bloat.plan_chunks()`, `bloat.merge_contention()`,
`bloat.enumerate_scope()`, `bloat.record_verdicts()`, `bloat.audit_bloat()`,
`bloat.load_bloat_verdicts()`, and the chunk cache seam (`bloat.load_chunk()` /
`bloat.store_chunk()`) as library calls.

Run: python3 tests/engine/bloat_test.py
"""

import os
import shutil
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from support import (  # noqa: E402  (also puts the engine on sys.path)
    CORPUS_REGISTRY as REGISTRY,
    SHARED_SENTENCE as SHARED,
    RepoTestCase,
)

from finding_test import lineage as finding_lineage  # noqa: E402
from report_test import GitRepoTestCase  # noqa: E402  (a real git repository)

from doclifecycle import ARTIFACT_SCHEMA_VERSION, RULESET_VERSION, bloat  # noqa: E402
from doclifecycle.approval import (  # noqa: E402
    MINTER_HUMAN,
    ApprovalSet,
    Minter,
    mint_approval_set,
)
from doclifecycle.context import build_context_index  # noqa: E402
from doclifecycle.digest import sha256_canonical  # noqa: E402
from doclifecycle.report import EvidenceBoundary, Report, current_lineage  # noqa: E402
from doclifecycle.results import Invalid  # noqa: E402


def lineage(**overrides):
    """The lineage a bloat chunk runs under.

    `finding_test`'s fixture with two fields moved, rather than a second copy:
    a bloat verdict is produced by a chunk worker reading documentation, so the
    mode is `chunk` and the evidence boundary is the corpus.
    """
    return finding_lineage(**{
        "audit_mode": "chunk",
        "evidence_boundary": EvidenceBoundary(("docs/**",)),
        **overrides,
    })





def problem_codes(result):
    return sorted(p.code for p in result.problems)


class ChunkPlanning(RepoTestCase):
    def index(self, files):
        return build_context_index(self.repo({
            ".doc-lifecycle/registry.json": REGISTRY, **files
        }))

    def test_every_indexed_document_lands_in_exactly_one_chunk(self):
        index = self.index({
            "docs/a.md": "# A\n\nAlpha.\n",
            "docs/b.md": "# B\n\nBeta.\n",
            "docs/guides/g.md": "# G\n\nGamma.\n",
            "docs/plans/p.md": "# P\n\nDelta.\n",
        })

        plan = bloat.plan_chunks(index, max_documents=2)

        placed = [path for chunk in plan.chunks for path in chunk.documents]
        self.assertEqual(sorted(placed), [d.path for d in index.documents])
        self.assertEqual(len(placed), len(set(placed)))

    def test_a_document_budget_bounds_each_chunk(self):
        index = self.index({
            f"docs/{name}.md": f"# {name}\n\nText {name}.\n"
            for name in ("a", "b", "c", "d", "e")
        })

        plan = bloat.plan_chunks(index, max_documents=2)

        self.assertTrue(all(len(c.documents) <= 2 for c in plan.chunks))
        self.assertEqual(len(plan.chunks), 3)

    def test_both_public_planners_reject_non_positive_budgets(self):
        repo = self.repo({
            ".doc-lifecycle/registry.json": REGISTRY,
            "docs/a.md": "# A\n\nAlpha.\n",
        })
        index = build_context_index(repo)
        planners = {
            "index": lambda **budgets: bloat.plan_chunks(index, **budgets),
            "repository": lambda **budgets: bloat.plan_repository_chunks(
                repo, **budgets,
            ),
        }

        for seam, planner in planners.items():
            for budget in ("max_documents", "max_units"):
                for value in (0, -1):
                    with self.subTest(seam=seam, budget=budget, value=value):
                        with self.assertRaisesRegex(ValueError, budget):
                            planner(**{budget: value})

    def test_a_document_larger_than_the_unit_budget_gets_its_own_chunk(self):
        big = "# Big\n\n" + "\n\n".join(f"Sentence {i}." for i in range(40)) + "\n"
        index = self.index({"docs/a.md": big, "docs/b.md": "# B\n\nBeta.\n"})

        plan = bloat.plan_chunks(index, max_documents=8, max_units=5)

        by_document = {c.documents: c for c in plan.chunks}
        self.assertIn(("docs/a.md",), by_document)
        self.assertIn(("docs/b.md",), by_document)

    def test_both_public_planners_fail_closed_on_non_integer_budgets(self):
        repo = self.repo({
            ".doc-lifecycle/registry.json": REGISTRY,
            "docs/a.md": "# A\n\nAlpha.\n",
        })
        index = build_context_index(repo)
        planners = {
            "index": lambda **budgets: bloat.plan_chunks(index, **budgets),
            "repository": lambda **budgets: bloat.plan_repository_chunks(
                repo, **budgets,
            ),
        }
        invalid = (True, False, 1.5, "2", "many", None)

        for seam, planner in planners.items():
            for budget in ("max_documents", "max_units"):
                for value in invalid:
                    with self.subTest(seam=seam, budget=budget, value=value):
                        with self.assertRaisesRegex(ValueError, budget):
                            planner(**{budget: value})

    def test_planning_the_same_index_twice_gives_the_same_chunk_ids(self):
        files = {
            "docs/a.md": "# A\n\nAlpha.\n",
            "docs/plans/p.md": "# P\n\nDelta.\n",
        }

        first = bloat.plan_chunks(self.index(files), max_documents=1)
        second = bloat.plan_chunks(self.index(files), max_documents=1)

        self.assertEqual(
            [c.chunk_id for c in first.chunks], [c.chunk_id for c in second.chunks]
        )

    def test_plan_records_the_budgets_needed_to_rederive_it(self):
        index = self.index({
            "docs/a.md": "# A\n\nAlpha.\n",
            "docs/b.md": "# B\n\nBeta.\n",
        })

        payload = bloat.plan_chunks(
            index, max_documents=1, max_units=17,
        ).to_dict()

        self.assertEqual(payload["max_documents"], 1)
        self.assertEqual(payload["max_units"], 17)

    def test_positive_boundary_budgets_match_at_both_library_seams(self):
        repo = self.repo({
            ".doc-lifecycle/registry.json": REGISTRY,
            "docs/a.md": "# A\n\nAlpha.\n",
            "docs/b.md": "# B\n\nBeta.\n",
        })
        index = build_context_index(repo)

        direct = bloat.plan_chunks(index, max_documents=1, max_units=1)
        repository = bloat.plan_repository_chunks(
            repo, max_documents=1, max_units=1,
        )

        self.assertEqual(direct.to_dict(), repository.to_dict())
        self.assertEqual(
            [chunk.documents for chunk in direct.chunks],
            [("docs/a.md",), ("docs/b.md",)],
        )

    def test_serialized_plan_round_trips_through_the_public_parser(self):
        plan = bloat.plan_chunks(self.index({
            "docs/a.md": "# A\n\nAlpha.\n",
            "docs/b.md": "# B\n\nBeta.\n",
        }), max_documents=1, max_units=17)

        parsed = bloat.chunk_plan_from_dict(plan.to_dict())

        self.assertEqual(parsed, plan)

    def test_public_plan_parser_refuses_a_tampered_shape(self):
        plan = bloat.plan_chunks(self.index({
            "docs/a.md": "# A\n\nAlpha.\n",
        })).to_dict()
        plan["chunks"][0]["documents"].append("docs/invented.md")

        parsed = bloat.chunk_plan_from_dict(plan)

        self.assertIsInstance(parsed, Invalid)
        self.assertIn("bloat-completion-plan-invalid",
                      [problem.code for problem in parsed.problems])

    def test_editing_one_document_re_keys_only_its_chunk(self):
        before = bloat.plan_chunks(self.index({
            "docs/a.md": "# A\n\nAlpha.\n", "docs/b.md": "# B\n\nBeta.\n",
        }), max_documents=1)
        after = bloat.plan_chunks(self.index({
            "docs/a.md": "# A\n\nAlpha changed.\n", "docs/b.md": "# B\n\nBeta.\n",
        }), max_documents=1)

        changed = {c.chunk_id for c in before.chunks} ^ {c.chunk_id for c in after.chunks}
        self.assertEqual(len(changed), 2)


class MergeContention(RepoTestCase):
    def index(self, files):
        return build_context_index(self.repo({
            ".doc-lifecycle/registry.json": REGISTRY, **files
        }))

    def test_two_copies_in_two_documents_both_claim_the_owner(self):
        index = self.index({
            "docs/a.md": f"# A\n\n{SHARED}\n",
            "docs/guides/g.md": f"# G\n\n{SHARED}\n",
            "docs/plans/p.md": f"# P\n\n{SHARED}\n",
        })

        contention = bloat.merge_contention(index)

        self.assertEqual(
            [(c.source, c.order) for c in contention["docs/a.md"]],
            [("docs/guides/g.md", 0), ("docs/plans/p.md", 1)],
        )

    def test_the_owner_never_claims_against_itself(self):
        index = self.index({
            "docs/a.md": f"# A\n\n{SHARED}\n",
            "docs/plans/p.md": f"# P\n\n{SHARED}\n",
        })

        contention = bloat.merge_contention(index)

        self.assertNotIn("docs/plans/p.md", contention)
        self.assertEqual(
            [c.source for c in contention["docs/a.md"]], ["docs/plans/p.md"]
        )

    def test_a_unit_occurring_once_produces_no_contention(self):
        index = self.index({"docs/a.md": f"# A\n\n{SHARED}\n"})

        self.assertEqual(bloat.merge_contention(index), {})


class ScopeEnumeration(RepoTestCase):
    def index(self, files=None):
        files = files or {
            "docs/a.md": "# A\n\nAlpha.\n",
            "docs/plans/p1.md": "# P1\n\nOne.\n",
            "docs/plans/p2.md": "# P2\n\nTwo.\n",
            "docs/plans/p3.md": "# P3\n\nThree.\n",
        }
        return build_context_index(self.repo({
            ".doc-lifecycle/registry.json": REGISTRY, **files
        }))

    def test_a_document_set_enumerates_every_member(self):
        enumeration = bloat.enumerate_scope(self.index(), {"set": "plans"})

        self.assertEqual(
            enumeration.members,
            ("docs/plans/p1.md", "docs/plans/p2.md", "docs/plans/p3.md"),
        )

    def test_a_glob_rule_enumerates_every_match(self):
        enumeration = bloat.enumerate_scope(self.index(), {"glob": "docs/plans/*.md"})

        self.assertEqual(len(enumeration.members), 3)

    def test_a_kind_rule_enumerates_every_document_of_that_kind(self):
        enumeration = bloat.enumerate_scope(self.index(), {"kind": "planning"})

        self.assertEqual(len(enumeration.members), 3)

    def test_the_enumeration_digest_moves_when_membership_moves(self):
        three = bloat.enumerate_scope(self.index(), {"set": "plans"})
        two = bloat.enumerate_scope(self.index({
            "docs/a.md": "# A\n\nAlpha.\n",
            "docs/plans/p1.md": "# P1\n\nOne.\n",
            "docs/plans/p2.md": "# P2\n\nTwo.\n",
        }), {"set": "plans"})

        self.assertNotEqual(three.digest, two.digest)

    def test_an_unenumerable_rule_is_refused(self):
        result = bloat.enumerate_scope(self.index(), {"about": "old plans"})

        self.assertIsInstance(result, Invalid)
        self.assertEqual(problem_codes(result), ["bloat-scope-not-enumerable"])

    def test_a_selector_whose_value_is_not_a_string_is_refused(self):
        # Issue #57 review (parity audit): `{"glob": 123}` reached
        # `registry.compile_glob` and raised `TypeError` out of a public seam,
        # so bloat-audit produced a traceback and no report at all. `set` and
        # `kind` degraded to `bloat-scope-empty`, which is a true statement
        # about a rule nobody could have written on purpose; all three name the
        # same fault now.
        for rule in ({"glob": 123}, {"set": 123}, {"kind": None},
                     {"glob": ""}, {"glob": ["docs/*.md"]}):
            with self.subTest(rule=rule):
                result = bloat.enumerate_scope(self.index(), rule)

                self.assertIsInstance(result, Invalid, result)
                self.assertEqual(problem_codes(result),
                                 ["bloat-scope-not-enumerable"])

    def test_a_rule_matching_nothing_is_refused(self):
        result = bloat.enumerate_scope(self.index(), {"set": "adr"})

        self.assertIsInstance(result, Invalid)
        self.assertEqual(problem_codes(result), ["bloat-scope-empty"])


class RecorderTestCase(RepoTestCase):
    """Verdict recording against a small three-document corpus.

    `docs/a.md` (living) states SHARED; `docs/plans/p.md` (planning) copies it;
    `docs/guides/g.md` (narrative) says something of its own.
    """

    def setUp(self):
        self.index = build_context_index(self.repo({
            ".doc-lifecycle/registry.json": REGISTRY,
            "docs/a.md": f"# A\n\n{SHARED}\n",
            "docs/guides/g.md": "# G\n\nGuide prose.\n",
            "docs/plans/p.md": f"# P\n\n{SHARED}\n",
        }))
        self.lineage = lineage()

    def unit(self, path, text):
        by_text = {u.text: u.digest for u in self.index.units}
        digest = by_text[text]
        assert digest in self.index.document(path).units
        return digest

    def record(self, verdicts, chunk=None):
        return bloat.record_verdicts(self.index, self.lineage, verdicts, chunk=chunk)

    def verdict(self, **overrides):
        entry = {
            "id": "BLOAT-001",
            "verdict": bloat.CUT,
            "path": "docs/plans/p.md",
            "units": [self.unit("docs/plans/p.md", SHARED)],
            "evidence": "The living document already states this.",
        }
        entry.update(overrides)
        if entry["verdict"] in bloat.WHOLE_DOCUMENT_VERDICTS and "units" not in overrides:
            entry["units"] = list(self.index.document(entry["path"]).units)
        return entry


class WholeDocumentVerdictsBindEveryCurrentUnit(RecorderTestCase):
    CASES = (
        (bloat.RETIRE_DOC, {}),
        (bloat.DISTILL, {"status": "pending-implementation"}),
        (bloat.MERGE_DOC, {}),
    )

    def all_units(self, path="docs/plans/p.md"):
        return list(self.index.document(path).units)

    def test_each_whole_document_verdict_omitting_a_current_unit_is_refused(self):
        for verdict, required in self.CASES:
            with self.subTest(verdict=verdict):
                result = self.record([self.verdict(
                    verdict=verdict,
                    units=[self.unit("docs/plans/p.md", SHARED)],
                    **required,
                )])

                self.assertEqual(
                    problem_codes(result),
                    ["bloat-whole-document-units-incomplete"],
                )

    def test_a_duplicate_unit_identity_is_refused(self):
        units = self.all_units()
        result = self.record([self.verdict(
            verdict=bloat.RETIRE_DOC, units=units + [units[0]],
        )])

        self.assertEqual(
            problem_codes(result), ["bloat-whole-document-unit-duplicate"]
        )

    def test_an_extra_unit_from_another_document_is_refused(self):
        guide_unit = self.unit("docs/guides/g.md", "Guide prose.")
        result = self.record([self.verdict(
            verdict=bloat.RETIRE_DOC, units=self.all_units() + [guide_unit],
        )])

        self.assertEqual(problem_codes(result), ["bloat-unknown-unit"])

    def test_a_stale_unit_identity_is_refused(self):
        result = self.record([self.verdict(
            verdict=bloat.RETIRE_DOC, units=self.all_units() + ["0" * 64],
        )])

        self.assertEqual(problem_codes(result), ["bloat-unknown-unit"])

    def test_a_non_identity_extra_unit_fails_shut(self):
        result = self.record([self.verdict(
            verdict=bloat.RETIRE_DOC, units=self.all_units() + [{}],
        )])

        self.assertEqual(problem_codes(result), ["bloat-unknown-unit"])

    def test_each_complete_whole_document_verdict_records(self):
        for verdict, required in self.CASES:
            with self.subTest(verdict=verdict):
                result = self.record([self.verdict(
                    verdict=verdict, units=self.all_units(), **required,
                )])

                self.assertNotIsInstance(
                    result, Invalid, getattr(result, "problems", None)
                )

    def test_passage_remedies_stay_bounded_to_selected_units(self):
        for verdict, proposal in (
            (bloat.CUT, None),
            (bloat.CONDENSE, "Shorter."),
            (bloat.EXTRACT_AND_MOVE, "Moved."),
        ):
            with self.subTest(verdict=verdict):
                overrides = {"verdict": verdict}
                if proposal is not None:
                    overrides["proposal"] = proposal
                if verdict == bloat.EXTRACT_AND_MOVE:
                    overrides["destination"] = "docs/a.md"
                result = self.record([self.verdict(**overrides)])
                self.assertNotIsInstance(
                    result, Invalid, getattr(result, "problems", None)
                )
                self.assertEqual(
                    result.records()[0]["units"],
                    [self.unit("docs/plans/p.md", SHARED)],
                )


class WhatAFindingExplains(RecorderTestCase):
    def test_it_records_the_value_judgment(self):
        result = self.record([self.verdict()])

        self.assertEqual(
            result.records()[0]["evidence"],
            "The living document already states this.",
        )

    def test_a_verdict_without_evidence_is_refused(self):
        result = self.record([self.verdict(evidence="")])

        self.assertIn("bloat-missing-evidence", problem_codes(result))

    def test_it_records_the_global_duplicate_search_that_informed_it(self):
        result = self.record([self.verdict()])

        search = result.records()[0]["duplicate_search"]
        self.assertEqual(search["scope"], "repository")
        self.assertEqual(search["documents_searched"], 3)
        self.assertEqual(search["index_digest"], self.index.digest)
        self.assertEqual(
            [(o["path"], o["line"]) for o in search["here"]],
            [("docs/plans/p.md", 3)],
        )
        self.assertEqual(
            [(o["path"], o["line"]) for o in search["elsewhere"]],
            [("docs/a.md", 3)],
        )

    def test_it_records_the_destination_constraints_that_were_checked(self):
        result = self.record([self.verdict(verdict=bloat.MERGE_DOC)])

        destination = result.records()[0]["destination"]
        self.assertEqual(destination["path"], "docs/a.md")
        self.assertEqual(destination["selected_by"], "index-owner")
        self.assertEqual(destination["kind"], "living")
        self.assertTrue(destination["constraints"]["kind_accepts_content"])


class DestinationsComeFromTheIndex(RecorderTestCase):
    def test_a_duplicate_destination_outside_the_slice_is_named(self):
        chunk = bloat.Chunk(chunk_id="c-x", documents=("docs/plans/p.md",),
                            unit_count=2)

        result = self.record([self.verdict(verdict=bloat.MERGE_DOC)], chunk=chunk)

        self.assertNotIn("docs/a.md", chunk.documents)
        self.assertEqual(result.records()[0]["destination"]["path"], "docs/a.md")

    def test_a_group_whose_units_have_different_owners_is_refused(self):
        # One destination cannot be right for a group owned in two places, and
        # falling back to whatever the worker proposed would be exactly the
        # slice-local guess the index exists to prevent.
        index = build_context_index(self.repo({
            ".doc-lifecycle/registry.json": REGISTRY,
            "docs/a.md": f"# A\n\n{SHARED}\n",
            "docs/b.md": "# B\n\nA second owned claim.\n",
            "docs/plans/p.md": f"# P\n\n{SHARED}\n\nA second owned claim.\n",
        }))
        result = bloat.record_verdicts(index, self.lineage, [{
            "id": "BLOAT-001",
            "verdict": bloat.MERGE_DOC,
            "path": "docs/plans/p.md",
            "units": list(index.document("docs/plans/p.md").units),
            "evidence": "Both claims are stated elsewhere.",
            "destination": "docs/a.md",
        }])

        self.assertEqual(problem_codes(result), ["bloat-destination-ambiguous"])

    def test_a_destination_the_index_contradicts_is_refused(self):
        result = self.record([self.verdict(
            verdict=bloat.MERGE_DOC, destination="docs/guides/g.md"
        )])

        self.assertEqual(
            problem_codes(result), ["bloat-destination-contradicts-index"]
        )

    def test_a_destination_the_index_agrees_with_is_accepted(self):
        result = self.record([self.verdict(
            verdict=bloat.MERGE_DOC, destination="docs/a.md"
        )])

        self.assertEqual(result.records()[0]["destination"]["path"], "docs/a.md")

    def test_a_planning_document_is_never_a_destination(self):
        result = self.record([self.verdict(
            id="BLOAT-002", verdict=bloat.EXTRACT_AND_MOVE,
            path="docs/guides/g.md",
            units=[self.unit("docs/guides/g.md", "Guide prose.")],
            destination="docs/plans/p.md", proposal="Moved line.",
        )])

        self.assertEqual(
            problem_codes(result), ["bloat-destination-kind-ineligible"]
        )

    def test_a_destination_that_is_not_a_document_is_refused(self):
        result = self.record([self.verdict(
            verdict=bloat.EXTRACT_AND_MOVE, path="docs/guides/g.md",
            units=[self.unit("docs/guides/g.md", "Guide prose.")],
            destination="docs/nowhere.md", proposal="Moved line.",
        )])

        self.assertEqual(
            problem_codes(result), ["bloat-destination-not-a-document"]
        )

    def test_a_verdict_that_moves_nothing_may_not_name_a_destination(self):
        result = self.record([self.verdict(destination="docs/a.md")])

        self.assertEqual(problem_codes(result), ["bloat-destination-forbidden"])


class MergingTheDocumentTheIndexOwnsIsRefused(RecorderTestCase):
    """`docs/a.md` (living) owns SHARED; `docs/plans/p.md` (planning) copies
    it. Judging the *owner* itself for MERGE-DOC used to empty the `owners`
    set (`owners = {...} - {path}`) and fall through to the "no other
    occurrence" branch — false, since the index's own `duplicate_search`
    shows the content elsewhere, and worse, a wrong model-proposed
    destination in that slot was silently accepted (`model-proposed`),
    bypassing the index guard. Both directions are refused here instead.
    """

    def test_omitting_a_destination_for_the_owner_is_refused_accurately(self):
        result = self.record([self.verdict(
            verdict=bloat.MERGE_DOC, path="docs/a.md",
            units=list(self.index.document("docs/a.md").units),
        )])

        self.assertEqual(problem_codes(result), ["bloat-destination-self-owner"])
        # The old message claimed no other occurrence existed; the index's
        # own duplicate_search over these units says otherwise.
        message = result.problems[0].message
        self.assertNotIn("found no other occurrence", message)

    def test_a_wrong_destination_for_the_owner_is_refused_not_accepted(self):
        result = self.record([self.verdict(
            verdict=bloat.MERGE_DOC, path="docs/a.md",
            units=list(self.index.document("docs/a.md").units),
            destination="docs/guides/g.md",
        )])

        self.assertEqual(problem_codes(result), ["bloat-destination-self-owner"])


class ContentionIsResolvedByTheIndex(RepoTestCase):
    """Two documents in two chunks, both folding into one living document."""

    def setUp(self):
        self.index = build_context_index(self.repo({
            ".doc-lifecycle/registry.json": REGISTRY,
            "docs/a.md": f"# A\n\n{SHARED}\n\nOwnership is stated once.\n",
            "docs/guides/g.md": "# G\n\nOwnership is stated once.\n",
            "docs/plans/p.md": f"# P\n\n{SHARED}\n",
        }))
        self.lineage = lineage()

    def merge_from(self, path, text):
        chunk = bloat.Chunk(chunk_id="c-" + path, documents=(path,), unit_count=2)
        result = bloat.record_verdicts(self.index, self.lineage, [{
            "id": "BLOAT-" + path,
            "verdict": bloat.MERGE_DOC,
            "path": path,
            "units": list(self.index.document(path).units),
            "evidence": "Duplicates the owning document.",
        }], chunk=chunk)
        self.assertNotIsInstance(result, Invalid, getattr(result, "problems", None))
        return result.records()[0]

    def test_both_chunks_name_the_same_destination(self):
        guide = self.merge_from("docs/guides/g.md", "Ownership is stated once.")
        plan = self.merge_from("docs/plans/p.md", SHARED)

        self.assertEqual(guide["destination"]["path"], "docs/a.md")
        self.assertEqual(plan["destination"]["path"], "docs/a.md")

    def test_each_chunk_sees_the_whole_claimant_list_and_its_own_rank(self):
        guide = self.merge_from("docs/guides/g.md", "Ownership is stated once.")
        plan = self.merge_from("docs/plans/p.md", SHARED)

        claimants = ["docs/guides/g.md", "docs/plans/p.md"]
        self.assertEqual(guide["contention"]["claimants"], claimants)
        self.assertEqual(plan["contention"]["claimants"], claimants)
        self.assertEqual((guide["contention"]["order"], plan["contention"]["order"]),
                         (0, 1))

    def test_the_order_the_chunks_run_in_changes_nothing(self):
        forward = (self.merge_from("docs/guides/g.md", "Ownership is stated once."),
                   self.merge_from("docs/plans/p.md", SHARED))
        backward = (self.merge_from("docs/plans/p.md", SHARED),
                    self.merge_from("docs/guides/g.md", "Ownership is stated once."))

        self.assertEqual(forward, tuple(reversed(backward)))


class ResidueDestinationsAreAuthorizedNotInventoried(RepoTestCase):
    """A distillation's destination is a document that does not exist yet.

    Every other destination names an inventoried document, so the index vouches
    for it. A residue document has nothing to look up — so the checks are the
    ones that can be made about an unwritten path: it authorizes as a
    documentation path inside a declared root, the registry classifies it as a
    kind content may durably live in, and nothing is there yet.
    """

    def setUp(self):
        self.root = self.repo({
            ".doc-lifecycle/registry.json": REGISTRY,
            "docs/a.md": f"# A\n\n{SHARED}\n",
            "docs/guides/g.md": "# G\n\nGuide prose.\n",
            # `> Status: ready`, since `distill()` below defaults its verdict's
            # own status to `ready` and, since #57's review remediation, that
            # must equal the file's own marker or the recorder refuses it.
            "docs/plans/p.md": f"> Status: ready\n\n# P\n\n{SHARED}\n",
            "docs/plans/other.md": "# Other\n\nA second plan.\n",
        })
        self.index = build_context_index(self.root)
        self.lineage = lineage()

    def refusals(self, result):
        """The codes of a refusal — and a readable failure if it recorded.

        A residue destination is a write target, so "it recorded something"
        is the interesting way these tests fail; naming the record it built
        beats an attribute error on a result that has no problems.
        """
        self.assertIsInstance(
            result, Invalid, f"recorded {getattr(result, 'records', tuple)()}"
        )
        return problem_codes(result)

    def distill(self, **overrides):
        entry = {
            "id": "BLOAT-D1",
            "verdict": bloat.DISTILL,
            "path": "docs/plans/p.md",
            "units": list(self.index.document("docs/plans/p.md").units),
            "evidence": "The design landed: src/fees.py:12 states the rate.",
            "status": "ready",
        }
        entry.update(overrides)
        return bloat.record_verdicts(self.index, self.lineage, [entry])

    def test_a_distillation_may_name_a_residue_document_that_does_not_exist_yet(self):
        result = self.distill(destination="docs/decisions.md")

        self.assertNotIsInstance(result, Invalid, getattr(result, "problems", None))
        destination = result.records()[0]["destination"]
        self.assertEqual(destination["path"], "docs/decisions.md")
        self.assertEqual(destination["kind"], "living")
        self.assertEqual(destination["selected_by"], "model-proposed-residue")

    def test_the_record_says_the_residue_document_is_not_inventoried(self):
        result = self.distill(destination="docs/decisions.md")

        constraints = result.records()[0]["destination"]["constraints"]
        self.assertFalse(constraints["is_inventoried_document"])
        self.assertTrue(constraints["is_authorized_new_document"])
        self.assertTrue(constraints["kind_accepts_content"])

    def test_a_distillation_that_names_no_destination_is_still_recorded(self):
        # Retire-only distillation stays legal: the residue may already have
        # landed under its own record.
        result = self.distill()

        self.assertNotIsInstance(result, Invalid, getattr(result, "problems", None))
        self.assertIsNone(result.records()[0]["destination"])

    def test_a_residue_destination_outside_the_declared_roots_is_refused(self):
        result = self.distill(destination="../evil.md")

        self.assertEqual(self.refusals(result), ["bloat-destination-unauthorized"])

    def test_a_residue_destination_traversing_out_of_a_root_is_refused(self):
        result = self.distill(destination="docs/../../etc/evil.md")

        self.assertEqual(self.refusals(result), ["bloat-destination-unauthorized"])

    def test_a_residue_destination_reached_through_a_symlink_is_refused(self):
        outside = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, outside, ignore_errors=True)
        os.symlink(outside, os.path.join(self.root, "docs/elsewhere"))

        result = self.distill(destination="docs/elsewhere/residue.md")

        self.assertEqual(self.refusals(result), ["bloat-destination-unauthorized"])

    def test_a_residue_destination_that_is_an_existing_document_is_refused(self):
        # Create-only, and that is a bound on authority: DISTILL's remedy set
        # includes the span edits, and the applier bounds a positioned edit to
        # an approved passage only on the record's *own* document — so an
        # existing destination would take a delete at any line of it.
        result = self.distill(destination="docs/a.md")

        self.assertEqual(self.refusals(result), ["bloat-destination-occupied"])

    def test_an_existing_planning_document_is_never_a_residue_destination(self):
        result = self.distill(destination="docs/plans/other.md")

        self.assertEqual(self.refusals(result),
                         ["bloat-destination-kind-ineligible"])

    def test_a_residue_destination_already_on_disk_is_refused_even_when_unindexed(self):
        # The index was built before the file appeared, so "not in the
        # inventory" is not enough to conclude the path is free.
        with open(os.path.join(self.root, "docs/decisions.md"), "w",
                  encoding="utf-8") as fh:
            fh.write("# Decisions\n\nAlready here.\n")

        result = self.distill(destination="docs/decisions.md")

        self.assertEqual(self.refusals(result), ["bloat-destination-occupied"])

    def test_a_residue_destination_in_a_planning_location_is_refused(self):
        result = self.distill(destination="docs/plans/residue.md")

        self.assertEqual(self.refusals(result),
                         ["bloat-destination-kind-ineligible"])

    def test_a_residue_destination_no_registry_rule_claims_is_refused(self):
        result = self.distill(destination="docs/deep/residue.md")

        self.assertEqual(self.refusals(result), ["bloat-destination-unclassified"])

    def test_a_residue_destination_that_is_the_artifact_itself_is_refused(self):
        result = self.distill(destination="docs/plans/p.md")

        self.assertEqual(self.refusals(result), ["bloat-destination-is-source"])

    def test_a_verdict_that_moves_nothing_still_may_not_name_a_destination(self):
        result = self.distill(verdict=bloat.CUT, status=None,
                              destination="docs/decisions.md")

        self.assertEqual(self.refusals(result), ["bloat-destination-forbidden"])


class ResidueClassificationHasThreeLegs(RepoTestCase):
    """Closed-world classification refuses more than an unclaimed path.

    `residue_destination_ineligibility` refuses a destination when *any* of
    three things holds: no rule claims it, a rule claims it but the path is not
    a document (wrong extension), or a rule claims it but an exclude covers it.
    The unclaimed leg is exercised elsewhere; these two guard the other legs,
    so collapsing the condition to `rule is None` fails here rather than
    silently letting an excluded or non-document destination be authored.
    """

    # A rule classifies docs/vendor/*.md, but an exclude covers docs/vendor;
    # a rule classifies everything under docs/notes, catching a non-.md file.
    REGISTRY = """{
  "schema_version": 1,
  "roots": ["docs"],
  "sets": ["plans"],
  "exclude": ["docs/vendor"],
  "rules": [
    {"glob": "docs/*.md", "kind": "living"},
    {"glob": "docs/plans/*.md", "kind": "planning", "set": "plans"},
    {"glob": "docs/vendor/*.md", "kind": "living"},
    {"glob": "docs/notes/*", "kind": "living"}
  ]
}
"""

    def setUp(self):
        self.root = self.repo({
            ".doc-lifecycle/registry.json": self.REGISTRY,
            # `distill()` below always asserts `status: "ready"`, so the file
            # must carry that marker or the file-bound cross-check refuses it.
            "docs/plans/p.md": f"> Status: ready\n\n# P\n\n{SHARED}\n",
        })
        self.index = build_context_index(self.root)
        self.lineage = lineage()

    def distill(self, destination):
        return bloat.record_verdicts(self.index, self.lineage, [{
            "id": "BLOAT-D1",
            "verdict": bloat.DISTILL,
            "path": "docs/plans/p.md",
            "units": list(self.index.document("docs/plans/p.md").units),
            "evidence": "The design landed: src/fees.py:12 states the rate.",
            "status": "ready",
            "destination": destination,
        }])

    def test_a_destination_a_rule_claims_but_an_exclude_covers_is_refused(self):
        # docs/vendor/*.md classifies as a living document, but docs/vendor is
        # excluded — so the path is not documentation the corpus reads.
        result = self.distill("docs/vendor/residue.md")

        self.assertIsInstance(result, Invalid, getattr(result, "records", None))
        self.assertEqual(problem_codes(result),
                         ["bloat-destination-unclassified"])

    def test_a_destination_a_rule_claims_but_is_not_a_document_is_refused(self):
        # docs/notes/* classifies as living, but a .txt file is not a document
        # under the registry's extensions — residue is never authored there.
        result = self.distill("docs/notes/data.txt")

        self.assertIsInstance(result, Invalid, getattr(result, "records", None))
        self.assertEqual(problem_codes(result),
                         ["bloat-destination-unclassified"])


class BulkJudgmentsAreEnumerated(RepoTestCase):
    def setUp(self):
        self.root = self.repo({
            ".doc-lifecycle/registry.json": REGISTRY,
            "docs/a.md": "# A\n\nAlpha.\n",
            "docs/plans/p1.md": "# P1\n\nOne.\n",
            "docs/plans/p2.md": "# P2\n\nTwo.\n",
            "docs/plans/p3.md": "# P3\n\nThree.\n",
        })
        self.index = build_context_index(self.root)
        self.lineage = lineage()

    def record(self, **overrides):
        entry = {
            "id": "BLOAT-BULK",
            "verdict": bloat.RETIRE_DOC,
            "evidence": "The tiered-fee work merged; these plans are spent.",
            "scope": {"set": "plans"},
        }
        entry.update(overrides)
        return bloat.record_verdicts(self.index, self.lineage, [entry])

    def test_one_bulk_judgment_becomes_one_finding_per_affected_file(self):
        result = self.record()

        self.assertEqual(
            [r["path"] for r in result.records()],
            ["docs/plans/p1.md", "docs/plans/p2.md", "docs/plans/p3.md"],
        )

    def test_every_finding_carries_the_enumeration_it_came_from(self):
        result = self.record()

        scope = result.records()[0]["scope"]
        self.assertEqual(scope["member_count"], 3)
        self.assertEqual(scope["rule"], {"set": "plans"})
        self.assertEqual(len(scope["members"]), 3)

    def test_a_sample_never_narrows_the_enumeration(self):
        result = self.record(sample=["docs/plans/p1.md"])

        self.assertEqual(len(result.records()), 3)
        scope = result.records()[0]["scope"]
        self.assertEqual(scope["sample"], ["docs/plans/p1.md"])
        self.assertTrue(scope["sample_is_not_authority"])

    def test_an_asserted_file_list_is_refused_outright(self):
        result = self.record(files=["docs/plans/p1.md", "docs/plans/p2.md"])

        self.assertEqual(problem_codes(result), ["bloat-sampling-not-authority"])

    def test_a_sample_on_a_single_document_verdict_is_refused(self):
        result = bloat.record_verdicts(self.index, self.lineage, [{
            "id": "BLOAT-1", "verdict": bloat.CUT, "path": "docs/a.md",
            "units": list(self.index.document("docs/a.md").units[:1]),
            "evidence": "Restates the code.", "sample": ["docs/a.md"],
        }])

        self.assertEqual(problem_codes(result), ["bloat-sampling-not-authority"])

    def test_a_sample_naming_a_file_outside_the_scope_is_refused(self):
        result = self.record(sample=["docs/a.md"])

        self.assertEqual(problem_codes(result), ["bloat-sample-outside-scope"])

    def test_an_empty_member_is_named_rather_than_quietly_dropped(self):
        # A finding binds to assertion units, and an empty document has none.
        # Dropping it would break "every affected file"; the confusing generic
        # refusal it used to raise named neither the member nor the fix.
        with open(os.path.join(self.root, "docs/plans/p4.md"), "w",
                  encoding="utf-8") as fh:
            fh.write("")
        self.index = build_context_index(self.root)

        result = self.record()

        self.assertEqual(problem_codes(result), ["bloat-scope-member-empty"])
        self.assertIn("docs/plans/p4.md", result.problems[0].message)

    def test_only_retirement_may_be_a_bulk_judgment(self):
        result = self.record(verdict=bloat.CONDENSE)

        self.assertEqual(problem_codes(result), ["bloat-scope-verdict-ineligible"])

    def test_a_bulk_refusal_names_the_verdicts_id_alongside_the_index(self):
        result = self.record(verdict=bloat.CONDENSE, id="P9")

        problem = result.problems[0]
        self.assertIn("verdicts[0]", problem.location)
        self.assertIn("id='P9'", problem.location)


class LifecycleStateIsFileBound(RecorderTestCase):
    """A DISTILL verdict's `status` is checked against the file, not trusted.

    The file is the authority; the model is a reporter. Three planning-
    document variants replace `RecorderTestCase`'s single `docs/plans/p.md`:
    one whose own `> Status:` marker says `ready`, one that says
    `pending-implementation`, and one carrying no marker at all (the
    fail-safe default). A verdict's `status` must equal whichever of those
    the file actually states.
    """

    def setUp(self):
        self.index = build_context_index(self.repo({
            ".doc-lifecycle/registry.json": REGISTRY,
            "docs/a.md": f"# A\n\n{SHARED}\n",
            "docs/guides/g.md": "# G\n\nGuide prose.\n",
            "docs/plans/ready.md": f"> Status: ready\n\n# P\n\n{SHARED}\n",
            "docs/plans/pending.md": (
                f"> Status: pending-implementation\n\n# P\n\n{SHARED}\n"
            ),
            "docs/plans/none.md": f"# P\n\n{SHARED}\n",
        }))
        self.lineage = lineage()

    def distill(self, path, **overrides):
        entry = {
            "id": "BLOAT-D1",
            "verdict": bloat.DISTILL,
            "path": path,
            "units": list(self.index.document(path).units),
            "evidence": "The design landed: src/fees.py:12 states the rate.",
        }
        entry.update(overrides)
        return self.record([entry])

    def test_ready_verdict_against_pending_marker_is_refused(self):
        result = self.distill("docs/plans/pending.md", status="ready")

        self.assertIn("bloat-status-not-file-bound", problem_codes(result))

    def test_ready_verdict_against_absent_marker_is_refused(self):
        # No marker reads as pending-implementation, so the model reporting
        # `ready` is the same mismatch as reporting it against an explicit
        # pending marker.
        result = self.distill("docs/plans/none.md", status="ready")

        self.assertIn("bloat-status-not-file-bound", problem_codes(result))

    def test_ready_verdict_against_ready_marker_records(self):
        # The honest path: the file says ready, the verdict says ready.
        result = self.distill("docs/plans/ready.md", status="ready")

        self.assertNotIsInstance(result, Invalid, getattr(result, "problems", None))
        self.assertEqual(result.records()[0]["status"], "ready")

    def test_pending_verdict_against_absent_marker_records(self):
        # The fail-safe default: no marker == pending-implementation, and a
        # verdict that honestly reports that is recorded, not refused.
        result = self.distill("docs/plans/none.md", status="pending-implementation")

        self.assertNotIsInstance(result, Invalid, getattr(result, "problems", None))
        self.assertEqual(result.records()[0]["status"], "pending-implementation")

    def test_pending_verdict_against_ready_marker_is_refused(self):
        # Symmetry: the model may not hold a plan back either — the record
        # must state what the file states, in both directions.
        result = self.distill("docs/plans/ready.md", status="pending-implementation")

        self.assertIn("bloat-status-not-file-bound", problem_codes(result))

    def test_the_refusal_names_the_verdicts_id_and_path_not_only_the_index(self):
        # `verdicts[N]` alone is a position in the *assembled* envelope: a
        # chunk worker's own id is renumbered on assembly
        # (output-contract.md's `B1..Bn`), so an index by itself names
        # neither an id a reviewer recognizes nor the document in question —
        # re-prompting the right chunk meant opening the envelope and
        # counting. The location must carry both alongside the index.
        result = self.distill("docs/plans/pending.md", id="P7", status="ready")

        problem = result.problems[0]
        self.assertEqual(problem.code, "bloat-status-not-file-bound")
        self.assertIn("verdicts[0]", problem.location)
        self.assertIn("id='P7'", problem.location)
        self.assertIn("path='docs/plans/pending.md'", problem.location)

    def test_the_refusal_does_not_cite_a_file_the_plugin_never_ships(self):
        # CONTEXT.md exists only at this repo's root, for the #57
        # re-architecture's own vocabulary — it is never distributed with the
        # plugin, so a shipped refusal citing it points a consumer nowhere.
        result = self.distill("docs/plans/pending.md", status="ready")

        self.assertNotIn("CONTEXT.md", result.problems[0].message)


class RefusalsAreExhaustive(RecorderTestCase):
    def test_a_unit_that_is_not_in_the_document_is_refused(self):
        result = self.record([self.verdict(
            path="docs/guides/g.md",
            units=[self.unit("docs/plans/p.md", SHARED)],
        )])

        self.assertEqual(problem_codes(result), ["bloat-unknown-unit"])

    def test_a_document_outside_the_chunk_is_refused(self):
        chunk = bloat.Chunk(chunk_id="c-x", documents=("docs/a.md",), unit_count=2)

        result = self.record([self.verdict()], chunk=chunk)

        self.assertEqual(problem_codes(result), ["bloat-document-outside-chunk"])

    def test_an_unknown_verdict_is_refused(self):
        result = self.record([self.verdict(verdict="DELETE")])

        self.assertEqual(problem_codes(result), ["bloat-unknown-verdict"])

    def test_a_distill_verdict_needs_a_lifecycle_status(self):
        result = self.record([self.verdict(verdict=bloat.DISTILL)])

        self.assertEqual(problem_codes(result), ["bloat-unknown-status"])

    def test_a_distill_verdict_against_a_non_planning_document_is_refused(self):
        # DISTILL is the planning-artifact verdict — nothing else validated
        # that a source path is actually planning-kind, so a verdict naming a
        # living document must be refused before its status is even checked
        # (docs/a.md carries no `> Status:` marker of its own; a
        # bloat-status-not-file-bound refusal here would misreport a living
        # document as if it were an unmarked plan).
        result = self.record([self.verdict(
            verdict=bloat.DISTILL,
            path="docs/a.md",
            units=list(self.index.document("docs/a.md").units),
            status="ready",
        )])

        self.assertEqual(problem_codes(result), ["bloat-distill-not-planning"])

    def test_a_condense_verdict_needs_its_replacement_line(self):
        result = self.record([self.verdict(verdict=bloat.CONDENSE)])

        self.assertEqual(problem_codes(result), ["bloat-proposal-required"])

    def test_two_verdicts_sharing_an_id_are_refused(self):
        result = self.record([self.verdict(), self.verdict()])

        self.assertIn("bloat-duplicate-id", problem_codes(result))

    def test_every_problem_in_one_response_is_reported_at_once(self):
        result = self.record([
            self.verdict(id="BLOAT-1", verdict="DELETE"),
            self.verdict(id="BLOAT-2", path="docs/nowhere.md"),
            self.verdict(id="BLOAT-3", evidence=""),
        ])

        self.assertEqual(
            problem_codes(result),
            ["bloat-missing-evidence", "bloat-unknown-document",
             "bloat-unknown-verdict"],
        )

    def test_any_problem_records_nothing(self):
        result = self.record([self.verdict(), self.verdict(id="X", verdict="DELETE")])

        self.assertIsInstance(result, Invalid)


class CoverageIsDeclared(RepoTestCase):
    def test_an_unindexable_document_is_carried_as_an_unexamined_scope(self):
        index = build_context_index(self.repo({
            ".doc-lifecycle/registry.json": REGISTRY,
            "docs/a.md": "# A\n\nAlpha.\n",
            "docs/notes/stray.md": "# Stray\n\nUnclassified.\n",
        }))

        result = bloat.record_verdicts(index, lineage(), [])

        self.assertEqual(
            [i["scope"] for i in result.incomplete], ["docs/notes/stray.md"]
        )


class LoadingBloatVerdicts(RepoTestCase):
    """`load_bloat_verdicts`'s file-reader-only seam.

    Mirrors `drift.load_verdicts` exactly: reading is a separate failure from
    what the payload says, and this function does not look inside the payload
    at all — that discipline moved to `audit_bloat` (`AuditBloatComposesTheReport`
    below), the same split drift draws between `load_verdicts` and
    `_verdict_entries`, so every call path into `audit_bloat` enforces it, not
    just this file loader's.
    """

    def path(self, text):
        root = self.repo({"verdicts.json": text})
        return os.path.join(root, "verdicts.json")

    def test_a_missing_file_is_unreadable(self):
        result = bloat.load_bloat_verdicts(
            os.path.join(tempfile.mkdtemp(), "absent.json")
        )

        self.assertIsInstance(result, Invalid)
        self.assertEqual(
            [p.code for p in result.problems], ["bloat-verdicts-unreadable"]
        )

    def test_unparseable_json_is_unreadable(self):
        result = bloat.load_bloat_verdicts(self.path("{ not json"))

        self.assertEqual(
            [p.code for p in result.problems], ["bloat-verdicts-unreadable"]
        )

    def test_a_well_shaped_file_returns_the_envelope_unchanged(self):
        result = bloat.load_bloat_verdicts(
            self.path('{"schema_version": 1, "verdicts": [{"id": "B-1"}]}')
        )

        self.assertEqual(
            result, {"schema_version": 1, "verdicts": [{"id": "B-1"}]}
        )

    def test_a_malformed_envelope_is_returned_unchanged_not_refused(self):
        """Shape checking is not this function's job — `audit_bloat` owns it,
        so nothing here can be routed around by a hand-built envelope."""
        result = bloat.load_bloat_verdicts(self.path("[]"))

        self.assertEqual(result, [])


class AuditBloatComposesTheReport(GitRepoTestCase):
    """`audit_bloat`'s one-call composition: index, lineage, verdicts, report.

    A real git repository, exactly as `TheChunkCache` below uses — lineage
    construction reads the repository's actual base commit, and a mocked one
    would prove nothing about it.
    """

    def corpus(self):
        return self.git_repo({
            ".doc-lifecycle/registry.json": REGISTRY,
            "docs/a.md": f"# A\n\n{SHARED}\n",
            "docs/plans/p.md": f"# P\n\n{SHARED}\n",
        })

    def verdict(self, repo, **overrides):
        index = build_context_index(repo)
        by_text = {u.text: u.digest for u in index.units}
        entry = {
            "id": "BLOAT-001",
            "verdict": bloat.CUT,
            "path": "docs/plans/p.md",
            "units": [by_text[SHARED]],
            "evidence": "The living document already states this.",
        }
        entry.update(overrides)
        return entry

    def envelope(self, repo, *verdicts, **overrides):
        entries = list(verdicts) or [self.verdict(repo)]
        plan = bloat.plan_repository_chunks(repo)
        outcomes = []
        for chunk in plan.chunks:
            selected = [entry for entry in entries
                        if entry.get("scope") is not None
                        or entry.get("path") in chunk.documents]
            outcomes.append(bloat.ChunkOutcome.complete(
                chunk.chunk_id, selected,
            ))
        payload = bloat.assemble_bloat_input(plan, outcomes).to_dict()
        payload.update(overrides)
        return payload

    def test_a_valid_verdict_list_yields_a_report_with_its_code(self):
        repo = self.corpus()

        result = bloat.audit_bloat(repo, self.envelope(repo))

        self.assertIsInstance(result, Report, result)
        self.assertEqual(result.records[0].to_dict()["code"], bloat.CUT)

    def test_the_lineage_carries_the_registry_digest(self):
        repo = self.corpus()
        index = build_context_index(repo)

        result = bloat.audit_bloat(repo, self.envelope(repo))

        self.assertEqual(result.lineage.registry_digest, index.registry_digest)

    def test_the_report_validates_with_schema_version_and_hex_digests(self):
        repo = self.corpus()

        result = bloat.audit_bloat(repo, self.envelope(repo))

        payload = result.to_dict()
        self.assertEqual(payload["schema_version"], ARTIFACT_SCHEMA_VERSION)
        digest = payload["records"][0]["digest"]
        self.assertEqual(len(digest), 64)
        int(digest, 16)  # raises ValueError if not hex

    def test_invalid_verdicts_return_invalid_preserving_recorder_codes(self):
        repo = self.corpus()

        result = bloat.audit_bloat(
            repo, self.envelope(repo, self.verdict(repo, evidence=""))
        )

        self.assertIsInstance(result, Invalid)
        self.assertIn("bloat-missing-evidence", [p.code for p in result.problems])

    def test_incomplete_whole_document_verdicts_are_refused_before_report_production(self):
        repo = self.corpus()
        for verdict in (bloat.RETIRE_DOC, bloat.DISTILL, bloat.MERGE_DOC):
            with self.subTest(verdict=verdict):
                overrides = {"verdict": verdict}
                if verdict == bloat.DISTILL:
                    overrides["status"] = "pending-implementation"
                result = bloat.audit_bloat(
                    repo, self.envelope(repo, self.verdict(repo, **overrides))
                )
                self.assertIsInstance(result, Invalid, result)
                self.assertEqual(
                    [p.code for p in result.problems],
                    ["bloat-whole-document-units-incomplete"],
                )

    def test_a_bare_list_is_not_a_valid_envelope(self):
        """`audit_bloat` takes the envelope, not a bare list — an in-process
        caller that hand-unwraps `load_bloat_verdicts`' payload and skips
        straight to a list is refused here, not silently accepted."""
        repo = self.corpus()

        result = bloat.audit_bloat(repo, [self.verdict(repo)])

        self.assertIsInstance(result, Invalid)
        self.assertIn(
            "bloat-verdicts-invalid-shape", [p.code for p in result.problems]
        )

    def test_an_envelope_missing_the_verdicts_key_is_invalid(self):
        repo = self.corpus()

        result = bloat.audit_bloat(repo, {"not": "verdicts"})

        self.assertIsInstance(result, Invalid)
        self.assertIn(
            "bloat-verdicts-invalid-shape", [p.code for p in result.problems]
        )

    def test_an_unexpected_top_level_key_is_invalid(self):
        repo = self.corpus()

        result = bloat.audit_bloat(repo, self.envelope(repo, extra=True))

        self.assertIsInstance(result, Invalid)
        self.assertIn(
            "bloat-verdicts-invalid-shape", [p.code for p in result.problems]
        )

    def test_an_unsupported_schema_version_is_invalid(self):
        repo = self.corpus()

        result = bloat.audit_bloat(repo, self.envelope(repo, schema_version=99))

        self.assertIsInstance(result, Invalid)
        self.assertIn(
            "bloat-verdicts-invalid-shape", [p.code for p in result.problems]
        )

    def test_a_schema_version_that_is_not_an_integer_is_invalid(self):
        """`True == 1` and `1.0 == 1` in Python, but not in a schema. A bare
        `!=` against the supported version let both through, so an envelope
        declaring either passed a check whose own message promises it read an
        *integer* version. Found by review on the split stack."""
        repo = self.corpus()
        for version in (True, 1.0, "1"):
            with self.subTest(schema_version=version):
                result = bloat.audit_bloat(
                    repo, self.envelope(repo, schema_version=version)
                )

                self.assertIsInstance(result, Invalid)
                self.assertIn(
                    "bloat-verdicts-invalid-shape",
                    [p.code for p in result.problems],
                )

    def test_schema_version_is_optional(self):
        repo = self.corpus()
        payload = self.envelope(repo)
        del payload["schema_version"]

        result = bloat.audit_bloat(repo, payload)

        self.assertIsInstance(result, Report, result)

    def test_completion_from_a_stale_index_is_refused(self):
        repo = self.corpus()
        payload = self.envelope(repo)
        completion = payload["completion"]
        plan = completion["plan"]
        plan["index_digest"] = "0" * 64
        plan["digest"] = sha256_canonical({
            "schema_version": plan["schema_version"],
            "index_digest": plan["index_digest"],
            "max_documents": plan["max_documents"],
            "max_units": plan["max_units"],
            "chunks": plan["chunks"],
        })
        completion["digest"] = sha256_canonical({
            "plan_digest": plan["digest"],
            "chunks": completion["chunks"],
            "verdicts": payload["verdicts"],
        })

        result = bloat.audit_bloat(repo, payload)

        self.assertIsInstance(result, Invalid)
        self.assertIn("bloat-completion-plan-mismatch",
                      [problem.code for problem in result.problems])

    def test_tampered_completion_digest_is_refused(self):
        repo = self.corpus()
        payload = self.envelope(repo)
        payload["completion"]["chunks"][0]["reason"] = "edited later"

        result = bloat.audit_bloat(repo, payload)

        self.assertIsInstance(result, Invalid)
        self.assertIn("bloat-completion-digest-mismatch",
                      [problem.code for problem in result.problems])

    def test_duplicate_chunk_is_refused_even_with_recomputed_digests(self):
        repo = self.corpus()
        payload = self.envelope(repo)
        completion = payload["completion"]
        completion["chunks"].append(dict(completion["chunks"][0]))
        completion["digest"] = sha256_canonical({
            "plan_digest": completion["plan"]["digest"],
            "chunks": completion["chunks"],
            "verdicts": payload["verdicts"],
        })

        result = bloat.audit_bloat(repo, payload)

        self.assertIsInstance(result, Invalid)
        self.assertIn("bloat-completion-chunks-mismatch",
                      [problem.code for problem in result.problems])

    def test_repartitioned_plan_is_refused_after_all_digests_are_recomputed(self):
        repo = self.corpus()
        payload = self.envelope(repo)
        completion = payload["completion"]
        plan = completion["plan"]
        self.assertEqual(len(plan["chunks"]), 2)
        plan["chunks"].reverse()
        completion["chunks"].reverse()
        plan["digest"] = sha256_canonical({
            "schema_version": plan["schema_version"],
            "index_digest": plan["index_digest"],
            "max_documents": plan["max_documents"],
            "max_units": plan["max_units"],
            "chunks": plan["chunks"],
        })
        completion["digest"] = sha256_canonical({
            "plan_digest": plan["digest"],
            "chunks": completion["chunks"],
            "verdicts": payload["verdicts"],
        })

        result = bloat.audit_bloat(repo, payload)

        self.assertIsInstance(result, Invalid)
        self.assertIn("bloat-completion-plan-mismatch",
                      [problem.code for problem in result.problems])

    def test_changed_verdict_content_is_refused_after_outer_digest_is_recomputed(self):
        repo = self.corpus()
        payload = self.envelope(repo)
        payload["verdicts"][0]["evidence"] = "attacker changed the judgment"
        completion = payload["completion"]
        completion["digest"] = sha256_canonical({
            "plan_digest": completion["plan"]["digest"],
            "chunks": completion["chunks"],
            "verdicts": payload["verdicts"],
        })

        result = bloat.audit_bloat(repo, payload)

        self.assertIsInstance(result, Invalid)
        self.assertIn("bloat-completion-result-mismatch",
                      [problem.code for problem in result.problems])

    def test_malformed_completion_chunk_fails_shut_without_a_traceback(self):
        repo = self.corpus()
        payload = self.envelope(repo)
        payload["completion"]["chunks"] = [{}]

        result = bloat.audit_bloat(repo, payload)

        self.assertIsInstance(result, Invalid)
        self.assertIn("bloat-completion-invalid-shape",
                      [problem.code for problem in result.problems])

    def test_an_invalid_registry_invalidates_the_run(self):
        repo = self.git_repo({
            ".doc-lifecycle/registry.json": "{ not json",
            "docs/a.md": "# A\n\nAlpha.\n",
        })

        result = bloat.audit_bloat(repo, {"verdicts": []})

        self.assertIsInstance(result, Invalid)

    def test_a_cut_records_digest_is_mintable_by_a_human(self):
        """End-to-end mintability: this is what makes fixing-docs' step 1 real
        for bloat, exactly as it already is for drift."""
        repo = self.corpus()
        report = bloat.audit_bloat(repo, self.envelope(repo))
        self.assertIsInstance(report, Report, report)
        digest = report.records[0].digest

        approval = mint_approval_set(
            report, [digest], repo_root=repo,
            minter=Minter(kind=MINTER_HUMAN, id="reviewer@example.com"),
        )

        self.assertIsInstance(approval, ApprovalSet, approval)
        self.assertEqual([r.digest for r in approval.records], [digest])


class TheChunkCache(GitRepoTestCase):
    """Cache revalidation is a comparison against a real repository.

    Reuses `report_test.GitRepoTestCase` — the same real-git base the cache's
    own suite uses — because a mocked repository would prove nothing about
    freshness.
    """

    def setUp(self):
        self.root = self.git_repo({
            ".doc-lifecycle/registry.json": REGISTRY,
            "docs/a.md": "# A\n\nAlpha.\n",
            "docs/b.md": "# B\n\nBeta.\n",
        })
        self.index = build_context_index(self.root)
        self.chunk = bloat.plan_chunks(self.index).chunks[0]
        self.cache_dir = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.cache_dir, ignore_errors=True)

    def load(self, state):
        return bloat.load_chunk(
            self.cache_dir, self.root, self.index, state, self.chunk
        )

    def current(self, **overrides):
        state, problems = current_lineage(
            self.root, audit_config_digest=overrides.pop("audit_config_digest", "2" * 64)
        )
        self.assertEqual(problems, ())
        return dict(state, **overrides)

    def test_an_unseen_chunk_is_all_misses(self):
        cached = self.load(self.current())

        self.assertEqual(cached.misses, ("docs/a.md", "docs/b.md"))
        self.assertEqual(cached.hits, {})

    def test_a_stored_chunk_result_is_reused(self):
        state = self.current()
        bloat.store_chunk(self.cache_dir, self.index, state, self.chunk,
                          {"docs/a.md": [{"id": "B-1", "verdict": bloat.CUT}]})

        cached = self.load(state)

        self.assertEqual(cached.misses, ("docs/b.md",))
        self.assertEqual(cached.hits["docs/a.md"][0]["verdict"], bloat.CUT)

    def test_a_document_judged_clean_is_not_re_judged(self):
        state = self.current()
        bloat.store_chunk(self.cache_dir, self.index, state, self.chunk,
                          {"docs/a.md": []})

        self.assertEqual(self.load(state).hits["docs/a.md"], ())

    def test_a_changed_audit_configuration_reruns_the_chunk(self):
        state = self.current()
        bloat.store_chunk(self.cache_dir, self.index, state, self.chunk,
                          {"docs/a.md": [], "docs/b.md": []})
        self.assertEqual(self.load(state).misses, ())

        rerun = self.load(self.current(audit_config_digest="9" * 64))

        self.assertEqual(rerun.misses, ("docs/a.md", "docs/b.md"))

    def test_a_ruleset_bump_reruns_the_chunk(self):
        state = self.current()
        bloat.store_chunk(self.cache_dir, self.index, state, self.chunk,
                          {"docs/a.md": [], "docs/b.md": []})

        rerun = self.load(self.current(ruleset_version=RULESET_VERSION + 1))

        self.assertEqual(rerun.misses, ("docs/a.md", "docs/b.md"))

    def test_a_change_elsewhere_in_the_corpus_reruns_the_chunk(self):
        state = self.current()
        bloat.store_chunk(self.cache_dir, self.index, state, self.chunk,
                          {"docs/a.md": [], "docs/b.md": []})
        self.assertEqual(self.load(state).misses, ())

        # A third document appears. `docs/a.md`'s own bytes are untouched, but
        # what "occurs nowhere else" means has changed, so its cached bloat
        # verdict cannot stand.
        with open(os.path.join(self.root, "docs/c.md"), "w", encoding="utf-8") as fh:
            fh.write("# C\n\nGamma.\n")
        self.index = build_context_index(self.root)

        rerun = self.load(self.current())

        self.assertIn("docs/a.md", rerun.misses)

    def test_storing_a_document_outside_the_chunk_is_a_programming_error(self):
        with self.assertRaises(ValueError):
            bloat.store_chunk(
                self.cache_dir, self.index, self.current(),
                bloat.Chunk(chunk_id="c-x", documents=("docs/a.md",), unit_count=2),
                {"docs/b.md": []},
            )


if __name__ == "__main__":
    unittest.main(verbosity=2)
