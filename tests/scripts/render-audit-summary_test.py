#!/usr/bin/env python3
"""Black-box tests for scheduling-doc-sync's render-audit-summary.py.

This script owns the run-surface rendering for the new read-only audit lane
(doc-audit.yml, issue #71): the self-explaining outcome (clean / findings /
partial / stale / invalid / no-report-at-all), the pinned lineage, and
cost/budget observability — as Markdown for the job summary, and as a small
JSON extraction from claude-code-action's execution-log for cost.

Tested as a subprocess: real argv, real exit codes, real stdout, and a real
$GITHUB_STEP_SUMMARY file for the `summary` subcommand.

Run: python3 tests/scripts/render-audit-summary_test.py
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
    "scripts", "render-audit-summary.py",
)

LINEAGE = {
    "repository": "origin:github.com/aj604/toolshed",
    "base_commit": "a" * 40,
    "audit_mode": "full",
    "inventory_digest": "b" * 64,
    "audit_config_digest": "c" * 64,
    "registry_digest": "d" * 64,
    "ruleset_version": 1,
    "plugin_version": "0.19.0",
    "evidence_boundary": {"sources": ["**"], "excluded": []},
}


def report(status, **over):
    payload = {
        "status": status,
        "schema_version": 1,
        "lineage": dict(LINEAGE),
        "records": [],
        "incomplete": [],
        "digest": "e" * 64,
    }
    payload.update(over)
    return payload


def record(rid="DRIFT-001", code="STALE", path="docs/architecture.md"):
    return {"id": rid, "digest": "f" * 64, "code": code, "path": path,
            "units": ["1" * 64]}


def read_json(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def run(*argv, env_extra=None):
    env = dict(os.environ)
    # The suite decides whether the script has a step summary to write to, not
    # the environment it happens to run in. Inheriting a real
    # GITHUB_STEP_SUMMARY makes the stdout-fallback test pass on a laptop and
    # fail on Actions — which is exactly what it did, unnoticed, for as long as
    # this suite was not wired into CI.
    env.pop("GITHUB_STEP_SUMMARY", None)
    if env_extra:
        env.update(env_extra)
    return subprocess.run(
        [sys.executable, SCRIPT, *argv], capture_output=True, text=True, env=env,
    )


class CostExtraction(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)

    def write_log(self, data):
        path = os.path.join(self.tmp.name, "execution.json")
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f)
        return path

    def out_path(self):
        return os.path.join(self.tmp.name, "cost.json")

    def test_extracts_turns_cost_and_duration_from_result_event(self):
        log = self.write_log([
            {"type": "system", "subtype": "init"},
            {"type": "result", "subtype": "success", "num_turns": 7,
             "total_cost_usd": 0.42, "duration_ms": 15000},
        ])
        out = self.out_path()
        proc = run("cost", "--execution-log", log, "--out", out)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        data = read_json(out)
        self.assertEqual(data, {
            "available": True, "turns": 7, "cost_usd": 0.42, "duration_ms": 15000,
        })

    def test_last_result_event_wins(self):
        log = self.write_log([
            {"type": "result", "subtype": "error_max_turns", "num_turns": 3,
             "total_cost_usd": 0.1, "duration_ms": 5000},
            {"type": "result", "subtype": "success", "num_turns": 9,
             "total_cost_usd": 0.9, "duration_ms": 20000},
        ])
        out = self.out_path()
        run("cost", "--execution-log", log, "--out", out)
        data = read_json(out)
        self.assertEqual(data["turns"], 9)

    def test_missing_log_is_unavailable_not_an_error(self):
        out = self.out_path()
        proc = run("cost", "--execution-log",
                    os.path.join(self.tmp.name, "nope.json"), "--out", out)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        data = read_json(out)
        self.assertEqual(data, {"available": False, "turns": None,
                                 "cost_usd": None, "duration_ms": None})

    def test_malformed_log_is_unavailable_not_an_error(self):
        path = os.path.join(self.tmp.name, "bad.json")
        with open(path, "w", encoding="utf-8") as f:
            f.write("{not json")
        out = self.out_path()
        proc = run("cost", "--execution-log", path, "--out", out)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        data = read_json(out)
        self.assertFalse(data["available"])

    def test_no_result_event_is_unavailable(self):
        log = self.write_log([{"type": "system", "subtype": "init"}])
        out = self.out_path()
        run("cost", "--execution-log", log, "--out", out)
        data = read_json(out)
        self.assertFalse(data["available"])


class RenderOutcomes(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.summary_path = os.path.join(self.tmp.name, "summary.md")

    def write_report(self, payload):
        path = os.path.join(self.tmp.name, "drift-report.json")
        with open(path, "w", encoding="utf-8") as f:
            json.dump(payload, f)
        return path

    def summary_run(self, *argv):
        env = {"GITHUB_STEP_SUMMARY": self.summary_path}
        return run("summary", *argv, env_extra=env)

    def summary_text(self):
        with open(self.summary_path, encoding="utf-8") as f:
            return f.read()

    def test_missing_report_file_renders_typed_no_report_failure(self):
        proc = self.summary_run(
            "--report", os.path.join(self.tmp.name, "absent.json"))
        self.assertEqual(proc.returncode, 0, proc.stderr)
        text = self.summary_text()
        self.assertIn("NO REPORT", text)
        self.assertIn("audit-report-missing", text)

    def test_invalid_report_lists_every_problem(self):
        path = self.write_report({
            "status": "invalid", "schema_version": 1,
            "problems": [
                {"code": "registry-invalid-root", "message": "docs/x missing",
                 "location": "roots[0]"},
                {"code": "registry-parse-error", "message": "bad json",
                 "location": None},
            ],
        })
        proc = self.summary_run("--report", path)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        text = self.summary_text()
        self.assertIn("INVALID", text)
        self.assertIn("registry-invalid-root", text)
        self.assertIn("docs/x missing", text)
        self.assertIn("registry-parse-error", text)

    def test_stale_report_names_every_changed_field(self):
        path = self.write_report(report(
            "stale",
            stale_reasons=[{"code": "lineage-base-commit-mismatch",
                             "message": "base commit moved",
                             "reported": "a" * 40, "current": "b" * 40}],
        ))
        proc = self.summary_run("--report", path)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        text = self.summary_text()
        self.assertIn("STALE", text)
        self.assertIn("lineage-base-commit-mismatch", text)
        self.assertIn("base commit moved", text)

    def test_partial_report_names_unexamined_scopes(self):
        path = self.write_report(report(
            "partial",
            incomplete=[{"scope": "docs/runbook.md",
                         "reason": "the chunk worker failed twice"}],
        ))
        proc = self.summary_run("--report", path)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        text = self.summary_text()
        self.assertIn("PARTIAL", text)
        self.assertIn("docs/runbook.md", text)
        self.assertIn("the chunk worker failed twice", text)

    def test_bloat_summary_names_typed_completion_gaps_from_the_report(self):
        path = self.write_report(report(
            "partial",
            incomplete=[{
                "scope": "docs/runbook.md",
                "reason": "chunk c-deadbeef is missing: result file was not produced",
            }],
        ))
        proc = self.summary_run("--kind", "bloat", "--report", path)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        text = self.summary_text()
        self.assertIn("Bloat audit: PARTIAL", text)
        self.assertIn("docs/runbook.md", text)
        self.assertIn("c-deadbeef", text)

    def test_clean_report_says_clean(self):
        path = self.write_report(report("clean"))
        proc = self.summary_run("--report", path)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertIn("CLEAN", self.summary_text())

    def test_findings_report_counts_by_code(self):
        path = self.write_report(report(
            "findings",
            records=[record(code="STALE"), record(rid="DRIFT-002", code="STALE"),
                     record(rid="DRIFT-003", code="UNVERIFIABLE")],
        ))
        proc = self.summary_run("--report", path)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        text = self.summary_text()
        self.assertIn("FINDINGS", text)
        self.assertIn("STALE", text)
        self.assertIn("2", text)
        self.assertIn("UNVERIFIABLE", text)

    def test_lineage_pins_commit_and_mode(self):
        path = self.write_report(report("clean"))
        proc = self.summary_run("--report", path)
        text = self.summary_text()
        self.assertIn("a" * 40, text)
        self.assertIn("full", text)

    def test_falls_back_to_stdout_without_env(self):
        path = self.write_report(report("clean"))
        proc = run("summary", "--report", path)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertIn("CLEAN", proc.stdout)


class CostObservability(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.summary_path = os.path.join(self.tmp.name, "summary.md")

    def write_report(self, payload):
        path = os.path.join(self.tmp.name, "drift-report.json")
        with open(path, "w", encoding="utf-8") as f:
            json.dump(payload, f)
        return path

    def write_cost(self, data):
        path = os.path.join(self.tmp.name, "cost.json")
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f)
        return path

    def summary_text(self):
        with open(self.summary_path, encoding="utf-8") as f:
            return f.read()

    def test_cost_appears_without_narrowing_scope_language(self):
        report_path = self.write_report(report("clean"))
        cost_path = self.write_cost({"available": True, "turns": 5,
                                      "cost_usd": 0.31, "duration_ms": 9000})
        env = {"GITHUB_STEP_SUMMARY": self.summary_path}
        proc = run("summary", "--report", report_path, "--cost", cost_path,
                    env_extra=env)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        text = self.summary_text()
        self.assertIn("5", text)
        self.assertIn("0.31", text)
        self.assertIn("does not narrow", text)

    def test_missing_cost_is_reported_as_unavailable_not_omitted(self):
        report_path = self.write_report(report("clean"))
        cost_path = self.write_cost({"available": False, "turns": None,
                                      "cost_usd": None, "duration_ms": None})
        env = {"GITHUB_STEP_SUMMARY": self.summary_path}
        proc = run("summary", "--report", report_path, "--cost", cost_path,
                    env_extra=env)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertIn("not available", self.summary_text())

    def test_without_cost_flag_no_cost_section_and_no_crash(self):
        report_path = self.write_report(report("clean"))
        proc = run("summary", "--report", report_path)
        self.assertEqual(proc.returncode, 0, proc.stderr)


class UsageErrors(unittest.TestCase):
    def test_summary_missing_report_flag_exits_2(self):
        proc = run("summary")
        self.assertEqual(proc.returncode, 2)

    def test_unknown_subcommand_exits_2(self):
        proc = run("not-a-command")
        self.assertEqual(proc.returncode, 2)


if __name__ == "__main__":
    unittest.main()
