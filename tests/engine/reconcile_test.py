"""Reconciliation: the deterministic phase that groups related findings.

Approval selects record digests. Reconciliation is what makes a selection
answerable to the *relationships* between records — so a person cannot take one
leg of a contradictory pair without noticing, and cannot take half of a group
whose members only make sense applied together.
"""

import unittest

from support import ENGINE  # noqa: F401  (puts the engine on sys.path)

from doclifecycle import ARTIFACT_SCHEMA_VERSION
from doclifecycle.digest import sha256_canonical
from doclifecycle.finding import build_finding
from doclifecycle.reconcile import (
    DISPOSITION_ATOMIC,
    DISPOSITION_EXCLUSIVE,
    DISPOSITION_INDEPENDENT,
    RELATION_DUPLICATE,
    RELATION_MUTUALLY_EXCLUSIVE,
    RELATION_OVERLAPPING,
    RELATION_SAME_TARGET,
    Reconciliation,
    reconcile,
)
from doclifecycle.report import EvidenceBoundary, Lineage, Report, validate_report
from doclifecycle.results import STATE_FINDINGS, Invalid

LINEAGE = Lineage(
    repository="origin:example.com/acme/docs",
    base_commit="a" * 40,
    audit_mode="full",
    inventory_digest="1" * 64,
    audit_config_digest="2" * 64,
    registry_digest="3" * 64,
    ruleset_version=1,
    plugin_version="0.19.0",
    evidence_boundary=EvidenceBoundary(("src/**",)),
)

UNIT_A = sha256_canonical("unit-a")
UNIT_B = sha256_canonical("unit-b")
UNIT_C = sha256_canonical("unit-c")


def finding_record(record_id, code, path, units, **extra):
    finding = build_finding(
        lineage=LINEAGE, code=code, path=path, units=list(units),
        record_id=record_id, extra=extra,
    )
    assert not isinstance(finding, Invalid), finding
    return finding.to_record()


def report_of(*records, **overrides):
    payload = {
        "status": STATE_FINDINGS,
        "schema_version": ARTIFACT_SCHEMA_VERSION,
        "lineage": LINEAGE.to_dict(),
        "records": [dict(r) for r in records],
        "incomplete": [],
    }
    payload.update(overrides)
    report = validate_report(payload)
    assert isinstance(report, Report), report
    return report


def codes(result):
    return sorted(p.code for p in result.problems)


def group_for(reconciliation, record):
    return reconciliation.group_of(record["digest"])


class Independence(unittest.TestCase):
    def test_findings_on_different_documents_are_independent(self):
        one = finding_record("R-1", "CUT", "docs/a.md", [UNIT_A])
        two = finding_record("R-2", "CUT", "docs/b.md", [UNIT_B])

        result = reconcile(report_of(one, two))

        self.assertIsInstance(result, Reconciliation)
        self.assertEqual(len(result.groups), 2)
        self.assertEqual(
            {g.disposition for g in result.groups}, {DISPOSITION_INDEPENDENT}
        )

    def test_the_same_unit_in_two_documents_is_two_targets(self):
        # A content digest is content, not location: the same sentence in two
        # documents is two targets, and editing one says nothing about the other.
        one = finding_record("R-1", "CUT", "docs/a.md", [UNIT_A])
        two = finding_record("R-2", "CONDENSE", "docs/b.md", [UNIT_A],
                             proposal="shorter")

        result = reconcile(report_of(one, two))

        self.assertEqual(len(result.groups), 2)

    def test_disjoint_findings_in_one_document_stay_selectable_apart(self):
        one = finding_record("R-1", "CUT", "docs/a.md", [UNIT_A])
        two = finding_record("R-2", "CUT", "docs/a.md", [UNIT_B])

        result = reconcile(report_of(one, two))

        self.assertEqual(len(result.groups), 2)
        self.assertEqual(group_for(result, one).disposition, DISPOSITION_INDEPENDENT)


class Duplicates(unittest.TestCase):
    def test_two_lanes_writing_one_replacement_are_duplicates(self):
        # A remedy is what a record writes, not what its detector calls the
        # verdict: a drift STALE fix and a bloat CONDENSE proposing the same
        # replacement for the same passage are one edit described twice.
        drift = finding_record("R-1", "STALE", "docs/a.md", [UNIT_A],
                               fix="one line")
        bloat = finding_record("R-2", "CONDENSE", "docs/a.md", [UNIT_A],
                               proposal="one line")

        result = reconcile(report_of(drift, bloat))

        self.assertEqual(len(result.groups), 1)
        group = result.groups[0]
        self.assertEqual(group.disposition, DISPOSITION_ATOMIC)
        self.assertEqual(
            [r.kind for r in group.relations], [RELATION_DUPLICATE]
        )

    def test_two_deletions_of_one_passage_are_duplicates(self):
        cut = finding_record("R-1", "CUT", "docs/a.md", [UNIT_A, UNIT_B])
        distill = finding_record("R-2", "DISTILL", "docs/a.md",
                                 # The same target listed the other way round:
                                 # a finding's units are a set, not a sequence.
                                 [UNIT_B, UNIT_A], status="ready")

        result = reconcile(report_of(cut, distill))

        self.assertEqual(
            [r.kind for r in result.groups[0].relations], [RELATION_DUPLICATE]
        )

    def test_one_detector_cannot_report_one_edit_twice(self):
        # The reachable duplicates above are cross-code. The same code, target,
        # and units *is* the same finding — its digest says so — so a report
        # carrying it twice is refused before reconciliation ever sees it.
        one = finding_record("R-1", "CUT", "docs/a.md", [UNIT_A],
                             evidence="chunk 1")
        two = finding_record("R-2", "CUT", "docs/a.md", [UNIT_A],
                             evidence="chunk 2")

        self.assertEqual(one["digest"], two["digest"])


class Conflicts(unittest.TestCase):
    def test_two_remedies_for_one_target_are_mutually_exclusive(self):
        cut = finding_record("R-1", "CUT", "docs/a.md", [UNIT_A])
        condense = finding_record("R-2", "CONDENSE", "docs/a.md", [UNIT_A],
                                  proposal="one line")

        result = reconcile(report_of(cut, condense))

        group = result.groups[0]
        self.assertEqual(group.disposition, DISPOSITION_EXCLUSIVE)
        self.assertEqual([r.kind for r in group.relations], [RELATION_SAME_TARGET])

    def test_two_replacements_for_one_passage_are_exclusive(self):
        # Both write, and they write different things: one passage cannot end
        # up as both, so applying either decides against the other.
        one = finding_record("R-1", "STALE", "docs/a.md", [UNIT_A],
                             fix="one line")
        two = finding_record("R-2", "CONDENSE", "docs/a.md", [UNIT_A],
                             proposal="a different line")

        result = reconcile(report_of(one, two))

        self.assertEqual(result.groups[0].disposition, DISPOSITION_EXCLUSIVE)

    def test_overlapping_targets_with_one_remedy_group_atomically(self):
        wide = finding_record("R-1", "CUT", "docs/a.md", [UNIT_A, UNIT_B])
        narrow = finding_record("R-2", "CUT", "docs/a.md", [UNIT_B])

        result = reconcile(report_of(wide, narrow))

        group = result.groups[0]
        self.assertEqual(group.disposition, DISPOSITION_ATOMIC)
        self.assertEqual([r.kind for r in group.relations], [RELATION_OVERLAPPING])

    def test_overlapping_targets_with_two_remedies_are_exclusive(self):
        cut = finding_record("R-1", "CUT", "docs/a.md", [UNIT_A, UNIT_B])
        condense = finding_record("R-2", "CONDENSE", "docs/a.md", [UNIT_B],
                                  proposal="one line")

        result = reconcile(report_of(cut, condense))

        group = result.groups[0]
        self.assertEqual(group.disposition, DISPOSITION_EXCLUSIVE)
        self.assertEqual(
            [r.kind for r in group.relations], [RELATION_MUTUALLY_EXCLUSIVE]
        )

    def test_a_whole_document_remedy_conflicts_with_edits_inside_it(self):
        # A bulk RETIRE-DOC binds every unit of the document, so an edit to any
        # passage in it intersects — retiring a document and rewriting a
        # sentence in it are not two edits anyone can apply together.
        retire = finding_record("R-1", "RETIRE-DOC", "docs/a.md",
                                [UNIT_A, UNIT_B, UNIT_C])
        condense = finding_record("R-2", "CONDENSE", "docs/a.md", [UNIT_B],
                                  proposal="one line")

        result = reconcile(report_of(retire, condense))

        self.assertEqual(result.groups[0].disposition, DISPOSITION_EXCLUSIVE)

    def test_a_conflict_anywhere_makes_the_whole_group_exclusive(self):
        # Chained: R-1 and R-2 merely overlap, R-2 and R-3 contradict. The
        # group is one connected component, and no part of it is selectable.
        one = finding_record("R-1", "CUT", "docs/a.md", [UNIT_A, UNIT_B])
        two = finding_record("R-2", "CUT", "docs/a.md", [UNIT_B, UNIT_C])
        three = finding_record("R-3", "CONDENSE", "docs/a.md", [UNIT_C],
                               proposal="one line")

        result = reconcile(report_of(one, two, three))

        self.assertEqual(len(result.groups), 1)
        group = result.groups[0]
        self.assertEqual(group.disposition, DISPOSITION_EXCLUSIVE)
        self.assertEqual(len(group.members), 3)

    def test_an_exclusive_group_names_both_sides_of_the_conflict(self):
        cut = finding_record("R-1", "CUT", "docs/a.md", [UNIT_A])
        condense = finding_record("R-2", "CONDENSE", "docs/a.md", [UNIT_A],
                                  proposal="one line")

        relation = reconcile(report_of(cut, condense)).groups[0].relations[0]

        self.assertEqual(
            {relation.left, relation.right},
            {cut["digest"], condense["digest"]},
        )
        self.assertIn("docs/a.md", relation.reason)


class Determinism(unittest.TestCase):
    def test_record_order_does_not_change_the_reconciliation(self):
        one = finding_record("R-1", "CUT", "docs/a.md", [UNIT_A, UNIT_B])
        two = finding_record("R-2", "CUT", "docs/a.md", [UNIT_B])
        three = finding_record("R-3", "CUT", "docs/b.md", [UNIT_C])

        forward = reconcile(report_of(one, two, three))
        backward = reconcile(report_of(three, two, one))

        # The two reports are not the same report — a records list is ordered,
        # so it re-keys the report digest — but the grouping they reconcile to
        # is identical, which is the property a selection rests on.
        self.assertEqual(
            [g.to_dict() for g in forward.groups],
            [g.to_dict() for g in backward.groups],
        )

    def test_reconciling_one_report_twice_gives_one_digest(self):
        report = report_of(
            finding_record("R-1", "CUT", "docs/a.md", [UNIT_A, UNIT_B]),
            finding_record("R-2", "CUT", "docs/a.md", [UNIT_B]),
        )

        self.assertEqual(reconcile(report).digest, reconcile(report).digest)

    def test_a_group_id_is_derived_from_its_members(self):
        one = finding_record("R-1", "CUT", "docs/a.md", [UNIT_A, UNIT_B])
        two = finding_record("R-2", "CUT", "docs/a.md", [UNIT_B])

        first = reconcile(report_of(one, two)).groups[0]
        # The same two records reported alongside an unrelated third keep the
        # group they had: a group id is its members, not its position.
        three = finding_record("R-3", "CUT", "docs/b.md", [UNIT_C])
        again = reconcile(report_of(one, two, three))

        self.assertEqual(first.group_id, group_for(again, one).group_id)

    def test_an_empty_report_reconciles_to_no_groups(self):
        result = reconcile(report_of(status="clean", records=[]))

        self.assertIsInstance(result, Reconciliation)
        self.assertEqual(result.groups, ())


class Refusals(unittest.TestCase):
    def test_reconcile_takes_a_validated_report_and_nothing_else(self):
        with self.assertRaises(TypeError):
            reconcile({"status": "findings"})

    def test_a_record_that_is_not_a_finding_cannot_be_reconciled(self):
        # No code, path, or units: nothing says what it would change, so
        # nothing can say whether it conflicts with anything.
        result = reconcile(report_of(
            {"id": "R-1", "digest": "d" * 64, "note": "something happened"}
        ))

        self.assertIsInstance(result, Invalid)
        self.assertEqual(codes(result), ["reconcile-record-not-a-finding"])

    def test_a_record_whose_digest_does_not_bind_its_target_is_refused(self):
        # The digest is what an approval selects by. A record whose declared
        # path is not the one its digest commits to would let a selection
        # authorize an edit somewhere else.
        record = finding_record("R-1", "CUT", "docs/a.md", [UNIT_A])
        record["path"] = "docs/elsewhere.md"

        result = reconcile(report_of(record))

        self.assertIsInstance(result, Invalid)
        self.assertEqual(codes(result), ["reconcile-record-digest-mismatch"])

    def test_every_unreadable_record_is_named_at_once(self):
        result = reconcile(report_of(
            {"id": "R-1", "digest": "d" * 64},
            {"id": "R-2", "digest": "e" * 64, "code": "CUT", "path": "docs/a.md",
             "units": []},
        ))

        self.assertIsInstance(result, Invalid)
        self.assertEqual(len(result.problems), 2)


if __name__ == "__main__":
    unittest.main()
