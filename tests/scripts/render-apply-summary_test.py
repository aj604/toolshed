#!/usr/bin/env python3
"""Black-box tests for scheduling-doc-sync's render-apply-summary.py.

This script owns the run surface of the scheduler adapter's apply lane
(doc-apply.yml, issue #72): every refusal the lane can reach, the staged path
list the credentialed job hands to `git add`, and the PR title, PR body, and
commit message that carry the approval set's digest and summary into the
change it authorizes.

Everything here is a function of artifacts the engine already validated — a
report, an approval set, and an `ApplyResult` — so the script re-derives
nothing and asserts nothing the engine did not: it renders, and it refuses.

Tested as a subprocess: real argv, real exit codes, real stdout, and a real
$GITHUB_STEP_SUMMARY file.

Run: python3 tests/scripts/render-apply-summary_test.py
"""

import json
import os
import subprocess
import sys
import tempfile
import unittest

SCRIPT = os.path.join(
    os.path.dirname(__file__),
    "..", "..",
    "plugins", "doc-lifecycle", "skills", "scheduling-doc-sync",
    "scripts", "render-apply-summary.py",
)

REPORT_DIGEST = "d" * 64
APPROVAL_DIGEST = "c" * 64
RECORD_DIGEST = "a" * 64
SKIPPED_DIGEST = "b" * 64

LINEAGE = {
    "repository": "origin:github.com/aj604/toolshed",
    "base_commit": "1" * 40,
    "audit_mode": "full",
    "inventory_digest": "e" * 64,
    "audit_config_digest": "f" * 64,
    "registry_digest": "9" * 64,
    "ruleset_version": 1,
    "plugin_version": "0.21.0",
    "evidence_boundary": {"sources": ["**"], "excluded": []},
}


def report(**over):
    payload = {
        "status": "findings",
        "schema_version": 1,
        "lineage": dict(LINEAGE),
        "records": [
            {"id": "DRIFT-001", "digest": RECORD_DIGEST, "code": "STALE",
             "path": "docs/architecture.md"},
            {"id": "DRIFT-002", "digest": SKIPPED_DIGEST, "code": "UNVERIFIABLE",
             "path": "docs/guides/onboarding.md"},
        ],
        "incomplete": [],
        "digest": REPORT_DIGEST,
    }
    payload.update(over)
    return payload


def approval(**over):
    payload = {
        "artifact": "approval-set",
        "schema_version": 1,
        "status": "clean",
        "minter": {"kind": "human", "id": "avery"},
        "report_digest": REPORT_DIGEST,
        "report_state": "findings",
        "lineage": dict(LINEAGE),
        "reconciliation_digest": "7" * 64,
        "records": [
            {"digest": RECORD_DIGEST, "id": "DRIFT-001", "code": "STALE",
             "path": "docs/architecture.md", "destination": None,
             "units": ["8" * 64]},
        ],
        "skipped": [{"digest": SKIPPED_DIGEST, "id": "DRIFT-002"}],
        "scope": {"roots": ["docs"], "paths": ["docs/architecture.md"]},
        "digest": APPROVAL_DIGEST,
    }
    payload.update(over)
    return payload


def result(**over):
    payload = {
        "status": "clean",
        "schema_version": 1,
        "approval_digest": APPROVAL_DIGEST,
        "plan_digest": "5" * 64,
        "applied": [{"op": "replace", "record": RECORD_DIGEST,
                     "path": "docs/architecture.md"}],
        "changed_paths": ["docs/architecture.md"],
        "already_applied": False,
    }
    payload.update(over)
    return payload


def stale_payload(*codes):
    return {
        "status": "stale",
        "schema_version": 1,
        "lineage": dict(LINEAGE),
        "records": [],
        "incomplete": [],
        "digest": REPORT_DIGEST,
        "stale_reasons": [
            {"code": code, "message": f"{code} moved",
             "reported": "x" * 8, "current": "y" * 8}
            for code in codes
        ],
    }


class ScriptTestCase(unittest.TestCase):
    """A temp dir, JSON fixtures on disk, and a real step-summary file."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.summary_path = self.path("step-summary.md")
        with open(self.summary_path, "w", encoding="utf-8"):
            pass

    def path(self, name):
        return os.path.join(self.tmp.name, name)

    def write(self, name, payload):
        target = self.path(name)
        with open(target, "w", encoding="utf-8") as fh:
            json.dump(payload, fh)
        return target

    def write_text(self, name, text):
        target = self.path(name)
        with open(target, "w", encoding="utf-8") as fh:
            fh.write(text)
        return target

    def read(self, name):
        with open(self.path(name), encoding="utf-8") as fh:
            return fh.read()

    def summary(self):
        with open(self.summary_path, encoding="utf-8") as fh:
            return fh.read()

    def run_script(self, *argv):
        env = dict(os.environ)
        env["GITHUB_STEP_SUMMARY"] = self.summary_path
        return subprocess.run(
            [sys.executable, SCRIPT, *argv],
            capture_output=True, text=True, env=env,
        )


class VerifyReport(ScriptTestCase):
    """The dispatched report digest binds the artifact to the reviewer's intent."""

    def test_matching_digest_and_approvable_state_is_accepted(self):
        path = self.write("report.json", report())
        proc = self.run_script("verify-report", "--report", path,
                               "--expected-digest", REPORT_DIGEST)
        self.assertEqual(proc.returncode, 0, proc.stderr)

    def test_a_different_report_is_refused_naming_both_digests(self):
        path = self.write("report.json", report(digest="0" * 64))
        proc = self.run_script("verify-report", "--report", path,
                               "--expected-digest", REPORT_DIGEST)
        self.assertEqual(proc.returncode, 1)
        self.assertIn("apply-report-digest-mismatch", self.summary())
        self.assertIn(REPORT_DIGEST, self.summary())
        self.assertIn("0" * 64, self.summary())

    def test_a_report_state_nothing_can_be_approved_from_is_refused(self):
        path = self.write("report.json", report(status="clean", records=[]))
        proc = self.run_script("verify-report", "--report", path,
                               "--expected-digest", REPORT_DIGEST)
        self.assertEqual(proc.returncode, 1)
        self.assertIn("apply-report-not-approvable", self.summary())

    def test_an_unreadable_report_is_refused_not_silently_skipped(self):
        proc = self.run_script("verify-report", "--report",
                               self.path("absent.json"),
                               "--expected-digest", REPORT_DIGEST)
        self.assertEqual(proc.returncode, 1)
        self.assertIn("apply-report-unreadable", self.summary())

    def test_a_refusal_says_no_branch_or_pr_was_created(self):
        path = self.write("report.json", report(digest="0" * 64))
        self.run_script("verify-report", "--report", path,
                        "--expected-digest", REPORT_DIGEST)
        self.assertIn("No branch and no pull request", self.summary())


class Gate(ScriptTestCase):
    """Every engine exit code the lane consumes reaches the run surface typed."""

    def test_a_clean_engine_exit_passes_the_gate(self):
        path = self.write("revalidated.json", report())
        proc = self.run_script("gate", "--stage", "revalidation",
                               "--payload", path, "--exit-code", "0")
        self.assertEqual(proc.returncode, 0, proc.stderr)

    def test_a_stale_report_refuses_naming_every_changed_lineage_field(self):
        path = self.write("revalidated.json", stale_payload(
            "lineage-base-commit-mismatch", "lineage-audit-config-mismatch"))
        proc = self.run_script("gate", "--stage", "revalidation",
                               "--payload", path, "--exit-code", "3")
        self.assertEqual(proc.returncode, 1)
        self.assertIn("lineage-base-commit-mismatch", self.summary())
        self.assertIn("lineage-audit-config-mismatch", self.summary())
        self.assertIn("REFUSED", self.summary())

    def test_a_stale_refusal_says_no_branch_or_pr_was_created(self):
        path = self.write("revalidated.json",
                          stale_payload("lineage-registry-mismatch"))
        self.run_script("gate", "--stage", "revalidation",
                        "--payload", path, "--exit-code", "3")
        self.assertIn("No branch and no pull request", self.summary())

    def test_an_invalid_payload_refuses_naming_every_problem(self):
        path = self.write("revalidated.json", {
            "status": "invalid", "schema_version": 1,
            "problems": [{"code": "report-digest-mismatch",
                          "message": "altered since it was produced",
                          "location": "digest"}],
        })
        proc = self.run_script("gate", "--stage", "revalidation",
                               "--payload", path, "--exit-code", "1")
        self.assertEqual(proc.returncode, 1)
        self.assertIn("report-digest-mismatch", self.summary())

    def test_a_nonzero_exit_with_no_readable_payload_still_refuses(self):
        proc = self.run_script("gate", "--stage", "minting",
                               "--payload", self.path("absent.json"),
                               "--exit-code", "1")
        self.assertEqual(proc.returncode, 1)
        self.assertIn("apply-stage-failed", self.summary())

    def test_a_zero_exit_with_no_readable_payload_refuses(self):
        # A stage that "succeeded" but produced nothing to carry forward is a
        # failure of the lane, never a pass — the same rule the audit lane's
        # missing-report state follows.
        proc = self.run_script("gate", "--stage", "minting",
                               "--payload", self.path("absent.json"),
                               "--exit-code", "0")
        self.assertEqual(proc.returncode, 1)
        self.assertIn("apply-stage-produced-nothing", self.summary())

    def test_a_stale_approval_set_refuses_naming_the_field_that_moved(self):
        path = self.write("approval.json", approval(
            status="stale",
            stale_reasons=[{"code": "approval-preimage-mismatch",
                            "message": "the passage changed",
                            "reported": "1", "current": "2"}]))
        proc = self.run_script("gate", "--stage", "minting",
                               "--payload", path, "--exit-code", "3")
        self.assertEqual(proc.returncode, 1)
        self.assertIn("approval-preimage-mismatch", self.summary())

    def test_a_declared_clean_status_with_a_nonzero_exit_still_refuses(self):
        # The exit code is the engine's verdict; a payload that says otherwise
        # never talks the lane past it.
        path = self.write("payload.json", approval(status="clean"))
        proc = self.run_script("gate", "--stage", "apply",
                               "--payload", path, "--exit-code", "3")
        self.assertEqual(proc.returncode, 1)


class RecordArgs(ScriptTestCase):
    """The dispatched record subset is the semantic approval — and inert."""

    def test_whitespace_and_comma_separated_digests_become_record_flags(self):
        out = self.path("record-args.txt")
        proc = self.run_script(
            "record-args", "--records", f"{RECORD_DIGEST}, {SKIPPED_DIGEST}",
            "--out", out)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertEqual(
            self.read("record-args.txt").splitlines(),
            ["--record", RECORD_DIGEST, "--record", SKIPPED_DIGEST])

    def test_a_token_that_is_not_a_record_digest_is_refused(self):
        out = self.path("record-args.txt")
        proc = self.run_script(
            "record-args", "--records", f"{RECORD_DIGEST} --minter-kind",
            "--out", out)
        self.assertEqual(proc.returncode, 1)
        self.assertIn("apply-record-not-a-digest", self.summary())
        self.assertFalse(os.path.exists(out))

    def test_an_empty_selection_is_refused(self):
        proc = self.run_script("record-args", "--records", "   ",
                               "--out", self.path("record-args.txt"))
        self.assertEqual(proc.returncode, 1)
        self.assertIn("apply-empty-selection", self.summary())

    def test_a_repeated_digest_is_refused(self):
        proc = self.run_script(
            "record-args", "--records", f"{RECORD_DIGEST} {RECORD_DIGEST}",
            "--out", self.path("record-args.txt"))
        self.assertEqual(proc.returncode, 1)
        self.assertIn("apply-duplicate-selection", self.summary())


class ConfigDigest(ScriptTestCase):
    """Configuration drift is only compared when the lane supplies the digest."""

    def test_the_current_audit_config_digest_is_extracted(self):
        path = self.write("fresh.json", report())
        out = self.path("config-digest.txt")
        proc = self.run_script("config-digest", "--report", path, "--out", out)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertEqual(self.read("config-digest.txt"), "f" * 64)

    def test_a_missing_digest_is_refused_rather_than_omitted(self):
        lineage = dict(LINEAGE)
        del lineage["audit_config_digest"]
        path = self.write("fresh.json", report(lineage=lineage))
        proc = self.run_script("config-digest", "--report", path,
                               "--out", self.path("config-digest.txt"))
        self.assertEqual(proc.returncode, 1)
        self.assertIn("apply-config-digest-unavailable", self.summary())


class ApprovalDigestOutput(ScriptTestCase):
    def test_the_approval_digest_is_emitted_as_a_step_output(self):
        path = self.write("approval.json", approval())
        out = self.path("output.txt")
        proc = self.run_script("approval-digest", "--approval", path,
                               "--out", out)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertEqual(self.read("output.txt"),
                         f"approval_digest={APPROVAL_DIGEST}\n")

    def test_the_output_file_is_appended_to_not_truncated(self):
        # $GITHUB_OUTPUT accumulates every step output; truncating it would
        # drop whatever an earlier step in the same step context wrote.
        path = self.write("approval.json", approval())
        out = self.write_text("output.txt", "earlier=value\n")
        proc = self.run_script("approval-digest", "--approval", path,
                               "--out", out)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertEqual(self.read("output.txt"),
                         f"earlier=value\napproval_digest={APPROVAL_DIGEST}\n")

    def test_a_digest_that_is_not_a_sha256_is_refused(self):
        path = self.write("approval.json", approval(digest="nope"))
        proc = self.run_script("approval-digest", "--approval", path,
                               "--out", self.path("output.txt"))
        self.assertEqual(proc.returncode, 1)
        self.assertIn("apply-approval-digest-invalid", self.summary())


class BranchName(ScriptTestCase):
    def test_the_branch_is_derived_from_the_approval_digest(self):
        path = self.write("approval.json", approval())
        out = self.path("branch.txt")
        proc = self.run_script("branch-name", "--approval", path, "--out", out)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertEqual(self.read("branch.txt"),
                         f"doc-lifecycle/apply-{APPROVAL_DIGEST[:12]}\n")


class StagedPaths(ScriptTestCase):
    """Staging is limited to what the verified apply result emitted."""

    def test_the_changed_paths_are_written_nul_separated(self):
        res = self.write("result.json", result())
        app = self.write("approval.json", approval())
        out = self.path("paths.txt")
        proc = self.run_script("staged-paths", "--result", res,
                               "--approval", app, "--out", out)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertEqual(self.read("paths.txt"), "docs/architecture.md\0")

    def test_a_result_that_is_not_clean_stages_nothing(self):
        res = self.write("result.json", result(status="stale"))
        app = self.write("approval.json", approval())
        out = self.path("paths.txt")
        proc = self.run_script("staged-paths", "--result", res,
                               "--approval", app, "--out", out)
        self.assertEqual(proc.returncode, 1)
        self.assertIn("apply-result-not-clean", self.summary())
        self.assertFalse(os.path.exists(out))

    def test_a_path_outside_the_approved_mutation_scope_stages_nothing(self):
        res = self.write("result.json", result(
            changed_paths=["docs/architecture.md", "docs/guides/onboarding.md"]))
        app = self.write("approval.json", approval())
        out = self.path("paths.txt")
        proc = self.run_script("staged-paths", "--result", res,
                               "--approval", app, "--out", out)
        self.assertEqual(proc.returncode, 1)
        self.assertIn("apply-path-outside-approved-scope", self.summary())
        self.assertIn("docs/guides/onboarding.md", self.summary())
        self.assertFalse(os.path.exists(out))

    def test_a_path_git_would_read_as_an_option_stages_nothing(self):
        res = self.write("result.json", result(changed_paths=["--output=x"]))
        app = self.write("approval.json", approval(
            scope={"roots": ["docs"], "paths": ["--output=x"]}))
        proc = self.run_script("staged-paths", "--result", res,
                               "--approval", app, "--out", self.path("p.txt"))
        self.assertEqual(proc.returncode, 1)
        self.assertIn("apply-path-unsafe", self.summary())

    def test_a_traversing_path_stages_nothing(self):
        res = self.write("result.json", result(
            changed_paths=["../../etc/passwd"]))
        app = self.write("approval.json", approval(
            scope={"roots": ["docs"], "paths": ["../../etc/passwd"]}))
        proc = self.run_script("staged-paths", "--result", res,
                               "--approval", app, "--out", self.path("p.txt"))
        self.assertEqual(proc.returncode, 1)
        self.assertIn("apply-path-unsafe", self.summary())

    def test_an_empty_change_set_stages_nothing(self):
        res = self.write("result.json", result(changed_paths=[], applied=[]))
        app = self.write("approval.json", approval())
        proc = self.run_script("staged-paths", "--result", res,
                               "--approval", app, "--out", self.path("p.txt"))
        self.assertEqual(proc.returncode, 1)
        self.assertIn("apply-nothing-changed", self.summary())

    def test_an_already_landed_apply_opens_no_pull_request(self):
        res = self.write("result.json", result(already_applied=True,
                                               applied=[]))
        app = self.write("approval.json", approval())
        proc = self.run_script("staged-paths", "--result", res,
                               "--approval", app, "--out", self.path("p.txt"))
        self.assertEqual(proc.returncode, 1)
        self.assertIn("apply-already-landed", self.summary())


class VerifyStaged(ScriptTestCase):
    """What git actually staged must equal what the apply result emitted."""

    def files(self, staged, unstaged=(), approved=("docs/architecture.md",)):
        return [
            "verify-staged",
            "--paths", self.write_text(
                "paths.txt", "".join(f"{p}\0" for p in approved)),
            "--staged", self.write_text(
                "staged.txt", "".join(f"{p}\0" for p in staged)),
            "--unstaged", self.write_text(
                "unstaged.txt", "".join(f"{p}\0" for p in unstaged)),
        ]

    def test_the_staged_set_equalling_the_approved_set_passes(self):
        proc = self.run_script(*self.files(["docs/architecture.md"]))
        self.assertEqual(proc.returncode, 0, proc.stderr)

    def test_a_staged_path_the_apply_result_did_not_emit_refuses(self):
        proc = self.run_script(*self.files(
            ["docs/architecture.md", ".github/workflows/release.yml"]))
        self.assertEqual(proc.returncode, 1)
        self.assertIn("apply-staging-not-confined", self.summary())
        self.assertIn(".github/workflows/release.yml", self.summary())

    def test_an_approved_path_that_was_not_staged_refuses(self):
        proc = self.run_script(*self.files([], approved=("docs/a.md",)))
        self.assertEqual(proc.returncode, 1)
        self.assertIn("apply-staging-incomplete", self.summary())

    def test_a_leftover_unstaged_or_untracked_change_refuses(self):
        proc = self.run_script(*self.files(
            ["docs/architecture.md"], unstaged=["docs/scratch.md"]))
        self.assertEqual(proc.returncode, 1)
        self.assertIn("apply-worktree-not-clean", self.summary())
        self.assertIn("docs/scratch.md", self.summary())


class PullRequestBody(ScriptTestCase):
    """Lineage, approved and skipped records, gaps, and confinement status."""

    def body(self, report_payload=None, approval_payload=None,
             result_payload=None, approval_summary=None):
        rep = self.write("report.json", report_payload or report())
        app = self.write("approval.json", approval_payload or approval())
        res = self.write("result.json", result_payload or result())
        out = self.path("pr-body.md")
        argv = ["pr-body", "--result", res, "--approval", app,
                "--report", rep, "--out", out]
        if approval_summary is not None:
            argv += ["--approval-summary",
                     self.write_text("approval.md", approval_summary)]
        proc = self.run_script(*argv)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        return self.read("pr-body.md")

    def test_the_approval_digest_travels_in_the_body(self):
        self.assertIn(APPROVAL_DIGEST, self.body())

    def test_the_report_digest_and_base_commit_travel_in_the_body(self):
        body = self.body()
        self.assertIn(REPORT_DIGEST, body)
        self.assertIn("1" * 40, body)

    def test_the_rendered_approval_summary_is_embedded_verbatim(self):
        body = self.body(approval_summary="## Approved\n\n- `DRIFT-001`\n")
        self.assertIn("- `DRIFT-001`", body)

    def test_skipped_records_are_listed(self):
        body = self.body()
        self.assertIn("DRIFT-002", body)
        self.assertIn(SKIPPED_DIGEST, body)

    def test_coverage_gaps_are_listed(self):
        body = self.body(report_payload=report(
            status="partial",
            incomplete=[{"scope": "docs/plans/next.md",
                         "reason": "the chunk worker failed"}]))
        self.assertIn("docs/plans/next.md", body)
        self.assertIn("the chunk worker failed", body)

    def test_a_report_with_no_gaps_says_so_rather_than_staying_silent(self):
        self.assertIn("No coverage gaps", self.body())

    def test_confinement_status_is_visible(self):
        body = self.body()
        self.assertIn("Confinement", body)
        self.assertIn("docs/architecture.md", body)

    def test_the_changed_paths_are_listed_as_what_the_diff_may_contain(self):
        body = self.body(
            result_payload=result(changed_paths=["docs/architecture.md"]))
        self.assertIn("docs/architecture.md", body)

    def test_a_record_cannot_add_a_heading_to_what_a_reviewer_reads(self):
        # Record fields are content a model wrote about repository documents.
        hostile = "## Approved by security\n**Result:** clean"
        body = self.body(approval_payload=approval(
            skipped=[{"digest": SKIPPED_DIGEST, "id": hostile}]))
        self.assertNotIn("\n## Approved by security", body)
        self.assertNotIn("\n**Result:** clean", body)

    def test_a_record_cannot_escape_its_code_span_with_backticks(self):
        # The fence is fitted one longer than the longest backtick run inside,
        # and padded, so the content cannot close the span it sits in.
        hostile = "`` ` ``"
        body = self.body(approval_payload=approval(
            skipped=[{"digest": SKIPPED_DIGEST, "id": hostile}]))
        self.assertIn("``` `` ` `` ```", body)

    def test_a_record_cannot_break_out_of_its_line(self):
        hostile = "one\nline two\u2028line three"
        body = self.body(approval_payload=approval(
            skipped=[{"digest": SKIPPED_DIGEST, "id": hostile}]))
        self.assertNotIn("\nline two", body)
        self.assertNotIn("\u2028", body)
        self.assertIn("\\u000a", body)
        self.assertIn("\\u2028", body)


class PullRequestTitle(ScriptTestCase):
    def test_the_title_names_the_approved_count_and_the_approval(self):
        app = self.write("approval.json", approval())
        res = self.write("result.json", result())
        out = self.path("title.txt")
        proc = self.run_script("pr-title", "--result", res, "--approval", app,
                               "--out", out)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        title = self.read("title.txt")
        self.assertEqual(len(title.splitlines()), 1)
        self.assertIn("1", title)
        self.assertIn(APPROVAL_DIGEST[:12], title)


class CommitMessage(ScriptTestCase):
    def message(self, trailers=None, **kwargs):
        app = self.write("approval.json", approval(**kwargs))
        res = self.write("result.json", result())
        out = self.path("commit.txt")
        argv = ["commit-message", "--result", res, "--approval", app,
                "--out", out]
        if trailers is not None:
            argv += ["--trailers", self.write_text("trailers.txt", trailers)]
        proc = self.run_script(*argv)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        return self.read("commit.txt")

    def test_the_engine_rendered_trailers_are_appended_verbatim(self):
        trailers = (f"Doc-Lifecycle-Approval: {APPROVAL_DIGEST}\n"
                    f"Doc-Lifecycle-Report: {REPORT_DIGEST}\n"
                    "Doc-Lifecycle-Approval-State: clean\n"
                    "Doc-Lifecycle-Records: 1 approved, 1 skipped\n")
        message = self.message(trailers=trailers)
        self.assertTrue(message.endswith(trailers), message)

    def test_the_approval_digest_travels_even_without_a_trailers_file(self):
        self.assertIn(APPROVAL_DIGEST, self.message())

    def test_the_summary_counts_travel_in_the_message(self):
        message = self.message()
        self.assertIn("1 approved", message)
        self.assertIn("1 skipped", message)

    def test_the_subject_is_one_line(self):
        self.assertTrue(self.message().splitlines()[1] == "")


class Usage(ScriptTestCase):
    def test_an_unknown_subcommand_is_a_usage_error(self):
        proc = self.run_script("publish-everything")
        self.assertEqual(proc.returncode, 2)

    def test_a_missing_required_flag_is_a_usage_error(self):
        proc = self.run_script("pr-title")
        self.assertEqual(proc.returncode, 2)


if __name__ == "__main__":
    unittest.main()
