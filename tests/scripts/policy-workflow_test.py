#!/usr/bin/env python3
"""Static guards for the audit-chained auto-apply policy lane (#143).

The engine owns eligibility, minting, planning validation, and application. The
scheduler adapter only connects a successful scheduled audit to the existing
three-job apply trust split. These tests pin that public wiring seam without
reimplementing either contract.

Run: python3 tests/scripts/policy-workflow_test.py
"""

import importlib.util
import json
import os
import re
import sys
import unittest


ROOT = os.path.join(os.path.dirname(__file__), "..", "..")
POLICY_WORKFLOW = os.path.join(
    ROOT, "plugins", "doc-lifecycle", "skills", "scheduling-doc-sync",
    "doc-policy-apply.yml",
)
MANUAL_WORKFLOW = os.path.join(
    ROOT, "plugins", "doc-lifecycle", "skills", "scheduling-doc-sync",
    "doc-apply.yml",
)
CONSUMER_POLICY = os.path.join(
    ROOT, ".doc-lifecycle", "auto-apply-policy.json",
)
SCHEDULING_SKILL = os.path.join(
    ROOT, "plugins", "doc-lifecycle", "skills", "scheduling-doc-sync",
    "SKILL.md",
)
SCHEDULING_GUIDE = os.path.join(
    ROOT, "docs", "guides", "scheduling-doc-sync.md",
)

USES_LINE = re.compile(r"uses:\s*([^\s#]+)")
SHA_PINNED = re.compile(r"^[^@]+@[0-9a-f]{40}$")


def load_permissions_test():
    path = os.path.join(os.path.dirname(__file__), "workflow-permissions_test.py")
    spec = importlib.util.spec_from_file_location("workflow_permissions_test", path)
    mod = importlib.util.module_from_spec(spec)
    sys.dont_write_bytecode = True
    spec.loader.exec_module(mod)
    return mod


WPT = load_permissions_test()


def lines():
    with open(POLICY_WORKFLOW, encoding="utf-8") as fh:
        return fh.read().splitlines()


def jobs():
    return WPT.jobs_of(POLICY_WORKFLOW)


def manual_jobs():
    return WPT.jobs_of(MANUAL_WORKFLOW)


class ACompletedScheduledAuditEntersTheSharedApplyLane(unittest.TestCase):
    def test_the_policy_trigger_enters_an_explicit_three_job_apply_lane(self):
        self.assertTrue(os.path.isfile(POLICY_WORKFLOW))
        policy = "\n".join(lines())

        self.assertIn("workflow_run:", policy)
        self.assertIn('workflows: ["doc-audit"]', policy)
        self.assertIn("github.event.workflow_run.event == 'schedule'", policy)
        self.assertIn("github.event.workflow_run.conclusion == 'success'", policy)
        self.assertIn("github.event.repository.default_branch", policy)
        self.assertIn("revalidate:", policy)
        self.assertIn("plan:", policy)
        self.assertIn("apply:", policy)
        self.assertNotIn("secrets: inherit", policy)

    def test_the_trigger_names_the_completed_audit_run_as_data(self):
        body = "\n".join(jobs()["revalidate"])

        self.assertIn("github.event.workflow_run.id", body)
        self.assertIn("name: audit-report", body)
        self.assertIn("run-id:", body)
        self.assertIn("github-token:", body)
        self.assertNotIn("inputs.", body)


class ThisConsumerOptsInExplicitly(unittest.TestCase):
    def test_the_dogfood_install_names_its_mechanical_policy(self):
        with open(CONSUMER_POLICY, encoding="utf-8") as fh:
            policy = json.load(fh)

        self.assertEqual(
            policy,
            {
                "artifact": "auto-apply-policy",
                "schema_version": 1,
                "id": "toolshed-mechanical-doc-maintenance",
                "classes": [
                    "drift-stale-mechanical",
                    "narrative-anchor-refresh",
                ],
            },
        )


class TheOptInIsDocumentedAtBothUserDoors(unittest.TestCase):
    def test_the_install_skill_documents_the_standing_policy_and_lane(self):
        with open(SCHEDULING_SKILL, encoding="utf-8") as fh:
            skill = fh.read()

        self.assertIn("doc-policy-apply.yml", skill)
        self.assertIn(".doc-lifecycle/auto-apply-policy.json", skill)
        self.assertIn("drift-stale-mechanical", skill)
        self.assertIn("narrative-anchor-refresh", skill)
        self.assertIn("never overwrite", skill)
        self.assertIn("real pull request", skill)

    def test_the_user_guide_explains_how_to_enable_and_review_it(self):
        with open(SCHEDULING_GUIDE, encoding="utf-8") as fh:
            guide = fh.read()

        self.assertIn("doc-policy-apply.yml", guide)
        self.assertIn(".doc-lifecycle/auto-apply-policy.json", guide)
        self.assertIn("No human selected these records", guide)
        self.assertIn("real pull request", guide)
        self.assertIn("PR review", guide)


class ThePolicyProducerIsDeterministicAndFailClosed(unittest.TestCase):
    def test_revalidate_holds_no_write_scope(self):
        self.assertEqual(
            WPT.mapping_under(jobs()["revalidate"], "permissions", 4),
            {"contents": "read", "actions": "read"},
        )

    def test_the_report_is_revalidated_before_policy_minting(self):
        body = "\n".join(jobs()["revalidate"])
        revalidate = body.index("validate-report")
        eligibility = body.index("doc-lifecycle.py policy-eligibility")
        mint = body.index("doc-lifecycle.py policy-mint")

        self.assertLess(revalidate, eligibility)
        self.assertLess(eligibility, mint)
        self.assertIn(".doc-lifecycle/auto-apply-policy.json", body)
        self.assertNotIn(" --record", body)

    def test_no_policy_or_no_eligible_record_cannot_reach_a_write_job(self):
        outputs = "\n".join(jobs()["revalidate"])
        self.assertIn("configured:", outputs)
        self.assertIn("eligible:", outputs)
        for name in ("plan", "apply"):
            body = "\n".join(jobs()[name])
            self.assertIn("needs.revalidate.outputs.configured == 'true'", body)
            self.assertIn("needs.revalidate.outputs.eligible == 'true'", body)

    def test_the_minted_approval_bundle_carries_the_same_lineage_as_manual_apply(self):
        body = "\n".join(jobs()["revalidate"])
        for name in (
            "drift-report.json",
            "approval.json",
            "approval-summary.md",
            "trailers.txt",
            "config-digest.txt",
            "branch.txt",
        ):
            with self.subTest(name=name):
                self.assertIn(name, body)
        self.assertIn("approval-digest", body)
        self.assertIn("render-approval", body)


class TheThreeJobsStaySplitByTrust(unittest.TestCase):
    def test_exactly_revalidate_plan_and_apply_exist(self):
        self.assertEqual(set(jobs()), {"revalidate", "plan", "apply"})

    def test_only_plan_runs_a_model(self):
        with_model = {
            name for name, body in jobs().items()
            if any(WPT.MODEL_ACTION in line for line in body)
        }
        self.assertEqual(with_model, {"plan"})

    def test_plan_has_only_read_and_oauth_permissions(self):
        self.assertEqual(
            WPT.mapping_under(jobs()["plan"], "permissions", 4),
            {"contents": "read", "id-token": "write"},
        )
        body = "\n".join(jobs()["plan"])
        self.assertIn("persist-credentials: false", body)
        self.assertNotIn("GH_TOKEN", body)

    def test_only_apply_has_repository_write_authority(self):
        credentialed = {
            name for name, body in jobs().items()
            if set(WPT.write_scopes(
                WPT.mapping_under(body, "permissions", 4) or {}
            )) - {"id-token"}
        }
        self.assertEqual(credentialed, {"apply"})
        self.assertEqual(
            WPT.mapping_under(jobs()["apply"], "permissions", 4),
            {"contents": "write", "pull-requests": "write"},
        )

    def test_every_third_party_action_is_sha_pinned(self):
        found, offenders = 0, []
        for number, line in enumerate(lines(), 1):
            match = USES_LINE.search(line)
            if not match:
                continue
            found += 1
            if not SHA_PINNED.match(match.group(1)):
                offenders.append(f"{number}: {match.group(1)}")
        self.assertGreater(found, 0)
        self.assertEqual(offenders, [])


class ManualAndPolicyApplyCannotDriftAtTheTrustSeams(unittest.TestCase):
    """The lanes differ in selection, not in model/write authority.

    GitHub grants permissions and secrets to jobs, not to a reusable sequence
    of steps. Keeping each lane's three jobs visible therefore preserves the
    reviewable trust graph; these parity checks give the security-critical
    repeated wiring one owner without hiding it behind secret forwarding.
    """

    def test_plan_and_apply_permissions_are_identical(self):
        def without_comments(mapping):
            return {
                key: value.split("#", 1)[0].strip()
                for key, value in (mapping or {}).items()
            }

        for name in ("plan", "apply"):
            with self.subTest(job=name):
                self.assertEqual(
                    without_comments(WPT.mapping_under(
                        jobs()[name], "permissions", 4)),
                    without_comments(WPT.mapping_under(
                        manual_jobs()[name], "permissions", 4)),
                )

    def test_model_jobs_share_the_repository_credential_boundary(self):
        for lane in (jobs(), manual_jobs()):
            body = "\n".join(lane["plan"])
            for seam in (
                WPT.MODEL_ACTION,
                "persist-credentials: false",
                "contents: read",
                "id-token: write",
            ):
                with self.subTest(seam=seam):
                    self.assertIn(seam, body)
            self.assertNotIn("GH_TOKEN", body)

    def test_writers_share_the_deterministic_confinement_boundary(self):
        for lane in (jobs(), manual_jobs()):
            body = "\n".join(lane["apply"])
            for seam in (
                "apply-plan",
                "--expected-digest",
                "staged-paths",
                "--pathspec-from-file",
                "--pathspec-file-nul",
                "verify-staged",
                "git push origin",
                "gh pr create",
            ):
                with self.subTest(seam=seam):
                    self.assertIn(seam, body)
            self.assertNotIn("git add -A", body)
            self.assertNotIn("--draft", body)

    def test_plan_and_apply_use_the_same_pinned_action_revisions(self):
        def action_refs(body):
            return {
                match.group(1)
                for line in body
                for match in [USES_LINE.search(line)]
                if match
            }

        for name in ("plan", "apply"):
            with self.subTest(job=name):
                self.assertEqual(
                    action_refs(jobs()[name]),
                    action_refs(manual_jobs()[name]),
                )


class CredentialClaimsNameTheCredentialTheyExclude(unittest.TestCase):
    def test_model_jobs_are_never_described_as_unqualified_credential_free(self):
        current_surfaces = (
            os.path.join(ROOT, "CLAUDE.md"),
            SCHEDULING_SKILL,
            os.path.join(ROOT, "tests", "scripts", "apply-workflow_test.py"),
            os.path.join(ROOT, "tests", "scripts", "audit-workflow_test.py"),
            os.path.join(
                ROOT, "plugins", "doc-lifecycle", "skills",
                "scheduling-doc-sync", "doc-audit.yml",
            ),
            os.path.join(
                ROOT, "plugins", "doc-lifecycle", "skills",
                "scheduling-doc-sync", "doc-apply.yml",
            ),
        )
        for path in current_surfaces:
            with open(path, encoding="utf-8") as fh:
                text = fh.read()
            with self.subTest(path=path):
                self.assertNotRegex(text, r"(?<!repository-)credential-free")


class TheWriterCanOnlyOpenAReviewableChange(unittest.TestCase):
    def test_apply_uses_the_engine_confinement_and_explicit_path_list(self):
        body = "\n".join(jobs()["apply"])

        self.assertIn("apply-plan", body)
        self.assertIn("--expected-digest", body)
        self.assertIn("staged-paths", body)
        self.assertIn("--pathspec-from-file", body)
        self.assertIn("--pathspec-file-nul", body)
        self.assertIn("verify-staged", body)
        self.assertNotIn("git add -A", body)
        self.assertNotIn("git add --all", body)

    def test_the_model_artifact_cannot_overwrite_the_trusted_bundle(self):
        body = "\n".join(jobs()["apply"])
        self.assertIn("path: ${{ runner.temp }}/apply", body)
        self.assertIn("path: ${{ runner.temp }}/plan", body)

    def test_the_lane_pushes_a_derived_branch_and_opens_a_real_pr(self):
        body = "\n".join(jobs()["apply"])

        # The branch is derived, and what it carries is the commit
        # `verify-apply-bytes.py commit` certified — never `HEAD`, which is
        # whatever the last thing to run left behind (aj604/toolshed#191).
        self.assertIn('verified-commit.txt"):refs/heads/', body)
        self.assertNotIn('"HEAD:refs/heads/', body)
        self.assertIn("gh pr create", body)
        self.assertIn("--body-file", body)
        self.assertNotIn("--draft", body)
        self.assertNotRegex(body, r"git\s+push[^\n]*(main|master)")

    def test_no_other_job_can_push_or_open_a_pr(self):
        for name in ("revalidate", "plan"):
            body = "\n".join(jobs()[name])
            self.assertNotIn("git push", body)
            self.assertNotIn("gh pr create", body)


if __name__ == "__main__":
    unittest.main()
