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
        self.assertIn("`abc123..def456`", r.stdout)
        self.assertIn("advance the marker", r.stdout)
        self.assertIn("### ✅ Fixed — 1 stale claim(s)", r.stdout)
        self.assertIn("- **`README.md:5`** — Makefile has `test:`", r.stdout)
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
        self.assertIn("### 🔍 Flagged for a human — 1 unverifiable claim(s), not edited",
                      r.stdout)
        self.assertIn("- **`docs/run.md:3`** — no timing source", r.stdout)

    def test_pr_body_escapes_pipes_and_flattens_newlines_in_evidence(self):
        report = self.write_report([
            rec(evidence="pipe | in\nevidence"),
        ])
        r = self.run_script("pr-body", "--report", report,
                            "--marker", "abc123", "--head", "def456")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("- **`README.md:5`** — pipe \\| in evidence", r.stdout)

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


class DriftWaivers(unittest.TestCase):
    """--waivers wiring: UNVERIFIABLE records get a durable disposition path."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.summary_path = os.path.join(self.tmp.name, "summary.md")

    def run_script(self, *argv):
        env = dict(os.environ)
        env["GITHUB_STEP_SUMMARY"] = self.summary_path
        return subprocess.run(
            [sys.executable, SCRIPT, *argv],
            capture_output=True, text=True, env=env,
        )

    def summary(self):
        with open(self.summary_path, encoding="utf-8") as f:
            return f.read()

    def write_json(self, name, payload):
        path = os.path.join(self.tmp.name, name)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(payload, f)
        return path

    def report_two_flagged(self):
        return self.write_json("report.json", {"records": [
            rec(),
            rec(verdict="UNVERIFIABLE", location="README.md:9",
                claim="blazing fast", evidence="no benchmark backs it", fix=None),
            rec(verdict="UNVERIFIABLE", location="docs/ops.md:2",
                claim="production-ready", evidence="quality boast", fix=None),
        ], "summary": {}})

    def waive(self, *entries):
        return self.write_json("drift-waivers.json", {"waivers": [
            {"file": f, "claim": c, "reason": "accepted marketing tone",
             "date": "2026-07-12"} for f, c in entries
        ]})

    # -- pr-body ------------------------------------------------------------

    def test_pr_body_suppresses_waived_and_hints_disposition(self):
        r = self.run_script(
            "pr-body", "--report", self.report_two_flagged(),
            "--marker", "aaa", "--head", "bbb",
            "--waivers", self.waive(("docs/ops.md", "production-ready")))
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("`README.md:9`", r.stdout)
        self.assertNotIn("`docs/ops.md:2`", r.stdout)
        self.assertIn("1 waived claim(s) suppressed", r.stdout)
        self.assertIn("drift-waivers.json", r.stdout)

    def test_pr_body_without_waivers_flag_lists_all_flagged(self):
        r = self.run_script(
            "pr-body", "--report", self.report_two_flagged(),
            "--marker", "aaa", "--head", "bbb")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("`README.md:9`", r.stdout)
        self.assertIn("`docs/ops.md:2`", r.stdout)
        self.assertNotIn("suppressed", r.stdout)

    def test_pr_body_missing_waiver_file_treated_as_empty(self):
        r = self.run_script(
            "pr-body", "--report", self.report_two_flagged(),
            "--marker", "aaa", "--head", "bbb",
            "--waivers", os.path.join(self.tmp.name, "absent.json"))
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("`README.md:9`", r.stdout)
        self.assertIn("`docs/ops.md:2`", r.stdout)

    def test_pr_body_malformed_waivers_errors(self):
        bad = self.write_json("drift-waivers.json", {"waivers": {}})
        r = self.run_script(
            "pr-body", "--report", self.report_two_flagged(),
            "--marker", "aaa", "--head", "bbb", "--waivers", bad)
        self.assertEqual(r.returncode, 2)
        self.assertIn("error:", r.stderr)

    # -- pr-title -----------------------------------------------------------

    def test_pr_title_flagged_count_excludes_waived(self):
        r = self.run_script(
            "pr-title", "--report", self.report_two_flagged(),
            "--date", "2026-07-12",
            "--waivers", self.waive(("docs/ops.md", "production-ready")))
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("1 flagged", r.stdout)

    def test_pr_title_all_waived_drops_flagged_suffix(self):
        r = self.run_script(
            "pr-title", "--report", self.report_two_flagged(),
            "--date", "2026-07-12",
            "--waivers", self.waive(("docs/ops.md", "production-ready"),
                                    ("README.md", "blazing fast")))
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertNotIn("flagged", r.stdout)

    # -- no-drift-summary (the quiet-night surface) ---------------------------

    def test_no_drift_summary_surfaces_unwaived_unverifiable(self):
        report = self.write_json("report.json", {"records": [
            rec(verdict="VERIFIED", fix=None),
            rec(verdict="UNVERIFIABLE", location="README.md:9",
                claim="blazing fast", evidence="no benchmark backs it", fix=None),
        ], "summary": {}})
        r = self.run_script(
            "no-drift-summary", "--commits", "3", "--head", "bbb",
            "--report", report,
            "--waivers", self.write_json("drift-waivers.json", {"waivers": []}))
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("No drift.", self.summary())
        self.assertIn("1 unverifiable claim(s) await disposition", self.summary())
        self.assertIn("drift-waivers.json", self.summary())

    def test_no_drift_summary_quiet_when_all_waived(self):
        report = self.write_json("report.json", {"records": [
            rec(verdict="UNVERIFIABLE", location="README.md:9",
                claim="blazing fast", evidence="no benchmark backs it", fix=None),
        ], "summary": {}})
        r = self.run_script(
            "no-drift-summary", "--commits", "3", "--head", "bbb",
            "--report", report,
            "--waivers", self.waive(("README.md", "blazing fast")))
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertNotIn("await disposition", self.summary())

    def test_no_drift_summary_without_report_unchanged(self):
        r = self.run_script("no-drift-summary", "--commits", "3", "--head", "bbb")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("No drift.", self.summary())
        self.assertNotIn("await disposition", self.summary())


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
        self.assertIn("- `CUT` @ `README.md:5` — seven lines carry one fact", out.stdout)
        self.assertIn("`CONDENSE` @ `README.md:22`", out.stdout)
        self.assertIn("### ✂️ Proposed changes — 2 record(s)", out.stdout)

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

    def _unswept_summary(self, report):
        """Run bloat-unswept-summary with a real $GITHUB_STEP_SUMMARY file
        (CI always sets one) and return (result, summary_text). The banner is a
        run-summary line, not stdout — the workflow step surfaces it there."""
        fd, summary_path = tempfile.mkstemp()
        os.close(fd)
        env = dict(os.environ, GITHUB_STEP_SUMMARY=summary_path)
        out = subprocess.run(
            [sys.executable, SCRIPT, "bloat-unswept-summary", "--report", report],
            capture_output=True, text=True, env=env,
        )
        with open(summary_path, encoding="utf-8") as f:
            summary = f.read()
        os.unlink(summary_path)
        return out, summary

    def test_unswept_summary_writes_gap_state(self):
        report = write_report([])
        with open(report) as f:
            data = json.load(f)
        data["unswept"] = [{"chunk": "c-dead1", "docs": ["docs/plans/p.md"]}]
        with open(report, "w") as f:
            json.dump(data, f)
        out, summary = self._unswept_summary(report)
        os.unlink(report)
        self.assertEqual(out.returncode, 0, out.stderr)
        self.assertIn("1 chunk(s) unswept", summary)
        self.assertIn("docs/plans/p.md", summary)
        self.assertIn("next sweep", summary)

    def test_unswept_summary_silent_when_complete(self):
        report = write_report([brec("CUT", location="README.md:5")])
        out, summary = self._unswept_summary(report)
        os.unlink(report)
        self.assertEqual(out.returncode, 0, out.stderr)
        self.assertEqual(summary.strip(), "")

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


class DocSyncWaiverWiring(unittest.TestCase):
    """Pins doc-sync.yml's waiver wiring: every UNVERIFIABLE surface renders
    waiver-aware, and the quiet-night (advance-marker) path renders its
    disposition line BEFORE the report file is deleted."""

    WAIVERS = "--waivers .github/doc-sync/drift-waivers.json"

    @classmethod
    def setUpClass(cls):
        cls.ymls = {}
        for label, parts in {
            "template": ("plugins", "doc-lifecycle", "skills",
                         "scheduling-doc-sync", "doc-sync.yml"),
            "dogfood": (".github", "workflows", "doc-sync.yml"),
        }.items():
            path = os.path.join(os.path.dirname(__file__), "..", "..", *parts)
            with open(path, encoding="utf-8") as f:
                cls.ymls[label] = f.read()

    def test_pr_body_and_title_are_waiver_aware(self):
        for label, yml in self.ymls.items():
            body = yml[yml.index("render-report.py pr-body"):]
            self.assertIn(self.WAIVERS, body[:body.index("pr-title")], label)
            title = yml[yml.index("render-report.py pr-title"):]
            self.assertIn(self.WAIVERS, title[:title.index("git config")], label)

    def test_no_drift_summary_carries_report_and_waivers(self):
        for label, yml in self.ymls.items():
            # Both branches (push ok / push rejected) must surface the count.
            self.assertEqual(yml.count("no-drift-summary"), 2, label)
            for chunk in yml.split("no-drift-summary")[1:]:
                head = chunk[:300]
                self.assertIn("--report drift-report.json", head, label)
                self.assertIn(self.WAIVERS, head, label)

    def test_report_deleted_only_after_quiet_night_render(self):
        for label, yml in self.ymls.items():
            step = yml[yml.index("Advance marker"):yml.index("blast-radius issue")]
            self.assertIn("rm -f drift-report.json", step, label)
            self.assertLess(step.index("no-drift-summary"),
                            step.index("rm -f drift-report.json"), label)

    def test_pr_body_compares_against_prior_stale_state(self):
        for label, yml in self.ymls.items():
            body = yml[yml.index("render-report.py pr-body"):]
            self.assertIn("--prev-stales .github/doc-sync/last-stales.json",
                          body[:body.index("pr-title")], label)

    def test_new_stale_state_rides_the_sync_pr(self):
        for label, yml in self.ymls.items():
            step = yml[yml.index("Open sync PR"):]
            self.assertIn("sync-gate.py stale-state", step, label)
            self.assertIn("--out .github/doc-sync/last-stales.json", step, label)
            # State must be staged before the PR commit, so it advances only
            # when the fix merges.
            self.assertLess(step.index("stale-state"),
                            step.index("git add -A"), label)


class DocBloatGrowthWiring(unittest.TestCase):
    """Pins the weekly grow-loop surface: every doc-bloat run renders the
    doc-scope.md growth backlog, skip paths included."""

    @classmethod
    def setUpClass(cls):
        cls.ymls = {}
        for label, parts in {
            "template": ("plugins", "doc-lifecycle", "skills",
                         "scheduling-doc-sync", "doc-bloat.yml"),
            "dogfood": (".github", "workflows", "doc-bloat.yml"),
        }.items():
            path = os.path.join(os.path.dirname(__file__), "..", "..", *parts)
            with open(path, encoding="utf-8") as f:
                cls.ymls[label] = f.read()

    def test_growth_backlog_rendered_every_run(self):
        for label, yml in self.ymls.items():
            self.assertIn("growth-backlog --scope-file docs/doc-scope.md",
                          yml, label)
            # Before the pre-gate branch: it must render on skip paths too.
            self.assertLess(yml.index("growth-backlog"),
                            yml.index("bloat-pre-summary"), label)


class RecurrenceRender(unittest.TestCase):
    """pr-body --prev-stales: a location STALE in consecutive proceed runs is a
    shape problem, not a fix problem — the PR body says so once, per record."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)

    def write_json(self, name, payload):
        path = os.path.join(self.tmp.name, name)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(payload, f)
        return path

    def pr_body(self, prev=None):
        report = self.write_json("report.json", {"records": [
            rec(location="README.md:5"),
            rec(location="docs/ops.md:40", claim="port is 8080",
                evidence="config says 9090", fix="port is 9090"),
        ], "summary": {}})
        argv = [sys.executable, SCRIPT, "pr-body", "--report", report,
                "--marker", "aaa", "--head", "bbb"]
        if prev is not None:
            argv += ["--prev-stales", prev]
        return subprocess.run(argv, capture_output=True, text=True)

    def test_recurred_location_tagged_with_shape_hint(self):
        prev = self.write_json("last-stales.json", {"stales": [
            {"file": "README.md", "line": 7, "kind": "command"},  # ±3 of line 5
        ]})
        r = self.pr_body(prev)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("recurred", r.stdout)
        self.assertLess(r.stdout.index("README.md:5"), r.stdout.index("recurred"))
        self.assertNotIn("docs/ops.md:40`** ⟳", r.stdout)
        self.assertIn("shape problem", r.stdout)
        self.assertIn("pointer", r.stdout)

    def test_no_match_renders_clean(self):
        prev = self.write_json("last-stales.json", {"stales": [
            {"file": "README.md", "line": 40, "kind": "command"},  # far away
        ]})
        r = self.pr_body(prev)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertNotIn("recurred", r.stdout)
        self.assertNotIn("shape problem", r.stdout)

    def test_missing_prev_stales_treated_as_empty(self):
        r = self.pr_body(os.path.join(self.tmp.name, "absent.json"))
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertNotIn("recurred", r.stdout)

    def test_kind_mismatch_is_not_recurrence(self):
        prev = self.write_json("last-stales.json", {"stales": [
            {"file": "README.md", "line": 5, "kind": "behavior"},
        ]})
        r = self.pr_body(prev)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertNotIn("recurred", r.stdout)


class GrowthBacklog(unittest.TestCase):
    """growth-backlog: the weekly bloat run surfaces docs/doc-scope.md Deferred
    items so the grow loop is seen on the same cadence as the prune loop."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.summary_path = os.path.join(self.tmp.name, "summary.md")

    def run_script(self, scope_path):
        env = dict(os.environ)
        env["GITHUB_STEP_SUMMARY"] = self.summary_path
        return subprocess.run(
            [sys.executable, SCRIPT, "growth-backlog", "--scope-file", scope_path],
            capture_output=True, text=True, env=env,
        )

    def summary(self):
        with open(self.summary_path, encoding="utf-8") as f:
            return f.read()

    def write_scope(self, text):
        path = os.path.join(self.tmp.name, "doc-scope.md")
        with open(path, "w", encoding="utf-8") as f:
            f.write(text)
        return path

    def test_renders_deferred_items_with_tallies(self):
        scope = self.write_scope(
            "# Doc scope record\n<!-- format: doc-lifecycle growing-docs -->\n\n"
            "## Deferred\n"
            "- runbook: CI triage — promote when: an on-call needs steps\n"
            "- rationale: why lint is a build mode — promote when: someone asks again\n"
            "  - seen: 2026-07-05 contributor asked in review\n\n"
            "## Done\n- 2026-06-28 baseline ← bootstrap\n")
        r = self.run_script(scope)
        self.assertEqual(r.returncode, 0, r.stderr)
        s = self.summary()
        self.assertIn("Growth backlog", s)
        self.assertIn("2 deferred", s)
        self.assertIn("runbook: CI triage", s)
        self.assertIn("seen: 2026-07-05", s)
        self.assertIn("next occurrence promotes", s)

    def test_missing_scope_file_is_quiet_not_fatal(self):
        r = self.run_script(os.path.join(self.tmp.name, "absent.md"))
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("no doc-scope.md", self.summary())

    def test_empty_deferred_section_reports_empty(self):
        scope = self.write_scope(
            "# Doc scope record\n\n## Deferred\n\n## Done\n- x\n")
        r = self.run_script(scope)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("Growth backlog: empty", self.summary())


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

    def test_hard_failed_retry_cannot_strand_an_invalid_chunk(self):
        # If the retry action itself dies hard, the final seam-validate must
        # still run (an implicit success() would skip it) or the always()
        # upload ships the dead attempt's partially-written chunk file — and
        # one invalid chunk fails the whole gap-tolerant assembly.
        retry_block = self.yml.split("Detect chunk (retry")[1].split("- name:")[0]
        self.assertIn("continue-on-error: true", retry_block)
        final_block = self.yml.split("Seam-validate (final)")[1].split("- name:")[0]
        self.assertIn("!cancelled() && steps.seam1.outcome == 'failure'",
                      final_block)

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

    def test_distill_lane_is_planned_dispatched_and_merged_by_scripts(self):
        # plan -> matrix -> merge: every distill-lane decision is script-borne.
        self.assertIn("plan-distill.py --report bloat-report.json --out distill-manifest.json",
                      self.yml)
        self.assertIn('plan-distill.py --emit-prompt "${GROUP_ID}"', self.yml)
        self.assertIn('--validate-result "distill-results/${GROUP_ID}.json"',
                      self.yml)
        self.assertIn("plan-distill.py --merge", self.yml)
        self.assertIn("distill-merge-summary", self.yml)
        self.assertIn('--merge "$RUNNER_TEMP/distill-merge.json"', self.yml)

    def test_distill_executor_keeps_skill_and_task_without_turn_cap(self):
        # The apply side is never truncated mid-judgment: no --max-turns on
        # its invocations (owner decision); the kill-switch is wall-clock.
        self.assertIn('"Skill,Task,Read', self.yml)
        self.assertIn("timeout-minutes: 60", self.yml)
        distill = self.yml[self.yml.index("distill_sweep:"):]
        for line in distill.splitlines():
            if "claude_args" in line:
                self.assertNotIn("--max-turns", line)

    def test_distill_merge_runs_even_when_a_group_fails(self):
        self.assertIn("always() && needs.assemble.outputs.distill == 'open'",
                      self.yml)


class UpgradeRender(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.summary_path = os.path.join(self.tmp.name, "summary.md")

    def run_script(self, *argv):
        env = dict(os.environ)
        env["GITHUB_STEP_SUMMARY"] = self.summary_path
        return subprocess.run([sys.executable, SCRIPT, *argv],
                              capture_output=True, text=True, env=env)

    def summary(self):
        with open(self.summary_path, encoding="utf-8") as f:
            return f.read()

    # -- upgrade-summary ---------------------------------------------------

    def test_current_reports_both_versions(self):
        r = self.run_script("upgrade-summary", "--status", "current",
                            "--current", "0.7.0", "--latest", "0.7.0")
        self.assertEqual(r.returncode, 0, r.stderr)
        s = self.summary()
        self.assertIn("current", s.lower())
        self.assertIn("0.7.0", s)

    def test_ahead_names_dev_pin(self):
        r = self.run_script("upgrade-summary", "--status", "ahead",
                            "--current", "0.8.0", "--latest", "0.7.0")
        self.assertEqual(r.returncode, 0, r.stderr)
        s = self.summary()
        self.assertIn("ahead", s.lower())
        self.assertIn("0.8.0", s)
        self.assertIn("0.7.0", s)

    def test_noop_states_no_wiring_change(self):
        r = self.run_script("upgrade-summary", "--status", "noop",
                            "--current", "0.7.0", "--latest", "0.8.0")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("no wiring change", self.summary().lower())

    def test_opened_includes_pr_url_and_bump(self):
        r = self.run_script("upgrade-summary", "--status", "opened",
                            "--current", "0.7.0", "--latest", "0.8.0",
                            "--pr-url", "https://gh/pr/9")
        self.assertEqual(r.returncode, 0, r.stderr)
        s = self.summary()
        self.assertIn("https://gh/pr/9", s)
        self.assertIn("0.7.0", s)
        self.assertIn("0.8.0", s)

    def test_pending_reports_open_pr(self):
        r = self.run_script("upgrade-summary", "--status", "pending",
                            "--current", "0.7.0", "--latest", "0.8.0",
                            "--pr-url", "https://gh/pr/3")
        self.assertEqual(r.returncode, 0, r.stderr)
        s = self.summary()
        self.assertIn("https://gh/pr/3", s)
        self.assertIn("already open", s.lower())

    def test_blocked_workflows_lists_files_and_apply_steps(self):
        r = self.run_script(
            "upgrade-summary", "--status", "blocked-workflows",
            "--current", "0.9.2", "--latest", "0.9.3",
            "--files", ".github/workflows/doc-bloat.yml,.github/doc-sync/render-report.py")
        self.assertEqual(r.returncode, 0, r.stderr)
        s = self.summary()
        # Names the offending workflow file, the artifact to apply, and git apply steps.
        self.assertIn(".github/workflows/doc-bloat.yml", s)
        self.assertIn("doc-sync-upgrade-patch", s)
        self.assertIn("git apply", s)
        self.assertIn("0.9.3", s)

    def test_unknown_status_exits_2(self):
        r = self.run_script("upgrade-summary", "--status", "bogus",
                            "--current", "0.7.0", "--latest", "0.8.0")
        self.assertEqual(r.returncode, 2)

    # -- upgrade-pr-body ---------------------------------------------------

    def test_pr_body_shows_bump_and_preserved_state(self):
        r = self.run_script("upgrade-pr-body", "--current", "0.7.0",
                            "--latest", "0.8.0")
        self.assertEqual(r.returncode, 0, r.stderr)
        out = r.stdout
        self.assertIn("0.7.0", out)
        self.assertIn("0.8.0", out)
        # states what the upgrade preserves, so a reviewer trusts the diff
        self.assertIn("marker", out.lower())
        self.assertIn("audit-scope", out.lower())

    def test_pr_body_lists_changed_files_when_given(self):
        r = self.run_script("upgrade-pr-body", "--current", "0.7.0",
                            "--latest", "0.8.0",
                            "--files", ".github/workflows/doc-sync.yml,.github/doc-sync/sync-gate.py")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("`.github/workflows/doc-sync.yml`", r.stdout)
        self.assertIn("`.github/doc-sync/sync-gate.py`", r.stdout)


class DistillMergeRender(unittest.TestCase):
    """The distill lane's merge outcomes: unapplied banner in the PR body,
    run-surface merge summary."""

    def write_merge(self, applied, unapplied):
        fd, path = tempfile.mkstemp(suffix=".json")
        with os.fdopen(fd, "w") as f:
            json.dump({"applied": applied, "unapplied": unapplied}, f)
        self.addCleanup(os.unlink, path)
        return path

    def test_pr_body_banners_unapplied_records(self):
        report = write_report([brec("DISTILL", doc="docs/plans/a.md",
                                    status="ready", rid="B1"),
                               brec("DISTILL", doc="docs/plans/b.md",
                                    status="ready", rid="B2")])
        merge = self.write_merge(["B1"], [
            {"id": "B2", "reason": "merge conflict: README.md",
             "stage": "merge"}])
        out = run(sys.executable, SCRIPT, "bloat-pr-body", "--report", report,
                  "--merge", merge)
        os.unlink(report)
        self.assertEqual(out.returncode, 0, out.stderr)
        self.assertIn("1 record(s) not landed this run", out.stdout)
        self.assertIn("`B2`", out.stdout)
        self.assertIn("merge conflict: README.md", out.stdout)
        self.assertIn("next sweep re-proposes", out.stdout)
        # The blanket "each row is applied" claim must not survive a gap.
        self.assertNotIn("each row is applied", out.stdout)

    def test_pr_body_with_clean_merge_has_no_banner(self):
        report = write_report([brec("DISTILL", doc="docs/plans/a.md",
                                    status="ready", rid="B1")])
        merge = self.write_merge(["B1"], [])
        out = run(sys.executable, SCRIPT, "bloat-pr-body", "--report", report,
                  "--merge", merge)
        os.unlink(report)
        self.assertEqual(out.returncode, 0, out.stderr)
        self.assertNotIn("not landed", out.stdout)
        self.assertIn("each row is applied", out.stdout)

    def _summary(self, merge_path):
        fd, summary_path = tempfile.mkstemp()
        os.close(fd)
        self.addCleanup(os.unlink, summary_path)
        env = dict(os.environ, GITHUB_STEP_SUMMARY=summary_path)
        out = subprocess.run(
            [sys.executable, SCRIPT, "distill-merge-summary",
             "--merge", merge_path],
            capture_output=True, text=True, env=env)
        with open(summary_path, encoding="utf-8") as f:
            return out, f.read()

    def test_merge_summary_all_landed(self):
        out, summary = self._summary(self.write_merge(["B1", "B2"], []))
        self.assertEqual(out.returncode, 0, out.stderr)
        self.assertIn("all 2 record(s) landed", summary)

    def test_merge_summary_names_gap_count(self):
        out, summary = self._summary(self.write_merge(
            ["B1"], [{"id": "B2", "reason": "skipped by executor: x",
                      "stage": "executor"}]))
        self.assertEqual(out.returncode, 0, out.stderr)
        self.assertIn("1 record(s) landed", summary)
        self.assertIn("1 not landed", summary)

    def test_malformed_merge_file_errors(self):
        fd, path = tempfile.mkstemp(suffix=".json")
        with os.fdopen(fd, "w") as f:
            f.write("{\"applied\": 3}")
        self.addCleanup(os.unlink, path)
        report = write_report([brec("DISTILL", doc="a.md", status="ready")])
        out = run(sys.executable, SCRIPT, "bloat-pr-body", "--report", report,
                  "--merge", path)
        os.unlink(report)
        self.assertNotEqual(out.returncode, 0)
        self.assertIn("error:", out.stderr)


if __name__ == "__main__":
    unittest.main(verbosity=1)
