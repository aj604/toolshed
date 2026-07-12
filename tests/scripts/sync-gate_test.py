#!/usr/bin/env python3
"""Black-box tests for scheduling-doc-sync's sync-gate.py.

Tests the script as a subprocess: real argv, real exit codes, real stdout.
Run: python3 tests/scripts/sync-gate_test.py
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
    "scripts", "sync-gate.py",
)


def rec(verdict="VERIFIED"):
    return {
        "claim": "README mentions make test",
        "location": "README.md:5",
        "kind": "command",
        "tier": 1,
        "verdict": verdict,
        "evidence": "Makefile has `test:`",
        "fix": "make check" if verdict == "STALE" else None,
    }


def run(*argv):
    return subprocess.run(
        [sys.executable, SCRIPT, *argv], capture_output=True, text=True
    )


def report_file(payload):
    f = tempfile.NamedTemporaryFile(
        "w", suffix=".json", delete=False, encoding="utf-8"
    )
    f.write(payload if isinstance(payload, str) else json.dumps(payload))
    f.close()
    return f.name


def brec(verdict, status=None, location=None, doc="README.md", files=None):
    r = {"id": "B1", "doc": doc, "location": location, "verdict": verdict,
         "evidence": "x", "proposal": None, "status": status, "files": files}
    return r


def write_report(records):
    fd, path = tempfile.mkstemp(suffix=".json")
    with os.fdopen(fd, "w") as f:
        json.dump({"records": records, "summary": {}}, f)
    return path


def wrapped(records):
    counts = {"verified": 0, "stale": 0, "unverifiable": 0}
    for r in records:
        counts[r["verdict"].lower()] += 1
    return {"records": records, "summary": counts}


class PreGate(unittest.TestCase):
    def test_no_new_commits_is_skip_empty(self):
        r = run("pre", "--commits", "0", "--open-prs", "0", "--open-issues", "0")
        self.assertEqual(r.returncode, 0)
        self.assertEqual(r.stdout.strip(), "skip-empty")

    def test_empty_range_wins_over_pending(self):
        r = run("pre", "--commits", "0", "--open-prs", "1", "--open-issues", "1")
        self.assertEqual(r.stdout.strip(), "skip-empty")

    def test_open_pr_is_skip_pending(self):
        r = run("pre", "--commits", "5", "--open-prs", "1", "--open-issues", "0")
        self.assertEqual(r.returncode, 0)
        self.assertEqual(r.stdout.strip(), "skip-pending")

    def test_open_issue_is_skip_pending(self):
        r = run("pre", "--commits", "5", "--open-prs", "0", "--open-issues", "1")
        self.assertEqual(r.stdout.strip(), "skip-pending")

    def test_all_clear_is_detect(self):
        r = run("pre", "--commits", "5", "--open-prs", "0", "--open-issues", "0")
        self.assertEqual(r.returncode, 0)
        self.assertEqual(r.stdout.strip(), "detect")

    def test_negative_count_is_bad_input(self):
        r = run("pre", "--commits", "-1", "--open-prs", "0", "--open-issues", "0")
        self.assertEqual(r.returncode, 2)


class PostGate(unittest.TestCase):
    def test_zero_stale_is_advance_marker(self):
        path = report_file(wrapped([rec("VERIFIED"), rec("UNVERIFIABLE")]))
        r = run("post", "--report", path, "--cap", "10")
        self.assertEqual(r.returncode, 0)
        self.assertEqual(r.stdout.strip(), "advance-marker")

    def test_stale_within_cap_is_proceed(self):
        path = report_file(wrapped([rec("STALE"), rec("VERIFIED")]))
        r = run("post", "--report", path, "--cap", "10")
        self.assertEqual(r.stdout.strip(), "proceed")

    def test_stale_equal_to_cap_still_proceeds(self):
        path = report_file(wrapped([rec("STALE"), rec("STALE")]))
        r = run("post", "--report", path, "--cap", "2")
        self.assertEqual(r.stdout.strip(), "proceed")

    def test_stale_over_cap_is_blast_radius(self):
        path = report_file(wrapped([rec("STALE"), rec("STALE"), rec("STALE")]))
        r = run("post", "--report", path, "--cap", "2")
        self.assertEqual(r.returncode, 0)
        self.assertEqual(r.stdout.strip(), "blast-radius")

    def test_bare_array_report_is_accepted(self):
        path = report_file([rec("STALE")])
        r = run("post", "--report", path, "--cap", "10")
        self.assertEqual(r.stdout.strip(), "proceed")

    def test_stale_counted_from_records_not_summary(self):
        payload = wrapped([rec("STALE")])
        payload["summary"] = {"verified": 1, "stale": 0, "unverifiable": 0}  # lies
        path = report_file(payload)
        r = run("post", "--report", path, "--cap", "10")
        self.assertEqual(r.stdout.strip(), "proceed")

    def test_missing_report_is_bad_input(self):
        r = run("post", "--report", "/nonexistent/report.json", "--cap", "10")
        self.assertEqual(r.returncode, 2)

    def test_invalid_json_is_bad_input(self):
        path = report_file("not json{")
        r = run("post", "--report", path, "--cap", "10")
        self.assertEqual(r.returncode, 2)

    def test_non_record_shape_is_bad_input(self):
        path = report_file({"summary": {}})
        r = run("post", "--report", path, "--cap", "10")
        self.assertEqual(r.returncode, 2)

    def test_cap_below_one_is_bad_input(self):
        path = report_file(wrapped([rec("STALE")]))
        r = run("post", "--report", path, "--cap", "0")
        self.assertEqual(r.returncode, 2)


class StaleState(unittest.TestCase):
    """stale-state: one run of location memory so the next run's PR body can
    tag same-spot recurrence (re-shaping advice, not another re-fix)."""

    def out_path(self):
        fd, path = tempfile.mkstemp(suffix=".json")
        os.close(fd)
        self.addCleanup(lambda: os.path.exists(path) and os.unlink(path))
        return path

    def test_derives_stale_identities_only(self):
        stale = rec("STALE")
        stale2 = dict(rec("STALE"), location="docs/ops.md:40", kind="value")
        path = report_file(wrapped([stale, rec("VERIFIED"), stale2,
                                    rec("UNVERIFIABLE")]))
        out = self.out_path()
        r = run("stale-state", "--report", path, "--out", out)
        self.assertEqual(r.returncode, 0, r.stderr)
        with open(out) as f:
            state = json.load(f)
        self.assertEqual(state, {"stales": [
            {"file": "README.md", "line": 5, "kind": "command"},
            {"file": "docs/ops.md", "line": 40, "kind": "value"},
        ]})

    def test_zero_stale_writes_empty_state(self):
        path = report_file(wrapped([rec("VERIFIED")]))
        out = self.out_path()
        r = run("stale-state", "--report", path, "--out", out)
        self.assertEqual(r.returncode, 0, r.stderr)
        with open(out) as f:
            self.assertEqual(json.load(f), {"stales": []})

    def test_malformed_report_exits_2(self):
        path = report_file('{"nope": true}')
        r = run("stale-state", "--report", path, "--out", self.out_path())
        self.assertEqual(r.returncode, 2)


class BloatPreGate(unittest.TestCase):
    def test_both_prs_open_skips(self):
        out = run("bloat-pre", "--prune-pr-open", "1", "--distill-pr-open", "2")
        self.assertEqual(out.returncode, 0)
        self.assertEqual(out.stdout.strip(), "skip-pending")

    def test_one_lane_free_detects(self):
        out = run("bloat-pre", "--prune-pr-open", "1", "--distill-pr-open", "0")
        self.assertEqual(out.stdout.strip(), "detect")

    def test_both_free_detects(self):
        out = run("bloat-pre", "--prune-pr-open", "0", "--distill-pr-open", "0")
        self.assertEqual(out.stdout.strip(), "detect")


class BloatLaneGate(unittest.TestCase):
    def _run(self, records, lane, pr_open=0):
        report = write_report(records)
        out_fd, out_path = tempfile.mkstemp(suffix=".json")
        os.close(out_fd)
        res = run("bloat-lane", "--report", report, "--lane", lane,
                  "--pr-open", str(pr_open), "--out", out_path)
        with open(out_path) as f:
            filtered = json.load(f)["records"]
        os.unlink(report); os.unlink(out_path)
        return res.stdout.strip(), filtered

    def test_prune_open_with_cut(self):
        dec, filtered = self._run([brec("CUT", location="README.md:5")], "prune")
        self.assertEqual(dec, "open")
        self.assertEqual(len(filtered), 1)

    def test_prune_empty_when_only_doc_verdicts(self):
        dec, filtered = self._run([brec("RETIRE-DOC")], "prune")
        self.assertEqual(dec, "skip-empty")
        self.assertEqual(filtered, [])

    def test_distill_includes_merge_retire_and_ready_distill(self):
        recs = [brec("MERGE-DOC"), brec("RETIRE-DOC"),
                brec("DISTILL", status="ready"),
                brec("DISTILL", status="pending-implementation")]
        dec, filtered = self._run(recs, "distill")
        self.assertEqual(dec, "open")
        self.assertEqual(len(filtered), 3)  # pending-implementation excluded

    def test_distill_empty_when_only_pending(self):
        dec, filtered = self._run([brec("DISTILL", status="pending-implementation")], "distill")
        self.assertEqual(dec, "skip-empty")

    def test_pr_open_skips_pending_even_with_findings(self):
        dec, _ = self._run([brec("CUT", location="README.md:5")], "prune", pr_open=1)
        self.assertEqual(dec, "skip-pending")

    def test_policy_routes_to_distill_lane(self):
        recs = [brec("POLICY", doc="docs/superpowers",
                     files=["docs/superpowers/plans/a.md"])]
        dec, filtered = self._run(recs, "distill")
        self.assertEqual(dec, "open")
        self.assertEqual(len(filtered), 1)

    def test_policy_not_in_prune_lane(self):
        recs = [brec("POLICY", doc="docs/superpowers",
                     files=["docs/superpowers/plans/a.md"])]
        dec, filtered = self._run(recs, "prune")
        self.assertEqual(dec, "skip-empty")
        self.assertEqual(filtered, [])

    def test_lane_out_propagates_unswept(self):
        report = write_report([brec("CUT", location="README.md:5")])
        with open(report) as f:
            data = json.load(f)
        data["unswept"] = [{"chunk": "c-dead", "docs": ["docs/plans/p.md"]}]
        with open(report, "w") as f:
            json.dump(data, f)
        out_fd, out_path = tempfile.mkstemp(suffix=".json")
        os.close(out_fd)
        res = run("bloat-lane", "--report", report, "--lane", "prune",
                  "--pr-open", "0", "--out", out_path)
        with open(out_path) as f:
            lane = json.load(f)
        os.unlink(report); os.unlink(out_path)
        self.assertEqual(res.returncode, 0, res.stderr)
        self.assertEqual(lane["unswept"],
                         [{"chunk": "c-dead", "docs": ["docs/plans/p.md"]}])

    def test_v2_wrapped_report_with_schema_key_loads(self):
        report = write_report([brec("CUT", location="README.md:5")])
        with open(report) as f:
            data = json.load(f)
        data["schema"] = 2
        with open(report, "w") as f:
            json.dump(data, f)
        out_fd, out_path = tempfile.mkstemp(suffix=".json")
        os.close(out_fd)
        res = run("bloat-lane", "--report", report, "--lane", "prune",
                  "--pr-open", "0", "--out", out_path)
        os.unlink(report); os.unlink(out_path)
        self.assertEqual(res.returncode, 0)
        self.assertEqual(res.stdout.strip(), "open")


def execution_log(payload):
    fd, path = tempfile.mkstemp(suffix=".json")
    with os.fdopen(fd, "w") as f:
        json.dump(payload, f)
    return path


class BloatRetry(unittest.TestCase):
    """bloat-retry classifies a failed sweep attempt: budget-shaped failures
    escalate the turn cap; everything else re-dispatches fresh and identical."""

    def classify(self, log_path, turns):
        res = run("bloat-retry", "--execution-log", log_path, "--turns", str(turns))
        self.assertEqual(res.returncode, 0, res.stdout + res.stderr)
        out = dict(line.split("=", 1) for line in res.stdout.strip().splitlines())
        return out, res.stderr

    def test_max_turns_escalates_budget_1_5x(self):
        # SDK stream format: array of events, result event last.
        log = execution_log([
            {"type": "system", "subtype": "init"},
            {"type": "result", "subtype": "error_max_turns",
             "is_error": True, "num_turns": 21},
        ])
        out, err = self.classify(log, 20)
        os.unlink(log)
        self.assertEqual(out, {"mode": "escalate", "turns": "30"})
        self.assertIn("max", err.lower())  # self-explaining reason on stderr

    def test_escalation_caps_at_60(self):
        log = execution_log(
            {"type": "result", "subtype": "error_max_turns", "is_error": True})
        out, _ = self.classify(log, 45)
        os.unlink(log)
        self.assertEqual(out, {"mode": "escalate", "turns": "60"})

    def test_non_budget_failure_is_fresh_identical(self):
        # Attempt finished (subtype success) but the seam validator rejected
        # the result — variance-shaped garbage, so a fresh identical retry.
        log = execution_log([{"type": "result", "subtype": "success",
                              "is_error": False, "num_turns": 9}])
        out, _ = self.classify(log, 20)
        os.unlink(log)
        self.assertEqual(out, {"mode": "fresh", "turns": "20"})

    def test_missing_log_is_fresh_identical(self):
        out, err = self.classify("/nonexistent/execution.json", 24)
        self.assertEqual(out, {"mode": "fresh", "turns": "24"})
        self.assertIn("no execution log", err)

    def test_bad_turns_exits_2(self):
        res = run("bloat-retry", "--execution-log", "/dev/null", "--turns", "0")
        self.assertEqual(res.returncode, 2)


if __name__ == "__main__":
    unittest.main(verbosity=2)
