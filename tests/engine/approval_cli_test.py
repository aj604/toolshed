#!/usr/bin/env python3
"""Tests for the approval commands.

Seam: `python3 -m doclifecycle` as a subprocess. The commands must hand back
exactly what the library returns — the payload byte-for-byte and the result
state as the exit code — so a person minting an approval set at a terminal and
a workflow doing it cannot reach different answers. The behavior itself is
`approval_test.py`'s and `reconcile_test.py`'s.

Run: python3 tests/engine/approval_cli_test.py
"""

import json
import os
import sys
import unittest
from dataclasses import replace

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from approval_test import (  # noqa: E402
    CONFIG_DIGEST,
    DOC_A,
    ApprovalTestCase,
)
from support import run_command  # noqa: E402

from doclifecycle.approval import (  # noqa: E402
    ARTIFACT_KIND,
    Minter,
    mint_approval_set,
)
from doclifecycle.reconcile import reconcile  # noqa: E402
from doclifecycle.render import render_approval_set  # noqa: E402
from doclifecycle.results import STATE_CLEAN, STATE_STALE  # noqa: E402

EXIT_OK = 0
EXIT_INVALID = 1
EXIT_USAGE = 2
EXIT_STALE = 3


class ApprovalCommandTestCase(ApprovalTestCase):
    def setUp(self):
        super().setUp()
        self.one, self.two = self.two_findings()
        self.source = self.report([self.one, self.two])
        self.report_path = self.json_file("report.json", self.source.to_dict())

    def json_file(self, name, payload):
        # Outside the repository: an approval set may not be written into the
        # work tree, and the report file keeps it company rather than making
        # the fixture repository dirty.
        path = os.path.join(self.repo, "..", name)
        with open(path, "w", encoding="utf-8") as fh:
            json.dump(payload, fh)
        self.addCleanup(lambda: os.path.exists(path) and os.remove(path))
        return path

    def mint_command(self, *extra, records=()):
        argv = ["mint-approval", "--report", self.report_path,
                "--repo", self.repo, "--minter", "avery@example.com",
                "--audit-config-digest", CONFIG_DIGEST]
        for digest in records:
            argv += ["--record", digest]
        return run_command(*argv, *extra)


class ReconcileCommand(ApprovalCommandTestCase):
    def test_it_emits_exactly_what_the_library_returns(self):
        result = run_command("reconcile-report", "--report", self.report_path,
                             "--repo", self.repo,
                             "--audit-config-digest", CONFIG_DIGEST)

        self.assertEqual(result.returncode, EXIT_OK, result.stderr)
        self.assertEqual(
            json.loads(result.stdout), reconcile(self.source).to_dict()
        )

    def test_an_unreadable_report_is_invalid(self):
        result = run_command("reconcile-report", "--report", "nowhere.json")

        self.assertEqual(result.returncode, EXIT_INVALID)
        self.assertIn("report-unreadable", result.stderr)


class MintCommand(ApprovalCommandTestCase):
    def test_it_mints_the_named_subset(self):
        result = self.mint_command(records=[self.one["digest"]])

        self.assertEqual(result.returncode, EXIT_OK, result.stderr)
        payload = json.loads(result.stdout)
        self.assertEqual(payload["artifact"], ARTIFACT_KIND)
        self.assertEqual([r["digest"] for r in payload["records"]],
                         [self.one["digest"]])
        self.assertEqual([r["id"] for r in payload["skipped"]], ["R-2"])

    def test_it_emits_exactly_what_the_library_returns(self):
        result = self.mint_command(records=[self.one["digest"]])

        expected = mint_approval_set(
            self.source, [self.one["digest"]], repo_root=self.repo,
            minter=Minter(kind="human", id="avery@example.com"),
        )
        self.assertEqual(json.loads(result.stdout), expected.to_dict())

    def test_a_record_the_report_does_not_carry_is_invalid(self):
        result = self.mint_command(records=["f" * 64])

        self.assertEqual(result.returncode, EXIT_INVALID)
        self.assertIn("approval-unknown-record", result.stderr)

    def test_selecting_no_records_is_a_usage_error(self):
        result = self.mint_command()

        self.assertEqual(result.returncode, EXIT_USAGE)

    def test_a_policy_may_be_named_as_the_minter(self):
        result = self.mint_command(
            "--minter-kind", "policy", records=[self.one["digest"]]
        )

        self.assertEqual(json.loads(result.stdout)["minter"],
                         {"kind": "policy", "id": "avery@example.com"})

    def test_a_policy_brand_on_a_bloat_record_is_refused(self):
        # The generic door, from the CLI seam: a policy minter can never
        # select a bloat record, whichever way the caller reaches minting.
        unit = self.units(self.repo, DOC_A)[0]
        cut = self.finding("R-1", "CUT", DOC_A, [unit])
        report_path = self.json_file("cut-report.json", self.report([cut]).to_dict())

        result = run_command(
            "mint-approval", "--report", report_path, "--repo", self.repo,
            "--minter", "nightly-policy", "--minter-kind", "policy",
            "--audit-config-digest", CONFIG_DIGEST, "--record", cut["digest"],
        )

        self.assertEqual(result.returncode, EXIT_INVALID)
        self.assertIn("approval-policy-ineligible-record", result.stderr)

    def test_an_unknown_minter_kind_is_a_usage_error(self):
        result = self.mint_command(
            "--minter-kind", "the-workflow", records=[self.one["digest"]]
        )

        self.assertEqual(result.returncode, EXIT_USAGE)

    def test_it_writes_the_artifact_where_it_is_told(self):
        target = os.path.join(self.repo, "..", "approval.json")
        self.addCleanup(lambda: os.path.exists(target) and os.remove(target))

        result = self.mint_command("--out", target, records=[self.one["digest"]])

        self.assertEqual(result.returncode, EXIT_OK, result.stderr)
        with open(target, encoding="utf-8") as fh:
            self.assertEqual(json.load(fh)["digest"],
                             json.loads(result.stdout)["digest"])

    def test_it_refuses_to_write_the_artifact_into_the_repository(self):
        target = os.path.join(self.repo, "docs", "approval.json")

        result = self.mint_command("--out", target, records=[self.one["digest"]])

        self.assertEqual(result.returncode, EXIT_INVALID)
        self.assertIn("approval-set-would-be-tracked", result.stderr)
        self.assertFalse(os.path.exists(target))


class ValidateCommand(ApprovalCommandTestCase):
    def setUp(self):
        super().setUp()
        approval = mint_approval_set(
            self.source, [self.one["digest"]], repo_root=self.repo,
            minter=Minter(kind="human", id="avery@example.com"),
        )
        self.approval = approval
        self.approval_path = self.json_file("approval.json", approval.to_dict())

    def validate(self, *extra):
        return run_command("validate-approval", "--approval", self.approval_path,
                           *extra)

    def test_a_live_approval_set_exits_zero(self):
        result = self.validate("--repo", self.repo, "--report", self.report_path,
                               "--audit-config-digest", CONFIG_DIGEST)

        self.assertEqual(result.returncode, EXIT_OK, result.stderr)
        self.assertEqual(json.loads(result.stdout)["status"], STATE_CLEAN)

    def test_a_stale_approval_set_exits_three_and_says_why(self):
        self.write(self.repo, DOC_A, "# Fees\n\nSomething else entirely.\n")

        result = self.validate("--repo", self.repo)

        self.assertEqual(result.returncode, EXIT_STALE)
        self.assertEqual(json.loads(result.stdout)["status"], STATE_STALE)
        self.assertIn("approval-preimage-mismatch", result.stderr)

    def test_a_report_handed_in_where_an_approval_set_belongs_is_invalid(self):
        result = run_command("validate-approval", "--approval", self.report_path)

        self.assertEqual(result.returncode, EXIT_INVALID)
        self.assertIn("approval-not-an-approval-set", result.stderr)

    def test_it_renders_the_summary_that_travels_with_the_change(self):
        result = run_command(
            "render-approval", "--approval", self.approval_path,
            "--repo", self.repo, "--report", self.report_path,
            "--audit-config-digest", CONFIG_DIGEST,
        )

        self.assertEqual(result.returncode, EXIT_OK, result.stderr)
        self.assertEqual(
            result.stdout.rstrip("\n"),
            # The command renders what validation returned, which carries the
            # report's state as the run observed it — the minted artifact has
            # not been shown a report.
            render_approval_set(replace(
                self.approval, observed_report_state=self.source.status
            )),
        )

    def test_a_render_without_the_report_or_the_repository_says_so(self):
        # A reduced-input verdict must not read as a full one: the summary is
        # what a change reviewer sees, and `clean` from a structural pass is
        # not the same claim.
        result = run_command("render-approval", "--approval", self.approval_path)

        self.assertEqual(result.returncode, EXIT_OK, result.stderr)
        self.assertIn("## Not checked", result.stdout)
        self.assertIn("no report was supplied", result.stdout)
        self.assertIn("no repository was supplied", result.stdout)

    def test_a_file_the_trailer_does_not_name_is_refused(self):
        result = self.validate("--expected-digest", "b" * 64)

        self.assertEqual(result.returncode, EXIT_INVALID)
        self.assertIn("approval-digest-unexpected", result.stderr)

    def test_an_invalid_approval_set_renders_nothing(self):
        result = run_command("render-approval", "--approval", self.report_path)

        self.assertEqual(result.returncode, EXIT_INVALID)
        self.assertEqual(result.stdout, "")

    def test_the_trailers_are_available_for_a_commit_message(self):
        result = run_command("render-approval", "--approval", self.approval_path,
                             "--trailers")

        self.assertEqual(result.returncode, EXIT_OK, result.stderr)
        self.assertIn(f"Doc-Lifecycle-Approval: {self.approval.digest}",
                      result.stdout)


if __name__ == "__main__":
    unittest.main()
