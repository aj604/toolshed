#!/usr/bin/env python3
"""Tests for finding identity and recorded assertion classes.

Seam: the library functions `build_finding` and `record_classifications`, plus
`report.lineage_digest` which the first of them binds to. Neither has a command
of its own — like path authorization, they are substrate the audit engine calls
— so the whole contract is exercised here, including the crossing point where a
finding becomes a record `validate_report` accepts.

Run: python3 tests/engine/finding_test.py
"""

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import support  # noqa: E402,F401  (puts the engine on sys.path)

from doclifecycle import ARTIFACT_SCHEMA_VERSION  # noqa: E402
from doclifecycle.finding import (  # noqa: E402
    ASSERTION_CLASSES,
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
    lineage_digest,
    validate_report,
)
from doclifecycle.results import Invalid  # noqa: E402
from doclifecycle.segment import segment_text  # noqa: E402

UNIT_A = "a" * 64
UNIT_B = "b" * 64
UNIT_C = "c" * 64


def lineage(**overrides):
    fields = {
        "repository": "origin:github.com/aj604/toolshed",
        "base_commit": "0" * 40,
        "audit_mode": "full",
        "inventory_digest": "1" * 64,
        "audit_config_digest": "2" * 64,
        "registry_digest": "3" * 64,
        "ruleset_version": 1,
        "plugin_version": "0.16.0",
        "evidence_boundary": EvidenceBoundary(("src/**",)),
    }
    fields.update(overrides)
    return Lineage(**fields)


def finding(**overrides):
    fields = {
        "lineage": lineage(),
        "code": "STALE",
        "path": "docs/architecture.md",
        "units": (UNIT_A, UNIT_B),
        "record_id": "DRIFT-001",
    }
    fields.update(overrides)
    return build_finding(**fields)


class LineageDigest(unittest.TestCase):
    def test_the_same_lineage_digests_the_same(self):
        self.assertEqual(lineage_digest(lineage()), lineage_digest(lineage()))

    def test_every_lineage_field_moves_the_digest(self):
        for field, value in (
            ("repository", "origin:github.com/other/repo"),
            ("base_commit", "1" * 40),
            ("audit_mode", "chunk"),
            ("inventory_digest", "9" * 64),
            ("audit_config_digest", "9" * 64),
            ("registry_digest", "9" * 64),
            ("ruleset_version", 2),
            ("plugin_version", "9.9.9"),
            ("evidence_boundary", EvidenceBoundary(("lib/**",))),
        ):
            with self.subTest(field):
                self.assertNotEqual(
                    lineage_digest(lineage()),
                    lineage_digest(lineage(**{field: value})),
                )

    def test_a_lineage_digest_is_a_sha256(self):
        self.assertRegex(lineage_digest(lineage()), r"^[0-9a-f]{64}$")


class WhatMovesAFindingDigest(unittest.TestCase):
    """The third acceptance criterion, stated in both directions."""

    def test_unit_content_moves_it(self):
        self.assertNotEqual(
            finding().digest, finding(units=(UNIT_A, UNIT_C)).digest
        )

    def test_grouping_moves_it(self):
        self.assertNotEqual(
            finding().digest, finding(units=(UNIT_A, UNIT_B, UNIT_C)).digest
        )
        self.assertNotEqual(finding().digest, finding(units=(UNIT_A,)).digest)

    def test_report_lineage_moves_it(self):
        self.assertNotEqual(
            finding().digest,
            finding(lineage=lineage(base_commit="1" * 40)).digest,
        )

    def test_the_document_moves_it(self):
        """Two documents can hold the same sentence; they are not one finding."""
        self.assertNotEqual(
            finding().digest, finding(path="docs/other.md").digest
        )

    def test_the_finding_code_moves_it(self):
        """Drift and bloat over the same units are two findings, not one."""
        self.assertNotEqual(finding().digest, finding(code="CONDENSE").digest)

    def test_the_display_id_does_not_move_it(self):
        """The whole point: approval cannot drift to a different finding that
        happens to have been numbered the same."""
        self.assertEqual(finding().digest, finding(record_id="DRIFT-014").digest)

    def test_reviewable_data_does_not_move_it(self):
        """A model's classification and prose are data, never identity."""
        classified = finding(extra={
            "message": "the rate is 2.5%, not 2%",
            "classifications": [{"unit": UNIT_A, "assertion_class": FACTUAL}],
        })

        self.assertEqual(finding().digest, classified.digest)

    def test_the_order_units_were_listed_in_does_not_move_it(self):
        """Normalized: the group is a set of units, not a sequence."""
        self.assertEqual(finding().digest, finding(units=(UNIT_B, UNIT_A)).digest)

    def test_listing_a_unit_twice_does_not_move_it(self):
        self.assertEqual(
            finding().digest, finding(units=(UNIT_A, UNIT_B, UNIT_A)).digest
        )

    def test_a_finding_digest_is_a_sha256(self):
        self.assertRegex(finding().digest, r"^[0-9a-f]{64}$")


class FindingShape(unittest.TestCase):
    def test_units_are_normalized_on_the_finding_itself(self):
        self.assertEqual(finding(units=(UNIT_B, UNIT_A, UNIT_B)).units,
                         (UNIT_A, UNIT_B))

    def test_a_finding_with_no_units_is_invalid(self):
        result = finding(units=())

        self.assertIsInstance(result, Invalid)
        self.assertEqual([p.code for p in result.problems], ["finding-no-units"])

    def test_a_unit_that_is_not_a_digest_is_invalid(self):
        result = finding(units=("docs/architecture.md:3",))

        self.assertIsInstance(result, Invalid)
        self.assertEqual([p.code for p in result.problems], ["finding-invalid-unit"])

    def test_an_empty_code_or_path_is_invalid(self):
        for field in ("code", "path"):
            with self.subTest(field):
                result = finding(**{field: "  "})
                self.assertIsInstance(result, Invalid)
                self.assertEqual(
                    [p.code for p in result.problems], ["finding-invalid-field"]
                )

    def test_an_empty_display_id_is_invalid(self):
        result = finding(record_id="")

        self.assertIsInstance(result, Invalid)
        self.assertEqual([p.code for p in result.problems], ["finding-invalid-field"])

    def test_extra_may_not_shadow_a_field_the_record_owns(self):
        result = finding(extra={"digest": "0" * 64})

        self.assertIsInstance(result, Invalid)
        self.assertEqual([p.code for p in result.problems], ["finding-reserved-field"])

    def test_every_problem_is_reported_in_one_pass(self):
        result = finding(code="", units=())

        self.assertEqual(
            sorted(p.code for p in result.problems),
            ["finding-invalid-field", "finding-no-units"],
        )

    def test_a_lineage_it_cannot_bind_to_is_a_type_error(self):
        with self.assertRaises(TypeError):
            finding(lineage={"base_commit": "0" * 40})

    def test_the_record_carries_the_reviewable_data(self):
        record = finding(extra={"message": "the rate moved"}).to_record()

        self.assertEqual(record["id"], "DRIFT-001")
        self.assertEqual(record["code"], "STALE")
        self.assertEqual(record["path"], "docs/architecture.md")
        self.assertEqual(record["units"], [UNIT_A, UNIT_B])
        self.assertEqual(record["message"], "the rate moved")

    def test_the_record_validates_inside_a_report(self):
        """The crossing point: a finding is a record the report contract takes."""
        built = finding()
        payload = {
            "status": "findings",
            "schema_version": ARTIFACT_SCHEMA_VERSION,
            "lineage": built.lineage.to_dict(),
            "records": [built.to_record()],
            "incomplete": [],
        }

        result = validate_report(payload)

        self.assertEqual(result.status, "findings")
        self.assertEqual(result.records[0].digest, built.digest)


class RecordedAssertionClasses(unittest.TestCase):
    """The model's only role, recorded as reviewable data and validated hard."""

    DOC = (
        "# Architecture\n\n"
        "The service charges a flat 2% fee.\n\n"
        "New endpoints must include an integration test.\n\n"
        "A flat rate was chosen because the processor bills per transaction.\n\n"
        "See the runbook for the rollout order.\n"
    )

    def segmentation(self):
        return segment_text(self.DOC, path="docs/architecture.md", kind="living")

    def entries(self, **overrides):
        segmentation = self.segmentation()
        capable = [u for u in segmentation.units if u.assertion_capable]
        classes = [FACTUAL, NORMATIVE, RATIONALE, NON_ASSERTIVE]
        entries = [
            {"unit": unit.digest, "assertion_class": overrides.get(str(i), cls)}
            for i, (unit, cls) in enumerate(zip(capable, classes))
        ]
        return segmentation, entries

    def test_all_four_classes_are_recordable(self):
        segmentation, entries = self.entries()

        result = record_classifications(segmentation, entries)

        self.assertEqual(
            [c.assertion_class for c in result.classifications],
            [FACTUAL, NORMATIVE, RATIONALE, NON_ASSERTIVE],
        )

    def test_the_four_classes_are_the_whole_vocabulary(self):
        self.assertEqual(
            ASSERTION_CLASSES, (FACTUAL, NORMATIVE, RATIONALE, NON_ASSERTIVE)
        )

    def test_it_is_keyed_to_the_segmentation_it_classifies(self):
        segmentation, entries = self.entries()

        result = record_classifications(segmentation, entries)

        self.assertEqual(result.segmentation_digest, segmentation.digest)

    def test_classes_are_reachable_by_unit(self):
        segmentation, entries = self.entries()

        result = record_classifications(segmentation, entries)

        self.assertEqual(result.by_unit()[entries[0]["unit"]], FACTUAL)

    def test_recording_a_class_does_not_change_a_unit_digest(self):
        segmentation, entries = self.entries()

        record_classifications(segmentation, entries)

        self.assertEqual(
            [u.digest for u in self.segmentation().units],
            [u.digest for u in segmentation.units],
        )

    def test_an_unknown_class_is_refused(self):
        segmentation, entries = self.entries(**{"0": "probably-true"})

        result = record_classifications(segmentation, entries)

        self.assertIsInstance(result, Invalid)
        self.assertEqual(
            [p.code for p in result.problems], ["classification-unknown-class"]
        )

    def test_a_claim_against_a_heading_is_refused(self):
        """The second acceptance criterion, enforced rather than hoped for."""
        segmentation, entries = self.entries()
        heading = next(u for u in segmentation.units if u.kind == "heading")
        entries.append({"unit": heading.digest, "assertion_class": FACTUAL})

        result = record_classifications(segmentation, entries)

        self.assertIsInstance(result, Invalid)
        self.assertEqual(
            [p.code for p in result.problems],
            ["classification-not-assertion-capable"],
        )

    def test_calling_a_heading_non_assertive_is_allowed(self):
        segmentation, entries = self.entries()
        heading = next(u for u in segmentation.units if u.kind == "heading")
        entries.append({"unit": heading.digest, "assertion_class": NON_ASSERTIVE})

        result = record_classifications(segmentation, entries)

        self.assertEqual(result.by_unit()[heading.digest], NON_ASSERTIVE)

    def test_a_class_for_a_unit_this_document_does_not_have_is_refused(self):
        segmentation, entries = self.entries()
        entries.append({"unit": UNIT_C, "assertion_class": FACTUAL})

        result = record_classifications(segmentation, entries)

        self.assertIsInstance(result, Invalid)
        self.assertEqual(
            [p.code for p in result.problems], ["classification-unknown-unit"]
        )

    def test_classifying_a_unit_twice_is_refused(self):
        segmentation, entries = self.entries()
        entries.append(dict(entries[0]))

        result = record_classifications(segmentation, entries)

        self.assertIsInstance(result, Invalid)
        self.assertEqual(
            [p.code for p in result.problems], ["classification-duplicate"]
        )

    def test_leaving_an_assertion_capable_unit_unclassified_is_refused(self):
        """Fail loud: a silently skipped unit reads as a unit with no claim."""
        segmentation, entries = self.entries()

        result = record_classifications(segmentation, entries[:-1])

        self.assertIsInstance(result, Invalid)
        self.assertEqual(
            [p.code for p in result.problems], ["classification-missing"]
        )

    def test_a_malformed_entry_is_refused(self):
        segmentation, entries = self.entries()
        entries.append({"unit": entries[0]["unit"]})

        result = record_classifications(segmentation, entries)

        self.assertIsInstance(result, Invalid)
        self.assertEqual(
            [p.code for p in result.problems], ["classification-invalid-shape"]
        )

    def test_something_that_is_not_a_list_of_entries_is_refused(self):
        segmentation, _ = self.entries()

        result = record_classifications(segmentation, {"unit": UNIT_A})

        self.assertIsInstance(result, Invalid)
        self.assertEqual(
            [p.code for p in result.problems], ["classification-invalid-shape"]
        )

    def test_every_problem_in_one_model_response_is_reported(self):
        segmentation, entries = self.entries(**{"0": "probably-true"})
        entries.append({"unit": UNIT_C, "assertion_class": FACTUAL})

        result = record_classifications(segmentation, entries)

        self.assertEqual(
            sorted(p.code for p in result.problems),
            ["classification-unknown-class", "classification-unknown-unit"],
        )

    def test_the_payload_is_the_reviewable_record(self):
        segmentation, entries = self.entries()

        payload = record_classifications(segmentation, entries).to_dict()

        self.assertEqual(payload["segmentation_digest"], segmentation.digest)
        self.assertEqual(payload["classifications"][0], entries[0])


if __name__ == "__main__":
    unittest.main(verbosity=2)
