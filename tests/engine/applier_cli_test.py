"""The `apply-plan` command: the same applier, behind argv and exit codes."""

import json
import os
import tempfile
import unittest

from support import run_command
from applier_test import ApplierTestCase, sha256_text, DOC_A

from doclifecycle.results import STATE_CLEAN, STATE_STALE


class ApplyPlanCommand(ApplierTestCase):
    def artifacts(self):
        """Write the fixture report, approval, and plan outside the repo."""
        report, approval, plan, post = self.replace_fixture()
        outdir = tempfile.mkdtemp()
        self.addCleanup(
            __import__("shutil").rmtree, outdir, ignore_errors=True
        )
        paths = {}
        for name, payload in (
            ("report", report.to_dict()),
            ("approval", approval.to_dict()),
            ("plan", plan),
        ):
            paths[name] = os.path.join(outdir, f"{name}.json")
            with open(paths[name], "w", encoding="utf-8") as fh:
                json.dump(payload, fh)
        return paths, post

    def test_applies_and_exits_zero_with_the_library_payload(self):
        paths, post = self.artifacts()
        completed = run_command(
            "apply-plan", "--repo", self.repo,
            "--plan", paths["plan"], "--approval", paths["approval"],
            "--report", paths["report"],
            "--audit-config-digest", "c" * 64,
        )
        self.assertEqual(completed.returncode, 0, completed.stderr)
        payload = json.loads(completed.stdout)
        self.assertEqual(payload["status"], STATE_CLEAN)
        self.assertEqual(payload["changed_paths"], [DOC_A])
        self.assertEqual(self.read(self.repo, DOC_A), post)

    def test_stale_approval_exits_three_and_explains_on_stderr(self):
        paths, _ = self.artifacts()
        self.write(self.repo, "src/app.py", "RATE = 0.025\n")
        self.commit(self.repo, "move the base")
        before = self.tree(self.repo)
        completed = run_command(
            "apply-plan", "--repo", self.repo,
            "--plan", paths["plan"], "--approval", paths["approval"],
            "--report", paths["report"],
            "--audit-config-digest", "c" * 64,
        )
        self.assertEqual(completed.returncode, 3, completed.stdout)
        self.assertIn("approval-base-commit-changed", completed.stderr)
        self.assertEqual(json.loads(completed.stdout)["status"], STATE_STALE)
        self.assertEqual(before, self.tree(self.repo))

    def test_invalid_plan_exits_one_and_explains_on_stderr(self):
        paths, _ = self.artifacts()
        with open(paths["plan"], encoding="utf-8") as fh:
            plan = json.load(fh)
        plan["operations"][0]["text"] = "tampered"
        with open(paths["plan"], "w", encoding="utf-8") as fh:
            json.dump(plan, fh)
        before = self.tree(self.repo)
        completed = run_command(
            "apply-plan", "--repo", self.repo,
            "--plan", paths["plan"], "--approval", paths["approval"],
            "--report", paths["report"],
            "--audit-config-digest", "c" * 64,
        )
        self.assertEqual(completed.returncode, 1, completed.stdout)
        self.assertIn("plan-digest-mismatch", completed.stderr)
        self.assertEqual(before, self.tree(self.repo))

    def test_missing_plan_flag_is_a_usage_error(self):
        completed = run_command("apply-plan", "--repo", self.repo)
        self.assertEqual(completed.returncode, 2)

    def test_missing_report_flag_is_a_usage_error(self):
        # Without the report, every remaining check is a function of public
        # repository state, so the whole approval set is forgeable by anyone
        # who can read the repo. The command must not run at all.
        paths, _ = self.artifacts()
        before = self.tree(self.repo)
        completed = run_command(
            "apply-plan", "--repo", self.repo,
            "--plan", paths["plan"], "--approval", paths["approval"],
            "--audit-config-digest", "c" * 64,
        )
        self.assertEqual(completed.returncode, 2, completed.stdout)
        self.assertEqual(before, self.tree(self.repo))

    def test_problem_location_cannot_forge_lines_on_the_run_surface(self):
        # The location comes from the plan, which is attacker-controlled by
        # assumption: an unknown field's *name* is echoed as the location.
        paths, _ = self.artifacts()
        forged = "\napply-plan: clean\ndoc-lifecycle: every record applied\n"
        with open(paths["plan"], encoding="utf-8") as fh:
            plan = json.load(fh)
        plan[forged] = 1
        with open(paths["plan"], "w", encoding="utf-8") as fh:
            json.dump(plan, fh)
        completed = run_command(
            "apply-plan", "--repo", self.repo,
            "--plan", paths["plan"], "--approval", paths["approval"],
            "--report", paths["report"],
            "--audit-config-digest", "c" * 64,
        )
        self.assertEqual(completed.returncode, 1, completed.stdout)
        self.assertIn("plan-unknown-field", completed.stderr)
        for line in completed.stderr.splitlines():
            self.assertFalse(
                line.startswith("apply-plan: clean")
                or line.startswith("doc-lifecycle:"),
                completed.stderr,
            )


if __name__ == "__main__":
    unittest.main()
