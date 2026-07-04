#!/usr/bin/env python3
"""Black-box tests for detecting-doc-bloat's validate-bloat-output.py.

Tests the script as a subprocess: real stdin/file input, real exit codes,
real stderr messages. Run: python3 tests/scripts/validate-bloat-output_test.py
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
    "plugins", "doc-lifecycle", "skills", "detecting-doc-bloat",
    "scripts", "validate-bloat-output.py",
)


def rec(**over):
    """A well-formed CUT record; override fields per test."""
    base = {
        "id": "B1",
        "doc": "README.md",
        "location": "README.md:12",
        "verdict": "CUT",
        "evidence": "README.md:12 restates src/notify.py:3 verbatim",
        "proposal": None,
        "status": None,
        "payload": None,
    }
    base.update(over)
    return base


def distill_ready(**over):
    base = rec(
        id="B9", doc="docs/plans/old-design.md", location=None,
        verdict="DISTILL", status="ready",
        evidence="implementation landed: src/notify.py implements the design",
        payload={
            "claims": [{
                "claim": "retries are capped at 3",
                "target": "README.md",
                "evidence": "src/notify.py:4 MAX_RETRIES = 3",
            }],
            "decision_entry": "## 2026-07-03 — notify retry design\n- Decided: cap retries at 3.",
        },
    )
    base.update(over)
    return base


def insight(**over):
    base = {
        "insight": "No invalidation API is deliberate: staleness is bounded by TTL.",
        "target": "docs/reference/caching.md",
        "anchor": "docs/plans/old-design.md @ abc1234",
    }
    base.update(over)
    return base


def run(payload, as_file=False):
    text = payload if isinstance(payload, str) else json.dumps(payload)
    if as_file:
        with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as f:
            f.write(text)
            path = f.name
        try:
            return subprocess.run(
                [sys.executable, SCRIPT, path], capture_output=True, text=True,
            )
        finally:
            os.unlink(path)
    return subprocess.run(
        [sys.executable, SCRIPT], input=text, capture_output=True, text=True,
    )


class ValidCases(unittest.TestCase):
    def test_bare_array_valid(self):
        r = run([rec()])
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("OK: 1 record(s) valid", r.stdout)

    def test_full_spectrum_report(self):
        records = [
            rec(),
            rec(id="B2", location="README.md:20", verdict="CONDENSE",
                evidence="README.md:20-24 — five lines carry one fact: make test runs the suite",
                proposal="Run `make test` (only @taskflow/shared has tests)."),
            rec(id="B3", location="README.md:30", verdict="EXTRACT-AND-MOVE",
                evidence="README.md:30-31 — operational gotcha in a user-facing doc",
                proposal={"target": "CLAUDE.md", "text": "api refuses to start without .state.json"}),
            rec(id="B4", doc="SETUP.md", location=None, verdict="RETIRE-DOC"),
            rec(id="B5", doc="SETUP.md", location=None, verdict="MERGE-DOC",
                proposal={"target": "README.md"}),
            distill_ready(id="B6"),
            rec(id="B7", doc="docs/plans/new-design.md", location=None,
                verdict="DISTILL", status="pending-implementation",
                evidence="PR #12 landed the artifact; implementation not merged"),
        ]
        r = run({"records": records, "summary": {
            "cut": 1, "condense": 1, "extract_and_move": 1,
            "retire_doc": 1, "merge_doc": 1, "distill": 2}})
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn('"distill": 2', r.stdout)

    def test_file_input(self):
        r = run([rec()], as_file=True)
        self.assertEqual(r.returncode, 0, r.stderr)


class InvalidRecords(unittest.TestCase):
    def assert_fails(self, payload, fragment):
        r = run(payload)
        self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
        self.assertIn(fragment, r.stderr)

    def test_missing_field(self):
        bad = rec(); del bad["evidence"]
        self.assert_fails([bad], "missing required field 'evidence'")

    def test_unexpected_field(self):
        self.assert_fails([rec(extra="x")], "unexpected field 'extra'")

    def test_unknown_verdict(self):
        self.assert_fails([rec(verdict="PRUNE")], "verdict")

    def test_duplicate_ids(self):
        self.assert_fails([rec(), rec(location="README.md:13")], "duplicate id")

    def test_empty_evidence(self):
        self.assert_fails([rec(evidence="  ")], "evidence")

    def test_passage_verdict_needs_location(self):
        self.assert_fails([rec(location=None)], "location")

    def test_doc_verdict_forbids_location(self):
        self.assert_fails(
            [rec(id="B4", verdict="RETIRE-DOC", location="README.md:1")], "location")

    def test_condense_needs_proposal(self):
        self.assert_fails([rec(verdict="CONDENSE")], "proposal")

    def test_cut_forbids_proposal(self):
        self.assert_fails([rec(proposal="new text")], "proposal")

    def test_extract_proposal_needs_target_and_text(self):
        self.assert_fails(
            [rec(verdict="EXTRACT-AND-MOVE", proposal={"target": "CLAUDE.md"})], "proposal")

    def test_merge_proposal_needs_target(self):
        self.assert_fails(
            [rec(id="B5", doc="SETUP.md", location=None, verdict="MERGE-DOC")], "proposal")

    def test_non_distill_forbids_status(self):
        self.assert_fails([rec(status="ready")], "status")

    def test_distill_needs_status(self):
        self.assert_fails([distill_ready(status=None)], "status")

    def test_distill_pending_forbids_payload(self):
        bad = distill_ready(status="pending-implementation")
        self.assert_fails([bad], "payload")

    def test_distill_ready_needs_payload(self):
        self.assert_fails([distill_ready(payload=None)], "payload")

    def test_distill_payload_empty_claims_without_insights(self):
        bad = distill_ready()
        bad["payload"]["claims"] = []
        self.assert_fails([bad], "claim")

    def test_distill_payload_unexpected_key(self):
        bad = distill_ready()
        bad["payload"]["notes"] = "x"
        self.assert_fails([bad], "payload")

    def test_insight_missing_anchor(self):
        bad = distill_ready()
        item = insight()
        del item["anchor"]
        bad["payload"]["insights"] = [item]
        self.assert_fails([bad], "insight")

    def test_insight_empty_target(self):
        bad = distill_ready()
        bad["payload"]["insights"] = [insight(target="  ")]
        self.assert_fails([bad], "insight")

    def test_insights_must_be_list(self):
        bad = distill_ready()
        bad["payload"]["insights"] = insight()
        self.assert_fails([bad], "insight")


class DistillInsights(unittest.TestCase):
    """DISTILL ready payload may carry anchored insights bound for a durable
    narrative doc; claims may be empty only when insights carry the residue."""

    def test_claims_plus_insights_valid(self):
        good = distill_ready()
        good["payload"]["insights"] = [insight()]
        r = run([good])
        self.assertEqual(r.returncode, 0, r.stderr)

    def test_insights_only_valid(self):
        good = distill_ready()
        good["payload"]["claims"] = []
        good["payload"]["insights"] = [insight()]
        r = run([good])
        self.assertEqual(r.returncode, 0, r.stderr)

    def test_empty_insights_list_with_claims_valid(self):
        good = distill_ready()
        good["payload"]["insights"] = []
        r = run([good])
        self.assertEqual(r.returncode, 0, r.stderr)

    def test_empty_claims_and_empty_insights_fails(self):
        bad = distill_ready()
        bad["payload"]["claims"] = []
        bad["payload"]["insights"] = []
        r = run([bad])
        self.assertEqual(r.returncode, 1, r.stdout + r.stderr)


class EvidenceSpan(unittest.TestCase):
    """Passage-verdict evidence must open with the passage's extent:
    'file:start-end' ('file:start' if one line), anchored at location."""

    def assert_fails(self, payload, fragment):
        r = run(payload)
        self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
        self.assertIn(fragment, r.stderr)

    def test_multiline_span_valid(self):
        r = run([rec(evidence="README.md:12-20 — nine lines restate src/notify.py:3")])
        self.assertEqual(r.returncode, 0, r.stderr)

    def test_evidence_without_leading_span_fails(self):
        self.assert_fails(
            [rec(evidence="restates src/notify.py:3 verbatim")], "span")

    def test_span_file_must_match_location(self):
        self.assert_fails(
            [rec(evidence="INSTALL.md:12 restates src/notify.py:3")], "location")

    def test_span_start_must_match_location_line(self):
        self.assert_fails(
            [rec(evidence="README.md:13-20 restates src/notify.py:3")], "location")

    def test_span_end_before_start_fails(self):
        self.assert_fails(
            [rec(evidence="README.md:12-9 restates src/notify.py:3")], "span")

    def test_doclevel_evidence_needs_no_span(self):
        r = run([rec(id="B4", doc="SETUP.md", location=None, verdict="RETIRE-DOC",
                     evidence="carries nothing README.md:6-14 lacks")])
        self.assertEqual(r.returncode, 0, r.stderr)


class SummaryAndInput(unittest.TestCase):
    def test_summary_mismatch(self):
        r = run({"records": [rec()], "summary": {
            "cut": 2, "condense": 0, "extract_and_move": 0,
            "retire_doc": 0, "merge_doc": 0, "distill": 0}})
        self.assertEqual(r.returncode, 1)
        self.assertIn("does not match", r.stderr)

    def test_bad_json_exits_2(self):
        r = run("not json {")
        self.assertEqual(r.returncode, 2)

    def test_non_array_exits_2(self):
        r = run({"foo": 1})
        self.assertEqual(r.returncode, 2)


if __name__ == "__main__":
    unittest.main()
