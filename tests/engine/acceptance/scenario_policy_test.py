#!/usr/bin/env python3
"""Scenario auto-apply (issue #73): the policy over the acceptance fixture.

Seams: `load_auto_apply_policy()`, `policy_eligibility()`,
`mint_policy_approval_set()` as library calls, `python3 -m doclifecycle
policy-mint` as a subprocess, and — the point of the whole scenario —
`apply_edit_plan()`, the *same* applier a human-minted approval set goes
through, over the REAL temporary git repository the fixture builds and the REAL
findings its drift audit produces.

What it holds that the unit suite cannot: the STALE finding is one an audit
actually produced against a document carrying a prompt-injection comment; the
waiver the fixture's own install carries is a real human dispute recorded in a
real file; the apply writes real bytes into a real work tree and is confined
against real `git status` output; and the absent-policy case is a real
repository with the configuration commit reverted.

One class per acceptance criterion.

Run: python3 tests/engine/acceptance/scenario_policy_test.py
"""

import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import fixture  # noqa: E402  (the acceptance fixture builder)
from scenario_approval_test import ApprovalScenarioTestCase  # noqa: E402

from doclifecycle import ARTIFACT_SCHEMA_VERSION  # noqa: E402
from doclifecycle.applier import apply_edit_plan  # noqa: E402
from doclifecycle.approval import (  # noqa: E402
    MINTER_POLICY,
    ApprovalSet,
    Minter,
    mint_approval_set,
)
from doclifecycle.digest import sha256_canonical  # noqa: E402
from doclifecycle.finding import build_finding  # noqa: E402
from doclifecycle.policy import (  # noqa: E402
    CLASS_ANCHOR_REFRESH,
    CLASS_DRIFT_STALE,
    AutoApplyPolicy,
    load_auto_apply_policy,
    mint_policy_approval_set,
    policy_eligibility,
)
from doclifecycle.render import approval_trailers, render_approval_set  # noqa: E402
from doclifecycle.results import STATE_CLEAN, Invalid  # noqa: E402

ENGINE = os.path.abspath(os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "..", "..", "..",
    "plugins", "doc-lifecycle", "engine",
))

# The two raw lines the fixture's living document hard-wraps its stale claim
# across, and the single line the audit's own `fix` proposes instead.
STALE_PREIMAGE = (
    "The payment service lives at `src/payment_service.py` and calculates fees "
    "at a\nflat 2% rate."
)
STALE_POSTIMAGE = (
    "The payment service lives at `src/payment_service.py` and calculates fees "
    "at a flat 2.5% rate."
)
STALE_FIRST_LINE, STALE_LAST_LINE = 3, 4


def sha256_text(text):
    import hashlib

    return hashlib.sha256(text.encode("utf-8")).hexdigest()


class PolicyScenarioTestCase(ApprovalScenarioTestCase):
    def policy(self, repo):
        loaded = load_auto_apply_policy(repo)
        self.assertIsInstance(loaded, AutoApplyPolicy, loaded)
        return loaded

    def drift_only(self, repo):
        """The fixture's policy, narrowed to the drift class by its consumer."""
        return AutoApplyPolicy(
            id=self.policy(repo).id, classes=(CLASS_DRIFT_STALE,)
        )

    def mint_by_policy(self, report, repo, policy=None):
        return mint_policy_approval_set(
            report, self.policy(repo) if policy is None else policy,
            repo_root=repo, registry_path=fixture.REGISTRY_PATH,
        )

    def decisions(self, report, repo, policy=None):
        eligibility = policy_eligibility(
            self.policy(repo) if policy is None else policy, report
        )
        return {d.record_id: d for d in eligibility.decisions}

    def git(self, repo, *args):
        env = dict(
            os.environ,
            GIT_AUTHOR_NAME="t", GIT_AUTHOR_EMAIL="t@example.com",
            GIT_COMMITTER_NAME="t", GIT_COMMITTER_EMAIL="t@example.com",
        )
        return subprocess.run(
            ["git", "-C", repo, "-c", "commit.gpgsign=false", *args],
            check=True, env=env, capture_output=True, text=True,
        ).stdout

    def status(self, repo):
        out = self.git(repo, "status", "--porcelain=v1", "--untracked-files=all")
        return sorted(line[3:] for line in out.splitlines() if line)

    def read(self, repo, rel):
        with open(os.path.join(repo, rel), encoding="utf-8") as fh:
            return fh.read()

    def plan_for(self, approval, record_digest, repo):
        """The edit plan the applier would be handed for the STALE record."""
        post = self.read(repo, fixture.LIVING_DOC).replace(
            STALE_PREIMAGE, STALE_POSTIMAGE
        )
        self.assertNotEqual(post, self.read(repo, fixture.LIVING_DOC))
        content = {
            "artifact": "edit-plan",
            "schema_version": ARTIFACT_SCHEMA_VERSION,
            "approval_digest": approval.digest,
            "operations": [{
                "op": "replace",
                "record": record_digest,
                "target_class": "documentation",
                "path": fixture.LIVING_DOC,
                "start_line": STALE_FIRST_LINE,
                "end_line": STALE_LAST_LINE,
                "preimage": STALE_PREIMAGE,
                "text": STALE_POSTIMAGE,
            }],
            "postimages": {fixture.LIVING_DOC: sha256_text(post)},
        }
        plan = dict(content, digest=sha256_canonical(content))
        return plan, post

    def run_cli(self, *argv, cwd=None):
        env = dict(os.environ, PYTHONPATH=ENGINE)
        return subprocess.run(
            [sys.executable, "-m", "doclifecycle", *argv],
            capture_output=True, text=True, env=env, cwd=cwd,
        )

    def outside(self, name):
        directory = tempfile.mkdtemp(prefix="doc-lifecycle-policy-scenario-")
        self.addCleanup(shutil.rmtree, directory, ignore_errors=True)
        return os.path.join(directory, name)


class ThePolicyMintsForAnEligibleDriftFinding(PolicyScenarioTestCase):
    """First acceptance criterion, against a finding an audit produced."""

    def test_the_fixtures_stale_finding_is_eligible_under_the_defaults(self):
        repo = self.build_fixture()
        report, by_path = self.approvable(repo)

        decision = self.decisions(report, repo)[
            by_path[fixture.LIVING_DOC].id]

        self.assertIsNone(decision.refusal)
        self.assertEqual(decision.eligible_class, CLASS_DRIFT_STALE)

    def test_the_narrative_anchor_is_eligible_under_the_defaults_too(self):
        repo = self.build_fixture()
        report, by_path = self.approvable(repo)

        decision = self.decisions(report, repo)[
            by_path[fixture.NARRATIVE_DOC].id]

        self.assertIsNone(decision.refusal)
        self.assertEqual(decision.eligible_class, CLASS_ANCHOR_REFRESH)

    def test_the_policy_mints_an_approval_set_naming_itself_as_minter(self):
        repo = self.build_fixture()
        report, _ = self.approvable(repo)

        approval = self.mint_by_policy(report, repo)

        self.assertIsInstance(approval, ApprovalSet, approval)
        self.assertEqual(approval.minter,
                         Minter(kind=MINTER_POLICY,
                                id=fixture.AUTO_APPLY_POLICY_ID))

    def test_a_consumer_narrowing_the_classes_narrows_the_selection(self):
        repo = self.build_fixture()
        report, by_path = self.approvable(repo)

        approval = self.mint_by_policy(report, repo, self.drift_only(repo))

        self.assertEqual([r.path for r in approval.records],
                         [fixture.LIVING_DOC])
        self.assertEqual([r.digest for r in approval.skipped],
                         [by_path[fixture.NARRATIVE_DOC].digest])

    def test_the_command_mints_the_same_artifact_the_library_does(self):
        repo = self.build_fixture()
        report, _ = self.approvable(repo)
        report_path = self.outside("report.json")
        with open(report_path, "w", encoding="utf-8") as fh:
            json.dump(report.to_dict(), fh)

        result = self.run_cli(
            "policy-mint", "--report", report_path, "--repo", repo,
            "--registry", fixture.REGISTRY_PATH,
        )

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout),
                         self.mint_by_policy(report, repo).to_dict())

    def test_the_provenance_that_travels_with_the_change_names_the_policy(self):
        # What a reviewer performing change approval reads: the PR body's
        # summary and the commit's trailers, rendered by the engine's own
        # renderers — the same ones a human-minted set goes through.
        repo = self.build_fixture()
        report, _ = self.approvable(repo)

        approval = self.mint_by_policy(report, repo, self.drift_only(repo))

        self.assertIn(f"`policy` `{fixture.AUTO_APPLY_POLICY_ID}`",
                      render_approval_set(approval))
        self.assertIn(f"Doc-Lifecycle-Approval: {approval.digest}",
                      approval_trailers(approval))


class ThePolicyMintedSetGoesThroughTheSameApplier(PolicyScenarioTestCase):
    """Fourth acceptance criterion: the identical applier, no bypass."""

    def applied(self, repo):
        report, by_path = self.approvable(repo)
        approval = self.mint_by_policy(report, repo, self.drift_only(repo))
        self.assertIsInstance(approval, ApprovalSet, approval)
        plan, post = self.plan_for(
            approval, by_path[fixture.LIVING_DOC].digest, repo
        )
        result = apply_edit_plan(
            repo, plan, approval.to_dict(), report=report,
            registry_path=fixture.REGISTRY_PATH,
        )
        return report, approval, result, post

    def test_the_applier_accepts_it_and_writes_the_approved_document(self):
        repo = self.build_fixture()

        _, _, result, post = self.applied(repo)

        self.assertNotIsInstance(result, Invalid, result)
        self.assertEqual(result.status, STATE_CLEAN)
        self.assertEqual(self.read(repo, fixture.LIVING_DOC), post)

    def test_it_writes_nothing_the_approval_did_not_cover(self):
        repo = self.build_fixture()

        _, _, result, _ = self.applied(repo)

        self.assertEqual(result.changed_paths, (fixture.LIVING_DOC,))
        self.assertEqual(self.status(repo), [fixture.LIVING_DOC])

    def test_nothing_is_staged_or_committed_by_the_apply(self):
        # Change approval is a person merging the PR. The applier never lands
        # anything, whoever minted the authority it ran under.
        repo = self.build_fixture()

        self.applied(repo)

        staged = self.git(repo, "diff", "--cached", "--name-only")
        self.assertEqual(staged.strip(), "")

    def test_the_injected_instruction_in_the_document_wins_nothing(self):
        # The fixture's living document tells its reader to approve everything
        # and delete the vendored file. An autonomous lane is exactly the
        # reader that comment is aimed at.
        repo = self.build_fixture()

        self.applied(repo)

        self.assertTrue(os.path.exists(
            os.path.join(repo, fixture.EXCLUDED_DOC)))
        self.assertEqual(self.status(repo), [fixture.LIVING_DOC])

    def test_a_policy_minted_plan_is_refused_the_moment_it_leaves_the_scope(self):
        # Same confinement path as a human's: an operation on a document the
        # approval does not cover is refused, and the tree is untouched.
        repo = self.build_fixture()
        report, by_path = self.approvable(repo)
        approval = self.mint_by_policy(report, repo, self.drift_only(repo))
        plan, _ = self.plan_for(
            approval, by_path[fixture.LIVING_DOC].digest, repo
        )
        plan["operations"][0]["path"] = fixture.POLICY_DOC
        plan["digest"] = sha256_canonical(
            {k: v for k, v in plan.items() if k != "digest"}
        )

        result = apply_edit_plan(
            repo, plan, approval.to_dict(), report=report,
            registry_path=fixture.REGISTRY_PATH,
        )

        self.assertIsInstance(result, Invalid, result)
        self.assertEqual(self.status(repo), [])

    def test_the_policy_produces_the_artifact_a_human_would_have(self):
        # The no-bypass property stated as an equality: mint by policy and mint
        # by hand over the same selection differ in the minter and nothing else.
        repo = self.build_fixture()
        report, by_path = self.approvable(repo)

        by_policy = self.mint_by_policy(report, repo, self.drift_only(repo))
        by_hand = mint_approval_set(
            report, [by_path[fixture.LIVING_DOC].digest], repo_root=repo,
            minter=Minter(kind="human", id="avery@example.com"),
            registry_path=fixture.REGISTRY_PATH,
        )

        policy_payload, human_payload = by_policy.to_dict(), by_hand.to_dict()
        for payload in (policy_payload, human_payload):
            payload.pop("minter")
            payload.pop("digest")
        self.assertEqual(policy_payload, human_payload)


class WhatThePolicyProvablyCannotMint(PolicyScenarioTestCase):
    """Second acceptance criterion: typed refusal, no PR."""

    def bloat_report(self, repo):
        """A real report whose one record is a bloat verdict on a real doc."""
        report, _ = self.approvable(repo)
        record = build_finding(
            lineage=report.lineage, code="CUT", path=fixture.POLICY_DOC,
            units=self.unit_digests(repo, fixture.POLICY_DOC)[:1],
            record_id="BLOAT-001",
            extra={"rationale": "restates what the heading already says"},
        )
        self.assertNotIsInstance(record, Invalid, record)
        return self.rebuild_report(report, [record.to_record()], repo)

    def retire_report(self, repo):
        report, _ = self.approvable(repo)
        record = build_finding(
            lineage=report.lineage, code="RETIRE-DOC", path=fixture.POLICY_DOC,
            units=self.unit_digests(repo, fixture.POLICY_DOC)[:1],
            record_id="BLOAT-002",
            extra={"rationale": "carries nothing another document lacks"},
        )
        return self.rebuild_report(report, [record.to_record()], repo)

    def unit_digests(self, repo, path):
        from doclifecycle.segment import segment_document

        segmentation = segment_document(repo, path, fixture.REGISTRY_PATH)
        self.assertNotIsInstance(segmentation, Invalid, segmentation)
        return [u.digest for u in segmentation.units if u.assertion_capable]

    def rebuild_report(self, report, records, repo):
        from doclifecycle.report import validate_report

        payload = report.to_dict()
        payload["records"] = [dict(r) for r in records]
        payload.pop("digest", None)
        rebuilt = validate_report(
            payload, repo_root=repo, registry_path=fixture.REGISTRY_PATH
        )
        self.assertNotIsInstance(rebuilt, Invalid, rebuilt)
        return rebuilt

    def test_a_bloat_cut_is_refused_by_name_and_mints_nothing(self):
        repo = self.build_fixture()

        result = self.mint_by_policy(self.bloat_report(repo), repo)

        self.assertIsInstance(result, Invalid, result)
        self.assertIn("policy-never-eligible",
                      [p.code for p in result.problems])
        self.assertNotIsInstance(result, ApprovalSet)

    def test_a_document_retirement_is_refused_the_same_way(self):
        repo = self.build_fixture()

        result = self.mint_by_policy(self.retire_report(repo), repo)

        self.assertIn("policy-never-eligible",
                      [p.code for p in result.problems])

    def test_the_command_exits_invalid_and_writes_no_approval_set(self):
        repo = self.build_fixture()
        report_path = self.outside("bloat-report.json")
        out = self.outside("approval.json")
        with open(report_path, "w", encoding="utf-8") as fh:
            json.dump(self.bloat_report(repo).to_dict(), fh)

        result = self.run_cli(
            "policy-mint", "--report", report_path, "--repo", repo,
            "--registry", fixture.REGISTRY_PATH, "--out", out,
        )

        self.assertEqual(result.returncode, 1)
        self.assertIn("policy-nothing-eligible", result.stderr)
        self.assertFalse(os.path.exists(out))
        self.assertEqual(self.status(repo), [])

    def test_the_waiver_the_install_carries_stops_the_policy_dead(self):
        # The fixture's own `.github/doc-sync/drift-waivers.json` disputes the
        # living document's stale claim. A policy that applied it anyway would
        # overrule the only person who looked.
        repo = self.build_fixture()
        report = self.full_report(repo, waivers=fixture.WAIVERS_PATH)

        decisions = self.decisions(report, repo, self.drift_only(repo))
        stale = [d for d in decisions.values()
                 if d.code == "STALE"]

        self.assertEqual([d.refusal.code for d in stale],
                         ["policy-record-waived"])

    def test_a_waived_report_mints_nothing_under_the_drift_class(self):
        repo = self.build_fixture()
        report = self.full_report(repo, waivers=fixture.WAIVERS_PATH)

        result = self.mint_by_policy(report, repo, self.drift_only(repo))

        self.assertIsInstance(result, Invalid, result)
        self.assertIn("policy-record-waived",
                      [p.code for p in result.problems])
        self.assertEqual(self.status(repo), [])


class AnAbsentPolicyMintsNothingAtAll(PolicyScenarioTestCase):
    """Third acceptance criterion, on a real repository with none configured."""

    def unconfigured(self):
        repo = self.build_fixture()
        os.remove(os.path.join(repo, fixture.AUTO_APPLY_POLICY_PATH))
        self.git(repo, "add", "-A")
        self.git(repo, "commit", "-q", "-m", "Remove the auto-apply policy")
        return repo

    def test_loading_it_refuses_rather_than_returning_a_default(self):
        repo = self.unconfigured()

        loaded = load_auto_apply_policy(repo)

        self.assertIsInstance(loaded, Invalid, loaded)
        self.assertEqual([p.code for p in loaded.problems],
                         ["policy-not-configured"])

    def test_the_command_refuses_and_says_so_on_the_run_surface(self):
        repo = self.unconfigured()
        report, _ = self.approvable(repo)
        report_path = self.outside("report.json")
        with open(report_path, "w", encoding="utf-8") as fh:
            json.dump(report.to_dict(), fh)

        result = self.run_cli(
            "policy-mint", "--report", report_path, "--repo", repo,
            "--registry", fixture.REGISTRY_PATH,
        )

        self.assertEqual(result.returncode, 1)
        self.assertIn("policy-not-configured", result.stderr)
        self.assertEqual(self.status(repo), [])

    def test_a_human_can_still_mint_from_the_same_report(self):
        # Removing the policy switches off autonomous minting, not approval.
        repo = self.unconfigured()
        report, by_path = self.approvable(repo)

        approval = mint_approval_set(
            report, [by_path[fixture.LIVING_DOC].digest], repo_root=repo,
            minter=Minter(kind="human", id="avery@example.com"),
            registry_path=fixture.REGISTRY_PATH,
        )

        self.assertIsInstance(approval, ApprovalSet, approval)


if __name__ == "__main__":
    unittest.main()
