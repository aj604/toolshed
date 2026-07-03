#!/usr/bin/env python3
"""Black-box tests for scheduling-doc-sync's render-report.py.

Tests the script as a subprocess: real argv, real exit codes, real stdout, and a
real $GITHUB_STEP_SUMMARY file for the summary subcommands.
Run: python3 tests/scripts/render-report_test.py
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
    "scripts", "render-report.py",
)


def rec(verdict="STALE", location="README.md:5", claim="README mentions make test",
        evidence="Makefile has `test:`", fix="say `make check`"):
    return {
        "claim": claim,
        "location": location,
        "kind": "command",
        "tier": 1,
        "verdict": verdict,
        "evidence": evidence,
        "fix": fix,
    }


class RenderReportTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.summary_path = os.path.join(self.tmp.name, "summary.md")

    def run_script(self, *argv, with_summary=True):
        env = dict(os.environ)
        if with_summary:
            env["GITHUB_STEP_SUMMARY"] = self.summary_path
        else:
            env.pop("GITHUB_STEP_SUMMARY", None)
        return subprocess.run(
            [sys.executable, SCRIPT, *argv],
            capture_output=True, text=True, env=env,
        )

    def write_report(self, records):
        path = os.path.join(self.tmp.name, "drift-report.json")
        with open(path, "w", encoding="utf-8") as f:
            json.dump({"records": records, "summary": {}}, f)
        return path

    def summary(self):
        with open(self.summary_path, encoding="utf-8") as f:
            return f.read()

    # -- pre-summary ------------------------------------------------------

    def pre_args(self, decision, **over):
        d = {"marker": "abc123", "head": "def456", "commits": "3",
             "open_prs": "0", "open_issues": "0"}
        d.update(over)
        return ["pre-summary", "--decision", decision,
                "--marker", d["marker"], "--head", d["head"],
                "--commits", d["commits"], "--open-prs", d["open_prs"],
                "--open-issues", d["open_issues"]]

    def test_pre_skip_empty_writes_notice_and_summary(self):
        r = self.run_script(*self.pre_args("skip-empty", commits="0"))
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("::notice::doc-sync skipped: nothing new since the marker", r.stdout)
        self.assertIn("Skipped — nothing to sync.", self.summary())
        self.assertIn("`abc123`", self.summary())

    def test_pre_skip_pending_reports_counts(self):
        r = self.run_script(*self.pre_args("skip-pending", open_prs="1", open_issues="2"))
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("::notice::", r.stdout)
        self.assertIn("Open doc-sync PRs: 1", self.summary())
        self.assertIn("issues: 2", self.summary())

    def test_pre_detect_reports_range_no_notice(self):
        r = self.run_script(*self.pre_args("detect"))
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertNotIn("::notice::", r.stdout)
        self.assertIn("**Checking 3 commit(s)**", self.summary())
        self.assertIn("`abc123..def456`", self.summary())

    def test_pre_unknown_decision_exits_2(self):
        r = self.run_script(*self.pre_args("bogus"))
        self.assertEqual(r.returncode, 2)
        self.assertIn("unknown pre-gate decision", r.stderr)

    def test_summary_falls_back_to_stdout_without_env(self):
        r = self.run_script(*self.pre_args("detect"), with_summary=False)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("**Checking 3 commit(s)**", r.stdout)

    # -- no-drift-summary --------------------------------------------------

    def test_no_drift_advanced(self):
        r = self.run_script("no-drift-summary", "--commits", "4", "--head", "def456")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertNotIn("::notice::", r.stdout)
        self.assertIn("**No drift.**", self.summary())
        self.assertIn("marker advanced to `def456`", self.summary())

    def test_no_drift_push_rejected(self):
        r = self.run_script("no-drift-summary", "--commits", "4", "--head", "def456",
                            "--push-rejected")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("::notice::marker push rejected", r.stdout)
        self.assertIn("push was rejected (branch protection?)", self.summary())

    # -- issue-body / blast-summary ----------------------------------------

    def test_issue_body_renders_stale_only(self):
        report = self.write_report([
            rec(verdict="STALE", location="README.md:5"),
            rec(verdict="VERIFIED", location="README.md:9"),
            rec(verdict="STALE", location="CLAUDE.md:2", fix="drop the flag"),
        ])
        r = self.run_script("issue-body", "--report", report, "--cap", "10",
                            "--marker", "abc123", "--head", "def456")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("blast-radius cap (10)", r.stdout)
        self.assertIn("`abc123..def456`", r.stdout)
        self.assertIn("- `README.md:5`", r.stdout)
        self.assertIn("**drafted fix:** drop the flag", r.stdout)
        self.assertNotIn("README.md:9", r.stdout)

    def test_blast_summary_counts_stale(self):
        report = self.write_report([rec(), rec(), rec(verdict="VERIFIED")])
        r = self.run_script("blast-summary", "--report", report, "--cap", "1",
                            "--issue-url", "https://github.com/x/y/issues/7")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("2 stale claims exceed the cap (1)", self.summary())
        self.assertIn("issues/7", self.summary())

    # -- pr-body / pr-summary ----------------------------------------------

    def test_pr_body_applied_fixes_no_unverifiable_section(self):
        report = self.write_report([rec()])
        r = self.run_script("pr-body", "--report", report,
                            "--marker", "abc123", "--head", "def456")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("## Applied fixes (STALE)", r.stdout)
        self.assertIn("**applied fix:**", r.stdout)
        self.assertNotIn("Flagged for a human", r.stdout)

    def test_pr_body_includes_unverifiable_section_when_present(self):
        report = self.write_report([
            rec(),
            rec(verdict="UNVERIFIABLE", location="docs/run.md:3",
                claim="deploy takes 5 minutes", evidence="no timing source"),
        ])
        r = self.run_script("pr-body", "--report", report,
                            "--marker", "abc123", "--head", "def456")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("## Flagged for a human (UNVERIFIABLE — not edited)", r.stdout)
        self.assertIn("- `docs/run.md:3` — deploy takes 5 minutes (no timing source)", r.stdout)

    def test_pr_summary_counts_and_url(self):
        report = self.write_report([rec(), rec(verdict="UNVERIFIABLE")])
        r = self.run_script("pr-summary", "--report", report,
                            "--pr-url", "https://github.com/x/y/pull/12")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("1 stale claim(s) corrected", self.summary())
        self.assertIn("pull/12", self.summary())

    # -- error paths ---------------------------------------------------------

    def test_missing_report_exits_2(self):
        r = self.run_script("pr-body", "--report", "/nonexistent.json",
                            "--marker", "a", "--head", "b")
        self.assertEqual(r.returncode, 2)
        self.assertIn("error:", r.stderr)

    def test_record_missing_field_exits_2(self):
        broken = self.write_report([{"verdict": "STALE", "location": "x"}])  # no claim/fix
        r = self.run_script("pr-body", "--report", broken,
                            "--marker", "a", "--head", "b")
        self.assertEqual(r.returncode, 2)
        self.assertIn("error:", r.stderr)


if __name__ == "__main__":
    unittest.main(verbosity=1)
