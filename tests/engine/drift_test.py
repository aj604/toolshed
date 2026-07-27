#!/usr/bin/env python3
"""Tests for the drift audit: scope planning, verdicts, anchors, coverage gaps.

Seam: the library functions `plan_drift_audit` and `audit_drift`. The command
half lives in `drift_cli_test.py`, and the fixture-level acceptance criteria in
`tests/engine/acceptance/scenario_drift_test.py`.

Every repository here is a real one with real commits: a diff-scoped audit is a
question about a commit range, and an anchor's staleness is a question about
when a file last changed, so a mocked git would prove nothing. The default
narrative anchor names no repository path, so it is honestly dated by
construction — a test that wants a stale anchor writes one that cites `src`.

Run: python3 tests/engine/drift_test.py
"""

import json
import os
import subprocess
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from support import RepoTestCase  # noqa: E402

from doclifecycle.drift import (  # noqa: E402
    MODE_FULL,
    MODE_INCREMENTAL,
    OBLIGATION_ANCHOR,
    OBLIGATION_ASSERTIONS,
    DriftPlan,
    audit_drift,
    plan_drift_audit,
)
from doclifecycle.report import Report  # noqa: E402
from doclifecycle.results import (  # noqa: E402
    STATE_CLEAN,
    STATE_FINDINGS,
    STATE_PARTIAL,
    Invalid,
)
from doclifecycle.segment import segment_document  # noqa: E402

REGISTRY = json.dumps({
    "schema_version": 1,
    "roots": ["docs"],
    "rules": [
        {"glob": "docs/*.md", "kind": "living"},
        {"glob": "docs/guides/*.md", "kind": "narrative"},
        {"glob": "docs/plans/*.md", "kind": "planning"},
    ],
})

LIVING = "docs/reference.md"
NARRATIVE = "docs/guides/tour.md"
PLANNING = "docs/plans/next.md"
UNRELATED = "docs/unrelated.md"
SOURCE = "src/fees.py"
WAIVERS = ".github/doc-sync/drift-waivers.json"

LIVING_CLAIM = "The fee is 2% of the amount, in `src/fees.py`."
UNRELATED_CLAIM = "Support answers within one business day."

# Anchors nothing in the repository, so nothing can have moved out from under
# it: the honestly-dated baseline every other narrative case is a departure from.
NARRATIVE_TEXT = "# Tour\n\n> As of 2026-01-01 (initial commit)\n\nWelcome aboard.\n"
# Anchors the module the living document also cites, so a commit touching that
# module leaves this anchor behind.
ANCHORED_TEXT = "# Tour\n\n> As of 2026-01-01 (`src/fees.py`)\n\nWelcome aboard.\n"

FILES = {
    ".doc-lifecycle/registry.json": REGISTRY,
    LIVING: f"# Reference\n\n{LIVING_CLAIM}\n",
    NARRATIVE: NARRATIVE_TEXT,
    PLANNING: "# Next\n\n**Status:** drafted.\n",
    SOURCE: "RATE = 0.02\n",
}

GIT_ENV = {
    "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@example.com",
    "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@example.com",
}


def codes(result):
    return sorted(p.code for p in result.problems)


def evidence(**overrides):
    payload = {"source": SOURCE, "line": 1, "observed": "RATE = 0.025"}
    payload.update(overrides)
    return payload


class DriftRepoTestCase(RepoTestCase):
    def git(self, root, *argv):
        return subprocess.run(
            ["git", "-C", root, "-c", "commit.gpgsign=false", *argv],
            check=True, capture_output=True, text=True,
            env=dict(os.environ, **GIT_ENV),
        ).stdout.strip()

    def commit(self, root, message="change"):
        self.git(root, "add", "-A")
        self.git(root, "commit", "-q", "-m", message)
        return self.git(root, "rev-parse", "HEAD")

    def drift_repo(self, **changes):
        """A repository with one document of each kind, committed once."""
        files = dict(FILES)
        files.update(changes)
        root = self.repo(files)
        self.git(root, "init", "-q", "-b", "main")
        self.base = self.commit(root, "initial")
        return root

    def write(self, root, rel, text):
        path = os.path.join(root, rel)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(text)

    def units_of(self, root, path):
        """{unit text: unit} for one document."""
        return {u.text: u for u in segment_document(root, path).units}

    def claim_unit(self, root, path=LIVING, text=LIVING_CLAIM):
        return self.units_of(root, path)[text]

    def verdict(self, root, path=LIVING, text=LIVING_CLAIM, **overrides):
        entry = {
            "unit": self.claim_unit(root, path, text).digest,
            "verdict": "STALE",
            "kind": "value",
            "tier": 2,
            "evidence": evidence(),
            "fix": "The fee is 2.5% of the amount, in `src/fees.py`.",
        }
        entry.update(overrides)
        return entry

    def verdicts_for(self, root, *entries, path=LIVING):
        return {"documents": [{"path": path, "status": "ok",
                               "verdicts": list(entries)}]}

    def audit(self, root, **kwargs):
        kwargs.setdefault("mode", MODE_FULL)
        return audit_drift(root, **kwargs)


class PlanningTheScope(DriftRepoTestCase):
    def test_a_full_audit_declares_every_living_and_narrative_document(self):
        root = self.drift_repo(**{UNRELATED: f"# U\n\n{UNRELATED_CLAIM}\n"})

        plan = plan_drift_audit(root, mode=MODE_FULL)

        self.assertIsInstance(plan, DriftPlan)
        self.assertEqual([d.path for d in plan.documents],
                         [NARRATIVE, LIVING, UNRELATED])

    def test_each_kind_carries_the_obligation_its_kind_owes(self):
        root = self.drift_repo()

        plan = plan_drift_audit(root, mode=MODE_FULL)

        self.assertEqual(
            {d.path: d.obligation for d in plan.documents},
            {LIVING: OBLIGATION_ASSERTIONS, NARRATIVE: OBLIGATION_ANCHOR},
        )

    def test_a_planning_document_is_declared_out_of_scope_with_its_reason(self):
        """Not silently dropped: a reader must be able to see that the audit
        deliberately did not examine it, and why."""
        root = self.drift_repo()

        plan = plan_drift_audit(root, mode=MODE_FULL)

        excluded = {d.path: d.reason for d in plan.excluded}
        self.assertIn(PLANNING, excluded)
        self.assertIn("lifecycle", excluded[PLANNING])

    def test_a_diff_scoped_audit_declares_only_the_affected_documents(self):
        root = self.drift_repo(**{UNRELATED: f"# U\n\n{UNRELATED_CLAIM}\n",
                                  NARRATIVE: ANCHORED_TEXT})
        self.write(root, SOURCE, "RATE = 0.025\n")
        self.commit(root, "raise the rate")

        plan = plan_drift_audit(root, mode=MODE_INCREMENTAL, since=self.base)

        self.assertEqual([d.path for d in plan.documents], [NARRATIVE, LIVING])

    def test_a_document_the_diff_changed_is_affected_even_citing_nothing(self):
        root = self.drift_repo(**{UNRELATED: f"# U\n\n{UNRELATED_CLAIM}\n"})
        self.write(root, UNRELATED, f"# U\n\n{UNRELATED_CLAIM} Always.\n")
        self.commit(root, "edit the unrelated doc")

        plan = plan_drift_audit(root, mode=MODE_INCREMENTAL, since=self.base)

        self.assertEqual([d.path for d in plan.documents], [UNRELATED])

    def test_a_diff_touching_no_document_declares_an_empty_scope(self):
        root = self.drift_repo()
        self.write(root, "README.md", "# unregistered, cited by nothing\n")
        self.commit(root, "add a readme")

        plan = plan_drift_audit(root, mode=MODE_INCREMENTAL, since=self.base)

        self.assertEqual(plan.documents, ())

    def test_the_two_modes_state_different_bases(self):
        root = self.drift_repo()

        full = plan_drift_audit(root, mode=MODE_FULL)
        diff = plan_drift_audit(root, mode=MODE_INCREMENTAL, since=self.base)

        self.assertNotEqual(full.basis, diff.basis)
        self.assertIn(self.base, diff.basis)

    def test_a_diff_scoped_audit_without_a_baseline_is_refused(self):
        root = self.drift_repo()

        result = plan_drift_audit(root, mode=MODE_INCREMENTAL)

        self.assertEqual(codes(result), ["drift-missing-baseline"])

    def test_a_full_audit_given_a_baseline_is_refused(self):
        """A baseline narrows a scope; a full audit that accepted one would be
        claiming a coverage it did not have."""
        root = self.drift_repo()

        result = plan_drift_audit(root, mode=MODE_FULL, since=self.base)

        self.assertEqual(codes(result), ["drift-baseline-not-applicable"])

    def test_a_baseline_the_repository_does_not_have_is_refused(self):
        root = self.drift_repo()

        result = plan_drift_audit(root, mode=MODE_INCREMENTAL, since="f" * 40)

        self.assertEqual(codes(result), ["drift-unknown-baseline"])

    def test_an_unknown_mode_is_refused(self):
        root = self.drift_repo()

        result = plan_drift_audit(root, mode="deep")

        self.assertEqual(codes(result), ["drift-unknown-mode"])

    def test_an_invalid_registry_invalidates_the_plan(self):
        root = self.drift_repo(**{".doc-lifecycle/registry.json": "{"})

        result = plan_drift_audit(root, mode=MODE_FULL)

        self.assertIsInstance(result, Invalid)
        self.assertTrue(result.problems)

    def test_planning_the_same_repository_twice_gives_the_same_plan(self):
        root = self.drift_repo()

        self.assertEqual(plan_drift_audit(root, mode=MODE_FULL).to_dict(),
                         plan_drift_audit(root, mode=MODE_FULL).to_dict())


class ReportingWhatWasExamined(DriftRepoTestCase):
    def test_a_full_audit_declares_the_documents_it_examined(self):
        root = self.drift_repo()

        report = self.audit(root, verdicts=self.verdicts_for(
            root, self.verdict(root)))

        self.assertIsInstance(report, Report)
        self.assertEqual(report.scope.documents, (NARRATIVE, LIVING))

    def test_the_declared_scope_says_how_it_was_derived(self):
        root = self.drift_repo()

        report = self.audit(root, verdicts=self.verdicts_for(
            root, self.verdict(root)))

        self.assertEqual(report.scope.basis,
                         plan_drift_audit(root, mode=MODE_FULL).basis)

    def test_a_diff_scoped_report_claims_less_than_a_full_one(self):
        root = self.drift_repo(**{UNRELATED: f"# U\n\n{UNRELATED_CLAIM}\n"})
        self.write(root, SOURCE, "RATE = 0.025\n")
        self.commit(root, "raise the rate")
        verdicts = self.verdicts_for(root, self.verdict(root))

        full = self.audit(root, verdicts=verdicts)
        diff = self.audit(root, mode=MODE_INCREMENTAL, since=self.base,
                          verdicts=verdicts)

        self.assertEqual(diff.scope.documents, (LIVING,))
        self.assertEqual(full.scope.documents, (NARRATIVE, LIVING, UNRELATED))
        self.assertNotEqual(full.scope.basis, diff.scope.basis)

    def test_the_audit_mode_travels_in_the_reports_lineage(self):
        root = self.drift_repo()

        report = self.audit(root, mode=MODE_INCREMENTAL, since=self.base)

        self.assertEqual(report.lineage.audit_mode, MODE_INCREMENTAL)

    def test_an_examined_document_with_nothing_wrong_is_clean(self):
        root = self.drift_repo()

        report = self.audit(root, verdicts=self.verdicts_for(root, self.verdict(
            root, verdict="VERIFIED", fix=None,
            evidence=evidence(observed="RATE = 0.02"))))

        self.assertEqual(report.status, STATE_CLEAN)
        self.assertEqual(report.records, ())

    def test_a_stale_verdict_becomes_a_record(self):
        root = self.drift_repo()

        report = self.audit(root, verdicts=self.verdicts_for(
            root, self.verdict(root)))

        self.assertEqual(report.status, STATE_FINDINGS)
        self.assertEqual([r.extra["code"] for r in report.records], ["STALE"])

    def test_records_are_numbered_in_a_stable_order(self):
        root = self.drift_repo(**{UNRELATED: f"# U\n\n{UNRELATED_CLAIM}\n"})
        verdicts = {"documents": [
            {"path": UNRELATED, "status": "ok", "verdicts": [self.verdict(
                root, path=UNRELATED, text=UNRELATED_CLAIM,
                fix="Support answers within two business days.")]},
            {"path": LIVING, "status": "ok", "verdicts": [self.verdict(root)]},
        ]}

        report = self.audit(root, verdicts=verdicts)

        self.assertEqual([(r.id, r.extra["path"]) for r in report.records],
                         [("DRIFT-001", LIVING), ("DRIFT-002", UNRELATED)])


class CoverageGaps(DriftRepoTestCase):
    def test_a_failed_chunk_makes_the_run_partial_not_clean(self):
        root = self.drift_repo()

        report = self.audit(root, verdicts={"documents": [{
            "path": LIVING, "status": "failed", "chunk": "chunk-3",
            "reason": "the worker failed twice",
        }]})

        self.assertEqual(report.status, STATE_PARTIAL)
        self.assertEqual([i.scope for i in report.incomplete], [LIVING])
        self.assertIn("chunk-3", report.incomplete[0].reason)

    def test_a_document_nobody_returned_a_verdict_for_is_a_gap(self):
        root = self.drift_repo()

        report = self.audit(root, verdicts={"documents": []})

        self.assertEqual(report.status, STATE_PARTIAL)
        self.assertEqual([i.scope for i in report.incomplete], [LIVING])

    def test_an_audit_given_no_verdicts_at_all_examines_no_living_document(self):
        root = self.drift_repo()

        report = self.audit(root)

        self.assertEqual(report.status, STATE_PARTIAL)
        self.assertEqual([i.scope for i in report.incomplete], [LIVING])

    def test_a_document_whose_verdicts_do_not_validate_is_a_gap(self):
        """Not a silent pass and not a whole-run failure: the document was not
        validly examined, so it is named as unexamined."""
        root = self.drift_repo()

        report = self.audit(root, verdicts=self.verdicts_for(
            root, self.verdict(root, verdict="PROBABLY")))

        self.assertEqual(report.status, STATE_PARTIAL)
        self.assertIn("drift-unknown-verdict", report.incomplete[0].reason)

    def test_a_claim_left_unjudged_makes_the_document_a_gap(self):
        root = self.drift_repo()

        report = self.audit(root, verdicts=self.verdicts_for(root))

        self.assertEqual(report.status, STATE_PARTIAL)
        self.assertIn("drift-verdict-missing", report.incomplete[0].reason)

    def test_findings_and_gaps_together_still_read_as_partial(self):
        root = self.drift_repo(**{UNRELATED: f"# U\n\n{UNRELATED_CLAIM}\n"})

        report = self.audit(root, verdicts={"documents": [
            {"path": LIVING, "status": "ok", "verdicts": [self.verdict(root)]},
            {"path": UNRELATED, "status": "failed", "reason": "timed out"},
        ]})

        self.assertEqual(report.status, STATE_PARTIAL)
        self.assertEqual(len(report.records), 1)
        self.assertEqual([i.scope for i in report.incomplete], [UNRELATED])


class VerdictDiscipline(DriftRepoTestCase):
    def gap_reason(self, root, **overrides):
        report = self.audit(root, verdicts=self.verdicts_for(
            root, self.verdict(root, **overrides)))
        self.assertEqual(report.status, STATE_PARTIAL, report.to_dict())
        return report.incomplete[0].reason

    def test_a_verdict_without_evidence_is_refused(self):
        root = self.drift_repo()

        self.assertIn("drift-verdict-invalid-evidence",
                      self.gap_reason(root, evidence=None))

    def test_a_verified_verdict_needs_a_pointer_too(self):
        """VERIFIED asserts that someone opened the code; without a pointer
        nobody can tell that from a guess."""
        root = self.drift_repo()

        self.assertIn(
            "drift-verdict-invalid-evidence",
            self.gap_reason(root, verdict="VERIFIED", fix=None,
                            evidence={"observed": "looks right"}),
        )

    def test_an_unverifiable_verdict_may_point_at_nothing(self):
        """Nothing checkable is named, which is the verdict — so requiring a
        source would force a pointer at code that has no bearing on it."""
        root = self.drift_repo()

        report = self.audit(root, verdicts=self.verdicts_for(
            root, self.verdict(root, verdict="UNVERIFIABLE", fix=None,
                               evidence={"observed": "no checkable value named"})))

        self.assertEqual([r.extra["code"] for r in report.records],
                         ["UNVERIFIABLE"])

    def test_a_stale_verdict_without_a_replacement_line_is_refused(self):
        root = self.drift_repo()

        self.assertIn("drift-verdict-invalid-fix", self.gap_reason(root, fix=None))

    def test_a_non_stale_verdict_carrying_a_fix_is_refused(self):
        root = self.drift_repo()

        self.assertIn("drift-verdict-invalid-fix",
                      self.gap_reason(root, verdict="VERIFIED"))

    def test_an_unknown_claim_kind_is_refused(self):
        root = self.drift_repo()

        self.assertIn("drift-verdict-unknown-kind",
                      self.gap_reason(root, kind="schema_mismatch"))

    def test_a_tier_outside_the_three_is_refused(self):
        root = self.drift_repo()

        self.assertIn("drift-verdict-invalid-tier", self.gap_reason(root, tier=4))

    def test_a_boolean_tier_is_not_tier_one(self):
        root = self.drift_repo()

        self.assertIn("drift-verdict-invalid-tier",
                      self.gap_reason(root, tier=True))

    def test_a_field_the_verdict_shape_does_not_know_is_refused(self):
        root = self.drift_repo()

        self.assertIn("drift-verdict-invalid-shape",
                      self.gap_reason(root, confidence=0.9))

    def test_a_verdict_against_a_unit_the_document_lacks_is_refused(self):
        root = self.drift_repo()

        self.assertIn("drift-verdict-unknown-unit",
                      self.gap_reason(root, unit="a" * 64))

    def test_a_verdict_against_a_heading_is_refused(self):
        """Structure cannot carry a claim, so it cannot be found stale — that
        is how injected prose in a non-assertive unit stays unactionable."""
        root = self.drift_repo()
        heading = self.units_of(root, LIVING)["Reference"]

        self.assertIn("drift-verdict-not-assertion-capable",
                      self.gap_reason(root, unit=heading.digest))

    def test_one_unit_judged_twice_is_refused(self):
        root = self.drift_repo()

        report = self.audit(root, verdicts=self.verdicts_for(
            root, self.verdict(root),
            self.verdict(root, verdict="VERIFIED", fix=None)))

        self.assertEqual(report.status, STATE_PARTIAL)
        self.assertIn("drift-verdict-duplicate", report.incomplete[0].reason)

    def test_evidence_outside_the_declared_boundary_is_refused(self):
        root = self.drift_repo()

        report = self.audit(root, evidence_sources=("lib/**",),
                            verdicts=self.verdicts_for(root, self.verdict(root)))

        self.assertIn("drift-evidence-outside-boundary",
                      report.incomplete[0].reason)


class VerdictsTheAuditRefusesOutright(DriftRepoTestCase):
    def test_a_verdict_set_for_an_undeclared_document_invalidates_the_run(self):
        """The lane examined something the plan did not declare: the report's
        scope would not describe the run, and which of the two is wrong is not
        knowable from here."""
        root = self.drift_repo()

        result = self.audit(root, mode=MODE_INCREMENTAL, since=self.base,
                            verdicts={"documents": [{"path": LIVING,
                                                     "status": "ok",
                                                     "verdicts": []}]})

        self.assertEqual(codes(result), ["drift-verdict-undeclared-document"])

    def test_a_narrative_document_is_never_put_through_claim_checks(self):
        root = self.drift_repo()

        result = self.audit(root, verdicts={"documents": [{
            "path": NARRATIVE, "status": "ok", "verdicts": [],
        }]})

        self.assertEqual(codes(result), ["drift-verdict-on-narrative-document"])

    def test_two_verdict_sets_for_one_document_invalidate_the_run(self):
        root = self.drift_repo()

        result = self.audit(root, verdicts={"documents": [
            {"path": LIVING, "status": "ok", "verdicts": []},
            {"path": LIVING, "status": "failed", "reason": "timed out"},
        ]})

        self.assertEqual(codes(result), ["drift-verdict-duplicate-document"])

    def test_a_verdict_payload_that_is_not_an_object_invalidates_the_run(self):
        root = self.drift_repo()

        result = self.audit(root, verdicts=[{"path": LIVING}])

        self.assertEqual(codes(result), ["drift-verdicts-invalid-shape"])

    def test_a_verdict_entry_without_a_status_invalidates_the_run(self):
        root = self.drift_repo()

        result = self.audit(root, verdicts={"documents": [{"path": LIVING}]})

        self.assertEqual(codes(result), ["drift-verdicts-invalid-entry"])

    def test_a_failed_entry_that_will_not_say_why_invalidates_the_run(self):
        """A gap with no reason is indistinguishable from a document nobody
        thought about."""
        root = self.drift_repo()

        result = self.audit(root, verdicts={"documents": [{"path": LIVING,
                                                           "status": "failed"}]})

        self.assertEqual(codes(result), ["drift-verdicts-invalid-entry"])


class NarrativeAnchors(DriftRepoTestCase):
    def anchor_records(self, report):
        return {r.extra["code"]: r for r in report.records}

    def test_an_anchor_older_than_the_code_it_names_is_stale(self):
        root = self.drift_repo(**{NARRATIVE: ANCHORED_TEXT})
        self.write(root, SOURCE, "RATE = 0.025\n")
        self.commit(root, "raise the rate")

        report = self.audit(root)

        record = self.anchor_records(report)["ANCHOR-STALE"]
        self.assertEqual(record.extra["as_of"], "2026-01-01")
        self.assertEqual(record.extra["evidence"]["source"], SOURCE)

    def test_a_narrative_document_needs_no_verdicts_to_be_examined(self):
        """The anchor check is deterministic and engine-side: a narrative
        document is fully examined without a model saying anything."""
        root = self.drift_repo()

        report = self.audit(root)

        self.assertNotIn(NARRATIVE, [i.scope for i in report.incomplete])

    def test_an_anchor_naming_a_file_that_is_gone_is_stale(self):
        root = self.drift_repo(**{NARRATIVE: ANCHORED_TEXT})
        os.remove(os.path.join(root, SOURCE))
        self.commit(root, "drop the module")

        report = self.audit(root)

        record = self.anchor_records(report)["ANCHOR-STALE"]
        self.assertIn("no longer", record.extra["evidence"]["observed"])

    def test_a_narrative_document_without_an_anchor_is_a_finding(self):
        root = self.drift_repo(**{NARRATIVE: "# Tour\n\nWelcome aboard.\n"})

        report = self.audit(root)

        self.assertIn("ANCHOR-MISSING", self.anchor_records(report))

    def test_an_anchor_without_a_readable_date_is_malformed(self):
        root = self.drift_repo(**{
            NARRATIVE: "# Tour\n\n> As of last spring (`src/fees.py`)\n\nHi.\n"})

        report = self.audit(root)

        self.assertIn("ANCHOR-MALFORMED", self.anchor_records(report))

    def test_an_impossible_date_is_malformed_too(self):
        root = self.drift_repo(**{
            NARRATIVE: "# Tour\n\n> As of 2026-02-31 (`src/fees.py`)\n\nHi.\n"})

        report = self.audit(root)

        self.assertIn("ANCHOR-MALFORMED", self.anchor_records(report))

    def test_an_anchor_ahead_of_the_code_it_names_is_left_alone(self):
        root = self.drift_repo(**{
            NARRATIVE: "# Tour\n\n> As of 2099-01-01 (`src/fees.py`)\n\nHi.\n"})

        report = self.audit(root)

        self.assertEqual(report.records, ())

    def test_a_narrative_finding_points_at_the_anchor_line(self):
        root = self.drift_repo(**{NARRATIVE: ANCHORED_TEXT})
        self.write(root, SOURCE, "RATE = 0.025\n")
        self.commit(root, "raise the rate")

        report = self.audit(root)

        self.assertEqual(
            self.anchor_records(report)["ANCHOR-STALE"].extra["location"],
            f"{NARRATIVE}:3",
        )

    def test_prose_around_the_anchor_is_never_verified_as_a_claim(self):
        """"Welcome aboard." is not a claim about the code, and a narrative
        audit must not manufacture a verdict about it."""
        root = self.drift_repo(**{NARRATIVE: ANCHORED_TEXT})
        self.write(root, SOURCE, "RATE = 0.025\n")
        self.commit(root, "raise the rate")

        report = self.audit(root)

        self.assertNotIn("Welcome aboard.",
                         json.dumps(report.to_dict(), sort_keys=True))


class EvidencePointers(DriftRepoTestCase):
    def stale_record(self, root, **overrides):
        report = self.audit(root, verdicts=self.verdicts_for(
            root, self.verdict(root, **overrides)))
        self.assertEqual(report.status, STATE_FINDINGS, report.to_dict())
        return report.records[0]

    def test_a_finding_points_at_the_line_it_is_about(self):
        root = self.drift_repo()

        self.assertEqual(self.stale_record(root).extra["location"], f"{LIVING}:3")

    def test_a_finding_quotes_the_claim_the_document_makes(self):
        """Taken from the segmentation, never from the model: what the document
        says is not the model's to report."""
        root = self.drift_repo()

        self.assertEqual(self.stale_record(root).extra["claim"], LIVING_CLAIM)

    def test_a_finding_carries_the_observed_fact_and_where_it_was_seen(self):
        root = self.drift_repo()

        self.assertEqual(self.stale_record(root).extra["evidence"],
                         {"source": SOURCE, "line": 1, "observed": "RATE = 0.025"})

    def test_a_finding_carries_the_replacement_line_for_a_stale_claim(self):
        root = self.drift_repo()

        self.assertIn("2.5%", self.stale_record(root).extra["fix"])

    def test_a_findings_identity_is_the_unit_it_groups(self):
        root = self.drift_repo()

        self.assertEqual(self.stale_record(root).extra["units"],
                         [self.claim_unit(root).digest])

    def test_rewording_the_evidence_prose_leaves_the_identity_alone(self):
        root = self.drift_repo()

        before = self.stale_record(root)
        after = self.stale_record(root, evidence=evidence(observed="rate is .025"))

        self.assertEqual(before.digest, after.digest)


class WaiverState(DriftRepoTestCase):
    def waived_repo(self, claim=UNRELATED_CLAIM, file=UNRELATED, **changes):
        changes.setdefault(UNRELATED, f"# U\n\n{UNRELATED_CLAIM}\n")
        changes[WAIVERS] = json.dumps({"waivers": [
            {"file": file, "claim": claim, "reason": "accepted",
             "date": "2026-01-01"},
        ]})
        return self.drift_repo(**changes)

    def plain_repo(self):
        return self.drift_repo(**{UNRELATED: f"# U\n\n{UNRELATED_CLAIM}\n"})

    def unverifiable_report(self, root, **kwargs):
        """One UNVERIFIABLE claim on the unrelated document."""
        kwargs.setdefault("waivers", WAIVERS)
        return self.audit(root, verdicts=self.verdicts_for(
            root,
            self.verdict(root, path=UNRELATED, text=UNRELATED_CLAIM,
                         verdict="UNVERIFIABLE", fix=None,
                         evidence={"observed": "no checkable value named"}),
            path=UNRELATED,
        ), **kwargs)

    def test_a_waived_claim_is_still_a_record_in_the_raw_report(self):
        root = self.waived_repo()

        report = self.unverifiable_report(root)

        self.assertEqual([r.extra["code"] for r in report.records],
                         ["UNVERIFIABLE"])

    def test_a_waived_record_says_it_is_waived_and_where_that_is_recorded(self):
        root = self.waived_repo()

        record = self.unverifiable_report(root).records[0]

        self.assertEqual(record.extra["waived"]["source"], WAIVERS)
        self.assertEqual(record.extra["waived"]["reason"], "accepted")

    def test_a_waiver_names_the_claim_it_accepts_however_the_line_wraps(self):
        """Legacy waivers name a fragment of the doc line; a unit is the whole
        sentence, so containment is the match."""
        root = self.waived_repo(claim="within one business day")

        self.assertIn("waived", self.unverifiable_report(root).records[0].extra)

    def test_an_unwaived_record_carries_no_waiver_state(self):
        root = self.plain_repo()

        record = self.unverifiable_report(root).records[0]

        self.assertNotIn("waived", record.extra)

    def test_a_waiver_for_another_document_does_not_reach_this_one(self):
        root = self.waived_repo(file=LIVING)

        self.assertNotIn("waived", self.unverifiable_report(root).records[0].extra)

    def test_a_waiver_does_not_move_the_findings_identity(self):
        """Disposition is not identity: waiving a claim must not re-key the
        record an approval set selects."""
        root = self.waived_repo()

        waived = self.unverifiable_report(root)
        raw = self.unverifiable_report(root, waivers=None)

        self.assertIn("waived", waived.records[0].extra)
        self.assertEqual(waived.records[0].digest, raw.records[0].digest)

    def test_a_waiver_on_a_stale_claim_surfaces_as_a_dispute(self):
        """A human accepted a claim the audit calls stale. The finding stands —
        and says so, because a dispute a report did not show is one an
        auto-apply policy would act straight through."""
        root = self.waived_repo(claim=LIVING_CLAIM, file=LIVING)

        report = self.audit(root, waivers=WAIVERS,
                            verdicts=self.verdicts_for(root, self.verdict(root)))

        self.assertEqual([r.extra["code"] for r in report.records], ["STALE"])
        self.assertEqual(report.records[0].extra["waived"]["source"], WAIVERS)

    def test_a_malformed_waivers_file_invalidates_the_run(self):
        """A typo that silently un-waived everything would defeat the
        mechanism."""
        root = self.drift_repo(**{WAIVERS: '{"waivers": "none"}'})

        result = self.audit(root, waivers=WAIVERS,
                            verdicts=self.verdicts_for(root, self.verdict(root)))

        self.assertEqual(codes(result), ["drift-waivers-invalid"])

    def test_an_absent_waivers_file_is_simply_no_waivers(self):
        root = self.drift_repo()

        report = self.audit(root, waivers=WAIVERS,
                            verdicts=self.verdicts_for(root, self.verdict(root)))

        self.assertEqual(report.status, STATE_FINDINGS)

    def test_accepting_a_claim_does_not_expire_earlier_reports(self):
        """Detection stays pure: a waiver changes what a reader is asked to
        look at, never what the audit found, so it is not audit configuration
        and cannot make prior reports stale."""
        root = self.waived_repo()

        annotated = self.unverifiable_report(root)
        raw = self.unverifiable_report(root, waivers=None)

        self.assertEqual(annotated.lineage.audit_config_digest,
                         raw.lineage.audit_config_digest)
        self.assertNotEqual(annotated.digest, raw.digest)

    def test_the_evidence_boundary_is_part_of_the_audit_configuration(self):
        """What a run was permitted to consult could change a verdict, so
        narrowing it makes prior reports stale rather than reusable."""
        root = self.plain_repo()

        wide = self.audit(root)
        narrow = self.audit(root, evidence_sources=("src/**",))

        self.assertNotEqual(wide.lineage.audit_config_digest,
                            narrow.lineage.audit_config_digest)


class ReadOnly(DriftRepoTestCase):
    def tree(self, root):
        listing = {}
        for base, dirs, names in os.walk(root):
            dirs[:] = [d for d in dirs if d != ".git"]
            for name in names:
                path = os.path.join(base, name)
                listing[os.path.relpath(path, root)] = os.stat(path).st_mtime_ns
        return listing

    def test_a_full_audit_changes_nothing_on_disk(self):
        root = self.drift_repo(**{NARRATIVE: ANCHORED_TEXT})
        before = self.tree(root)

        self.audit(root, verdicts=self.verdicts_for(root, self.verdict(root)))

        self.assertEqual(self.tree(root), before)

    def test_a_fix_in_a_verdict_is_recorded_and_never_applied(self):
        root = self.drift_repo()

        self.audit(root, verdicts=self.verdicts_for(root, self.verdict(root)))

        with open(os.path.join(root, LIVING), encoding="utf-8") as fh:
            self.assertIn("2% of the amount", fh.read())


if __name__ == "__main__":
    unittest.main(verbosity=2)
