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
    DOC_A,
    DOC_B,
    POLICY_ID,
    PolicyTestCase,
    resigned,
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
        self.assertEqual(minter["kind"], MINTER_POLICY)
        self.assertEqual(minter["id"], POLICY_ID)

    def test_the_payload_carries_the_declarations_digest_as_provenance(self):
        # What makes the brand checkable rather than descriptive: a reader with
        # the repository can reload the declaration and derive the selection
        # again from it.
        _, result = self.run_policy("policy-mint", [self.stale()])

        self.assertEqual(
            self.payload(result)["minter"]["policy_digest"],
            load_auto_apply_policy(self.repo).digest,
        )

    def test_it_derives_the_exact_eligible_set_from_the_declaration(self):
        # The other half of the same criterion: the command selects every
        # record the standing declaration admits and nothing else, with no
        # flag through which a caller could have said so.
        stale, bloat = self.stale(), self.bloat()
        report, result = self.run_policy("policy-mint", [stale, bloat])

        eligible = policy_eligibility(
            load_auto_apply_policy(self.repo), report
        ).eligible_digests
        self.assertEqual([r["digest"] for r in self.payload(result)["records"]],
                         list(eligible))
        self.assertEqual([r["digest"] for r in self.payload(result)["skipped"]],
                         [bloat["digest"]])

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


class ValidateABrandedSet(PolicyCommandTestCase):
    """`validate-approval` as a subprocess: the route the applier's lane takes.

    The provenance revalidation has to hold at the command seam too — a lane
    reads the exit code, and a branded artifact nobody can trace to the
    standing declaration must not be one of the codes that means "apply this".
    """

    def branded(self, records):
        """`(report path, approval path)` for a real policy mint."""
        report, report_path = self.report_file(records)
        approval = mint_policy_approval_set(
            report, load_auto_apply_policy(self.repo), repo_root=self.repo
        )
        return report, report_path, approval

    def written(self, payload):
        path = self.outside("approval.json")
        with open(path, "w", encoding="utf-8") as fh:
            json.dump(payload, fh)
        return path

    def validate(self, approval_path, report_path):
        return run_command(
            "validate-approval", "--approval", approval_path,
            "--report", report_path, "--repo", self.repo,
        )

    def test_a_policy_minted_set_validates_clean(self):
        _, report_path, approval = self.branded([self.stale()])

        result = self.validate(self.written(approval.to_dict()), report_path)

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout)["status"], "clean")

    def test_a_brand_the_declaration_does_not_derive_is_refused(self):
        # The forgery a text editor produces: an honest mint, one record
        # dropped from the selection, and the file re-signed.
        stale, other = self.stale(), self.stale("R-8", path=DOC_B)
        _, report_path, approval = self.branded([stale, other])
        payload = approval.to_dict()
        payload["records"] = [
            r for r in payload["records"] if r["digest"] == stale["digest"]
        ]
        payload["skipped"] = sorted(
            payload["skipped"] + [{"digest": other["digest"], "id": "R-8"}],
            key=lambda entry: entry["digest"],
        )
        payload["scope"]["paths"] = [DOC_A]

        result = self.validate(
            self.written(resigned(payload)), report_path
        )

        self.assertEqual(result.returncode, 1)
        self.assertIn("approval-policy-selection-not-derived", result.stderr)

    def test_a_declaration_that_moved_is_reported_stale(self):
        _, report_path, approval = self.branded([self.stale()])
        self.write(self.repo, DEFAULT_POLICY_PATH, json.dumps({
            "artifact": "auto-apply-policy", "schema_version": 1,
            "id": POLICY_ID, "classes": ["narrative-anchor-refresh"],
        }))

        result = self.validate(self.written(approval.to_dict()), report_path)

        self.assertEqual(result.returncode, 3)
        self.assertIn("approval-policy-changed", result.stderr)


if __name__ == "__main__":
    unittest.main()
