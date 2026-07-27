#!/usr/bin/env python3
"""Scenario approval (issue #68): approval sets over the acceptance fixture.

Seams, per the engine's convention (`plugins/doc-lifecycle/engine/README.md`):
`reconcile()`, `mint_approval_set()`, `validate_approval_set()`, and
`write_approval_set()` as library calls, and `python3 -m doclifecycle
mint-approval` / `validate-approval` as subprocesses — over the REAL temporary
git repository the fixture builds, and over the REAL findings the drift audit
produces from it.

What it holds that the unit suites cannot: the findings are ones an audit
actually produced rather than ones a test wrote; the document a finding targets
carries a prompt-injection comment telling a reader to approve everything and
delete a vendored file; the "apply" between two subsets is a real edit to a
real file in a real work tree; and the repository the approval set may not be
written into is a real git repository with a real index.

Run: python3 tests/engine/acceptance/scenario_approval_test.py
"""

import json
import os
import shutil
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import fixture  # noqa: E402  (the acceptance fixture builder)
from scenario_drift_test import DriftScenarioTestCase, run_cli  # noqa: E402

from doclifecycle.approval import (  # noqa: E402
    ARTIFACT_KIND,
    ApprovalSet,
    Minter,
    mint_approval_set,
    validate_approval_set,
    write_approval_set,
)
from doclifecycle.finding import build_finding  # noqa: E402
from doclifecycle.reconcile import DISPOSITION_EXCLUSIVE, reconcile  # noqa: E402
from doclifecycle.render import approval_trailers, render_approval_set  # noqa: E402
from doclifecycle.report import validate_report  # noqa: E402
from doclifecycle.results import STATE_CLEAN, STATE_STALE, Invalid  # noqa: E402

APPROVER = Minter(kind="human", id="avery@example.com")

# What the fixture's living document says today, and what the drift finding
# proposes instead — the "apply" a scenario performs between two subsets.
STALE_SENTENCE = "flat 2% rate"
APPLIED_SENTENCE = "flat 2.5% rate"


class ApprovalScenarioTestCase(DriftScenarioTestCase):
    def approvable(self, repo):
        """The fixture's real drift report, and its two findings by document."""
        report = self.full_report(repo)
        by_path = {r.extra["path"]: r for r in report.records}
        self.assertEqual(
            sorted(by_path), [fixture.LIVING_DOC, fixture.NARRATIVE_DOC]
        )
        return report, by_path

    def mint(self, report, repo, digests):
        return mint_approval_set(
            report, digests, repo_root=repo, minter=APPROVER,
            registry_path=fixture.REGISTRY_PATH,
        )

    def check(self, approval, repo, report=None):
        return validate_approval_set(
            approval.to_dict(), report=report, repo_root=repo,
            registry_path=fixture.REGISTRY_PATH,
        )

    def apply_the_approved_edit(self, repo):
        """What an applier would do to the living document, done by hand."""
        path = os.path.join(repo, fixture.LIVING_DOC)
        with open(path, encoding="utf-8") as fh:
            text = fh.read()
        self.assertIn(STALE_SENTENCE, text)
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(text.replace(STALE_SENTENCE, APPLIED_SENTENCE))

    def outside(self, name):
        """A path outside the fixture — where an approval set may live."""
        directory = tempfile.mkdtemp(prefix="doc-lifecycle-approval-")
        self.addCleanup(shutil.rmtree, directory, ignore_errors=True)
        return os.path.join(directory, name)

    def json_outside(self, name, payload):
        path = self.outside(name)
        with open(path, "w", encoding="utf-8") as fh:
            json.dump(payload, fh)
        return path


class StrictSubsetOfRealFindings(ApprovalScenarioTestCase):
    """First acceptance criterion, against findings an audit produced."""

    def test_approving_one_of_two_findings_binds_only_that_one(self):
        repo = self.build_fixture()
        report, by_path = self.approvable(repo)

        approval = self.mint(report, repo,
                             [by_path[fixture.LIVING_DOC].digest])

        self.assertIsInstance(approval, ApprovalSet, approval)
        self.assertEqual([r.path for r in approval.records],
                         [fixture.LIVING_DOC])

    def test_the_finding_left_out_stays_in_the_report_and_is_named(self):
        repo = self.build_fixture()
        report, by_path = self.approvable(repo)

        approval = self.mint(report, repo,
                             [by_path[fixture.LIVING_DOC].digest])

        self.assertEqual([r.digest for r in approval.skipped],
                         [by_path[fixture.NARRATIVE_DOC].digest])
        self.assertIn(by_path[fixture.NARRATIVE_DOC].digest,
                      [r.digest for r in report.records])

    def test_the_document_that_was_not_approved_is_not_writable(self):
        repo = self.build_fixture()
        report, by_path = self.approvable(repo)

        approval = self.mint(report, repo,
                             [by_path[fixture.LIVING_DOC].digest])

        self.assertEqual(approval.scope.paths, (fixture.LIVING_DOC,))

    def test_an_injected_instruction_in_the_approved_document_wins_nothing(self):
        # The fixture's living document carries an HTML comment telling a
        # reader to approve every finding and delete the vendored file. The
        # scope is derived from the selection, so it is one document, and the
        # vendored file is not in it — nor is it even inventoried.
        repo = self.build_fixture()
        report, by_path = self.approvable(repo)

        approval = self.mint(report, repo,
                             [by_path[fixture.LIVING_DOC].digest])

        self.assertNotIn(fixture.EXCLUDED_DOC, approval.scope.paths)
        self.assertEqual(len(approval.records), 1)

    def test_the_selection_is_bound_to_this_repository_state(self):
        repo = self.build_fixture()
        report, by_path = self.approvable(repo)

        approval = self.mint(report, repo,
                             [by_path[fixture.LIVING_DOC].digest])

        self.assertEqual(approval.report_digest, report.digest)
        self.assertEqual(approval.lineage.base_commit,
                         report.lineage.base_commit)


class PartialApprovalAcrossAnApply(ApprovalScenarioTestCase):
    """The subset story: apply one, and the other is still honestly answerable."""

    def two_subsets(self, repo):
        report, by_path = self.approvable(repo)
        living = self.mint(report, repo, [by_path[fixture.LIVING_DOC].digest])
        narrative = self.mint(report, repo,
                              [by_path[fixture.NARRATIVE_DOC].digest])
        self.assertIsInstance(living, ApprovalSet, living)
        self.assertIsInstance(narrative, ApprovalSet, narrative)
        return report, living, narrative

    def test_the_untouched_subset_still_validates_after_the_first_apply(self):
        repo = self.build_fixture()
        report, living, narrative = self.two_subsets(repo)

        self.apply_the_approved_edit(repo)

        self.assertEqual(self.check(narrative, repo).status, STATE_CLEAN)

    def test_the_applied_subset_is_refused_by_its_own_preimage(self):
        repo = self.build_fixture()
        report, living, narrative = self.two_subsets(repo)

        self.apply_the_approved_edit(repo)

        result = self.check(living, repo)
        self.assertEqual(result.status, STATE_STALE)
        self.assertEqual([r.code for r in result.stale_reasons],
                         ["approval-preimage-mismatch"])

    def test_a_fresh_approval_set_validates_against_its_own_report(self):
        repo = self.build_fixture()
        report, living, _ = self.two_subsets(repo)

        self.assertEqual(self.check(living, repo, report=report).status,
                         STATE_CLEAN)

    def test_committing_the_change_expires_both_subsets(self):
        # The honest cost of the base-commit binding: once the apply lands, an
        # approval minted against the previous commit is over. Re-run the audit.
        repo = self.build_fixture()
        report, living, narrative = self.two_subsets(repo)
        self.apply_the_approved_edit(repo)
        fixture._commit(repo, "apply the approved drift fix")

        for approval in (living, narrative):
            result = self.check(approval, repo)
            self.assertEqual(result.status, STATE_STALE)
            self.assertIn("approval-base-commit-changed",
                          [r.code for r in result.stale_reasons])


class ContradictoryFindings(ApprovalScenarioTestCase):
    """Third acceptance criterion, over a real report's real lineage."""

    def contested(self, repo):
        """The fixture's report, plus a rival remedy for the same passage.

        Built through `build_finding` under the report's own lineage, so the
        rival is a record the contract accepts — the point is what happens when
        two legitimate findings disagree, not what happens to a malformed one.
        """
        report, by_path = self.approvable(repo)
        target = by_path[fixture.LIVING_DOC]
        rival = build_finding(
            lineage=report.lineage, code="CONDENSE", path=fixture.LIVING_DOC,
            units=target.extra["units"], record_id="BLOAT-001",
            extra={"proposal": "Fees are charged at the rate in `src/`."},
        )
        self.assertNotIsInstance(rival, Invalid)
        payload = report.to_dict()
        payload["records"].append(rival.to_record())
        del payload["digest"]
        contested = validate_report(payload, repo_root=repo,
                                    registry_path=fixture.REGISTRY_PATH)
        self.assertNotIsInstance(contested, Invalid, contested)
        return contested, target.digest, rival.digest

    def test_reconciliation_puts_the_rival_remedies_in_one_exclusive_group(self):
        repo = self.build_fixture()
        contested, drift, bloat = self.contested(repo)

        group = reconcile(contested).group_of(drift)

        self.assertEqual(group.disposition, DISPOSITION_EXCLUSIVE)
        self.assertEqual(set(group.members), {drift, bloat})

    def test_neither_leg_of_the_pair_can_be_approved(self):
        repo = self.build_fixture()
        contested, drift, bloat = self.contested(repo)

        for selection in ([drift], [bloat], [drift, bloat]):
            result = self.mint(contested, repo, selection)
            self.assertIsInstance(result, Invalid, result)
            self.assertEqual([p.code for p in result.problems],
                             ["approval-exclusive-group"])

    def test_the_untouched_finding_is_still_approvable_beside_them(self):
        repo = self.build_fixture()
        contested, _, _ = self.contested(repo)
        narrative = next(r for r in contested.records
                         if r.extra["path"] == fixture.NARRATIVE_DOC)

        approval = self.mint(contested, repo, [narrative.digest])

        self.assertIsInstance(approval, ApprovalSet, approval)
        self.assertEqual(len(approval.skipped), 2)


class NeverRepositoryState(ApprovalScenarioTestCase):
    """Fifth acceptance criterion, against a real index and a real work tree."""

    def approval(self, repo):
        report, by_path = self.approvable(repo)
        return self.mint(report, repo, [by_path[fixture.LIVING_DOC].digest])

    def test_it_cannot_be_written_beside_the_documents_it_authorizes(self):
        repo = self.build_fixture()
        target = os.path.join(repo, "docs", "approval.json")

        result = write_approval_set(self.approval(repo), target)

        self.assertIsInstance(result, Invalid)
        self.assertEqual([p.code for p in result.problems],
                         ["approval-set-would-be-tracked"])
        self.assertFalse(os.path.exists(target))

    def test_it_cannot_overwrite_a_tracked_file(self):
        repo = self.build_fixture()
        target = os.path.join(repo, fixture.PLANNING_DOC)

        result = write_approval_set(self.approval(repo), target)

        self.assertEqual([p.code for p in result.problems],
                         ["approval-set-tracked-path"])

    def test_it_can_be_written_outside_the_repository(self):
        repo = self.build_fixture()
        approval = self.approval(repo)
        target = self.outside("approval.json")

        self.assertEqual(write_approval_set(approval, target), target)

    def test_what_travels_in_the_change_is_the_digest_and_the_summary(self):
        repo = self.build_fixture()
        approval = self.approval(repo)

        trailers = approval_trailers(approval)
        summary = render_approval_set(approval)

        self.assertIn(approval.digest, trailers)
        self.assertIn(approval.digest, summary)
        self.assertIn("1 approved, 1 skipped", trailers)


class CommandSeam(ApprovalScenarioTestCase):
    """The commands reach the same artifact the library does."""

    def test_minting_at_the_command_seam_reproduces_the_library_artifact(self):
        repo = self.build_fixture()
        report, by_path = self.approvable(repo)
        report_path = self.json_outside("report.json", report.to_dict())
        digest = by_path[fixture.LIVING_DOC].digest

        result = run_cli(
            "mint-approval", "--report", report_path, "--repo", repo,
            "--registry", fixture.REGISTRY_PATH, "--record", digest,
            "--minter", APPROVER.id,
        )

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout),
                         self.mint(report, repo, [digest]).to_dict())

    def test_a_report_handed_in_where_an_approval_set_belongs_is_refused(self):
        repo = self.build_fixture()
        report, _ = self.approvable(repo)
        report_path = self.json_outside("report.json", report.to_dict())

        result = run_cli("validate-approval", "--approval", report_path)

        self.assertEqual(result.returncode, 1)
        self.assertIn("approval-not-an-approval-set", result.stderr)

    def test_a_dispatch_list_of_record_digests_is_refused(self):
        repo = self.build_fixture()
        _, by_path = self.approvable(repo)
        listed = self.json_outside(
            "dispatch.json", [r.digest for r in by_path.values()]
        )

        result = run_cli("validate-approval", "--approval", listed)

        self.assertEqual(result.returncode, 1)
        self.assertIn("dispatch list", result.stderr)

    def test_the_minted_artifact_says_what_it_is(self):
        repo = self.build_fixture()
        report, by_path = self.approvable(repo)
        report_path = self.json_outside("report.json", report.to_dict())
        out = self.outside("approval.json")

        result = run_cli(
            "mint-approval", "--report", report_path, "--repo", repo,
            "--registry", fixture.REGISTRY_PATH,
            "--record", by_path[fixture.NARRATIVE_DOC].digest,
            "--minter", APPROVER.id, "--out", out,
        )

        self.assertEqual(result.returncode, 0, result.stderr)
        with open(out, encoding="utf-8") as fh:
            self.assertEqual(json.load(fh)["artifact"], ARTIFACT_KIND)


if __name__ == "__main__":
    unittest.main()
