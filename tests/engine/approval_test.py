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
    ApprovalSet,
    Minter,
    load_approval_set,
    mint_approval_set,
    validate_approval_set,
    write_approval_set,
)
from doclifecycle.digest import sha256_canonical
from doclifecycle.reconcile import reconcile
from doclifecycle.render import approval_trailers, render_approval_set
from doclifecycle.finding import build_finding
from doclifecycle.report import (
    EXCLUSION_PLANNING_KIND,
    SCOPE_DECLARED_ONLY,
    SCOPE_WHOLE_INVENTORY,
    EvidenceBoundary,
    Lineage,
    Report,
    current_lineage,
    validate_report,
)
from doclifecycle.results import (
    STATE_CLEAN,
    STATE_FINDINGS,
    STATE_STALE,
    Invalid,
)
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
PLAN_DOC = "docs/plans/2026-07-20-fee-tiers.md"

DOC_A_TEXT = """# Fees

The payment service charges a flat 2% fee.

Refunds reverse the fee at the rate charged.
"""

DOC_B_TEXT = """# Workers

The worker retries a failed job three times.
"""

# A planning document, so a declared scope has something it may legitimately
# exclude: planning documents are never examined for drift.
PLAN_DOC_TEXT = """# Plan: tiered fees

**Status:** in-progress. The flat rate does not scale to enterprise volume.
"""

FILES = {
    ".doc-lifecycle/registry.json": REGISTRY,
    DOC_A: DOC_A_TEXT,
    DOC_B: DOC_B_TEXT,
    PLAN_DOC: PLAN_DOC_TEXT,
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

    `whole-inventory` coverage says every document was accounted for; it says
    nothing about what may be *changed*. PR #87's review found the weaker half
    of that (N1: a living document laundered into `excluded` with prose), and
    #88 closed it — but approval must not rest on that fix. The allowed
    mutation scope is derived from the selected records, so the strongest
    coverage claim a report can make authorizes exactly as much as the weakest.
    """

    def scoped_report(self, records, coverage):
        # Only a `whole-inventory` claim accounts for what it left out, so only
        # it may enumerate exclusions — the two claims differ in exactly the
        # way that would matter if coverage were authority.
        excluded = [{
            "path": PLAN_DOC,
            "reason": "planning documents are never examined for drift",
            "code": EXCLUSION_PLANNING_KIND,
        }] if coverage == SCOPE_WHOLE_INVENTORY else []
        return self.report(records, scope={
            "basis": "every living and narrative document in the inventory",
            "coverage": coverage,
            "documents": [DOC_A, DOC_B],
            "excluded": excluded,
        })

    def test_a_whole_inventory_claim_authorizes_only_the_selection(self):
        # The scope declares both documents examined. One record is approved,
        # so one document is writable.
        one, _ = self.two_findings()
        report = self.scoped_report([one], SCOPE_WHOLE_INVENTORY)

        approval = self.mint(report, [one["digest"]])

        self.assertEqual(approval.scope.paths, (DOC_A,))

    def test_the_two_coverage_claims_authorize_identically(self):
        one, _ = self.two_findings()

        wide = self.mint(
            self.scoped_report([one], SCOPE_WHOLE_INVENTORY), [one["digest"]]
        )
        narrow = self.mint(
            self.scoped_report([one], SCOPE_DECLARED_ONLY), [one["digest"]]
        )

        self.assertEqual(wide.scope.paths, narrow.scope.paths)

    def test_a_document_the_scope_excluded_is_not_writable(self):
        one, _ = self.two_findings()
        report = self.scoped_report([one], SCOPE_WHOLE_INVENTORY)

        approval = self.mint(report, [one["digest"]])

        self.assertNotIn(PLAN_DOC, approval.scope.paths)


class ApprovedTestCase(ApprovalTestCase):
    """Fixtures that start from a minted approval set over two documents."""

    def setUp(self):
        super().setUp()
        self.one, self.two = self.two_findings()
        self.source = self.report([self.one, self.two])
        self.approval = self.mint(self.source, [self.one["digest"]])
        self.assertIsInstance(self.approval, ApprovalSet, self.approval)

    def check(self, approval=None, **kwargs):
        kwargs.setdefault("report", self.source)
        kwargs.setdefault("repo_root", self.repo)
        kwargs.setdefault("audit_config_digest", CONFIG_DIGEST)
        payload = (self.approval if approval is None else approval).to_dict()
        return validate_approval_set(payload, **kwargs)


class Freshness(ApprovedTestCase):
    def test_a_freshly_minted_approval_set_validates_clean(self):
        result = self.check()

        self.assertIsInstance(result, ApprovalSet, result)
        self.assertEqual(result.status, STATE_CLEAN)
        self.assertEqual(result.stale_reasons, ())

    def test_it_keeps_its_digest_through_validation(self):
        self.assertEqual(self.check().digest, self.approval.digest)

    def test_a_new_commit_makes_it_stale_naming_the_base_commit(self):
        self.write(self.repo, "unrelated.txt", "a change somewhere else")
        self.commit(self.repo, "second")

        result = self.check()

        self.assertEqual(result.status, STATE_STALE)
        self.assertEqual(reasons(result), ["approval-base-commit-changed"])

    def test_a_registry_change_makes_it_stale_naming_the_rules(self):
        self.write(self.repo, ".doc-lifecycle/registry.json",
                   REGISTRY.replace('"sets": ["plans"],',
                                    '"exclude": ["docs/vendor"],\n  "sets": ["plans"],'))

        result = self.check()

        self.assertEqual(reasons(result), ["approval-registry-changed"])

    def test_a_configuration_change_makes_it_stale_naming_it(self):
        result = self.check(audit_config_digest="d" * 64)

        self.assertEqual(reasons(result), ["approval-audit-config-changed"])

    def test_a_ruleset_bump_makes_it_stale_naming_the_rules(self):
        payload = self.approval.to_dict()
        payload["lineage"]["ruleset_version"] = 99
        del payload["digest"]

        result = validate_approval_set(
            payload, report=None, repo_root=self.repo,
            audit_config_digest=CONFIG_DIGEST,
        )

        self.assertIn("approval-ruleset-changed", reasons(result))

    def test_a_different_report_makes_it_stale_naming_the_report(self):
        other = self.report([self.two])

        result = self.check(report=other)

        self.assertEqual(reasons(result), ["approval-report-changed"])

    def test_rewriting_the_approved_passage_names_the_preimage(self):
        self.write(self.repo, DOC_A,
                   "# Fees\n\nThe payment service charges a flat 3% fee.\n")

        result = self.check()

        self.assertEqual(reasons(result), ["approval-preimage-mismatch"])
        self.assertIn(DOC_A, result.stale_reasons[0].message)

    def test_deleting_the_approved_document_makes_it_stale(self):
        os.remove(os.path.join(self.repo, DOC_A))

        result = self.check()

        self.assertEqual(reasons(result), ["approval-preimage-unreadable"])

    def test_a_target_that_stopped_authorizing_makes_the_scope_stale(self):
        target = os.path.join(self.repo, DOC_A)
        os.remove(target)
        os.symlink("/etc/hosts", target)

        result = self.check()

        self.assertIn("approval-scope-changed", reasons(result))

    def test_a_second_subset_still_validates_when_its_text_is_untouched(self):
        # Partial approval, working: subset one is minted, applied to docs/a.md,
        # and subset two — over a document the apply never touched — is still
        # good. The inventory digest moved; the second subset's preimage did not.
        second = self.mint(self.source, [self.two["digest"]])
        self.write(self.repo, DOC_A,
                   "# Fees\n\nThe payment service charges a flat 2.5% fee.\n")

        result = self.check(approval=second)

        self.assertEqual(result.status, STATE_CLEAN)

    def test_the_first_subset_is_refused_once_its_own_text_moved(self):
        # The other half of the same story, and the reason the check is
        # per-record: re-approving what was already applied is refused honestly.
        self.write(self.repo, DOC_A,
                   "# Fees\n\nThe payment service charges a flat 2.5% fee.\n")

        result = self.check()

        self.assertEqual(reasons(result), ["approval-preimage-mismatch"])

    def test_every_field_that_moved_is_named_at_once(self):
        self.write(self.repo, DOC_A, "# Fees\n\nSomething else.\n")
        self.commit(self.repo, "second")

        result = self.check(audit_config_digest="d" * 64)

        self.assertEqual(reasons(result), [
            "approval-audit-config-changed",
            "approval-base-commit-changed",
            "approval-preimage-mismatch",
        ])

    def test_without_a_repository_the_check_is_structural_only(self):
        self.write(self.repo, DOC_A, "# Fees\n\nSomething else.\n")
        self.commit(self.repo, "second")

        result = validate_approval_set(self.approval.to_dict())

        self.assertEqual(result.status, STATE_CLEAN)
        self.assertEqual(result.stale_reasons, ())

    def test_an_altered_approval_set_is_invalid_not_stale(self):
        payload = self.approval.to_dict()
        payload["minter"]["id"] = "someone-else@example.com"

        result = validate_approval_set(payload)

        self.assertIsInstance(result, Invalid)
        self.assertEqual(codes(result), ["approval-digest-mismatch"])

    def test_a_selection_the_report_no_longer_carries_is_stale(self):
        # The report is the one the digest names, but the record is not in it:
        # nothing the applier could look up, so the authority does not stand.
        payload = self.approval.to_dict()
        payload["records"][0]["digest"] = "f" * 64
        del payload["digest"]

        result = validate_approval_set(payload, report=self.source)

        self.assertIn("approval-report-changed", reasons(result))


class ReconciledOnReadBack(ApprovedTestCase):
    """The group discipline is the applier's gate, not only the minter's.

    An approval set is a file. Whatever `mint_approval_set` refused, the
    applier sees only what validation says about the artifact in front of it —
    so a selection that takes one leg of a contradictory pair has to be caught
    here too, or the guarantee is advisory in the one place it must be
    structural.
    """

    def contested(self):
        unit = self.units(self.repo, DOC_A)[0]
        cut = self.finding("R-1", "CUT", DOC_A, [unit])
        condense = self.finding("R-2", "CONDENSE", DOC_A, [unit],
                                proposal="Fees: 2%.")
        return self.report([cut, condense]), cut, condense

    def forged(self, report, record):
        """An approval set naming `record`, assembled by hand around the report.

        Everything the contract can check on its own is honest: the artifact
        declares the report's real digest, the report's real reconciliation
        digest, and a scope derived from the record it selects.
        """
        payload = self.approval.to_dict()
        payload["report_digest"] = report.digest
        payload["reconciliation_digest"] = reconcile(report).digest
        payload["records"] = [{
            "digest": record["digest"], "id": record["id"],
            "code": record["code"], "path": record["path"],
            "destination": None, "units": sorted(record["units"]),
        }]
        payload["skipped"] = sorted(
            ({"digest": r.digest, "id": r.id} for r in report.records
             if r.digest != record["digest"]),
            key=lambda r: r["digest"],
        )
        payload["scope"]["paths"] = [record["path"]]
        del payload["digest"]
        return payload

    def test_one_leg_of_an_exclusive_pair_is_refused_on_read_back(self):
        report, cut, _ = self.contested()

        result = validate_approval_set(self.forged(report, cut), report=report)

        self.assertIsInstance(result, Invalid, result)
        self.assertEqual(codes(result), ["approval-exclusive-group"])

    def test_half_an_atomic_group_is_refused_on_read_back(self):
        units = self.units(self.repo, DOC_A)
        wide = self.finding("R-1", "CUT", DOC_A, units[:2])
        narrow = self.finding("R-2", "DISTILL", DOC_A, units[:1], status="ready")
        report = self.report([wide, narrow])

        result = validate_approval_set(self.forged(report, wide), report=report)

        self.assertEqual(codes(result), ["approval-partial-group"])

    def test_a_skipped_list_that_hides_a_record_is_refused(self):
        payload = self.approval.to_dict()
        payload["skipped"] = []
        del payload["digest"]

        result = validate_approval_set(payload, report=self.source)

        self.assertIsInstance(result, Invalid)
        self.assertEqual(codes(result), ["approval-skipped-not-derived"])

    def test_an_honest_selection_still_validates_against_its_report(self):
        report, cut, condense = self.contested()
        other = self.finding("R-3", "STALE", DOC_B, self.units(self.repo, DOC_B)[:1],
                             fix="The worker retries five times.")
        with_other = self.report([cut, condense, other])
        approval = self.mint(with_other, [other["digest"]])

        result = validate_approval_set(approval.to_dict(), report=with_other)

        self.assertIsInstance(result, ApprovalSet, result)
        self.assertEqual(result.status, STATE_CLEAN)


class NotAnApprovalSet(ApprovedTestCase):
    """AC4: whatever else a caller has in hand, it is not authority."""

    def test_a_report_is_refused(self):
        result = validate_approval_set(self.source.to_dict())

        self.assertIsInstance(result, Invalid)
        self.assertEqual(codes(result), ["approval-not-an-approval-set"])
        self.assertIn("report", result.problems[0].message)

    def test_a_branch_name_is_refused(self):
        result = validate_approval_set("doc-sync/nightly-2026-07-26")

        self.assertEqual(codes(result), ["approval-not-an-approval-set"])

    def test_a_workflow_run_id_is_refused(self):
        result = validate_approval_set(1234567890)

        self.assertEqual(codes(result), ["approval-not-an-approval-set"])

    def test_a_dispatch_list_of_record_digests_is_refused(self):
        result = validate_approval_set(
            [self.one["digest"], self.two["digest"]]
        )

        self.assertEqual(codes(result), ["approval-not-an-approval-set"])
        self.assertIn("record digests", result.problems[0].message)

    def test_a_cached_report_is_refused(self):
        entry = os.path.join(self.repo, "cache-entry.json")
        with open(entry, "w", encoding="utf-8") as fh:
            json.dump(self.source.to_dict(), fh)

        result = load_approval_set(entry)

        self.assertEqual(codes(result), ["approval-not-an-approval-set"])

    def test_an_unreadable_file_is_refused(self):
        result = load_approval_set(os.path.join(self.repo, "nothing.json"))

        self.assertEqual(codes(result), ["approval-unreadable"])

    def test_a_file_that_is_not_json_is_refused(self):
        path = os.path.join(self.repo, "not.json")
        with open(path, "w", encoding="utf-8") as fh:
            fh.write("approved: everything")

        self.assertEqual(codes(load_approval_set(path)),
                         ["approval-unparseable"])

    def test_a_minted_approval_set_round_trips_through_a_file(self):
        path = os.path.join(self.repo, "..", "approval.json")
        with open(path, "w", encoding="utf-8") as fh:
            json.dump(self.approval.to_dict(), fh)

        result = load_approval_set(path)

        self.assertIsInstance(result, ApprovalSet, result)
        self.assertEqual(result.digest, self.approval.digest)


class StructuralRefusals(ApprovedTestCase):
    def payload(self, **overrides):
        payload = self.approval.to_dict()
        payload.update(overrides)
        payload.pop("digest", None)
        return payload

    def test_an_unknown_minter_kind_is_refused(self):
        result = validate_approval_set(
            self.payload(minter={"kind": "the-workflow", "id": "doc-sync.yml"})
        )

        self.assertEqual(codes(result), ["approval-invalid-minter"])

    def test_an_approval_set_selecting_nothing_is_refused(self):
        result = validate_approval_set(self.payload(records=[]))

        self.assertEqual(codes(result), ["approval-empty-selection"])

    def test_a_scope_that_omits_a_selected_record_is_refused(self):
        payload = self.payload()
        payload["scope"]["paths"] = [DOC_B]

        result = validate_approval_set(payload)

        self.assertEqual(codes(result), ["approval-scope-not-derived"])

    def test_a_scope_widened_beyond_the_selection_is_refused(self):
        # The forgery the mint-time derivation cannot stop on its own: an
        # approval set is a file, and a file can be edited to make the
        # unselected finding's document writable.
        payload = self.payload()
        payload["scope"]["paths"] = [DOC_A, DOC_B]

        result = validate_approval_set(payload)

        self.assertIsInstance(result, Invalid)
        self.assertEqual(codes(result), ["approval-scope-not-derived"])
        self.assertIn(DOC_B, result.problems[0].message)

    def test_a_move_destination_is_part_of_the_derivation(self):
        move = self.finding(
            "R-9", "EXTRACT-AND-MOVE", DOC_A, self.units(self.repo, DOC_A)[:1],
            proposal="The fee is 2%.",
            destination={"path": DOC_B, "kind": "living", "set": None},
        )
        approval = self.mint(self.report([move]), [move["digest"]])

        result = validate_approval_set(approval.to_dict())

        self.assertIsInstance(result, ApprovalSet, result)
        self.assertEqual(result.scope.paths, (DOC_A, DOC_B))
        self.assertEqual(result.records[0].destination, DOC_B)

    def test_an_unknown_field_is_refused(self):
        result = validate_approval_set(self.payload(expires="never"))

        self.assertEqual(codes(result), ["approval-unknown-field"])

    def test_a_missing_field_is_refused(self):
        payload = self.payload()
        del payload["scope"]

        result = validate_approval_set(payload)

        self.assertEqual(codes(result), ["approval-missing-field"])

    def test_every_structural_problem_is_named_at_once(self):
        payload = self.payload(minter={"kind": "nope", "id": ""})
        del payload["reconciliation_digest"]

        result = validate_approval_set(payload)

        self.assertEqual(
            codes(result),
            ["approval-invalid-minter", "approval-missing-field"],
        )


class NeverTracked(ApprovedTestCase):
    """AC5: an approval set is never written into tracked repository state."""

    def test_writing_it_into_the_repository_is_refused(self):
        target = os.path.join(self.repo, "docs", "approval.json")

        result = write_approval_set(self.approval, target)

        self.assertIsInstance(result, Invalid)
        self.assertEqual(codes(result), ["approval-set-would-be-tracked"])
        self.assertFalse(os.path.exists(target))

    def test_overwriting_a_tracked_file_is_refused(self):
        target = os.path.join(self.repo, DOC_B)

        result = write_approval_set(self.approval, target)

        self.assertEqual(codes(result), ["approval-set-tracked-path"])
        with open(target, encoding="utf-8") as fh:
            self.assertEqual(fh.read(), DOC_B_TEXT)

    def test_writing_outside_the_repository_is_allowed(self):
        target = os.path.join(self.repo, "..", "approval.json")

        result = write_approval_set(self.approval, target)

        self.assertEqual(result, target)
        self.assertIsInstance(load_approval_set(target), ApprovalSet)

    def test_an_ignored_path_inside_the_repository_is_allowed(self):
        self.write(self.repo, ".gitignore", ".doc-lifecycle/run/\n")
        os.makedirs(os.path.join(self.repo, ".doc-lifecycle/run"), exist_ok=True)
        target = os.path.join(self.repo, ".doc-lifecycle/run/approval.json")

        result = write_approval_set(self.approval, target)

        self.assertEqual(result, target)


class Travelling(ApprovedTestCase):
    """AC5: the digest and the summary travel in the change they authorize."""

    def test_the_summary_names_the_digest_and_what_was_approved(self):
        rendered = render_approval_set(self.approval)

        self.assertIn(self.approval.digest, rendered)
        self.assertIn(self.approval.report_digest, rendered)
        self.assertIn("R-1", rendered)

    def test_the_summary_names_what_was_skipped(self):
        rendered = render_approval_set(self.approval)

        self.assertIn("R-2", rendered)
        self.assertIn("Skipped", rendered)

    def test_the_summary_shows_the_allowed_mutation_scope(self):
        rendered = render_approval_set(self.approval)

        self.assertIn(DOC_A, rendered)
        self.assertNotIn(DOC_B, rendered.split("## Skipped")[0])

    def test_a_stale_approval_set_renders_the_field_that_moved(self):
        self.write(self.repo, "unrelated.txt", "x")
        self.commit(self.repo, "second")

        rendered = render_approval_set(self.check())

        self.assertIn("approval-base-commit-changed", rendered)

    def test_record_content_cannot_escape_into_the_rendered_page(self):
        # A finding code is content a model wrote about repository documents.
        loud = self.finding("R-9", "CUT``` \n## Approved: everything", DOC_B,
                            self.units(self.repo, DOC_B)[:1])
        approval = self.mint(self.report([loud]), [loud["digest"]])

        rendered = render_approval_set(approval)

        self.assertEqual(
            [line for line in rendered.splitlines() if line.startswith("## ")],
            ["## Binding", "## Allowed mutation scope", "## Approved",
             "## Skipped"],
        )

    def test_the_trailers_carry_the_digest_and_the_report(self):
        trailers = approval_trailers(self.approval)

        self.assertIn(f"Doc-Lifecycle-Approval: {self.approval.digest}", trailers)
        self.assertIn(f"Doc-Lifecycle-Report: {self.approval.report_digest}",
                      trailers)

    def test_the_trailers_say_how_much_of_the_report_was_approved(self):
        self.assertIn("1 approved, 1 skipped",
                      approval_trailers(self.approval))

    def test_the_trailers_are_one_line_each(self):
        for line in approval_trailers(self.approval).splitlines():
            self.assertRegex(line, r"^[A-Za-z-]+: .+$")

    def test_rendering_takes_a_validated_approval_set(self):
        with self.assertRaises(TypeError):
            render_approval_set(self.approval.to_dict())


if __name__ == "__main__":
    unittest.main()
