#!/usr/bin/env python3
"""Black-box tests for scheduling-doc-sync's compare-shadow-lanes.py.

The shadow-mode parity gate (aj604/toolshed#76) compares the legacy drift lane
against the new engine's read-only audit over the same repository. The
comparison has to be a program rather than a reading of two JSON files, so that
the gate's numbers are reproducible and cannot be assembled to suit the verdict.

Tests the script as a subprocess: real argv, real exit codes, real stdout.
Run: python3 tests/scripts/compare-shadow-lanes_test.py
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
    "scripts", "compare-shadow-lanes.py",
)

LEGACY_META = {
    "run": "28847329392",
    "base_commit": "6d525c9dfa92e995631398ff877927b459f95d0f",
    "cost_usd": 2.72,
    "turns": 60,
    "duration_ms": 480000,
}
SHADOW_META = {"cost_usd": 5.44, "turns": 120, "duration_ms": 900000}


def legacy_record(location, claim="a claim", verdict="VERIFIED", fix=None):
    return {
        "claim": claim,
        "location": location,
        "kind": "path",
        "tier": 1,
        "verdict": verdict,
        "evidence": "read it",
        "fix": fix,
    }


def shadow_record(rid, path, unit, code="STALE", line=1, **extra):
    record = {
        "id": rid,
        "digest": "d" * 64,
        "code": code,
        "path": path,
        "units": [unit],
        "location": f"{path}:{line}",
        "assertion": "an assertion",
        "assertion_class": "factual",
        "kind": "path",
        "tier": 1,
        "evidence": {"observed": "it moved", "source": "src/a.py"},
    }
    if code == "STALE":
        record["fix"] = "the replacement line"
    record.update(extra)
    return record


def shadow_report(records=(), declared=("README.md",), excluded=(),
                  examined=(), incomplete=(), status=None):
    return {
        "status": status or ("findings" if records else "clean"),
        "schema_version": 1,
        "lineage": {
            "repository": "origin:github.com/aj604/toolshed",
            "base_commit": "a" * 40,
            "audit_mode": "full",
            "inventory_digest": "b" * 64,
            "registry_digest": "c" * 64,
            "ruleset_version": 1,
            "plugin_version": "0.21.0",
            "evidence_boundary": {"sources": ["**"], "excluded": []},
        },
        "records": list(records),
        "examined": list(examined),
        "incomplete": list(incomplete),
        "scope": {
            "basis": "every living and narrative document",
            "coverage": "whole-inventory",
            "documents": list(declared),
            "excluded": list(excluded),
        },
    }


def examined(path, verified=()):
    return {
        "scope": path,
        "obligation": "assertions",
        "units": 10,
        "classes": {"factual": len(verified)},
        "verdicts": {"VERIFIED": len(verified)},
        "verified": [
            {
                "unit": unit,
                "assertion_class": "factual",
                "location": f"{path}:{line}",
                "kind": "path",
                "tier": 1,
                "evidence": {"observed": "still true", "source": path},
            }
            for unit, line in verified
        ],
    }


def segments(mapping):
    """{path: [(digest, line)]} -> the segmentation payload the tool reads."""
    return {
        "documents": [
            {
                "path": path,
                "units": [
                    {
                        "digest": digest,
                        "line": line,
                        "kind": "sentence",
                        "text": f"unit at {path}:{line}",
                        "assertion_capable": True,
                    }
                    for digest, line in units
                ],
            }
            for path, units in sorted(mapping.items())
        ]
    }


class Harness(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.dir.cleanup)

    def write(self, name, payload):
        path = os.path.join(self.dir.name, name)
        with open(path, "w", encoding="utf-8") as fh:
            json.dump(payload, fh)
        return path

    def compare(self, legacy=None, shadow=None, segs=None,
                legacy_meta=None, shadow_meta=None, extra=()):
        argv = [
            "compare",
            "--legacy", self.write("legacy.json", legacy if legacy is not None
                                   else {"records": [], "summary": {}}),
            "--legacy-meta", self.write("legacy-meta.json",
                                        legacy_meta or LEGACY_META),
            "--shadow", self.write("shadow.json", shadow if shadow is not None
                                   else shadow_report()),
            "--shadow-meta", self.write("shadow-meta.json",
                                        shadow_meta or SHADOW_META),
            "--segments", self.write("segments.json", segs or segments({})),
            *extra,
        ]
        return subprocess.run(
            [sys.executable, SCRIPT, *argv], capture_output=True, text=True
        )

    def compared(self, **kwargs):
        result = self.compare(**kwargs)
        self.assertEqual(result.returncode, 0, result.stderr)
        return json.loads(result.stdout)


class LaneSummaries(Harness):
    def test_legacy_records_are_counted_by_verdict(self):
        out = self.compared(legacy={"records": [
            legacy_record("README.md:3"),
            legacy_record("README.md:9", verdict="STALE", fix="new line"),
            legacy_record("CLAUDE.md:2", verdict="UNVERIFIABLE"),
        ]})
        self.assertEqual(
            out["lanes"]["legacy"]["verdicts"],
            {"STALE": 1, "UNVERIFIABLE": 1, "VERIFIED": 1},
        )
        self.assertEqual(out["lanes"]["legacy"]["records"], 3)

    def test_legacy_documents_come_from_record_locations(self):
        out = self.compared(legacy={"records": [
            legacy_record("docs/a.md:3"),
            legacy_record("docs/a.md:44"),
            legacy_record(".github/workflows/x.yml:6"),
        ]})
        self.assertEqual(
            out["lanes"]["legacy"]["documents"],
            [".github/workflows/x.yml", "docs/a.md"],
        )

    def test_shadow_records_are_counted_by_code(self):
        out = self.compared(shadow=shadow_report(records=[
            shadow_record("D-001", "README.md", "u1"),
            shadow_record("D-002", "README.md", "u2", code="UNVERIFIABLE"),
            shadow_record("D-003", "docs/g.md", "u3", code="ANCHOR-MISSING"),
        ]))
        self.assertEqual(
            out["lanes"]["shadow"]["codes"],
            {"ANCHOR-MISSING": 1, "STALE": 1, "UNVERIFIABLE": 1},
        )

    def test_shadow_state_and_lineage_travel_into_the_comparison(self):
        out = self.compared()
        self.assertEqual(out["lanes"]["shadow"]["status"], "clean")
        self.assertEqual(out["lanes"]["shadow"]["base_commit"], "a" * 40)
        self.assertEqual(out["lanes"]["shadow"]["audit_mode"], "full")

    def test_shadow_incomplete_scopes_are_reported_not_hidden(self):
        report = shadow_report(
            declared=["README.md", "CLAUDE.md"],
            incomplete=[{"scope": "CLAUDE.md", "reason": "no verdicts"}],
            status="partial",
        )
        out = self.compared(shadow=report)
        self.assertEqual(out["lanes"]["shadow"]["status"], "partial")
        self.assertEqual(out["lanes"]["shadow"]["incomplete"], ["CLAUDE.md"])


class Coverage(Harness):
    def test_documents_both_lanes_examined(self):
        out = self.compared(
            legacy={"records": [legacy_record("README.md:3")]},
            shadow=shadow_report(declared=["README.md", "CLAUDE.md"]),
        )
        self.assertEqual(out["coverage"]["both"], ["README.md"])
        self.assertEqual(out["coverage"]["shadow_only"], ["CLAUDE.md"])
        self.assertEqual(out["coverage"]["legacy_only"], [])

    def test_a_legacy_document_the_shadow_scope_excluded_carries_its_reason(self):
        out = self.compared(
            legacy={"records": [legacy_record("docs/plans/p.md:3")]},
            shadow=shadow_report(
                declared=["README.md"],
                excluded=[{"path": "docs/plans/p.md",
                           "reason": "a planning document is not line-verified",
                           "code": "planning-kind"}],
            ),
        )
        self.assertEqual(out["coverage"]["legacy_only"], ["docs/plans/p.md"])
        self.assertEqual(
            out["coverage"]["legacy_only_reasons"]["docs/plans/p.md"],
            {"code": "planning-kind",
             "reason": "a planning document is not line-verified"},
        )

    def test_a_legacy_document_outside_the_inventory_is_named_as_such(self):
        out = self.compared(
            legacy={"records": [legacy_record(".github/workflows/x.yml:6")]},
            shadow=shadow_report(declared=["README.md"]),
        )
        self.assertEqual(
            out["coverage"]["legacy_only_reasons"][".github/workflows/x.yml"],
            {"code": "outside-inventory",
             "reason": "not in the shadow registry's inventory — neither "
                       "declared nor excluded by the audit's scope"},
        )


class AssertionCorrespondence(Harness):
    def test_same_line_same_verdict_is_agreement(self):
        out = self.compared(
            legacy={"records": [legacy_record("README.md:7")]},
            shadow=shadow_report(
                declared=["README.md"],
                examined=[examined("README.md", verified=[("u7", 7)])],
            ),
            segs=segments({"README.md": [("u7", 7)]}),
        )
        self.assertEqual(len(out["assertions"]["agreed"]), 1)
        self.assertEqual(out["assertions"]["agreed"][0]["unit"], "u7")
        self.assertEqual(out["assertions"]["agreed"][0]["verdict"], "VERIFIED")
        self.assertEqual(out["assertions"]["disagreed"], [])

    def test_same_line_different_verdict_is_disagreement(self):
        out = self.compared(
            legacy={"records": [legacy_record("README.md:7")]},
            shadow=shadow_report(
                declared=["README.md"],
                records=[shadow_record("D-001", "README.md", "u7", line=7)],
                examined=[examined("README.md")],
            ),
            segs=segments({"README.md": [("u7", 7)]}),
        )
        self.assertEqual(out["assertions"]["agreed"], [])
        self.assertEqual(len(out["assertions"]["disagreed"]), 1)
        pair = out["assertions"]["disagreed"][0]
        self.assertEqual(pair["legacy_verdict"], "VERIFIED")
        self.assertEqual(pair["shadow_verdict"], "STALE")

    def test_a_legacy_line_that_no_longer_holds_a_unit_is_unresolved(self):
        # The legacy lane's newest report describes an older commit. A record
        # whose line no longer carries a unit cannot be compared, and saying so
        # is the honest answer — not silently counting it as unique.
        out = self.compared(
            legacy={"records": [legacy_record("README.md:900")]},
            shadow=shadow_report(declared=["README.md"],
                                 examined=[examined("README.md")]),
            segs=segments({"README.md": [("u7", 7)]}),
        )
        self.assertEqual(out["assertions"]["agreed"], [])
        self.assertEqual(
            out["assertions"]["legacy_unresolved"],
            [{"path": "README.md", "line": 900,
              "reason": "no assertion unit at that line in the shadow commit's "
                        "segmentation"}],
        )

    def test_a_legacy_record_in_an_unsegmented_document_is_unresolved(self):
        out = self.compared(
            legacy={"records": [legacy_record("docs/gone.md:3")]},
            shadow=shadow_report(declared=["README.md"]),
            segs=segments({"README.md": [("u7", 7)]}),
        )
        self.assertEqual(
            out["assertions"]["legacy_unresolved"][0]["reason"],
            "the document was not segmented by the shadow run",
        )

    def test_shadow_records_with_no_legacy_counterpart_are_shadow_only(self):
        out = self.compared(
            legacy={"records": []},
            shadow=shadow_report(
                declared=["README.md"],
                records=[shadow_record("D-001", "README.md", "u7", line=7)],
                examined=[examined("README.md")],
            ),
            segs=segments({"README.md": [("u7", 7)]}),
        )
        self.assertEqual(out["assertions"]["disagreed"], [])
        self.assertEqual(len(out["assertions"]["shadow_only"]), 1)
        self.assertEqual(out["assertions"]["shadow_only"][0]["id"], "D-001")
        self.assertEqual(out["assertions"]["shadow_only"][0]["code"], "STALE")


class FalsePositiveCandidates(Harness):
    def test_a_shadow_finding_the_legacy_lane_verified_is_a_candidate(self):
        out = self.compared(
            legacy={"records": [legacy_record("README.md:7")]},
            shadow=shadow_report(
                declared=["README.md"],
                records=[shadow_record("D-001", "README.md", "u7", line=7)],
                examined=[examined("README.md")],
            ),
            segs=segments({"README.md": [("u7", 7)]}),
        )
        candidates = out["false_positive_candidates"]
        self.assertEqual(len(candidates), 1)
        self.assertEqual(candidates[0]["id"], "D-001")
        self.assertEqual(candidates[0]["legacy_verdict"], "VERIFIED")

    def test_agreement_produces_no_candidate(self):
        out = self.compared(
            legacy={"records": [legacy_record("README.md:7", verdict="STALE",
                                              fix="new")]},
            shadow=shadow_report(
                declared=["README.md"],
                records=[shadow_record("D-001", "README.md", "u7", line=7)],
                examined=[examined("README.md")],
            ),
            segs=segments({"README.md": [("u7", 7)]}),
        )
        self.assertEqual(out["false_positive_candidates"], [])

    def test_auto_apply_eligible_records_are_counted_separately(self):
        # #57's auto-apply policy may mint an approval set for a STALE record
        # carrying an exact preimage and an evidence pointer, with no human in
        # the loop. Those land autonomously, so the gate budgets them apart.
        out = self.compared(shadow=shadow_report(
            declared=["README.md"],
            records=[
                shadow_record("D-001", "README.md", "u1"),
                shadow_record("D-002", "README.md", "u2", code="UNVERIFIABLE"),
                shadow_record("D-003", "docs/g.md", "u3", code="ANCHOR-MISSING"),
            ],
        ))
        self.assertEqual(out["adjudication"]["auto_apply_eligible"], ["D-001"])
        self.assertEqual(
            out["adjudication"]["human_approval_required"], ["D-002", "D-003"]
        )
        self.assertEqual(out["adjudication"]["records_to_adjudicate"], 3)

    def test_a_stale_record_without_an_evidence_pointer_is_not_auto_eligible(self):
        record = shadow_record("D-001", "README.md", "u1")
        record["evidence"] = {"observed": "it moved"}
        out = self.compared(shadow=shadow_report(records=[record]))
        self.assertEqual(out["adjudication"]["auto_apply_eligible"], [])

    def test_a_waived_record_is_not_auto_eligible(self):
        # A waiver is a standing human disposition; the policy never mints over
        # one.
        record = shadow_record("D-001", "README.md", "u1",
                               waived={"by": "someone"})
        out = self.compared(shadow=shadow_report(records=[record]))
        self.assertEqual(out["adjudication"]["auto_apply_eligible"], [])


class Cost(Harness):
    def test_cost_is_normalized_per_examined_document(self):
        out = self.compared(
            legacy={"records": [legacy_record("README.md:3"),
                                legacy_record("CLAUDE.md:4")]},
            shadow=shadow_report(declared=["README.md", "CLAUDE.md",
                                           "CONTEXT.md", "docs/a.md"]),
        )
        self.assertEqual(out["cost"]["legacy"]["documents"], 2)
        self.assertEqual(out["cost"]["legacy"]["usd_per_document"], 1.36)
        self.assertEqual(out["cost"]["shadow"]["documents"], 4)
        self.assertEqual(out["cost"]["shadow"]["usd_per_document"], 1.36)
        self.assertEqual(out["cost"]["ratio_per_document"], 1.0)

    def test_totals_travel_untouched(self):
        out = self.compared(legacy={"records": [legacy_record("README.md:3")]})
        self.assertEqual(out["cost"]["legacy"]["usd"], 2.72)
        self.assertEqual(out["cost"]["legacy"]["turns"], 60)
        self.assertEqual(out["cost"]["shadow"]["duration_ms"], 900000)

    def test_a_lane_that_examined_nothing_has_no_per_document_cost(self):
        # Division by zero is not a cost of 0.0 — it is the absence of a figure,
        # and reporting it as a number would understate the lane.
        out = self.compared(legacy={"records": []})
        self.assertIsNone(out["cost"]["legacy"]["usd_per_document"])
        self.assertIsNone(out["cost"]["ratio_per_document"])


class Determinism(Harness):
    def test_two_runs_over_the_same_inputs_are_byte_identical(self):
        legacy = {"records": [legacy_record("README.md:7"),
                              legacy_record("CLAUDE.md:2")]}
        shadow = shadow_report(
            declared=["README.md", "CLAUDE.md"],
            records=[shadow_record("D-002", "CLAUDE.md", "u2", line=2),
                     shadow_record("D-001", "README.md", "u7", line=7)],
            examined=[examined("README.md"), examined("CLAUDE.md")],
        )
        segs = segments({"README.md": [("u7", 7)], "CLAUDE.md": [("u2", 2)]})
        first = self.compare(legacy=legacy, shadow=shadow, segs=segs)
        second = self.compare(legacy=legacy, shadow=shadow, segs=segs)
        self.assertEqual(first.returncode, 0, first.stderr)
        self.assertEqual(first.stdout, second.stdout)


class BadInput(Harness):
    def test_unreadable_input_exits_two_and_says_which_file(self):
        result = self.compare(extra=["--legacy", "/nonexistent/legacy.json"])
        self.assertEqual(result.returncode, 2)
        self.assertIn("/nonexistent/legacy.json", result.stderr)

    def test_a_legacy_location_without_a_line_is_refused(self):
        result = self.compare(legacy={"records": [legacy_record("README.md")]})
        self.assertEqual(result.returncode, 2)
        self.assertIn("README.md", result.stderr)

    def test_an_invalid_shadow_report_is_refused(self):
        # `invalid` carries no content, so there is nothing to compare; the
        # gate must see that as a failed comparison, not an empty one.
        result = self.compare(shadow={"status": "invalid", "problems": []})
        self.assertEqual(result.returncode, 2)
        self.assertIn("invalid", result.stderr)


class Render(Harness):
    def render(self, comparison):
        path = self.write("comparison.json", comparison)
        return subprocess.run(
            [sys.executable, SCRIPT, "render", "--comparison", path],
            capture_output=True, text=True,
        )

    def test_render_emits_the_headline_numbers(self):
        comparison = self.compared(
            legacy={"records": [legacy_record("README.md:7")]},
            shadow=shadow_report(
                declared=["README.md", "CLAUDE.md"],
                records=[shadow_record("D-001", "README.md", "u7", line=7)],
                examined=[examined("README.md")],
            ),
            segs=segments({"README.md": [("u7", 7)]}),
        )
        result = self.render(comparison)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("| Legacy | Shadow |", result.stdout)
        self.assertIn("D-001", result.stdout)
        self.assertIn("CLAUDE.md", result.stdout)

    def test_render_refuses_a_payload_it_did_not_produce(self):
        result = self.render({"not": "a comparison"})
        self.assertEqual(result.returncode, 2)
        self.assertIn("comparison", result.stderr)


if __name__ == "__main__":
    unittest.main(verbosity=2)
