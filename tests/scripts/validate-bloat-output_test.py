#!/usr/bin/env python3
"""Black-box tests for detecting-doc-bloat's validate-bloat-output.py (contract v2).

Tests the script as a subprocess: real stdin/file input, real exit codes,
real stderr messages. Covers the three duties: final wrapped v2 reports
(with the legible v1 reject), chunk seam validation (--chunk/--manifest),
and assembly (--assemble/--out/--allow-partial).
Run: python3 tests/scripts/validate-bloat-output_test.py
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
    """A well-formed v2 CUT record; override fields per test."""
    base = {
        "id": "B1",
        "doc": "README.md",
        "location": "README.md:12",
        "verdict": "CUT",
        "evidence": "README.md:12 restates src/notify.py:3 verbatim",
        "proposal": None,
        "status": None,
        "files": None,
    }
    base.update(over)
    return base


def distill_ready(**over):
    base = rec(id="B9", doc="docs/plans/old-design.md", location=None,
               verdict="DISTILL", status="ready",
               evidence="implementation landed: src/notify.py implements the design")
    base.update(over)
    return base


def policy_rec(**over):
    base = rec(id="B7", doc="docs/superpowers", location=None,
               verdict="POLICY", status=None,
               evidence="10 dated plan/spec artifacts for merged work — one class",
               proposal="Ephemeral process artifacts; retire after the work merges.",
               files=["docs/superpowers/plans/a.md", "docs/superpowers/specs/b.md"])
    base.update(over)
    return base


def summary_for(records):
    counts = {"cut": 0, "condense": 0, "extract_and_move": 0,
              "retire_doc": 0, "merge_doc": 0, "distill": 0, "policy": 0}
    key = {"CUT": "cut", "CONDENSE": "condense", "EXTRACT-AND-MOVE": "extract_and_move",
           "RETIRE-DOC": "retire_doc", "MERGE-DOC": "merge_doc",
           "DISTILL": "distill", "POLICY": "policy"}
    for r in records:
        if r.get("verdict") in key:
            counts[key[r["verdict"]]] += 1
    return counts


def wrap(records, **over):
    obj = {"schema": 2, "records": records, "summary": summary_for(records)}
    obj.update(over)
    return obj


def run(payload, *argv, as_file=False):
    text = payload if isinstance(payload, str) else json.dumps(payload)
    if as_file or argv:
        with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as f:
            f.write(text)
            path = f.name
        try:
            return subprocess.run(
                [sys.executable, SCRIPT, path, *argv],
                capture_output=True, text=True)
        finally:
            os.unlink(path)
    return subprocess.run(
        [sys.executable, SCRIPT], input=text, capture_output=True, text=True)


def run_argv(*argv):
    return subprocess.run(
        [sys.executable, SCRIPT, *argv], capture_output=True, text=True)


class SchemaGate(unittest.TestCase):
    def test_v2_wrapped_report_valid(self):
        r = run(wrap([rec()]))
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("OK: 1 record(s) valid", r.stdout)

    def test_v2_report_without_summary_valid(self):
        r = run({"schema": 2, "records": [rec()]})
        self.assertEqual(r.returncode, 0, r.stderr)

    def test_bare_array_is_legible_v1_reject(self):
        r = run([rec()])
        self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
        self.assertIn("schema v1", r.stderr)
        self.assertIn("regenerate", r.stderr)

    def test_wrapped_without_schema_is_v1_reject(self):
        r = run({"records": [rec()], "summary": summary_for([rec()])})
        self.assertEqual(r.returncode, 1)
        self.assertIn("schema v1", r.stderr)

    def test_record_with_payload_field_rejected(self):
        bad = distill_ready()
        bad["payload"] = {"claims": [], "decision_entry": "x"}
        r = run(wrap([bad]))
        self.assertEqual(r.returncode, 1)
        self.assertIn("payload", r.stderr)
        self.assertIn("post-approval", r.stderr)

    def test_summary_with_policy_key_matches(self):
        r = run(wrap([rec(), policy_rec()]))
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn('"policy": 1', r.stdout)

    def test_v1_six_key_summary_rejected(self):
        report = wrap([rec()])
        del report["summary"]["policy"]
        r = run(report)
        self.assertEqual(r.returncode, 1)
        self.assertIn("summary", r.stderr)

    def test_summary_mismatch_rejected(self):
        report = wrap([rec()])
        report["summary"]["cut"] = 2
        r = run(report)
        self.assertEqual(r.returncode, 1)
        self.assertIn("does not match", r.stderr)

    def test_file_input(self):
        r = run(wrap([rec()]), as_file=True)
        self.assertEqual(r.returncode, 0, r.stderr)

    def test_bad_json_exits_2(self):
        r = run("not json {")
        self.assertEqual(r.returncode, 2)


class PolicyRecords(unittest.TestCase):
    def assert_fails(self, record, fragment):
        r = run(wrap([record]))
        self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
        self.assertIn(fragment, r.stderr)

    def test_valid_policy_record(self):
        r = run(wrap([policy_rec()]))
        self.assertEqual(r.returncode, 0, r.stderr)

    def test_policy_requires_files(self):
        self.assert_fails(policy_rec(files=None), "files")

    def test_policy_files_must_be_nonempty(self):
        self.assert_fails(policy_rec(files=[]), "files")

    def test_policy_files_entries_must_be_nonempty_strings(self):
        self.assert_fails(policy_rec(files=["a.md", "  "]), "files")

    def test_policy_requires_proposal_text(self):
        self.assert_fails(policy_rec(proposal=None), "proposal")

    def test_policy_forbids_location(self):
        self.assert_fails(policy_rec(location="docs/superpowers/plans/a.md:1"),
                          "location")

    def test_policy_forbids_status(self):
        self.assert_fails(policy_rec(status="ready"), "status")

    def test_non_policy_forbids_files(self):
        self.assert_fails(rec(files=["a.md"]), "files")


class DistillV2(unittest.TestCase):
    def test_ready_without_payload_valid(self):
        r = run(wrap([distill_ready()]))
        self.assertEqual(r.returncode, 0, r.stderr)

    def test_pending_without_payload_valid(self):
        pending = distill_ready(status="pending-implementation",
                                evidence="grep for RetryQueue returns nothing")
        r = run(wrap([pending]))
        self.assertEqual(r.returncode, 0, r.stderr)

    def test_distill_needs_status(self):
        r = run(wrap([distill_ready(status=None)]))
        self.assertEqual(r.returncode, 1)
        self.assertIn("status", r.stderr)


class InvalidRecords(unittest.TestCase):
    def assert_fails(self, records, fragment):
        r = run(wrap(records))
        self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
        self.assertIn(fragment, r.stderr)

    def test_missing_field(self):
        bad = rec(); del bad["evidence"]
        report = {"schema": 2, "records": [bad]}
        r = run(report)
        self.assertEqual(r.returncode, 1)
        self.assertIn("missing required field 'evidence'", r.stderr)

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
            [rec(verdict="EXTRACT-AND-MOVE", proposal={"target": "CLAUDE.md"})],
            "proposal")

    def test_merge_proposal_needs_target(self):
        self.assert_fails(
            [rec(id="B5", doc="SETUP.md", location=None, verdict="MERGE-DOC")],
            "proposal")

    def test_non_distill_forbids_status(self):
        self.assert_fails([rec(status="ready")], "status")


class EvidenceSpan(unittest.TestCase):
    """Passage-verdict evidence must open with the passage's extent:
    'file:start-end' ('file:start' if one line), anchored at location."""

    def assert_fails(self, records, fragment):
        r = run(wrap(records))
        self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
        self.assertIn(fragment, r.stderr)

    def test_multiline_span_valid(self):
        r = run(wrap([rec(evidence="README.md:12-20 — nine lines restate src/notify.py:3")]))
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
        r = run(wrap([rec(id="B4", doc="SETUP.md", location=None,
                          verdict="RETIRE-DOC",
                          evidence="carries nothing README.md:6-14 lacks")]))
        self.assertEqual(r.returncode, 0, r.stderr)


class SeamFixture(unittest.TestCase):
    """Shared tempdir with a manifest (one sweep + one policy chunk)."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.chunks_dir = os.path.join(self.tmp.name, "chunks")
        os.makedirs(self.chunks_dir)
        self.manifest = {
            "schema": 1,
            "chunks": [
                {"id": "c-aaa", "kind": "sweep",
                 "docs": [{"path": "README.md", "lines": 20, "hint": "living"},
                          {"path": "RUNBOOK.md", "lines": 5, "hint": "living"}]},
                {"id": "p-bbb", "kind": "policy", "dir": "docs/superpowers",
                 "files": ["docs/superpowers/plans/a.md",
                           "docs/superpowers/specs/b.md"]},
            ],
            "pending": ["c-aaa", "p-bbb"],
        }
        self.manifest_path = os.path.join(self.tmp.name, "manifest.json")
        with open(self.manifest_path, "w", encoding="utf-8") as f:
            json.dump(self.manifest, f)

    def write_chunk(self, name, obj):
        path = os.path.join(self.chunks_dir, name)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(obj, f)
        return path

    def sweep_result(self, records=None):
        return {"chunk": "c-aaa", "records": [rec()] if records is None else records}

    def policy_result(self):
        return {"chunk": "p-bbb",
                "records": [policy_rec(doc="docs/superpowers",
                                       files=self.manifest["chunks"][1]["files"])]}


class ChunkSeam(SeamFixture):
    def check(self, obj, *argv):
        path = self.write_chunk("candidate.json", obj)
        return run_argv("--chunk", path, *argv)

    def check_m(self, obj):
        return self.check(obj, "--manifest", self.manifest_path)

    def test_valid_sweep_chunk_result(self):
        r = self.check_m(self.sweep_result())
        self.assertEqual(r.returncode, 0, r.stderr)

    def test_valid_policy_chunk_result(self):
        r = self.check_m(self.policy_result())
        self.assertEqual(r.returncode, 0, r.stderr)

    def test_empty_records_chunk_is_valid(self):
        r = self.check_m(self.sweep_result([]))
        self.assertEqual(r.returncode, 0, r.stderr)

    def test_chunk_shape_must_be_exact(self):
        r = self.check_m({"chunk": "c-aaa", "records": [], "extra": 1})
        self.assertEqual(r.returncode, 1)
        self.assertIn("chunk result must be exactly", r.stderr)

    def test_record_doc_outside_slice_fails(self):
        r = self.check_m(self.sweep_result([rec(doc="OTHER.md",
                                                location="OTHER.md:1",
                                                evidence="OTHER.md:1 restates x")]))
        self.assertEqual(r.returncode, 1)
        self.assertIn("outside this chunk's slice", r.stderr)

    def test_sweep_chunk_never_emits_policy(self):
        bad = policy_rec(doc="README.md", files=["README.md"])
        r = self.check_m(self.sweep_result([bad]))
        self.assertEqual(r.returncode, 1)
        self.assertIn("never emit POLICY", r.stderr)

    def test_unknown_chunk_id_fails(self):
        r = self.check_m({"chunk": "c-zzz", "records": []})
        self.assertEqual(r.returncode, 1)
        self.assertIn("not in the manifest", r.stderr)

    def test_policy_chunk_exactly_one_policy_record(self):
        r = self.check_m({"chunk": "p-bbb", "records": []})
        self.assertEqual(r.returncode, 1)
        self.assertIn("exactly one", r.stderr)

    def test_policy_files_must_equal_chunk_files(self):
        result = self.policy_result()
        result["records"][0]["files"] = ["docs/superpowers/plans/a.md"]
        r = self.check_m(result)
        self.assertEqual(r.returncode, 1)
        self.assertIn("provenance", r.stderr)

    def test_policy_doc_must_be_chunk_dir(self):
        result = self.policy_result()
        result["records"][0]["doc"] = "docs"
        r = self.check_m(result)
        self.assertEqual(r.returncode, 1)
        self.assertIn("covered dir", r.stderr)

    def test_without_manifest_record_rules_still_apply(self):
        good = self.check(self.sweep_result())
        self.assertEqual(good.returncode, 0, good.stderr)
        bad = self.check(self.sweep_result([rec(verdict="PRUNE")]))
        self.assertEqual(bad.returncode, 1)


class Assembly(SeamFixture):
    def assemble(self, *extra):
        out = os.path.join(self.tmp.name, "bloat-report.json")
        r = run_argv("--assemble", self.chunks_dir,
                     "--manifest", self.manifest_path, "--out", out, *extra)
        return r, out

    def write_both(self):
        self.write_chunk("c-aaa.json", self.sweep_result())
        self.write_chunk("p-bbb.json", self.policy_result())

    def test_assembles_and_renumbers_ids(self):
        self.write_both()
        r, out = self.assemble()
        self.assertEqual(r.returncode, 0, r.stderr)
        with open(out, encoding="utf-8") as f:
            report = json.load(f)
        self.assertEqual(report["schema"], 2)
        self.assertEqual([x["id"] for x in report["records"]], ["B1", "B2"])
        self.assertEqual(report["summary"]["cut"], 1)
        self.assertEqual(report["summary"]["policy"], 1)
        final = run_argv(out)
        self.assertEqual(final.returncode, 0, final.stderr)

    def test_missing_chunk_refused_by_name(self):
        self.write_chunk("c-aaa.json", self.sweep_result())
        r, _ = self.assemble()
        self.assertEqual(r.returncode, 1)
        self.assertIn("p-bbb", r.stderr)
        self.assertIn("partial assembly refused", r.stderr)

    def test_allow_partial_skips_missing_only(self):
        self.write_chunk("c-aaa.json", self.sweep_result())
        r, out = self.assemble("--allow-partial")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("skipping chunk p-bbb", r.stderr)
        with open(out, encoding="utf-8") as f:
            report = json.load(f)
        self.assertEqual(len(report["records"]), 1)

    def test_invalid_chunk_fails_even_with_allow_partial(self):
        self.write_chunk("c-aaa.json", self.sweep_result([rec(verdict="PRUNE")]))
        self.write_chunk("p-bbb.json", self.policy_result())
        for extra in ((), ("--allow-partial",)):
            r, _ = self.assemble(*extra)
            self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
            self.assertIn("c-aaa", r.stderr)

    def test_empty_manifest_assembles_empty_report(self):
        with open(self.manifest_path, "w", encoding="utf-8") as f:
            json.dump({"schema": 1, "chunks": [], "pending": []}, f)
        r, out = self.assemble()
        self.assertEqual(r.returncode, 0, r.stderr)
        with open(out, encoding="utf-8") as f:
            report = json.load(f)
        self.assertEqual(report["records"], [])
        self.assertEqual(sum(report["summary"].values()), 0)

    def test_usage_errors_exit_2(self):
        cases = (
            ("--assemble", self.chunks_dir),                      # no manifest/out
            ("--assemble", self.chunks_dir, "--manifest", self.manifest_path),
            ("--chunk", "x.json", "--assemble", self.chunks_dir,
             "--manifest", self.manifest_path, "--out", "o.json"),
            ("--allow-partial",),
        )
        for argv in cases:
            r = run_argv(*argv)
            self.assertEqual(r.returncode, 2, f"{argv}: {r.stdout}{r.stderr}")


if __name__ == "__main__":
    unittest.main()
