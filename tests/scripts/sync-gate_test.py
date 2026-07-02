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


if __name__ == "__main__":
    unittest.main(verbosity=2)
