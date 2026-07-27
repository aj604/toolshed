#!/usr/bin/env python3
"""Scenario two (issue #63): the document model over the acceptance fixture.

Seams, per the engine's convention (`plugins/doc-lifecycle/engine/README.md`):
`segment_document()`, `record_classifications()`, and `build_finding()` as
library calls, and `python3 -m doclifecycle segment` as a subprocess — over the
REAL temporary git repository scenario one builds on, with its real commits,
real symlinks, and real prompt-injection content.

What it holds that a synthetic one-off cannot: the four assertion classes are
distinguished on documents a person would recognize, the injected instructions
in the fixture's living document land in a unit that structurally cannot carry
a claim, and finding digests are bound to a lineage read from actual git.

Run: python3 tests/engine/acceptance/scenario_two_test.py
"""

import json
import os
import subprocess
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import fixture  # noqa: E402  (the acceptance fixture builder)
from support import ENGINE  # noqa: E402  (also puts the engine on sys.path)

from doclifecycle.finding import (  # noqa: E402
    FACTUAL,
    NON_ASSERTIVE,
    NORMATIVE,
    RATIONALE,
    build_finding,
    record_classifications,
)
from doclifecycle.report import (  # noqa: E402
    EvidenceBoundary,
    Lineage,
    current_lineage,
)
from doclifecycle.results import Invalid  # noqa: E402
from doclifecycle.segment import segment_document  # noqa: E402

CONFIG_DIGEST = "c" * 64


def run_cli(*argv, cwd=None):
    env = dict(os.environ, PYTHONPATH=ENGINE)
    return subprocess.run(
        [sys.executable, "-m", "doclifecycle", *argv],
        capture_output=True, text=True, env=env, cwd=cwd,
    )


def fixture_lineage(repo):
    """The lineage a fresh report about the fixture would carry."""
    current, problems = current_lineage(repo, audit_config_digest=CONFIG_DIGEST)
    assert not problems, problems
    return Lineage(
        audit_mode="full",
        evidence_boundary=EvidenceBoundary(("src/**",)),
        **current,
    )


def by_text(segmentation):
    return {unit.text: unit for unit in segmentation.units}


class SegmentingTheFixturesDocuments(fixture.AcceptanceFixtureTestCase):
    def test_the_living_document_splits_into_its_prose_units(self):
        repo = self.build_fixture()

        result = segment_document(repo, fixture.LIVING_DOC)

        self.assertEqual(
            [(u.kind, u.text) for u in result.units][:4],
            [
                ("heading", fixture.LIVING_HEADING),
                ("sentence", fixture.LIVING_FACTUAL),
                ("sentence", fixture.LIVING_NORMATIVE),
                ("sentence", fixture.LIVING_RATIONALE),
            ],
        )
        self.assertEqual([u.kind for u in result.units[4:]], ["html_block"])

    def test_a_hard_wrapped_claim_is_one_unit(self):
        """The factual claim is wrapped across two lines in the file."""
        repo = self.build_fixture()

        result = segment_document(repo, fixture.LIVING_DOC)

        self.assertIn(fixture.LIVING_FACTUAL, by_text(result))

    def test_it_carries_the_registered_kind_of_each_document(self):
        repo = self.build_fixture()

        for path, kind in (
            (fixture.LIVING_DOC, "living"),
            (fixture.NARRATIVE_DOC, "narrative"),
            (fixture.PLANNING_DOC, "planning"),
        ):
            with self.subTest(path):
                self.assertEqual(segment_document(repo, path).kind, kind)

    def test_the_narrative_as_of_anchor_is_its_own_unit(self):
        repo = self.build_fixture()

        result = segment_document(repo, fixture.NARRATIVE_DOC)

        self.assertEqual(
            by_text(result)[fixture.NARRATIVE_ANCHOR].kind, "block_quote"
        )

    def test_segmenting_the_fixture_twice_is_byte_identical(self):
        repo = self.build_fixture()

        for path in (fixture.LIVING_DOC, fixture.NARRATIVE_DOC,
                     fixture.PLANNING_DOC):
            with self.subTest(path):
                self.assertEqual(
                    segment_document(repo, path).to_dict(),
                    segment_document(repo, path).to_dict(),
                )

    def test_a_symlinked_path_is_never_opened(self):
        repo = self.build_fixture()

        result = segment_document(repo, fixture.SYMLINK_ABS_DOC)

        self.assertIsInstance(result, Invalid)
        self.assertEqual(
            [p.code for p in result.problems], ["document-not-inventoried"]
        )

    def test_the_command_agrees_with_the_library(self):
        repo = self.build_fixture()

        result = run_cli("segment", "--repo", repo, "--path", fixture.LIVING_DOC)

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(
            json.loads(result.stdout),
            segment_document(repo, fixture.LIVING_DOC).to_dict(),
        )


class TheFourAssertionClasses(fixture.AcceptanceFixtureTestCase):
    """The fourth acceptance criterion, on the fixture's own documents."""

    def living_classes(self, repo):
        segmentation = segment_document(repo, fixture.LIVING_DOC)
        units = by_text(segmentation)
        return segmentation, [
            {"unit": units[fixture.LIVING_FACTUAL].digest,
             "assertion_class": FACTUAL},
            {"unit": units[fixture.LIVING_NORMATIVE].digest,
             "assertion_class": NORMATIVE},
            {"unit": units[fixture.LIVING_RATIONALE].digest,
             "assertion_class": RATIONALE},
        ]

    def test_factual_normative_and_rationale_prose_are_distinguished(self):
        repo = self.build_fixture()
        segmentation, entries = self.living_classes(repo)

        result = record_classifications(segmentation, entries)

        units = by_text(segmentation)
        self.assertEqual(result.by_unit(), {
            units[fixture.LIVING_FACTUAL].digest: FACTUAL,
            units[fixture.LIVING_NORMATIVE].digest: NORMATIVE,
            units[fixture.LIVING_RATIONALE].digest: RATIONALE,
        })

    def test_connective_prose_is_recorded_as_non_assertive(self):
        repo = self.build_fixture()
        segmentation = segment_document(repo, fixture.NARRATIVE_DOC)
        units = by_text(segmentation)
        entries = [
            {"unit": u.digest,
             "assertion_class": NON_ASSERTIVE if u.text != fixture.NARRATIVE_ANCHOR
             else FACTUAL}
            for u in segmentation.units if u.assertion_capable
        ]

        result = record_classifications(segmentation, entries)

        self.assertEqual(
            result.by_unit()[units[fixture.NARRATIVE_NON_ASSERTIVE].digest],
            NON_ASSERTIVE,
        )

    def test_structural_prose_cannot_carry_a_claim(self):
        repo = self.build_fixture()
        segmentation = segment_document(repo, fixture.LIVING_DOC)

        structural = [u for u in segmentation.units if not u.assertion_capable]

        self.assertEqual(
            [u.kind for u in structural], ["heading", "html_block"]
        )

    def test_the_injected_instructions_land_in_a_unit_that_cannot_be_a_claim(self):
        """The fixture's living document tells the reader to approve everything
        and delete a file. Structurally it is an HTML comment, so no factual
        class can be recorded against it, and the engine acts on none of it."""
        repo = self.build_fixture()
        segmentation = segment_document(repo, fixture.LIVING_DOC)
        injected = next(u for u in segmentation.units if u.kind == "html_block")
        _, entries = self.living_classes(repo)

        result = record_classifications(
            segmentation,
            entries + [{"unit": injected.digest, "assertion_class": FACTUAL}],
        )

        self.assertIn("ignore all previous instructions", injected.text)
        self.assertIsInstance(result, Invalid)
        self.assertEqual(
            [p.code for p in result.problems],
            ["classification-not-assertion-capable"],
        )
        self.assertTrue(os.path.exists(os.path.join(repo, fixture.EXCLUDED_DOC)))

    def test_skipping_a_units_class_is_refused_over_the_fixture(self):
        repo = self.build_fixture()
        segmentation, entries = self.living_classes(repo)

        result = record_classifications(segmentation, entries[:2])

        self.assertIsInstance(result, Invalid)
        self.assertEqual(
            [p.code for p in result.problems], ["classification-missing"]
        )


class FindingIdentityOverTheFixture(fixture.AcceptanceFixtureTestCase):
    def finding_for(self, repo, lineage=None):
        """A STALE finding over the living document's fee claim, whatever the
        claim currently says — the point is that its digest tracks the text."""
        segmentation = segment_document(repo, fixture.LIVING_DOC)
        claim = next(u for u in segmentation.units if "calculates fees" in u.text)
        return build_finding(
            lineage=lineage or fixture_lineage(repo),
            code="STALE",
            path=fixture.LIVING_DOC,
            units=(claim.digest,),
            record_id="DRIFT-001",
        )

    def test_the_same_repository_state_reproduces_the_same_digest(self):
        repo = self.build_fixture()

        self.assertEqual(self.finding_for(repo).digest,
                         self.finding_for(repo).digest)

    def test_editing_the_claim_changes_the_finding_digest(self):
        repo = self.build_fixture()
        before = self.finding_for(repo)
        lineage = before.lineage
        path = os.path.join(repo, fixture.LIVING_DOC)
        with open(path, encoding="utf-8") as fh:
            text = fh.read()
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(text.replace("flat 2% rate", "flat 2.5% rate"))

        after = self.finding_for(repo, lineage=lineage)

        self.assertNotEqual(before.digest, after.digest)

    def test_a_new_commit_changes_the_finding_digest(self):
        """Lineage binding, against real git: the same claim under a different
        repository state is a different finding."""
        repo = self.build_fixture()
        before = self.finding_for(repo)
        with open(os.path.join(repo, fixture.EVIDENCE_SOURCE), "a",
                  encoding="utf-8") as fh:
            fh.write("\n\nMAX_FEE = 100\n")
        subprocess.run(["git", "add", "-A"], cwd=repo, check=True,
                       stdout=subprocess.PIPE)
        subprocess.run(
            ["git", "-c", "commit.gpgsign=false", "-c", "user.name=fixture",
             "-c", "user.email=fixture@doc-lifecycle.invalid",
             "commit", "-q", "-m", "Cap the fee"],
            cwd=repo, check=True, stdout=subprocess.PIPE,
        )

        after = self.finding_for(repo)

        self.assertNotEqual(before.digest, after.digest)

    def test_renumbering_the_finding_leaves_its_digest_alone(self):
        repo = self.build_fixture()
        lineage = fixture_lineage(repo)
        segmentation = segment_document(repo, fixture.LIVING_DOC)
        units = (by_text(segmentation)[fixture.LIVING_FACTUAL].digest,)

        first = build_finding(lineage=lineage, code="STALE",
                              path=fixture.LIVING_DOC, units=units,
                              record_id="DRIFT-001")
        second = build_finding(lineage=lineage, code="STALE",
                               path=fixture.LIVING_DOC, units=units,
                               record_id="DRIFT-097")

        self.assertEqual(first.digest, second.digest)

    def test_recording_the_model_verdict_leaves_the_digest_alone(self):
        repo = self.build_fixture()
        lineage = fixture_lineage(repo)
        segmentation = segment_document(repo, fixture.LIVING_DOC)
        units = (by_text(segmentation)[fixture.LIVING_FACTUAL].digest,)
        classified = record_classifications(segmentation, [
            {"unit": by_text(segmentation)[text].digest, "assertion_class": cls}
            for text, cls in (
                (fixture.LIVING_FACTUAL, FACTUAL),
                (fixture.LIVING_NORMATIVE, NORMATIVE),
                (fixture.LIVING_RATIONALE, RATIONALE),
            )
        ])

        bare = build_finding(lineage=lineage, code="STALE",
                             path=fixture.LIVING_DOC, units=units,
                             record_id="DRIFT-001")
        reviewed = build_finding(
            lineage=lineage, code="STALE", path=fixture.LIVING_DOC, units=units,
            record_id="DRIFT-001",
            extra={"assertion_classes": classified.to_dict(),
                   "message": "the rate is 2.5%, not 2%"},
        )

        self.assertEqual(bare.digest, reviewed.digest)


if __name__ == "__main__":
    unittest.main(verbosity=2)
