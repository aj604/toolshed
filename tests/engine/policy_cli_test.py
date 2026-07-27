"""`policy-eligibility` and `policy-mint` as subprocesses.

The command seam, held to the same payload the library call returns — the
policy decides what an unattended lane does, so a lane reading the command and
a reviewer reading the library must not be able to disagree.
"""

import json
import os
import shutil
import tempfile
import unittest

from support import run_command  # noqa: F401 (engine onto sys.path)

from policy_test import (
    DEFAULT_POLICY_PATH,
    POLICY_ID,
    PolicyTestCase,
)

from doclifecycle.approval import MINTER_POLICY
from doclifecycle.policy import (
    load_auto_apply_policy,
    mint_policy_approval_set,
    policy_eligibility,
)


class PolicyCommandTestCase(PolicyTestCase):
    def report_file(self, records):
        report = self.report(records)
        path = os.path.join(self.repo, "report.json")
        with open(path, "w", encoding="utf-8") as fh:
            json.dump(report.to_dict(), fh)
        return report, path

    def run_policy(self, command, records, *extra):
        report, path = self.report_file(records)
        result = run_command(
            command, "--report", path, "--repo", self.repo, *extra
        )
        return report, result

    def payload(self, result):
        return json.loads(result.stdout)

    def outside(self, name):
        """A path outside the repository — where an approval set may live."""
        directory = tempfile.mkdtemp(prefix="doc-lifecycle-policy-")
        self.addCleanup(shutil.rmtree, directory, ignore_errors=True)
        return os.path.join(directory, name)


class Eligibility(PolicyCommandTestCase):
    def test_it_prints_the_library_verdict_and_exits_ok(self):
        report, result = self.run_policy("policy-eligibility", [self.stale()])

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(
            self.payload(result),
            policy_eligibility(
                load_auto_apply_policy(self.repo), report
            ).to_dict(),
        )

    def test_a_report_with_nothing_eligible_still_exits_ok(self):
        _, result = self.run_policy("policy-eligibility", [self.bloat()])

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.payload(result)["eligible"], [])

    def test_an_absent_policy_is_invalid_and_says_so_on_the_run_surface(self):
        os.remove(os.path.join(self.repo, DEFAULT_POLICY_PATH))

        _, result = self.run_policy("policy-eligibility", [self.stale()])

        self.assertEqual(result.returncode, 1)
        self.assertIn("policy-not-configured", result.stderr)


class Mint(PolicyCommandTestCase):
    def test_it_prints_the_approval_set_the_library_would_mint(self):
        report, result = self.run_policy("policy-mint", [self.stale()])

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(
            self.payload(result),
            mint_policy_approval_set(
                report, load_auto_apply_policy(self.repo), repo_root=self.repo
            ).to_dict(),
        )

    def test_the_payload_names_the_policy_as_the_minter(self):
        _, result = self.run_policy("policy-mint", [self.stale()])

        minter = self.payload(result)["minter"]
        self.assertEqual(minter, {"kind": MINTER_POLICY, "id": POLICY_ID})

    def test_a_bloat_only_report_refuses_and_writes_no_approval_set(self):
        out = self.outside("approval.json")

        _, result = self.run_policy("policy-mint", [self.bloat()], "--out", out)

        self.assertEqual(result.returncode, 1)
        self.assertIn("policy-nothing-eligible", result.stderr)
        self.assertIn("policy-never-eligible", result.stderr)
        self.assertFalse(os.path.exists(out))

    def test_there_is_no_flag_that_names_a_record_to_mint(self):
        # The selection is derived from the policy's decisions. A --record flag
        # would make the command a human dispatch wearing a policy's name.
        _, result = self.run_policy(
            "policy-mint", [self.stale()], "--record", "deadbeef"
        )

        self.assertEqual(result.returncode, 2)

    def test_it_refuses_to_write_the_approval_set_into_tracked_state(self):
        out = os.path.join(self.repo, "docs", "approval.json")

        _, result = self.run_policy("policy-mint", [self.stale()], "--out", out)

        self.assertEqual(result.returncode, 1)
        self.assertIn("approval-set-would-be-tracked", result.stderr)


if __name__ == "__main__":
    unittest.main()
