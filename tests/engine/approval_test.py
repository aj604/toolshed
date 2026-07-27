"""Approval sets: the sole authority the applier accepts.

Every fixture here is a real git repository with real documents on disk —
minting authorizes paths against the filesystem, and a preimage check re-reads
the text a record was written about, so neither is meaningful against a mock.
"""

import json
import os
import subprocess
import unittest

from support import ENGINE, RepoTestCase  # noqa: F401 (engine onto sys.path)

from doclifecycle import ARTIFACT_SCHEMA_VERSION
from doclifecycle.approval import (
    ARTIFACT_KIND,
    ApprovalSet,
    Minter,
    mint_approval_set,
)
from doclifecycle.digest import sha256_canonical
from doclifecycle.finding import build_finding
from doclifecycle.report import (
    EvidenceBoundary,
    Lineage,
    Report,
    current_lineage,
    validate_report,
)
from doclifecycle.results import STATE_CLEAN, STATE_FINDINGS, Invalid
from doclifecycle.segment import segment_document

CONFIG_DIGEST = "c" * 64

REGISTRY = """{
  "schema_version": 1,
  "roots": ["docs"],
  "sets": ["plans"],
  "rules": [
    {"glob": "docs/*.md", "kind": "living"},
    {"glob": "docs/plans/*.md", "kind": "planning", "set": "plans"}
  ]
}
"""

DOC_A = "docs/a.md"
DOC_B = "docs/b.md"

DOC_A_TEXT = """# Fees

The payment service charges a flat 2% fee.

Refunds reverse the fee at the rate charged.
"""

DOC_B_TEXT = """# Workers

The worker retries a failed job three times.
"""

FILES = {
    ".doc-lifecycle/registry.json": REGISTRY,
    DOC_A: DOC_A_TEXT,
    DOC_B: DOC_B_TEXT,
}

HUMAN = Minter(kind="human", id="avery@example.com")


def codes(result):
    return sorted(p.code for p in result.problems)


def reasons(approval):
    return sorted(r.code for r in approval.stale_reasons)


class ApprovalTestCase(RepoTestCase):
    """A real repository, real documents, and findings bound to both."""

    def setUp(self):
        self.repo = self.git_repo()
        self.lineage = self.lineage_for(self.repo)

    def git_repo(self, files=None):
        root = self.repo_files(FILES if files is None else files)
        self.git(root, "init", "-q", "-b", "main")
        self.commit(root, "fixture")
        return root

    def repo_files(self, files):
        return super().repo(dict(files))

    def git(self, root, *argv):
        env = dict(
            os.environ,
            GIT_AUTHOR_NAME="t", GIT_AUTHOR_EMAIL="t@example.com",
            GIT_COMMITTER_NAME="t", GIT_COMMITTER_EMAIL="t@example.com",
        )
        subprocess.run(
            ["git", "-C", root, "-c", "commit.gpgsign=false", *argv],
            check=True, env=env, capture_output=True, text=True,
        )

    def commit(self, root, message):
        self.git(root, "add", "-A")
        self.git(root, "commit", "-q", "-m", message)

    def write(self, root, rel, text):
        path = os.path.join(root, rel)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(text)

    def lineage_for(self, repo, **overrides):
        state, problems = current_lineage(repo, audit_config_digest=CONFIG_DIGEST)
        self.assertEqual(problems, ())
        fields = dict(
            state, audit_mode="full",
            evidence_boundary=EvidenceBoundary(("src/**",)),
        )
        fields.update(overrides)
        return Lineage(**fields)

    def units(self, repo, path):
        """The real assertion-unit digests of a document, in document order."""
        segmentation = segment_document(repo, path)
        self.assertNotIsInstance(segmentation, Invalid)
        return [u.digest for u in segmentation.units if u.assertion_capable]

    def finding(self, record_id, code, path, units, lineage=None, **extra):
        finding = build_finding(
            lineage=self.lineage if lineage is None else lineage,
            code=code, path=path, units=list(units), record_id=record_id,
            extra=extra,
        )
        self.assertNotIsInstance(finding, Invalid)
        return finding.to_record()

    def report(self, records, repo=None, lineage=None, **overrides):
        lineage = self.lineage if lineage is None else lineage
        payload = {
            "status": STATE_FINDINGS if records else STATE_CLEAN,
            "schema_version": ARTIFACT_SCHEMA_VERSION,
            "lineage": lineage.to_dict(),
            "records": [dict(r) for r in records],
            "incomplete": [],
        }
        payload.update(overrides)
        report = validate_report(
            payload,
            repo_root=self.repo if repo is None else repo,
            audit_config_digest=CONFIG_DIGEST,
        )
        self.assertIsInstance(report, Report, report)
        return report

    def two_findings(self):
        """One finding in each document, unrelated and separately selectable."""
        return (
            self.finding("R-1", "STALE", DOC_A, self.units(self.repo, DOC_A)[:1],
                         fix="The payment service charges a flat 2.5% fee."),
            self.finding("R-2", "STALE", DOC_B, self.units(self.repo, DOC_B)[:1],
                         fix="The worker retries a failed job five times."),
        )

    def mint(self, report, selected, **kwargs):
        kwargs.setdefault("repo_root", self.repo)
        kwargs.setdefault("minter", HUMAN)
        return mint_approval_set(report, selected, **kwargs)


class PartialApproval(ApprovalTestCase):
    def test_a_strict_subset_binds_exactly_the_selected_digests(self):
        one, two = self.two_findings()
        report = self.report([one, two])

        approval = self.mint(report, [one["digest"]])

        self.assertIsInstance(approval, ApprovalSet, approval)
        self.assertEqual([r.digest for r in approval.records], [one["digest"]])

    def test_an_unselected_finding_is_recorded_as_skipped(self):
        one, two = self.two_findings()

        approval = self.mint(self.report([one, two]), [one["digest"]])

        self.assertEqual([r.digest for r in approval.skipped], [two["digest"]])
        self.assertEqual([r.record_id for r in approval.skipped], ["R-2"])

    def test_the_approval_set_binds_the_report_it_was_minted_from(self):
        one, two = self.two_findings()
        report = self.report([one, two])

        approval = self.mint(report, [one["digest"]])

        self.assertEqual(approval.report_digest, report.digest)
        self.assertEqual(approval.lineage.to_dict(), report.lineage.to_dict())

    def test_an_unselected_finding_cannot_ride_along_in_the_scope(self):
        # The allowed mutation scope is derived from the selected records
        # alone: the skipped record's document is not writable.
        one, two = self.two_findings()

        approval = self.mint(self.report([one, two]), [one["digest"]])

        self.assertEqual(approval.scope.paths, (DOC_A,))

    def test_a_destination_a_move_writes_to_is_in_the_allowed_scope(self):
        move = self.finding(
            "R-1", "EXTRACT-AND-MOVE", DOC_A, self.units(self.repo, DOC_A)[:1],
            proposal="The fee is 2%.",
            destination={"path": DOC_B, "kind": "living", "set": None},
        )

        approval = self.mint(self.report([move]), [move["digest"]])

        self.assertEqual(approval.scope.paths, (DOC_A, DOC_B))

    def test_the_declared_documentation_roots_travel_with_the_scope(self):
        one, _ = self.two_findings()

        approval = self.mint(self.report([one]), [one["digest"]])

        self.assertEqual(approval.scope.roots, ("docs",))

    def test_the_minter_is_recorded(self):
        one, _ = self.two_findings()

        approval = self.mint(self.report([one]), [one["digest"]])

        self.assertEqual(approval.minter.kind, "human")
        self.assertEqual(approval.minter.id, "avery@example.com")

    def test_selection_order_does_not_change_the_approval_set(self):
        one, two = self.two_findings()
        report = self.report([one, two])

        forward = self.mint(report, [one["digest"], two["digest"]])
        backward = self.mint(report, [two["digest"], one["digest"]])

        self.assertEqual(forward.digest, backward.digest)

    def test_minting_the_same_selection_twice_gives_one_digest(self):
        one, two = self.two_findings()
        report = self.report([one, two])

        self.assertEqual(
            self.mint(report, [one["digest"]]).digest,
            self.mint(report, [one["digest"]]).digest,
        )

    def test_two_subsets_of_one_report_are_two_different_approval_sets(self):
        one, two = self.two_findings()
        report = self.report([one, two])

        self.assertNotEqual(
            self.mint(report, [one["digest"]]).digest,
            self.mint(report, [two["digest"]]).digest,
        )


class MintRefusals(ApprovalTestCase):
    def test_selecting_a_digest_the_report_does_not_carry_is_refused(self):
        one, _ = self.two_findings()

        result = self.mint(self.report([one]), ["f" * 64])

        self.assertIsInstance(result, Invalid)
        self.assertEqual(codes(result), ["approval-unknown-record"])

    def test_selecting_nothing_is_refused(self):
        one, _ = self.two_findings()

        result = self.mint(self.report([one]), [])

        self.assertIsInstance(result, Invalid)
        self.assertEqual(codes(result), ["approval-empty-selection"])

    def test_selecting_one_record_twice_is_refused(self):
        one, _ = self.two_findings()

        result = self.mint(self.report([one]), [one["digest"], one["digest"]])

        self.assertEqual(codes(result), ["approval-duplicate-selection"])

    def test_a_stale_report_cannot_authorize_anything(self):
        one, _ = self.two_findings()
        report = self.report([one], lineage=self.lineage_for(
            self.repo, base_commit="b" * 40
        ))

        result = self.mint(report, [one["digest"]])

        self.assertEqual(codes(result), ["approval-report-not-approvable"])

    def test_a_record_outside_the_declared_roots_cannot_be_approved(self):
        stray = self.finding("R-1", "STALE", "README.md", [sha256_canonical("x")],
                             fix="anything")

        result = self.mint(self.report([stray]), [stray["digest"]])

        self.assertEqual(codes(result), ["path-outside-root"])

    def test_a_symlinked_target_cannot_be_approved(self):
        os.symlink("/etc/hosts", os.path.join(self.repo, "docs/link.md"))
        # The symlink is part of the repository the report is about, so the
        # report must be built after it — otherwise the refusal under test
        # never runs, because the report is stale first.
        self.lineage = self.lineage_for(self.repo)
        record = self.finding("R-1", "STALE", "docs/link.md",
                              [sha256_canonical("x")], fix="anything")

        result = self.mint(self.report([record]), [record["digest"]])

        self.assertEqual(codes(result), ["symlinked-path"])

    def test_a_selected_record_whose_text_already_moved_is_refused(self):
        one, _ = self.two_findings()
        report = self.report([one])
        self.write(self.repo, DOC_A, "# Fees\n\nSomething else entirely.\n")

        result = self.mint(report, [one["digest"]])

        self.assertEqual(codes(result), ["approval-preimage-mismatch"])

    def test_the_minter_must_be_a_minter(self):
        one, _ = self.two_findings()

        with self.assertRaises(TypeError):
            self.mint(self.report([one]), [one["digest"]], minter="avery")

    def test_minting_takes_a_validated_report(self):
        with self.assertRaises(TypeError):
            self.mint({"status": "findings"}, ["a" * 64])


class ReconciledSelection(ApprovalTestCase):
    def conflicting_pair(self):
        unit = self.units(self.repo, DOC_A)[0]
        return (
            self.finding("R-1", "CUT", DOC_A, [unit]),
            self.finding("R-2", "CONDENSE", DOC_A, [unit], proposal="Fees: 2%."),
        )

    def overlapping_pair(self):
        units = self.units(self.repo, DOC_A)
        return (
            self.finding("R-1", "CUT", DOC_A, units[:2]),
            self.finding("R-2", "DISTILL", DOC_A, units[:1], status="ready"),
        )

    def test_one_leg_of_an_exclusive_pair_cannot_be_selected(self):
        cut, condense = self.conflicting_pair()

        result = self.mint(self.report([cut, condense]), [cut["digest"]])

        self.assertIsInstance(result, Invalid)
        self.assertEqual(codes(result), ["approval-exclusive-group"])

    def test_the_refusal_names_the_record_the_selection_decided_against(self):
        cut, condense = self.conflicting_pair()

        result = self.mint(self.report([cut, condense]), [cut["digest"]])

        self.assertIn(condense["digest"], result.problems[0].message)

    def test_selecting_both_legs_of_an_exclusive_pair_is_still_refused(self):
        # Naming the contradiction does not resolve it: one passage cannot be
        # both deleted and rewritten, and the applier must not pick.
        cut, condense = self.conflicting_pair()

        result = self.mint(
            self.report([cut, condense]), [cut["digest"], condense["digest"]]
        )

        self.assertEqual(codes(result), ["approval-exclusive-group"])

    def test_half_of_an_atomic_group_cannot_be_selected(self):
        wide, narrow = self.overlapping_pair()

        result = self.mint(self.report([wide, narrow]), [wide["digest"]])

        self.assertIsInstance(result, Invalid)
        self.assertEqual(codes(result), ["approval-partial-group"])

    def test_a_whole_atomic_group_mints(self):
        wide, narrow = self.overlapping_pair()

        approval = self.mint(
            self.report([wide, narrow]), [wide["digest"], narrow["digest"]]
        )

        self.assertIsInstance(approval, ApprovalSet, approval)
        self.assertEqual(len(approval.records), 2)

    def test_an_unrelated_finding_stays_selectable_beside_a_conflict(self):
        cut, condense = self.conflicting_pair()
        other = self.finding("R-3", "STALE", DOC_B, self.units(self.repo, DOC_B)[:1],
                             fix="The worker retries five times.")

        approval = self.mint(
            self.report([cut, condense, other]), [other["digest"]]
        )

        self.assertIsInstance(approval, ApprovalSet, approval)

    def test_the_approval_set_binds_the_reconciliation_it_satisfied(self):
        one, two = self.two_findings()
        report = self.report([one, two])

        approval = self.mint(report, [one["digest"]])

        self.assertRegex(approval.reconciliation_digest, r"^[0-9a-f]{64}$")


class CoverageIsNotAuthority(ApprovalTestCase):
    """A report's coverage claim never widens what an approval may write.

    Issue #88/N1: `whole-inventory` coverage only means every document is
    *mentioned*, and an exclusion carrying unconstrained prose is enough to
    mention one. So the allowed mutation scope is derived from the selected
    records, and a coverage claim contributes nothing to it.
    """

    def scoped_report(self, records, coverage, excluded):
        return self.report(records, scope={
            "basis": "every living and narrative document in the inventory",
            "coverage": coverage,
            "documents": [DOC_A],
            "excluded": excluded,
        })

    def test_a_laundered_whole_inventory_claim_authorizes_no_more(self):
        one, _ = self.two_findings()
        laundered = self.scoped_report(
            [one], "whole-inventory",
            [{"path": DOC_B, "reason": "not relevant to this run"}],
        )
        declared = self.scoped_report(
            [one], "declared-only",
            [{"path": DOC_B, "reason": "not relevant to this run"}],
        )

        wide = self.mint(laundered, [one["digest"]])
        narrow = self.mint(declared, [one["digest"]])

        self.assertEqual(wide.scope.paths, (DOC_A,))
        self.assertEqual(wide.scope.paths, narrow.scope.paths)

    def test_an_excluded_document_is_not_writable(self):
        # The document the scope pushed out with a prose reason is exactly the
        # one an exclusion-laundered report would smuggle in.
        one, _ = self.two_findings()
        report = self.scoped_report(
            [one], "whole-inventory",
            [{"path": DOC_B, "reason": "not relevant to this run"}],
        )

        approval = self.mint(report, [one["digest"]])

        self.assertNotIn(DOC_B, approval.scope.paths)


if __name__ == "__main__":
    unittest.main()
