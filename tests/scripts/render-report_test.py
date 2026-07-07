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


def brec(verdict, location=None, doc="README.md", evidence="seven lines carry one fact",
         status=None, files=None, rid="B1"):
    return {"id": rid, "doc": doc, "location": location, "verdict": verdict,
            "evidence": evidence, "proposal": None, "status": status, "files": files}


def run(*cmd):
    """Run a subprocess command and return the result."""
    return subprocess.run(cmd, capture_output=True, text=True)


class RenderReportTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.summary_path = os.path.join(self.tmp.name, "summary.md")

    def run_script(self, *argv, with_summary=True):
        """Run the script, handling $GITHUB_STEP_SUMMARY."""
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

    def test_pr_body_table_no_unverifiable_section(self):
        report = self.write_report([rec()])
        r = self.run_script("pr-body", "--report", report,
                            "--marker", "abc123", "--head", "def456")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("`abc123..def456` — merge to advance the marker", r.stdout)
        self.assertIn("| Fixed (see diff) | Why it was stale |", r.stdout)
        self.assertIn("| `README.md:5` | Makefile has `test:` |", r.stdout)
        self.assertNotIn("Flagged for a human", r.stdout)

    def test_pr_body_includes_unverifiable_table_when_present(self):
        report = self.write_report([
            rec(),
            rec(verdict="UNVERIFIABLE", location="docs/run.md:3",
                claim="deploy takes 5 minutes", evidence="no timing source"),
        ])
        r = self.run_script("pr-body", "--report", report,
                            "--marker", "abc123", "--head", "def456")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("| Flagged for a human — not edited | Why unverifiable |", r.stdout)
        self.assertIn("| `docs/run.md:3` | no timing source |", r.stdout)

    def test_pr_body_escapes_pipes_and_flattens_newlines_in_evidence(self):
        report = self.write_report([
            rec(evidence="pipe | in\nevidence"),
        ])
        r = self.run_script("pr-body", "--report", report,
                            "--marker", "abc123", "--head", "def456")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("| pipe \\| in evidence |", r.stdout)

    def test_pr_title_singular_plural_and_flagged(self):
        one = self.write_report([rec()])
        r = self.run_script("pr-title", "--report", one, "--date", "2026-07-03")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(r.stdout.strip(), "docs: nightly sync — 1 fix (2026-07-03)")

        many = self.write_report([rec(), rec(), rec(verdict="UNVERIFIABLE")])
        r = self.run_script("pr-title", "--report", many, "--date", "2026-07-03")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(r.stdout.strip(),
                         "docs: nightly sync — 2 fixes, 1 flagged (2026-07-03)")

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


def write_report(records):
    """Write a bloat report (filtered lane file) to a temp JSON file."""
    fd, path = tempfile.mkstemp(suffix=".json")
    with os.fdopen(fd, "w") as f:
        json.dump({"records": records}, f)
    return path


class BloatRender(unittest.TestCase):
    def test_pr_body_lists_each_record(self):
        report = write_report([brec("CUT", location="README.md:5"),
                               brec("CONDENSE", location="README.md:22")])
        out = run(sys.executable, SCRIPT, "bloat-pr-body", "--report", report)
        os.unlink(report)
        self.assertEqual(out.returncode, 0)
        self.assertIn("`CUT` @ `README.md:5`", out.stdout)
        self.assertIn("`CONDENSE` @ `README.md:22`", out.stdout)
        self.assertIn("| Change (see diff) | Why it's bloat |", out.stdout)

    def test_pr_body_uses_doc_when_location_null(self):
        report = write_report([brec("RETIRE-DOC", doc="docs/plans/old.md")])
        out = run(sys.executable, SCRIPT, "bloat-pr-body", "--report", report)
        os.unlink(report)
        self.assertIn("`RETIRE-DOC` @ `docs/plans/old.md`", out.stdout)

    def test_pr_body_distill_row_shows_status(self):
        ready = brec("DISTILL", doc="docs/plans/old.md", status="ready")
        report = write_report([ready])
        out = run(sys.executable, SCRIPT, "bloat-pr-body", "--report", report)
        os.unlink(report)
        self.assertIn("`DISTILL(ready)` @ `docs/plans/old.md`", out.stdout)

    def test_pr_body_policy_row_counts_files(self):
        rec = brec("POLICY", doc="docs/superpowers",
                   files=["docs/superpowers/plans/a.md",
                          "docs/superpowers/specs/b.md"])
        report = write_report([rec])
        out = run(sys.executable, SCRIPT, "bloat-pr-body", "--report", report)
        os.unlink(report)
        self.assertIn("`POLICY` @ `docs/superpowers` (2 files)", out.stdout)

    def test_pr_body_opens_with_rollup(self):
        report = write_report([
            brec("CUT", location="README.md:5"),
            brec("CONDENSE", location="README.md:22", rid="B2"),
            brec("POLICY", doc="docs/superpowers", rid="B3",
                 files=["docs/superpowers/plans/a.md"]),
        ])
        out = run(sys.executable, SCRIPT, "bloat-pr-body", "--report", report)
        os.unlink(report)
        self.assertIn("**Rollup:** 3 record(s) across 2 doc(s) — "
                      "cut 1, condense 1, policy 1", out.stdout)

    def test_triage_groups_by_doc_with_ids(self):
        report = write_report([
            brec("CUT", location="README.md:5"),
            brec("POLICY", doc="docs/superpowers", rid="B2",
                 files=["docs/superpowers/plans/a.md"]),
            brec("DISTILL", doc="docs/plans/old.md", status="ready", rid="B3"),
        ])
        out = run(sys.executable, SCRIPT, "bloat-triage", "--report", report)
        os.unlink(report)
        self.assertEqual(out.returncode, 0, out.stderr)
        self.assertIn("README.md", out.stdout)
        self.assertIn("[B1] CUT", out.stdout)
        self.assertIn("README.md:5", out.stdout)
        self.assertIn("[B2] POLICY", out.stdout)
        self.assertIn("(1 files)", out.stdout)
        self.assertIn("[B3] DISTILL(ready)", out.stdout)
        self.assertIn("**Rollup:**", out.stdout)
        self.assertNotIn("approve", out.stdout.lower())

    def test_pr_body_renders_unswept_banner_before_rollup(self):
        report = write_report([brec("CUT", location="README.md:5")])
        with open(report) as f:
            data = json.load(f)
        data["unswept"] = [
            {"chunk": "c-dead1", "docs": ["docs/plans/p.md", "docs/plans/q.md"]},
            {"chunk": "c-dead2", "docs": ["docs/guide.md"]},
        ]
        with open(report, "w") as f:
            json.dump(data, f)
        out = run(sys.executable, SCRIPT, "bloat-pr-body", "--report", report)
        os.unlink(report)
        self.assertEqual(out.returncode, 0, out.stderr)
        self.assertIn("2 chunk(s) unswept", out.stdout)
        self.assertIn("docs/plans/p.md", out.stdout)
        self.assertIn("docs/guide.md", out.stdout)
        self.assertIn("next sweep", out.stdout)
        self.assertLess(out.stdout.index("unswept"),
                        out.stdout.index("**Rollup:**"))

    def test_pr_body_no_banner_when_complete(self):
        report = write_report([brec("CUT", location="README.md:5")])
        out = run(sys.executable, SCRIPT, "bloat-pr-body", "--report", report)
        os.unlink(report)
        self.assertNotIn("unswept", out.stdout)

    def test_triage_renders_unswept_banner(self):
        report = write_report([brec("CUT", location="README.md:5")])
        with open(report) as f:
            data = json.load(f)
        data["unswept"] = [{"chunk": "c-dead1", "docs": ["docs/plans/p.md"]}]
        with open(report, "w") as f:
            json.dump(data, f)
        out = run(sys.executable, SCRIPT, "bloat-triage", "--report", report)
        os.unlink(report)
        self.assertEqual(out.returncode, 0, out.stderr)
        self.assertIn("1 chunk(s) unswept", out.stdout)
        self.assertIn("docs/plans/p.md", out.stdout)

    def test_unswept_summary_writes_gap_state(self):
        report = write_report([])
        with open(report) as f:
            data = json.load(f)
        data["unswept"] = [{"chunk": "c-dead1", "docs": ["docs/plans/p.md"]}]
        with open(report, "w") as f:
            json.dump(data, f)
        out = run(sys.executable, SCRIPT, "bloat-unswept-summary",
                  "--report", report)
        os.unlink(report)
        self.assertEqual(out.returncode, 0, out.stderr)
        self.assertIn("1 chunk(s) unswept", out.stdout)
        self.assertIn("docs/plans/p.md", out.stdout)
        self.assertIn("next sweep", out.stdout)

    def test_unswept_summary_silent_when_complete(self):
        report = write_report([brec("CUT", location="README.md:5")])
        out = run(sys.executable, SCRIPT, "bloat-unswept-summary",
                  "--report", report)
        os.unlink(report)
        self.assertEqual(out.returncode, 0, out.stderr)
        self.assertEqual(out.stdout.strip(), "")

    def test_triage_missing_report_exits_2(self):
        out = run(sys.executable, SCRIPT, "bloat-triage",
                  "--report", "/nonexistent.json")
        self.assertEqual(out.returncode, 2)

    def test_pr_body_escapes_pipe(self):
        report = write_report([brec("CUT", location="README.md:5", evidence="a | b")])
        out = run(sys.executable, SCRIPT, "bloat-pr-body", "--report", report)
        os.unlink(report)
        self.assertIn("a \\| b", out.stdout)

    def test_pr_title_pluralizes(self):
        one = write_report([brec("CUT", location="a:1")])
        many = write_report([brec("CUT", location="a:1"), brec("CUT", location="a:2")])
        t1 = run(sys.executable, SCRIPT, "bloat-pr-title", "--report", one, "--lane", "prune", "--date", "2026-07-03")
        tm = run(sys.executable, SCRIPT, "bloat-pr-title", "--report", many, "--lane", "prune", "--date", "2026-07-03")
        os.unlink(one); os.unlink(many)
        self.assertEqual(t1.stdout.strip(), "docs: bloat prune — 1 change (2026-07-03)")
        self.assertEqual(tm.stdout.strip(), "docs: bloat prune — 2 changes (2026-07-03)")

    def test_skip_summary_known_reasons(self):
        for reason in ("skip-empty", "skip-pending", "skip-noop"):
            out = run(sys.executable, SCRIPT, "bloat-skip-summary", "--lane", "distill", "--reason", reason)
            self.assertEqual(out.returncode, 0)

    def test_skip_summary_rejects_unknown_reason(self):
        out = run(sys.executable, SCRIPT, "bloat-skip-summary", "--lane", "prune", "--reason", "bogus")
        self.assertEqual(out.returncode, 2)

    def test_pre_summary_known_decisions(self):
        for d in ("detect", "skip-pending"):
            out = run(sys.executable, SCRIPT, "bloat-pre-summary", "--decision", d)
            self.assertEqual(out.returncode, 0)


class WorkflowWiring(unittest.TestCase):
    """Pins doc-bloat.yml's harness wiring: the deterministic resume-aware
    plan job, script-rendered dispatch payloads under planner-computed turn
    budgets, per-chunk seam validation with a classified retry, and
    gap-tolerant assembly. The YAML stays an allowlist-thin shell; these
    strings are its contract with the unit-tested scripts."""

    @classmethod
    def setUpClass(cls):
        path = os.path.join(
            os.path.dirname(__file__), "..", "..",
            "plugins", "doc-lifecycle", "skills", "scheduling-doc-sync",
            "doc-bloat.yml")
        with open(path, encoding="utf-8") as f:
            cls.yml = f.read()

    def test_plan_job_resumes_prior_results(self):
        self.assertIn("plan-chunks.py --out manifest.json --results-dir chunks",
                      self.yml)
        self.assertIn("--pattern 'bloat-chunk*'", self.yml)

    def test_chunks_seam_validated_in_job(self):
        self.assertIn('--chunk "chunks/${CHUNK_ID}.json" --manifest manifest.json',
                      self.yml)

    def test_assembly_tolerates_gaps_and_surfaces_them(self):
        self.assertIn("--assemble chunks --manifest manifest.json", self.yml)
        self.assertIn("--allow-partial", self.yml)
        self.assertIn("bloat-unswept-summary", self.yml)

    def test_dispatch_is_script_rendered_with_planner_budget(self):
        self.assertIn("--emit-prompt", self.yml)
        self.assertIn("--emit-turns", self.yml)
        self.assertIn("--max-turns ${{ steps.slice.outputs.turns }}", self.yml)
        self.assertNotIn("--max-turns 15", self.yml)

    def test_executor_can_invoke_its_skill(self):
        self.assertIn('"Skill,Read', self.yml)

    def test_retry_is_classified_and_uses_escalated_budget(self):
        self.assertIn("sync-gate.py bloat-retry", self.yml)
        self.assertIn("--max-turns ${{ steps.retry.outputs.turns }}", self.yml)

    def test_double_failure_discards_invalid_result_before_exit(self):
        # A leftover invalid result would fail gap-tolerant assembly (which
        # tolerates only MISSING chunks) and mask the chunk as done on resume.
        self.assertIn('|| { rm -f "chunks/${CHUNK_ID}.json"; echo "::error::chunk',
                      self.yml)

    def test_fully_resumed_run_still_assembles(self):
        # assemble must NOT carry sweep's pending-empty guard, or an
        # all-carried run silently produces nothing forever.
        sweep_if = "needs.plan.outputs.decision == 'detect' && needs.plan.outputs.pending != '[]'"
        self.assertIn(sweep_if, self.yml)          # sweep keeps the guard
        assemble_if = "always() && needs.plan.outputs.decision == 'detect'"
        self.assertIn(assemble_if, self.yml)
        self.assertNotIn("always() && needs.plan.outputs.decision == 'detect' "
                         "&& needs.plan.outputs.pending", self.yml)

    def test_matrix_does_not_fail_fast(self):
        self.assertIn("fail-fast: false", self.yml)

    def test_distill_lane_covers_policy_and_keeps_task(self):
        self.assertIn("RETIRE-DOC, or POLICY", self.yml)
        self.assertIn('"Task,Read', self.yml)


if __name__ == "__main__":
    unittest.main(verbosity=1)
