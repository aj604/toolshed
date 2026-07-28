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
from doclifecycle.finding import (  # noqa: E402
    FACTUAL,
    NON_ASSERTIVE,
    NORMATIVE,
    RATIONALE,
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
WAIVERS = ".doc-lifecycle/drift-waivers.json"

LIVING_CLAIM = "The fee is 2% of the amount, in `src/fees.py`."
UNRELATED_CLAIM = "Support answers within one business day."

# A living document whose prose is not all of one kind: the four assertion
# classes, in the one place they can be told apart.
MIXED = "docs/mixed.md"
MIXED_CONNECTIVE = "For example, consider a refund."
MIXED_RATIONALE = "The rate is flat because the processor bills once per charge."
MIXED_NORMATIVE = "Every endpoint must carry an integration test."
MIXED_TEXT = (
    f"# Mixed\n\n{MIXED_CONNECTIVE}\n\n{MIXED_RATIONALE}\n\n{MIXED_NORMATIVE}\n"
)

# Anchors nothing in the repository, so nothing can have moved out from under
# it: the honestly-dated baseline every other narrative case is a departure from.
NARRATIVE_TEXT = "# Tour\n\n> As of 2026-01-01 (initial commit)\n\nWelcome aboard.\n"
# Anchors the module the living document also cites, so a commit touching that
# module leaves this anchor behind.
ANCHORED_TEXT = "# Tour\n\n> As of 2026-01-01 (`src/fees.py`)\n\nWelcome aboard.\n"
# Anchors that same module by its bare filename: the module is in the
# repository, but not at the path the anchor spells.
ABBREVIATED = os.path.basename(SOURCE)
ABBREVIATED_TEXT = f"# Tour\n\n> As of 2026-01-01 (`{ABBREVIATED}`)\n\nHi.\n"

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
            "assertion_class": FACTUAL,
            "verdict": "STALE",
            "kind": "value",
            "tier": 2,
            "evidence": evidence(),
            "fix": "The fee is 2.5% of the amount, in `src/fees.py`.",
        }
        entry.update(overrides)
        return entry

    def unit_entry(self, root, path, text, assertion_class):
        """An answer for a unit that carries no evidence obligation."""
        return {"unit": self.claim_unit(root, path, text).digest,
                "assertion_class": assertion_class}

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

    def test_a_unit_left_unanswered_makes_the_document_a_gap(self):
        root = self.drift_repo()

        report = self.audit(root, verdicts=self.verdicts_for(root))

        self.assertEqual(report.status, STATE_PARTIAL)
        self.assertIn("classification-missing", report.incomplete[0].reason)

    def test_findings_and_gaps_together_still_read_as_partial(self):
        root = self.drift_repo(**{UNRELATED: f"# U\n\n{UNRELATED_CLAIM}\n"})

        report = self.audit(root, verdicts={"documents": [
            {"path": LIVING, "status": "ok", "verdicts": [self.verdict(root)]},
            {"path": UNRELATED, "status": "failed", "reason": "timed out"},
        ]})

        self.assertEqual(report.status, STATE_PARTIAL)
        self.assertEqual(len(report.records), 1)
        self.assertEqual([i.scope for i in report.incomplete], [UNRELATED])


class UnclassifiedDocuments(DriftRepoTestCase):
    """A document the registry does not claim is a hole in coverage.

    Classification is closed-world within the declared roots, so an
    unregistered document has no known obligation — the audit cannot examine
    it, and a full-corpus run that stayed silent about it would be claiming a
    coverage it does not have.
    """

    STRAY = "docs/notes/stray.md"

    def stray_repo(self, **changes):
        changes.setdefault(self.STRAY, "# Stray\n\nMatched by no rule.\n")
        return self.drift_repo(**changes)

    def test_the_plan_names_it_rather_than_walking_past_it(self):
        root = self.stray_repo()

        plan = plan_drift_audit(root, mode=MODE_FULL)

        self.assertEqual(plan.unclassified, (self.STRAY,))

    def test_it_becomes_an_enumerated_coverage_gap(self):
        root = self.stray_repo()

        report = self.audit(root, verdicts=self.verdicts_for(
            root, self.verdict(root)))

        self.assertEqual(report.status, STATE_PARTIAL)
        self.assertIn(self.STRAY, [i.scope for i in report.incomplete])

    def test_the_gap_says_what_would_close_it(self):
        root = self.stray_repo()

        report = self.audit(root, verdicts=self.verdicts_for(
            root, self.verdict(root)))

        reason = next(i.reason for i in report.incomplete
                      if i.scope == self.STRAY)
        self.assertIn("registry", reason)

    def test_it_is_not_in_the_declared_scope_it_was_never_examinable_in(self):
        root = self.stray_repo()

        report = self.audit(root, verdicts=self.verdicts_for(
            root, self.verdict(root)))

        self.assertNotIn(self.STRAY, report.scope.documents)

    def test_a_diff_scoped_run_leaves_one_its_range_never_reached(self):
        root = self.stray_repo()
        self.write(root, SOURCE, "RATE = 0.025\n")
        self.commit(root, "raise the rate")

        report = self.audit(root, mode=MODE_INCREMENTAL, since=self.base,
                            verdicts=self.verdicts_for(root, self.verdict(root)))

        self.assertNotIn(self.STRAY, [i.scope for i in report.incomplete])

    def test_a_diff_scoped_run_reports_one_its_range_did_reach(self):
        root = self.stray_repo()
        self.write(root, self.STRAY, "# Stray\n\nEdited.\n")
        self.commit(root, "edit the stray note")

        report = self.audit(root, mode=MODE_INCREMENTAL, since=self.base)

        self.assertIn(self.STRAY, [i.scope for i in report.incomplete])

    def test_a_registered_corpus_can_still_complete(self):
        """The gap is the unregistered document, not the closed-world rule: a
        fully classified corpus reaches a state with no gaps at all."""
        root = self.drift_repo()

        report = self.audit(root, verdicts=self.verdicts_for(
            root, self.verdict(root)))

        self.assertEqual(report.incomplete, ())


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

    def test_an_answer_about_a_unit_the_document_lacks_is_refused(self):
        root = self.drift_repo()

        self.assertIn("classification-unknown-unit",
                      self.gap_reason(root, unit="a" * 64))

    def test_a_verdict_against_a_heading_is_refused(self):
        """Structure cannot carry an assertion, so it cannot be found stale —
        that is how injected prose in a non-assertive unit stays
        unactionable."""
        root = self.drift_repo()
        heading = self.units_of(root, LIVING)["Reference"]

        self.assertIn("classification-not-assertion-capable",
                      self.gap_reason(root, unit=heading.digest))

    def test_one_unit_judged_twice_is_refused(self):
        root = self.drift_repo()

        report = self.audit(root, verdicts=self.verdicts_for(
            root, self.verdict(root),
            self.verdict(root, verdict="VERIFIED", fix=None)))

        self.assertEqual(report.status, STATE_PARTIAL)
        self.assertIn("classification-duplicate", report.incomplete[0].reason)

    def test_evidence_outside_the_declared_boundary_is_refused(self):
        root = self.drift_repo()

        report = self.audit(root, evidence_sources=("lib/**",),
                            verdicts=self.verdicts_for(root, self.verdict(root)))

        self.assertIn("drift-evidence-outside-boundary",
                      report.incomplete[0].reason)


class OrdinalKeyedVerdicts(DriftRepoTestCase):
    """#116: a verdict may answer for a unit by the segmenter's own per-document
    ordinal instead of its 64-character digest, and the engine resolves that
    back to the digest itself. This is what removes the shadow-parity gate's
    G3 near-miss failure mode (docs/plans/2026-07-26-shadow-parity-gate.md) —
    a model no longer has to transcribe a 64-character hex string verbatim, so
    a truncated or off-by-one-character transcription of one cannot happen.
    """

    def test_an_ordinal_keyed_answer_resolves_to_the_right_unit(self):
        root = self.drift_repo()
        ordinal = self.claim_unit(root).ordinal

        report = self.audit(root, verdicts=self.verdicts_for(
            root, self.verdict(root, unit=ordinal)))

        self.assertEqual(report.status, STATE_FINDINGS)
        self.assertEqual([r.extra["code"] for r in report.records], ["STALE"])

    def test_an_ordinal_outside_the_documents_range_is_refused(self):
        root = self.drift_repo()

        report = self.audit(root, verdicts=self.verdicts_for(
            root, self.verdict(root, unit=99999)))

        self.assertEqual(report.status, STATE_PARTIAL)
        self.assertIn("drift-verdict-unknown-ordinal", report.incomplete[0].reason)

    def test_a_truncated_digest_no_longer_has_to_be_answered_by_a_model(self):
        """Reproduces the shadow-parity gate's G3 measurement directly: 36 of
        39 first-round near-misses were a real unit's digest truncated to
        57-63 characters. Answered the old way (a bare digest string, still
        accepted for a direct caller), a garbled digest still names no unit
        and the document still fails closed — unit identity is still the
        digest, and garbage in is garbage out. What #116 removes is the
        model's *obligation* to transcribe that digest at all: the same
        answer, keyed by the unit's ordinal instead, cannot be truncated into
        a near miss, because there is no 64-character string to transcribe.
        """
        root = self.drift_repo()
        unit = self.claim_unit(root)
        garbled_digest = unit.digest[:-3]     # truncated, the recorded shape

        by_garbled_digest = self.audit(root, verdicts=self.verdicts_for(
            root, self.verdict(root, unit=garbled_digest)))
        self.assertEqual(by_garbled_digest.status, STATE_PARTIAL)

        by_ordinal = self.audit(root, verdicts=self.verdicts_for(
            root, self.verdict(root, unit=unit.ordinal)))
        self.assertEqual(by_ordinal.status, STATE_FINDINGS)


class AssertionClasses(DriftRepoTestCase):
    """What each unit *is* is the model's other answer, and it is recorded.

    A structurally capable sentence is not automatically a claim: connective
    prose is a real answer, not the absence of one, and forcing a verdict onto
    it would manufacture a claim nobody made.
    """

    def mixed_repo(self):
        return self.drift_repo(**{MIXED: MIXED_TEXT})

    def mixed_audit(self, root, *overrides):
        """The three mixed-document units, classified but unjudged by default."""
        entries = {
            MIXED_CONNECTIVE: self.unit_entry(root, MIXED, MIXED_CONNECTIVE,
                                              NON_ASSERTIVE),
            MIXED_RATIONALE: self.unit_entry(root, MIXED, MIXED_RATIONALE,
                                             RATIONALE),
            MIXED_NORMATIVE: self.unit_entry(root, MIXED, MIXED_NORMATIVE,
                                             NORMATIVE),
        }
        for text, entry in overrides:
            entries[text] = entry
        return self.audit(root, verdicts={"documents": [
            {"path": LIVING, "status": "ok",
             "verdicts": [self.verdict(root)]},
            {"path": MIXED, "status": "ok",
             "verdicts": [e for e in entries.values() if e is not None]},
        ]})

    def gap_for(self, report, path=MIXED):
        return next(i.reason for i in report.incomplete if i.scope == path)

    def test_prose_carrying_no_obligation_needs_no_verdict(self):
        root = self.mixed_repo()

        report = self.mixed_audit(root)

        self.assertEqual(report.status, STATE_FINDINGS)
        self.assertEqual([i.scope for i in report.incomplete], [])

    def test_a_normative_unit_may_still_be_found_stale(self):
        root = self.mixed_repo()

        report = self.mixed_audit(root, (MIXED_NORMATIVE, self.verdict(
            root, path=MIXED, text=MIXED_NORMATIVE,
            assertion_class=NORMATIVE, kind="behavior",
            fix="Every endpoint must carry two integration tests.")))

        self.assertEqual(sorted(r.extra["path"] for r in report.records),
                         sorted([LIVING, MIXED]))

    def test_the_recorded_class_travels_on_the_finding(self):
        root = self.mixed_repo()

        report = self.mixed_audit(root)

        self.assertEqual(report.records[0].extra["assertion_class"], FACTUAL)

    def test_a_verdict_against_non_assertive_prose_is_refused(self):
        """The category error AC3 forbids for a narrative document, inside a
        living one."""
        root = self.mixed_repo()

        report = self.mixed_audit(root, (MIXED_CONNECTIVE, self.verdict(
            root, path=MIXED, text=MIXED_CONNECTIVE,
            assertion_class=NON_ASSERTIVE)))

        self.assertIn("drift-verdict-not-obligated", self.gap_for(report))

    def test_a_factual_unit_without_a_verdict_is_refused(self):
        root = self.mixed_repo()

        report = self.mixed_audit(root, (MIXED_RATIONALE, self.unit_entry(
            root, MIXED, MIXED_RATIONALE, FACTUAL)))

        self.assertIn("drift-verdict-owed", self.gap_for(report))

    def test_a_unit_nobody_classified_is_a_coverage_gap(self):
        root = self.mixed_repo()

        report = self.mixed_audit(root, (MIXED_RATIONALE, None))

        self.assertEqual(report.status, STATE_PARTIAL)
        self.assertIn("classification-missing", self.gap_for(report))

    def test_an_unknown_assertion_class_is_refused(self):
        root = self.mixed_repo()

        report = self.mixed_audit(root, (MIXED_RATIONALE, self.unit_entry(
            root, MIXED, MIXED_RATIONALE, "editorial")))

        self.assertIn("classification-unknown-class", self.gap_for(report))

    def test_a_class_against_a_heading_is_refused_by_its_one_owner(self):
        """`finding.record_classifications` owns that rule; the drift audit
        calls it rather than re-deriving it."""
        root = self.mixed_repo()
        heading = self.units_of(root, MIXED)["Mixed"]

        report = self.mixed_audit(root, (MIXED_RATIONALE, {
            "unit": heading.digest, "assertion_class": FACTUAL,
        }))

        self.assertIn("classification-not-assertion-capable",
                      self.gap_for(report))


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

    def test_an_anchor_naming_a_path_the_repository_lacks_is_unresolvable(self):
        """Issue #97: a reference the repository cannot resolve is reported
        under its own code. The engine cannot tell a deleted file from a
        shorthand spelling, so it claims neither."""
        root = self.drift_repo(**{NARRATIVE: ANCHORED_TEXT})
        os.remove(os.path.join(root, SOURCE))
        self.commit(root, "drop the module")

        report = self.audit(root)

        record = self.anchor_records(report)["ANCHOR-UNRESOLVABLE-REFERENCE"]
        self.assertEqual(record.extra["evidence"]["source"], SOURCE)

    def test_an_abbreviated_reference_is_not_reported_as_a_gone_file(self):
        """Issue #97: `fees.py` names a file that is in the repository under
        `src/`, so "is no longer in the repository" is a false claim — the
        shorthand is what is wrong, not the target."""
        root = self.drift_repo(**{NARRATIVE: ABBREVIATED_TEXT})

        report = self.audit(root)

        records = self.anchor_records(report)
        self.assertNotIn("ANCHOR-STALE", records)
        self.assertNotIn(
            "no longer",
            records["ANCHOR-UNRESOLVABLE-REFERENCE"].extra["evidence"]["observed"],
        )

    def test_an_unresolvable_reference_asks_for_a_repo_relative_path(self):
        """The finding has to say what a correct anchor looks like: the fix for
        a shorthand is the full path, and nothing else in the run says so."""
        root = self.drift_repo(**{NARRATIVE: ABBREVIATED_TEXT})

        report = self.audit(root)

        record = self.anchor_records(report)["ANCHOR-UNRESOLVABLE-REFERENCE"]
        self.assertIn("repository-relative", record.extra["evidence"]["observed"])

    def test_an_unresolvable_reference_does_not_absorb_a_stale_sibling(self):
        """Two defects in one anchor stay two findings: fixing the spelling of
        one reference does not refresh the date the other is behind."""
        root = self.drift_repo(**{
            NARRATIVE: "# Tour\n\n"
                       f"> As of 2026-01-01 (`{ABBREVIATED}`, `{SOURCE}`)\n\nHi.\n"})
        self.write(root, SOURCE, "RATE = 0.025\n")
        self.commit(root, "raise the rate")

        report = self.audit(root)

        records = self.anchor_records(report)
        self.assertEqual(records["ANCHOR-UNRESOLVABLE-REFERENCE"]
                         .extra["references"], [ABBREVIATED])
        self.assertEqual(records["ANCHOR-STALE"].extra["references"], [SOURCE])

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

    def test_an_anchor_dated_after_the_repository_exists_is_dishonest(self):
        """"Honestly dated" has two directions. A date the repository has not
        reached cannot be when anything was checked."""
        root = self.drift_repo(**{
            NARRATIVE: "# Tour\n\n> As of 2099-01-01 (`src/fees.py`)\n\nHi.\n"})

        report = self.audit(root)

        self.assertIn("ANCHOR-FUTURE-DATED", self.anchor_records(report))

    def test_an_anchor_as_current_as_the_code_it_names_is_left_alone(self):
        root = self.drift_repo()
        today = self.git(root, "log", "-1", "--format=%cs")
        self.write(root, NARRATIVE,
                   f"# Tour\n\n> As of {today} (`src/fees.py`)\n\nHi.\n")
        self.commit(root, "refresh the anchor")

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

    def test_a_directory_anchor_is_not_falsely_reported_missing(self):
        """Issue #93: the anchor check gated every reference on `os.path.
        isfile`, which is False for a directory, so a narrative anchor naming
        a real directory (`src/`) was falsely reported "no longer in the
        repository" even though nothing beneath it had moved."""
        root = self.drift_repo()
        today = self.git(root, "log", "-1", "--format=%cs")
        self.write(root, NARRATIVE, f"# Tour\n\n> As of {today} (`src/`)\n\nHi.\n")
        self.commit(root, "refresh the anchor")

        report = self.audit(root)

        self.assertEqual(report.records, ())

    def test_a_directory_anchor_is_stale_when_something_beneath_it_changes(self):
        """A directory anchor's freshness is the most recent change to
        anything beneath it, not just the directory entry itself."""
        root = self.drift_repo(
            **{NARRATIVE: "# Tour\n\n> As of 2026-01-01 (`src/`)\n\nHi.\n"})
        self.write(root, SOURCE, "RATE = 0.025\n")
        self.commit(root, "raise the rate")

        report = self.audit(root)

        record = self.anchor_records(report)["ANCHOR-STALE"]
        self.assertEqual(record.extra["evidence"]["source"], "src/")
        self.assertIn("last changed", record.extra["evidence"]["observed"])


class EvidencePointers(DriftRepoTestCase):
    def stale_record(self, root, **overrides):
        report = self.audit(root, verdicts=self.verdicts_for(
            root, self.verdict(root, **overrides)))
        self.assertEqual(report.status, STATE_FINDINGS, report.to_dict())
        return report.records[0]

    def test_a_finding_points_at_the_line_it_is_about(self):
        root = self.drift_repo()

        self.assertEqual(self.stale_record(root).extra["location"], f"{LIVING}:3")

    def test_a_finding_quotes_the_assertion_the_document_makes(self):
        """Taken from the segmentation, never from the model: what the document
        says is not the model's to report."""
        root = self.drift_repo()

        self.assertEqual(self.stale_record(root).extra["assertion"], LIVING_CLAIM)

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


class TheEvidenceBoundary(DriftRepoTestCase):
    """A pointer is checked as a path before it is matched against the boundary.

    The boundary is a glob, and a glob is a string match: `src/**` matches
    `src/../../../etc/passwd` exactly as happily as it matches `src/fees.py`.
    So `paths.py` — the single owner of path safety — decides what a
    repository-relative path is, and only then does the boundary decide whether
    it is inside one.
    """

    def gap_reason(self, root, source, **kwargs):
        report = self.audit(root, verdicts=self.verdicts_for(
            root, self.verdict(root, evidence=evidence(source=source))
        ), **kwargs)
        self.assertEqual(report.status, STATE_PARTIAL, report.to_dict())
        return report.incomplete[0].reason

    def test_a_traversal_spelling_does_not_walk_through_the_boundary(self):
        """The reviewer's probe on PR #87: with a boundary of `src/**`, a
        `source` of `src/../../../../../../etc/passwd` was accepted into the
        report as a finding's evidence pointer, while the plain absolute
        spelling was blocked."""
        root = self.drift_repo()

        reason = self.gap_reason(root, "src/../../../../../../etc/passwd",
                                 evidence_sources=("src/**",))

        self.assertIn("drift-verdict-invalid-evidence", reason)

    def test_no_unsafe_spelling_of_a_pointer_is_accepted(self):
        root = self.drift_repo()
        unsafe = {
            "traversal": "src/../../../../../../etc/passwd",
            "absolute": "/etc/passwd",
            "home relative": "~/.ssh/id_rsa",
            "doubled separator": "src//fees.py",
            "dot component": "./src/fees.py",
            "trailing separator": "src/fees.py/",
            "windows separator": "src\\fees.py",
            "leading dash": "-rf/fees.py",
            "control character": "src/fees.py\x00",
            "empty": "   ",
        }

        for name, source in unsafe.items():
            with self.subTest(spelling=name):
                self.assertIn("drift-verdict-invalid-evidence",
                              self.gap_reason(root, source))

    def test_the_refusal_names_which_rule_the_spelling_broke(self):
        """`paths.py` diagnoses, drift reports: a lane that must re-point its
        evidence should not have to guess what was wrong with it."""
        root = self.drift_repo()

        report = self.audit(root, verdicts=self.verdicts_for(
            root, self.verdict(root, evidence=evidence(source="src/../etc"))
        ))

        problems = report.incomplete[0].reason
        self.assertIn("drift-verdict-invalid-evidence", problems)

    def test_the_gap_names_the_source_that_broke_the_spelling_rule(self):
        """PR #87 review, N4: the fixture's own hostile filenames (a leading
        dash, `; rm -rf ~`) are documents drift declares and examines but
        that can never be cited as evidence sources — the gap this produced
        named only `drift-verdict-invalid-evidence`, losing which source
        broke which rule. The gap now names the source too."""
        root = self.drift_repo()
        hostile = "-rf/fees.py"

        reason = self.gap_reason(root, hostile)

        self.assertIn("drift-verdict-invalid-evidence", reason)
        self.assertIn(hostile, reason)

    def test_the_boundary_gap_also_names_the_offending_source(self):
        """The same detail for the other evidence code: a source that is a
        well-formed path but outside the declared boundary."""
        root = self.drift_repo()

        reason = self.gap_reason(root, SOURCE, evidence_sources=("lib/**",))

        self.assertIn("drift-evidence-outside-boundary", reason)
        self.assertIn(SOURCE, reason)

    def test_a_canonical_pointer_inside_the_boundary_is_accepted(self):
        root = self.drift_repo()

        report = self.audit(root, evidence_sources=("src/**",),
                            verdicts=self.verdicts_for(root, self.verdict(root)))

        self.assertEqual(report.status, STATE_FINDINGS)
        self.assertEqual(report.records[0].extra["evidence"]["source"], SOURCE)

    def test_a_pointer_at_a_file_a_commit_deleted_is_still_a_pointer(self):
        """Existence is deliberately not part of the check: a claim about a
        file that is gone is exactly what a STALE finding reports."""
        root = self.drift_repo()

        report = self.audit(root, verdicts=self.verdicts_for(
            root, self.verdict(root, evidence=evidence(source="src/removed.py"))
        ))

        self.assertEqual(report.status, STATE_FINDINGS)


class RecordedCoverage(DriftRepoTestCase):
    """VERIFIED coverage and the assertion classes, recorded rather than dropped.

    The spec says the model "only classifies units ... and renders verdicts,
    recorded in the report as reviewable data". Validating both and then
    discarding them leaves positive coverage resting on an absence: a document
    with no finding and no gap is indistinguishable from one nobody looked at.
    """

    def verified_report(self, root, **kwargs):
        """A living document whose one claim was checked and holds."""
        return self.audit(root, verdicts=self.verdicts_for(
            root, self.verdict(root, verdict="VERIFIED", fix=None)
        ), **kwargs)

    def coverage(self, report, path=LIVING):
        return next(e.detail for e in report.examined if e.scope == path)

    def test_a_clean_document_is_recorded_as_examined(self):
        """The reviewer's probe on PR #87: on a document where every unit was
        classified and the factual unit was VERIFIED, `assertion_class` did not
        appear anywhere in the payload and the document was simply absent."""
        root = self.drift_repo()

        report = self.verified_report(root)

        self.assertEqual(report.status, STATE_CLEAN)
        self.assertIn(LIVING, [e.scope for e in report.examined])

    def test_recorded_coverage_counts_the_classes_the_model_assigned(self):
        root = self.drift_repo()

        detail = self.coverage(self.verified_report(root))

        self.assertEqual(detail["classes"], {FACTUAL: 1})

    def test_recorded_coverage_counts_the_verdicts_reached(self):
        root = self.drift_repo()

        detail = self.coverage(self.verified_report(root))

        self.assertEqual(detail["verdicts"], {"VERIFIED": 1})

    def test_a_verified_unit_keeps_the_evidence_that_backed_it(self):
        """Evidence is mandatory for VERIFIED precisely so it can be checked;
        validating it and dropping it makes the requirement decorative."""
        root = self.drift_repo()

        verified = self.coverage(self.verified_report(root))["verified"]

        self.assertEqual(len(verified), 1)
        self.assertEqual(verified[0]["evidence"]["source"], SOURCE)
        self.assertEqual(verified[0]["location"], f"{LIVING}:3")
        self.assertEqual(verified[0]["assertion_class"], FACTUAL)

    def test_a_verified_unit_does_not_become_a_finding(self):
        root = self.drift_repo()

        report = self.verified_report(root)

        self.assertEqual(report.records, ())

    def test_the_classes_of_unjudged_units_are_recorded_too(self):
        """A unit that owed no verdict was still classified, and the class is
        the answer — it is what says nobody was asked to judge it."""
        root = self.drift_repo(**{MIXED: MIXED_TEXT})
        report = self.audit(root, verdicts=self.verdicts_for(
            root,
            self.unit_entry(root, MIXED, MIXED_CONNECTIVE, NON_ASSERTIVE),
            self.unit_entry(root, MIXED, MIXED_RATIONALE, RATIONALE),
            self.unit_entry(root, MIXED, MIXED_NORMATIVE, NORMATIVE),
            path=MIXED,
        ))

        self.assertEqual(self.coverage(report, MIXED)["classes"],
                         {NON_ASSERTIVE: 1, NORMATIVE: 1, RATIONALE: 1})

    def test_a_narrative_document_records_the_anchor_it_was_checked_against(self):
        """A narrative document that passes produces no record either, and
        "the anchor was read and it was honestly dated" is a different fact
        from "nobody looked"."""
        root = self.drift_repo()

        report = self.verified_report(root)

        self.assertEqual(self.coverage(report, NARRATIVE),
                         {"obligation": OBLIGATION_ANCHOR, "anchor": "dated",
                          "as_of": "2026-01-01", "references": []})

    def test_a_document_that_was_not_examined_records_no_coverage(self):
        """Exactly one of the two: a report saying both would describe two
        different runs."""
        root = self.drift_repo()

        report = self.audit(root, verdicts={"documents": [
            {"path": LIVING, "status": "failed", "reason": "the lane died"},
        ]})

        self.assertEqual(report.status, STATE_PARTIAL)
        self.assertNotIn(LIVING, [e.scope for e in report.examined])
        self.assertEqual([g.scope for g in report.incomplete], [LIVING])

    def test_recorded_coverage_is_part_of_the_reports_identity(self):
        """Two runs finding nothing, one having verified a claim and one
        having declared it unjudgeable, are not the same report."""
        root = self.drift_repo()
        verified = self.verified_report(root)
        unjudged = self.audit(root, verdicts=self.verdicts_for(
            root, self.unit_entry(root, LIVING, LIVING_CLAIM, NON_ASSERTIVE)
        ))

        self.assertEqual(verified.status, unjudged.status)
        self.assertNotEqual(verified.digest, unjudged.digest)


class WaiverBreadth(DriftRepoTestCase):
    """A waiver is exactly as broad as the text it quotes — so bound the text.

    Containment is the right matcher: a human quotes what they read on a line,
    and a unit is the sentence that line sits in. The unstated half was that
    nothing bounded the fragment and the report never said how far one reached.
    """

    def repo_with(self, claim, documents=1):
        """A repository whose living documents all share one sentence."""
        changes = {
            f"docs/shared-{i}.md": f"# S{i}\n\n{UNRELATED_CLAIM}\n"
            for i in range(documents)
        }
        changes[WAIVERS] = json.dumps({"waivers": [
            {"file": "docs/shared-0.md", "claim": claim},
        ]})
        return self.drift_repo(**changes)

    def unverifiable(self, root, path, texts):
        entries = [
            self.verdict(root, path=path, text=text, verdict="UNVERIFIABLE",
                         fix=None, evidence={"observed": "nothing checkable"})
            for text in texts
        ]
        return self.audit(root, waivers=WAIVERS,
                          verdicts=self.verdicts_for(root, *entries, path=path))

    def test_a_one_character_waiver_is_refused(self):
        """The reviewer's probe on PR #87: `{"file": ..., "claim": "e"}` waived
        every assertion-bearing record in the file."""
        root = self.repo_with("e")

        result = self.unverifiable(root, "docs/shared-0.md", [UNRELATED_CLAIM])

        self.assertEqual(codes(result), ["drift-waivers-invalid"])

    def test_no_fragment_below_the_minimum_is_accepted(self):
        for claim in ("e", "a", "the", "fee rate", "within one"):
            with self.subTest(claim=claim):
                root = self.repo_with(claim)

                result = self.unverifiable(root, "docs/shared-0.md",
                                           [UNRELATED_CLAIM])

                self.assertEqual(codes(result), ["drift-waivers-invalid"])

    def test_the_refusal_says_what_a_short_fragment_would_have_done(self):
        root = self.repo_with("e")

        result = self.unverifiable(root, "docs/shared-0.md", [UNRELATED_CLAIM])

        self.assertIn("containment", result.problems[0].message)

    def test_a_quoted_fragment_of_a_real_line_is_accepted(self):
        root = self.repo_with("within one business day")

        report = self.unverifiable(root, "docs/shared-0.md", [UNRELATED_CLAIM])

        self.assertIsInstance(report, Report)
        self.assertIn("waived", report.records[0].extra)

    def test_an_annotation_states_how_far_its_waiver_reached(self):
        root = self.repo_with("within one business day")

        report = self.unverifiable(root, "docs/shared-0.md", [UNRELATED_CLAIM])

        self.assertEqual(report.records[0].extra["waived"]["matched"], 1)

    def test_a_waiver_reaching_past_the_cap_refuses_the_run(self):
        """Both ways this fails are silent: an auto-apply policy that declines
        waiver-disputed records is switched off document-wide, and one that
        does not is told a human disputed findings nobody looked at."""
        sentences = [f"Fact number {i} still holds today." for i in range(12)]
        root = self.drift_repo(**{
            "docs/shared-0.md": "# S0\n\n" + "\n\n".join(sentences) + "\n",
            WAIVERS: json.dumps({"waivers": [
                {"file": "docs/shared-0.md", "claim": "still holds today"},
            ]}),
        })

        result = self.unverifiable(root, "docs/shared-0.md", sentences)

        self.assertEqual(codes(result), ["drift-waiver-too-broad"])

    def test_the_breadth_refusal_names_the_waiver_and_its_reach(self):
        sentences = [f"Fact number {i} still holds today." for i in range(12)]
        root = self.drift_repo(**{
            "docs/shared-0.md": "# S0\n\n" + "\n\n".join(sentences) + "\n",
            WAIVERS: json.dumps({"waivers": [
                {"file": "docs/shared-0.md", "claim": "still holds today"},
            ]}),
        })

        result = self.unverifiable(root, "docs/shared-0.md", sentences)

        self.assertIn("still holds today", result.problems[0].message)
        self.assertIn("12", result.problems[0].message)

    def test_a_waiver_at_the_cap_is_still_accepted(self):
        sentences = [f"Fact number {i} still holds today." for i in range(10)]
        root = self.drift_repo(**{
            "docs/shared-0.md": "# S0\n\n" + "\n\n".join(sentences) + "\n",
            WAIVERS: json.dumps({"waivers": [
                {"file": "docs/shared-0.md", "claim": "still holds today"},
            ]}),
        })

        report = self.unverifiable(root, "docs/shared-0.md", sentences)

        self.assertIsInstance(report, Report)
        self.assertEqual(report.records[0].extra["waived"]["matched"], 10)


class WaiverProvenance(DriftRepoTestCase):
    """A `waived` annotation names a file; on its own that is unverifiable.

    Excluding waivers from the audit-configuration digest is right — accepting
    a claim must not expire prior reports or re-key the findings an approval
    set selects. But the conclusion overshoots if the annotations are then
    unreproducible: nobody holding the report can tell whether the named file
    said that. The digest travels *beside* the annotation, not in lineage.
    """

    DEFAULT = json.dumps({
        "waivers": [{"file": UNRELATED, "claim": "within one business day"}],
    })

    def waived(self, contents=None, repo=None):
        """One UNVERIFIABLE finding, annotated from the waivers file.

        `repo` is reused rather than rebuilt when a test compares two runs: a
        second repository has a different root commit, so its lineage — and
        therefore every finding digest under it — legitimately differs, and
        the comparison would prove nothing about waivers.
        """
        if repo is None:
            repo = self.drift_repo(**{
                UNRELATED: f"# U\n\n{UNRELATED_CLAIM}\n",
                WAIVERS: contents if contents is not None else self.DEFAULT,
            })
        else:
            self.write(repo, WAIVERS,
                       contents if contents is not None else self.DEFAULT)
        report = self.audit(repo, waivers=WAIVERS, verdicts=self.verdicts_for(
            repo,
            self.verdict(repo, path=UNRELATED, text=UNRELATED_CLAIM,
                         verdict="UNVERIFIABLE", fix=None,
                         evidence={"observed": "no checkable value named"}),
            path=UNRELATED,
        ))
        self.assertIsInstance(report, Report, getattr(report, "problems", None))
        return report, repo

    def test_an_annotation_carries_the_digest_of_the_file_it_came_from(self):
        report, _ = self.waived()

        digest = report.records[0].extra["waived"]["source_digest"]
        self.assertRegex(digest, r"^[0-9a-f]{64}$")

    def test_the_digest_is_of_the_waivers_file_as_it_was_read(self):
        one, repo = self.waived()
        other, _ = self.waived(json.dumps({"waivers": [
            {"file": UNRELATED, "claim": "within one business day",
             "reason": "accepted by the platform team"},
        ]}), repo=repo)

        self.assertNotEqual(
            one.records[0].extra["waived"]["source_digest"],
            other.records[0].extra["waived"]["source_digest"],
        )

    def test_the_waivers_digest_stays_out_of_the_audit_configuration(self):
        """Detection stays pure. Accepting a claim must not make every report
        produced before it read as stale."""
        waived, repo = self.waived()
        unwaived = self.audit(repo, verdicts=self.verdicts_for(
            repo,
            self.verdict(repo, path=UNRELATED, text=UNRELATED_CLAIM,
                         verdict="UNVERIFIABLE", fix=None,
                         evidence={"observed": "no checkable value named"}),
            path=UNRELATED,
        ))

        self.assertEqual(waived.lineage.audit_config_digest,
                         unwaived.lineage.audit_config_digest)

    def test_the_waivers_digest_does_not_move_the_findings_identity(self):
        """Disposition is not identity: which waivers file accepted a claim
        must not re-key the record an approval set selects."""
        one, repo = self.waived()
        other, _ = self.waived(json.dumps({"waivers": [
            {"file": UNRELATED, "claim": "within one business day",
             "date": "2026-01-01"},
        ]}), repo=repo)

        self.assertNotEqual(
            one.records[0].extra["waived"]["source_digest"],
            other.records[0].extra["waived"]["source_digest"],
        )
        self.assertEqual(one.records[0].digest, other.records[0].digest)


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


class ToolCitations(DriftRepoTestCase):
    """A verdict settled by running a declared local tool, not by opening a file.

    The verification method's tier 2 sanctions `--help`/`--version`/dry-run on a
    local read-only tool, and a document that documents a tool's flags can only
    be checked that way. Before this the boundary was paths alone, so such a
    verdict had no contract-legal expression and came back UNVERIFIABLE — six
    false findings and one hidden STALE on this repository's own corpus (#115).
    """

    COMMAND = "gh pr list --json bogus"

    def cited(self, root, **overrides):
        """A verdict whose evidence cites a command instead of a path."""
        return self.verdict(root, evidence={
            "command": self.COMMAND,
            "observed": "Available fields: … author … (no authorAssociation)",
            **overrides,
        })

    def gap_for(self, root, entry, **kwargs):
        report = self.audit(root, verdicts=self.verdicts_for(root, entry),
                            **kwargs)
        self.assertEqual(report.status, STATE_PARTIAL, report.to_dict())
        return report.incomplete[0].reason

    def test_a_verdict_may_rest_on_a_command_the_boundary_declares(self):
        root = self.drift_repo()

        report = self.audit(root, evidence_commands=("gh",),
                            verdicts=self.verdicts_for(root, self.cited(root)))

        self.assertEqual([r.extra["code"] for r in report.records], ["STALE"])

    def test_the_record_keeps_the_command_a_reader_would_re_run(self):
        root = self.drift_repo()

        report = self.audit(root, evidence_commands=("gh",),
                            verdicts=self.verdicts_for(root, self.cited(root)))

        self.assertEqual(report.records[0].extra["evidence"]["command"],
                         self.COMMAND)

    def test_a_verified_verdict_may_be_settled_by_a_declared_command(self):
        """VERIFIED asserts someone checked; running the tool is checking."""
        root = self.drift_repo()

        report = self.audit(
            root, evidence_commands=("gh",),
            verdicts=self.verdicts_for(root, self.verdict(
                root, verdict="VERIFIED", fix=None,
                evidence={"command": "gh issue edit --help",
                          "observed": "--add-label is a flag"})))

        self.assertEqual(report.records, ())

    def test_an_unverifiable_verdict_may_cite_the_tool_that_did_not_settle_it(self):
        """"I ran it and still could not tell" is a real answer, and the
        command is what makes the finding worth anything to whoever reads it."""
        root = self.drift_repo()

        report = self.audit(
            root, evidence_commands=("gh",),
            verdicts=self.verdicts_for(root, self.verdict(
                root, verdict="UNVERIFIABLE", fix=None,
                evidence={"command": "gh issue edit --help",
                          "observed": "the help text does not mention it"})))

        self.assertEqual([r.extra["evidence"]["command"] for r in report.records],
                         ["gh issue edit --help"])

    def test_an_unverifiable_verdict_may_not_cite_an_undeclared_tool(self):
        """Pointing at nothing is allowed; pointing outside the boundary is
        not — that would rest the finding on something never consulted."""
        root = self.drift_repo()

        self.assertIn(
            "drift-evidence-outside-boundary",
            self.gap_for(root, self.verdict(
                root, verdict="UNVERIFIABLE", fix=None,
                evidence={"command": "gh issue edit --help",
                          "observed": "the help text does not mention it"})),
        )

    def test_a_boundary_declaring_no_commands_admits_none(self):
        """The closed world stays closed by default: a run that did not declare
        a tool cannot have consulted one."""
        root = self.drift_repo()

        self.assertIn("drift-evidence-outside-boundary",
                      self.gap_for(root, self.cited(root)))

    def test_a_command_outside_the_declared_set_is_refused(self):
        root = self.drift_repo()

        self.assertIn(
            "drift-evidence-outside-boundary",
            self.gap_for(root, self.cited(root), evidence_commands=("make",)),
        )

    def test_the_gap_names_the_command_that_broke_the_rule(self):
        """Same reason the offending source is folded in: the code alone says a
        citation broke a rule, not which one."""
        root = self.drift_repo()

        reason = self.gap_for(root, self.cited(root))

        self.assertIn(self.COMMAND, reason)

    def test_citing_a_path_and_a_command_at_once_is_refused(self):
        """A verdict rests on one place a reader goes; two pointers is two
        verdicts, and nobody can tell which one settled it."""
        root = self.drift_repo()

        self.assertIn(
            "drift-verdict-invalid-evidence",
            self.gap_for(root, self.cited(root, source=SOURCE),
                         evidence_commands=("gh",)),
        )

    def test_a_command_carrying_shell_syntax_is_refused(self):
        """The citation is an instruction a reader re-runs. A compound or
        substituting line must not be laundered as one read-only invocation."""
        root = self.drift_repo()

        self.assertIn(
            "drift-verdict-invalid-evidence",
            self.gap_for(root, self.verdict(root, evidence={
                "command": "gh pr list; rm -rf ~", "observed": "no such field"}),
                evidence_commands=("gh",)),
        )

    def test_a_command_substitution_is_refused_too(self):
        root = self.drift_repo()

        self.assertIn(
            "drift-verdict-invalid-evidence",
            self.gap_for(root, self.verdict(root, evidence={
                "command": "gh pr list --json $(cat /etc/passwd)",
                "observed": "no such field"}),
                evidence_commands=("gh",)),
        )

    def test_a_command_citation_takes_no_line_number(self):
        """A line number points into a file; a tool's output is not one."""
        root = self.drift_repo()

        self.assertIn(
            "drift-verdict-invalid-evidence",
            self.gap_for(root, self.cited(root, line=3),
                         evidence_commands=("gh",)),
        )

    def test_an_empty_command_names_nothing_to_re_run(self):
        root = self.drift_repo()

        self.assertIn(
            "drift-verdict-invalid-evidence",
            self.gap_for(root, self.cited(root, command="   "),
                         evidence_commands=("gh",)),
        )

    def test_the_declared_commands_are_part_of_the_audit_configuration(self):
        """Widening what a run may run could change a verdict, exactly as
        widening its paths could."""
        root = self.drift_repo()

        without = self.audit(root, verdicts=self.verdicts_for(
            root, self.verdict(root)))
        with_gh = self.audit(root, evidence_commands=("gh",),
                             verdicts=self.verdicts_for(root, self.verdict(root)))

        self.assertNotEqual(without.lineage.audit_config_digest,
                            with_gh.lineage.audit_config_digest)

    def test_the_finding_the_gap_used_to_hide_comes_back_stale(self):
        """The shadow-parity gate's false negative, end to end (#115).

        `docs/agents/issue-tracker.md` documented a `gh pr list --json` field
        that does not exist. The claim was checkable — `gh pr list --json bogus`
        enumerates the real ones — but the boundary was paths alone, so the only
        contract-legal answer was UNVERIFIABLE and the drift went unreported.
        """
        claim = ("List external PRs with `gh pr list --json "
                 "number,authorAssociation`.")
        root = self.drift_repo(**{UNRELATED: f"# Tracker\n\n{claim}\n"})

        report = self.audit(
            root, evidence_commands=("gh",),
            verdicts=self.verdicts_for(root, self.verdict(
                root, path=UNRELATED, text=claim, kind="command",
                evidence={"command": "gh pr list --json bogus",
                          "observed": "available fields do not include "
                                      "authorAssociation"},
                fix="List external PRs with `gh api "
                    "\"repos/{owner}/{repo}/pulls?state=open\"`."),
                path=UNRELATED))

        self.assertEqual([(r.extra["code"], r.extra["location"])
                          for r in report.records],
                         [("STALE", f"{UNRELATED}:3")])

    def test_the_report_declares_which_commands_were_citable(self):
        root = self.drift_repo()

        report = self.audit(root, evidence_commands=("gh",),
                            verdicts=self.verdicts_for(root, self.cited(root)))

        self.assertEqual(report.lineage.evidence_boundary.commands, ("gh",))


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
