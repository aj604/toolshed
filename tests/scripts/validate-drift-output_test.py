#!/usr/bin/env python3
"""Black-box tests for detecting-doc-drift's validate-drift-output.py.

Tests the script as a subprocess: real stdin/file input, real exit codes,
real stderr messages. The contract under test is the engine's verdicts
artifact (`doclifecycle/drift.py`, `--verdicts`), not the legacy wrapped
records shape. Run: python3 tests/scripts/validate-drift-output_test.py
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
    """A well-formed judged VERIFIED verdict; override fields per test."""
    base = {
        "unit": 4,
        "assertion_class": "factual",
        "verdict": "VERIFIED",
        "kind": "command",
        "tier": 1,
        "evidence": {
            "source": "Makefile",
            "line": 12,
            "observed": "`test:` target runs node --test",
        },
    }
    base.update(over)
    return base


def doc(path="README.md", **over):
    """A well-formed examined document entry; override fields per test."""
    base = {"path": path, "status": "ok", "verdicts": [rec()]}
    base.update(over)
    return base


def payload(*documents, **over):
    """The verdicts artifact wrapping the given document entries."""
    base = {"documents": list(documents) or [doc()]}
    base.update(over)
    return base


def run(data, as_file=False):
    """Run the validator on data (a Python obj, JSON-encoded, or raw str)."""
    text = data if isinstance(data, str) else json.dumps(data)
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
    def test_bare_documents_object_passes(self):
        r = run(payload())
        self.assertEqual(r.returncode, 0, r.stderr)

    def test_schema_version_one_passes(self):
        r = run(payload(schema_version=1))
        self.assertEqual(r.returncode, 0, r.stderr)

    def test_empty_documents_list_passes(self):
        r = run({"documents": []})
        self.assertEqual(r.returncode, 0, r.stderr)

    def test_failed_entry_with_reason_passes(self):
        entry = {"path": "docs/api.md", "status": "failed",
                 "reason": "the generator that writes it was not runnable here"}
        r = run(payload(entry))
        self.assertEqual(r.returncode, 0, r.stderr)

    def test_chunk_is_accepted_on_an_entry(self):
        r = run(payload(doc(chunk="chunk-3")))
        self.assertEqual(r.returncode, 0, r.stderr)

    def test_non_assertive_unit_without_a_verdict_passes(self):
        entry = doc(verdicts=[{"unit": 0, "assertion_class": "non-assertive"}])
        r = run(payload(entry))
        self.assertEqual(r.returncode, 0, r.stderr)

    def test_normative_unit_may_be_unjudged(self):
        entry = doc(verdicts=[{"unit": 2, "assertion_class": "normative"}])
        r = run(payload(entry))
        self.assertEqual(r.returncode, 0, r.stderr)

    def test_rationale_unit_may_be_judged(self):
        entry = doc(verdicts=[rec(assertion_class="rationale")])
        r = run(payload(entry))
        self.assertEqual(r.returncode, 0, r.stderr)

    def test_digest_unit_is_accepted(self):
        r = run(payload(doc(verdicts=[rec(unit="a" * 64)])))
        self.assertEqual(r.returncode, 0, r.stderr)

    def test_unit_ordinal_zero_passes(self):
        r = run(payload(doc(verdicts=[rec(unit=0)])))
        self.assertEqual(r.returncode, 0, r.stderr)

    def test_stale_with_fix_passes(self):
        entry = doc(verdicts=[rec(verdict="STALE", fix="Run tests with `make check`.")])
        r = run(payload(entry))
        self.assertEqual(r.returncode, 0, r.stderr)

    def test_unverifiable_without_a_citation_passes(self):
        entry = doc(verdicts=[rec(
            verdict="UNVERIFIABLE",
            kind="value",
            tier=3,
            evidence={"observed": "no threshold named anywhere in the repo"},
        )])
        r = run(payload(entry))
        self.assertEqual(r.returncode, 0, r.stderr)

    def test_command_citation_passes(self):
        entry = doc(verdicts=[rec(evidence={
            "command": "gh label list",
            "observed": "needs-triage exists",
        })])
        r = run(payload(entry))
        self.assertEqual(r.returncode, 0, r.stderr)

    def test_recomputes_authoritative_summary_on_stdout(self):
        entry = doc(verdicts=[
            rec(unit=1, verdict="VERIFIED"),
            rec(unit=2, verdict="STALE", fix="use `make check`"),
            rec(unit=3, verdict="UNVERIFIABLE",
                evidence={"observed": "nothing checkable named"}),
        ])
        r = run(payload(entry))
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn('summary: {"verified": 1, "stale": 1, "unverifiable": 1}', r.stdout)

    def test_summary_counts_across_all_documents(self):
        a = doc("README.md", verdicts=[rec(unit=1, verdict="VERIFIED")])
        b = doc("CLAUDE.md", verdicts=[rec(unit=1, verdict="VERIFIED")])
        r = run(payload(a, b))
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn('summary: {"verified": 2, "stale": 0, "unverifiable": 0}', r.stdout)

    def test_success_prints_ok_line(self):
        r = run(payload())
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("OK:", r.stdout)

    def test_reads_from_file_argument(self):
        r = run(payload(), as_file=True)
        self.assertEqual(r.returncode, 0, r.stderr)


class EnumViolations(unittest.TestCase):
    def test_invalid_verdict_rejected(self):
        r = run(payload(doc(verdicts=[rec(verdict="MAYBE")])))
        self.assertEqual(r.returncode, 1)
        self.assertIn("verdict", r.stderr)

    def test_invented_kind_rejected(self):
        r = run(payload(doc(verdicts=[rec(kind="schema_mismatch")])))
        self.assertEqual(r.returncode, 1)
        self.assertIn("kind", r.stderr)

    def test_invalid_tier_rejected(self):
        r = run(payload(doc(verdicts=[rec(tier=4)])))
        self.assertEqual(r.returncode, 1)
        self.assertIn("tier", r.stderr)

    def test_bool_tier_rejected(self):
        # JSON `true` is `True` in Python, and `True == 1` — must not slip through.
        r = run(json.dumps(payload(doc(verdicts=[rec(tier=True)]))))
        self.assertEqual(r.returncode, 1)
        self.assertIn("tier", r.stderr)

    def test_float_tier_rejected(self):
        # `1.0 == 1` — a float tier must not slip through either.
        r = run(json.dumps(payload(doc(verdicts=[rec(tier=1.0)]))))
        self.assertEqual(r.returncode, 1)
        self.assertIn("tier", r.stderr)

    def test_unknown_assertion_class_rejected(self):
        r = run(payload(doc(verdicts=[rec(assertion_class="prose")])))
        self.assertEqual(r.returncode, 1)
        self.assertIn("assertion_class", r.stderr)

    def test_invalid_entry_status_rejected(self):
        r = run(payload(doc(status="skipped")))
        self.assertEqual(r.returncode, 1)
        self.assertIn("status", r.stderr)


class EntryRules(unittest.TestCase):
    def test_ok_entry_with_a_reason_rejected(self):
        r = run(payload(doc(reason="ran out of time")))
        self.assertEqual(r.returncode, 1)
        self.assertIn("reason", r.stderr)

    def test_ok_entry_without_verdicts_rejected(self):
        entry = {"path": "README.md", "status": "ok"}
        r = run(payload(entry))
        self.assertEqual(r.returncode, 1)
        self.assertIn("verdicts", r.stderr)

    def test_failed_entry_without_reason_rejected(self):
        entry = {"path": "README.md", "status": "failed"}
        r = run(payload(entry))
        self.assertEqual(r.returncode, 1)
        self.assertIn("reason", r.stderr)

    def test_failed_entry_with_verdicts_rejected(self):
        entry = {"path": "README.md", "status": "failed",
                 "reason": "unreadable", "verdicts": [rec()]}
        r = run(payload(entry))
        self.assertEqual(r.returncode, 1)
        self.assertIn("verdicts", r.stderr)

    def test_empty_reason_rejected(self):
        entry = {"path": "README.md", "status": "failed", "reason": "   "}
        r = run(payload(entry))
        self.assertEqual(r.returncode, 1)
        self.assertIn("reason", r.stderr)

    def test_entry_without_path_rejected(self):
        entry = {"status": "ok", "verdicts": [rec()]}
        r = run(payload(entry))
        self.assertEqual(r.returncode, 1)
        self.assertIn("path", r.stderr)

    def test_empty_path_rejected(self):
        r = run(payload(doc(path="")))
        self.assertEqual(r.returncode, 1)
        self.assertIn("path", r.stderr)

    def test_unexpected_entry_field_rejected(self):
        r = run(payload(doc(severity="high")))
        self.assertEqual(r.returncode, 1)
        self.assertIn("severity", r.stderr)

    def test_duplicate_document_rejected(self):
        r = run(payload(doc("README.md"), doc("README.md")))
        self.assertEqual(r.returncode, 1)
        self.assertIn("README.md", r.stderr)

    def test_empty_chunk_rejected(self):
        r = run(payload(doc(chunk="")))
        self.assertEqual(r.returncode, 1)
        self.assertIn("chunk", r.stderr)

    def test_non_object_entry_rejected(self):
        r = run(payload("README.md"))
        self.assertEqual(r.returncode, 1)
        self.assertIn("documents[0]", r.stderr)

    def test_verdicts_not_a_list_rejected(self):
        r = run(payload(doc(verdicts={"unit": 1})))
        self.assertEqual(r.returncode, 1)
        self.assertIn("verdicts", r.stderr)


class FieldRules(unittest.TestCase):
    def test_missing_unit_rejected(self):
        bad = rec()
        del bad["unit"]
        r = run(payload(doc(verdicts=[bad])))
        self.assertEqual(r.returncode, 1)
        self.assertIn("unit", r.stderr)

    def test_missing_assertion_class_rejected(self):
        bad = rec()
        del bad["assertion_class"]
        r = run(payload(doc(verdicts=[bad])))
        self.assertEqual(r.returncode, 1)
        self.assertIn("assertion_class", r.stderr)

    def test_unexpected_verdict_field_rejected(self):
        r = run(payload(doc(verdicts=[rec(location="README.md:5")])))
        self.assertEqual(r.returncode, 1)
        self.assertIn("location", r.stderr)

    def test_legacy_record_shape_rejected(self):
        # The shape this skill used to teach must not validate any more.
        legacy = {"claim": "make test runs the suite", "location": "README.md:5",
                  "kind": "command", "tier": 1, "verdict": "VERIFIED",
                  "evidence": "Makefile has `test:`", "fix": None}
        r = run(payload(doc(verdicts=[legacy])))
        self.assertEqual(r.returncode, 1)

    def test_legacy_wrapped_toplevel_rejected(self):
        r = run({"records": [], "summary": {"verified": 0, "stale": 0,
                                            "unverifiable": 0}})
        self.assertEqual(r.returncode, 2)

    def test_bool_unit_rejected(self):
        r = run(json.dumps(payload(doc(verdicts=[rec(unit=True)]))))
        self.assertEqual(r.returncode, 1)
        self.assertIn("unit", r.stderr)

    def test_negative_unit_rejected(self):
        r = run(payload(doc(verdicts=[rec(unit=-1)])))
        self.assertEqual(r.returncode, 1)
        self.assertIn("unit", r.stderr)

    def test_non_digest_string_unit_rejected(self):
        r = run(payload(doc(verdicts=[rec(unit="the second sentence")])))
        self.assertEqual(r.returncode, 1)
        self.assertIn("unit", r.stderr)

    def test_factual_unit_without_a_verdict_rejected(self):
        entry = doc(verdicts=[{"unit": 1, "assertion_class": "factual"}])
        r = run(payload(entry))
        self.assertEqual(r.returncode, 1)
        self.assertIn("factual", r.stderr)

    def test_partially_judged_unit_rejected(self):
        bad = rec()
        del bad["tier"]
        r = run(payload(doc(verdicts=[bad])))
        self.assertEqual(r.returncode, 1)
        self.assertIn("tier", r.stderr)

    def test_non_assertive_unit_with_a_verdict_rejected(self):
        r = run(payload(doc(verdicts=[rec(assertion_class="non-assertive")])))
        self.assertEqual(r.returncode, 1)
        self.assertIn("non-assertive", r.stderr)

    def test_non_object_verdict_rejected(self):
        r = run(payload(doc(verdicts=["VERIFIED"])))
        self.assertEqual(r.returncode, 1)
        self.assertIn("verdicts[0]", r.stderr)


class EvidenceRules(unittest.TestCase):
    def test_missing_evidence_rejected(self):
        bad = rec()
        del bad["evidence"]
        r = run(payload(doc(verdicts=[bad])))
        self.assertEqual(r.returncode, 1)
        self.assertIn("evidence", r.stderr)

    def test_evidence_string_rejected(self):
        # The legacy contract's one-line string is no longer an evidence value.
        r = run(payload(doc(verdicts=[rec(evidence="Makefile has `test:`")])))
        self.assertEqual(r.returncode, 1)
        self.assertIn("evidence", r.stderr)

    def test_missing_observed_rejected(self):
        r = run(payload(doc(verdicts=[rec(evidence={"source": "Makefile"})])))
        self.assertEqual(r.returncode, 1)
        self.assertIn("observed", r.stderr)

    def test_multiline_observed_rejected(self):
        entry = doc(verdicts=[rec(evidence={
            "source": "Makefile", "observed": "test:\n\tnode --test"})])
        r = run(payload(entry))
        self.assertEqual(r.returncode, 1)
        self.assertIn("observed", r.stderr)

    def test_unexpected_evidence_field_rejected(self):
        entry = doc(verdicts=[rec(evidence={
            "source": "Makefile", "observed": "has a test target",
            "note": "checked twice"})])
        r = run(payload(entry))
        self.assertEqual(r.returncode, 1)
        self.assertIn("note", r.stderr)

    def test_two_citations_rejected(self):
        entry = doc(verdicts=[rec(evidence={
            "source": "Makefile", "command": "make -n test",
            "observed": "has a test target"})])
        r = run(payload(entry))
        self.assertEqual(r.returncode, 1)
        self.assertIn("evidence", r.stderr)

    def test_verified_without_a_citation_rejected(self):
        entry = doc(verdicts=[rec(evidence={"observed": "has a test target"})])
        r = run(payload(entry))
        self.assertEqual(r.returncode, 1)
        self.assertIn("evidence", r.stderr)

    def test_stale_without_a_citation_rejected(self):
        entry = doc(verdicts=[rec(
            verdict="STALE", fix="Run tests with `make check`.",
            evidence={"observed": "no test target"})])
        r = run(payload(entry))
        self.assertEqual(r.returncode, 1)
        self.assertIn("evidence", r.stderr)

    def test_command_with_line_rejected(self):
        entry = doc(verdicts=[rec(evidence={
            "command": "gh label list", "line": 3,
            "observed": "needs-triage exists"})])
        r = run(payload(entry))
        self.assertEqual(r.returncode, 1)
        self.assertIn("line", r.stderr)

    def test_command_with_shell_syntax_rejected(self):
        entry = doc(verdicts=[rec(evidence={
            "command": "gh label list | grep triage",
            "observed": "needs-triage exists"})])
        r = run(payload(entry))
        self.assertEqual(r.returncode, 1)
        self.assertIn("command", r.stderr)

    def test_command_with_substitution_rejected(self):
        entry = doc(verdicts=[rec(evidence={
            "command": "gh label list $(whoami)",
            "observed": "needs-triage exists"})])
        r = run(payload(entry))
        self.assertEqual(r.returncode, 1)
        self.assertIn("command", r.stderr)

    def test_line_zero_rejected(self):
        entry = doc(verdicts=[rec(evidence={
            "source": "Makefile", "line": 0, "observed": "has a test target"})])
        r = run(payload(entry))
        self.assertEqual(r.returncode, 1)
        self.assertIn("line", r.stderr)

    def test_bool_line_rejected(self):
        entry = doc(verdicts=[rec(evidence={
            "source": "Makefile", "line": True,
            "observed": "has a test target"})])
        r = run(json.dumps(payload(entry)))
        self.assertEqual(r.returncode, 1)
        self.assertIn("line", r.stderr)

    def test_empty_source_rejected(self):
        entry = doc(verdicts=[rec(evidence={
            "source": "", "observed": "has a test target"})])
        r = run(payload(entry))
        self.assertEqual(r.returncode, 1)
        self.assertIn("source", r.stderr)


class FixRule(unittest.TestCase):
    def test_stale_without_fix_rejected(self):
        r = run(payload(doc(verdicts=[rec(verdict="STALE")])))
        self.assertEqual(r.returncode, 1)
        self.assertIn("fix", r.stderr)

    def test_stale_with_null_fix_rejected(self):
        r = run(payload(doc(verdicts=[rec(verdict="STALE", fix=None)])))
        self.assertEqual(r.returncode, 1)
        self.assertIn("fix", r.stderr)

    def test_stale_with_empty_fix_rejected(self):
        r = run(payload(doc(verdicts=[rec(verdict="STALE", fix="")])))
        self.assertEqual(r.returncode, 1)
        self.assertIn("fix", r.stderr)

    def test_stale_with_non_string_fix_rejected(self):
        r = run(payload(doc(verdicts=[rec(verdict="STALE", fix=123)])))
        self.assertEqual(r.returncode, 1)
        self.assertIn("fix", r.stderr)

    def test_verified_with_fix_rejected(self):
        r = run(payload(doc(verdicts=[rec(fix="something")])))
        self.assertEqual(r.returncode, 1)
        self.assertIn("fix", r.stderr)

    def test_unverifiable_with_fix_rejected(self):
        entry = doc(verdicts=[rec(
            verdict="UNVERIFIABLE", fix="something",
            evidence={"observed": "nothing checkable named"})])
        r = run(payload(entry))
        self.assertEqual(r.returncode, 1)
        self.assertIn("fix", r.stderr)

    def test_verified_with_null_fix_passes(self):
        # The engine tolerates an explicit null on an unfixed verdict.
        r = run(payload(doc(verdicts=[rec(fix=None)])))
        self.assertEqual(r.returncode, 0, r.stderr)

    def test_multiline_fix_passes(self):
        # Span ownership is the engine's call; LF itself is legal shape.
        entry = doc(verdicts=[rec(
            verdict="STALE",
            fix="- `make check` runs the suite\n  against every package")])
        r = run(payload(entry))
        self.assertEqual(r.returncode, 0, r.stderr)

    def test_fix_with_blank_physical_line_rejected(self):
        entry = doc(verdicts=[rec(verdict="STALE", fix="first line\n\nthird line")])
        r = run(payload(entry))
        self.assertEqual(r.returncode, 1)
        self.assertIn("fix", r.stderr)

    def test_fix_with_carriage_return_rejected(self):
        entry = doc(verdicts=[rec(verdict="STALE", fix="first line\r\nsecond line")])
        r = run(payload(entry))
        self.assertEqual(r.returncode, 1)
        self.assertIn("fix", r.stderr)

    def test_fix_with_nul_rejected(self):
        entry = doc(verdicts=[rec(verdict="STALE", fix="first\x00second")])
        r = run(payload(entry))
        self.assertEqual(r.returncode, 1)
        self.assertIn("fix", r.stderr)


class BadInput(unittest.TestCase):
    def test_malformed_json_exits_2(self):
        r = run("{not json")
        self.assertEqual(r.returncode, 2)

    def test_toplevel_array_exits_2(self):
        r = run([doc()])
        self.assertEqual(r.returncode, 2)

    def test_missing_documents_key_exits_2(self):
        r = run({"schema_version": 1})
        self.assertEqual(r.returncode, 2)

    def test_documents_not_a_list_exits_2(self):
        r = run({"documents": {"README.md": []}})
        self.assertEqual(r.returncode, 2)

    def test_unexpected_toplevel_key_exits_2(self):
        r = run(payload(summary={"verified": 1}))
        self.assertEqual(r.returncode, 2)

    def test_unsupported_schema_version_exits_2(self):
        r = run(payload(schema_version=2))
        self.assertEqual(r.returncode, 2)
        self.assertIn("schema_version", r.stderr)

    def test_bool_schema_version_exits_2(self):
        r = run(json.dumps(payload(schema_version=True)))
        self.assertEqual(r.returncode, 2)
        self.assertIn("schema_version", r.stderr)

    def test_extra_argv_is_usage_error(self):
        r = subprocess.run(
            [sys.executable, SCRIPT, "one.json", "two.json"],
            capture_output=True, text=True,
        )
        self.assertEqual(r.returncode, 2)
        self.assertIn("usage:", r.stderr)

    def test_nonexistent_file_exits_2(self):
        r = subprocess.run(
            [sys.executable, SCRIPT, "/no/such/verdicts.json"],
            capture_output=True, text=True,
        )
        self.assertEqual(r.returncode, 2)
        self.assertIn("error:", r.stderr)


class FailureReporting(unittest.TestCase):
    def test_failure_count_line(self):
        r = run(payload(doc(verdicts=[rec(tier=4)])))
        self.assertEqual(r.returncode, 1)
        self.assertIn("FAILED: 1 contract violation(s)", r.stderr)

    def test_violation_names_document_and_index(self):
        r = run(payload(doc("docs/api.md", verdicts=[rec(tier=4)])))
        self.assertEqual(r.returncode, 1)
        self.assertIn("docs/api.md:verdicts[0]", r.stderr)

    def test_all_violations_reported_in_one_pass(self):
        entry = doc(verdicts=[rec(tier=4), rec(verdict="MAYBE")])
        r = run(payload(entry))
        self.assertEqual(r.returncode, 1)
        self.assertIn("FAILED: 2 contract violation(s)", r.stderr)


if __name__ == "__main__":
    unittest.main(verbosity=2)
