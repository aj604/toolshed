#!/usr/bin/env python3
"""Black-box tests for detecting-doc-drift's validate-drift-output.py.

Tests the script as a subprocess: real stdin/file input, real exit codes,
real stderr messages. Run: python3 tests/scripts/validate-drift-output_test.py
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
    "plugins", "doc-lifecycle", "skills", "detecting-doc-drift",
    "scripts", "validate-drift-output.py",
)


def rec(**over):
    """A well-formed VERIFIED record; override fields per test."""
    base = {
        "claim": "README mentions make test",
        "location": "README.md:5",
        "kind": "command",
        "tier": 1,
        "verdict": "VERIFIED",
        "evidence": "Makefile has `test:`",
        "fix": None,
    }
    base.update(over)
    return base


def run(payload, as_file=False):
    """Run the validator on payload (a Python obj, JSON-encoded, or raw str)."""
    text = payload if isinstance(payload, str) else json.dumps(payload)
    if as_file:
        with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as f:
            f.write(text)
            path = f.name
        try:
            return subprocess.run(
                [sys.executable, SCRIPT, path],
                capture_output=True, text=True,
            )
        finally:
            os.unlink(path)
    return subprocess.run(
        [sys.executable, SCRIPT],
        input=text, capture_output=True, text=True,
    )


class ValidCases(unittest.TestCase):
    def test_bare_array_of_valid_records_passes(self):
        r = run([rec()])
        self.assertEqual(r.returncode, 0, r.stderr)

    def test_object_with_matching_summary_passes(self):
        payload = {"records": [rec()], "summary": {"verified": 1, "stale": 0, "unverifiable": 0}}
        r = run(payload)
        self.assertEqual(r.returncode, 0, r.stderr)

    def test_recomputes_authoritative_summary_on_stdout(self):
        records = [
            rec(verdict="VERIFIED", fix=None),
            rec(verdict="STALE", fix="use make check"),
            rec(verdict="UNVERIFIABLE", fix=None),
        ]
        r = run(records)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("'verified': 1", r.stdout)
        self.assertIn("'stale': 1", r.stdout)
        self.assertIn("'unverifiable': 1", r.stdout)

    def test_reads_from_file_argument(self):
        r = run([rec()], as_file=True)
        self.assertEqual(r.returncode, 0, r.stderr)


class EnumViolations(unittest.TestCase):
    def test_invented_kind_rejected(self):
        r = run([rec(kind="schema_mismatch")])
        self.assertEqual(r.returncode, 1)
        self.assertIn("kind", r.stderr)

    def test_invalid_verdict_rejected(self):
        r = run([rec(verdict="MAYBE")])
        self.assertEqual(r.returncode, 1)
        self.assertIn("verdict", r.stderr)

    def test_invalid_tier_rejected(self):
        r = run([rec(tier=4)])
        self.assertEqual(r.returncode, 1)
        self.assertIn("tier", r.stderr)

    def test_bool_tier_rejected(self):
        # JSON `true` is `True` in Python, and `True == 1` — must not slip through.
        r = run('[%s]' % json.dumps(rec(tier=True)))
        self.assertEqual(r.returncode, 1)
        self.assertIn("tier", r.stderr)

    def test_float_tier_rejected(self):
        # `1.0 == 1` — a float tier must not slip through either.
        r = run('[%s]' % json.dumps(rec(tier=1.0)))
        self.assertEqual(r.returncode, 1)
        self.assertIn("tier", r.stderr)


class FieldRules(unittest.TestCase):
    def test_missing_required_field_rejected(self):
        bad = rec()
        del bad["claim"]
        r = run([bad])
        self.assertEqual(r.returncode, 1)
        self.assertIn("claim", r.stderr)

    def test_empty_evidence_rejected_even_for_verified(self):
        r = run([rec(verdict="VERIFIED", evidence="", fix=None)])
        self.assertEqual(r.returncode, 1)
        self.assertIn("evidence", r.stderr)

    def test_location_without_line_rejected(self):
        r = run([rec(location="CLAUDE.md")])
        self.assertEqual(r.returncode, 1)
        self.assertIn("location", r.stderr)

    def test_location_line_range_accepted(self):
        r = run([rec(location="services/worker/worker.js:17-19")])
        self.assertEqual(r.returncode, 0, r.stderr)


class FixRule(unittest.TestCase):
    def test_stale_without_fix_rejected(self):
        r = run([rec(verdict="STALE", fix=None)])
        self.assertEqual(r.returncode, 1)
        self.assertIn("fix", r.stderr)

    def test_verified_with_fix_rejected(self):
        r = run([rec(verdict="VERIFIED", fix="something")])
        self.assertEqual(r.returncode, 1)
        self.assertIn("fix", r.stderr)

    def test_unverifiable_with_fix_rejected(self):
        r = run([rec(verdict="UNVERIFIABLE", fix="something")])
        self.assertEqual(r.returncode, 1)
        self.assertIn("fix", r.stderr)


class SummaryRule(unittest.TestCase):
    def test_summary_mismatch_rejected(self):
        payload = {"records": [rec()], "summary": {"verified": 5, "stale": 0, "unverifiable": 0}}
        r = run(payload)
        self.assertEqual(r.returncode, 1)
        self.assertIn("summary", r.stderr)


class BadInput(unittest.TestCase):
    def test_malformed_json_exits_2(self):
        r = run("{not json")
        self.assertEqual(r.returncode, 2)

    def test_wrong_toplevel_shape_exits_2(self):
        r = run({"foo": "bar"})
        self.assertEqual(r.returncode, 2)


if __name__ == "__main__":
    unittest.main(verbosity=2)
