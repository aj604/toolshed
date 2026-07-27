#!/usr/bin/env python3
"""Tests for the drift commands: `drift-plan` and `drift-audit`.

Seam: `python3 -m doclifecycle` as a subprocess. The commands must hand back
exactly what the library returns — the payload byte-for-byte and the result
state as the exit code — so a lane and an interactive run cannot disagree about
what an audit found. The behavior itself is `drift_test.py`'s.

Run: python3 tests/engine/drift_cli_test.py
"""

import json
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from drift_test import (  # noqa: E402
    LIVING,
    NARRATIVE,
    DriftRepoTestCase,
)
from support import run_command  # noqa: E402

from doclifecycle.drift import (  # noqa: E402
    MODE_FULL,
    MODE_INCREMENTAL,
    audit_drift,
    plan_drift_audit,
)


class DriftCommandTestCase(DriftRepoTestCase):
    def verdicts_file(self, root, payload):
        path = os.path.join(root, "verdicts.json")
        with open(path, "w", encoding="utf-8") as fh:
            json.dump(payload, fh)
        return path


class ThePlanCommand(DriftCommandTestCase):
    def test_it_prints_what_the_library_planned(self):
        root = self.drift_repo()

        result = run_command("drift-plan", "--repo", root)

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout),
                         plan_drift_audit(root, mode=MODE_FULL).to_dict())

    def test_a_diff_scoped_plan_takes_its_baseline_from_argv(self):
        root = self.drift_repo()
        self.write(root, "src/fees.py", "RATE = 0.025\n")
        self.commit(root, "raise the rate")

        result = run_command("drift-plan", "--repo", root, "--mode",
                             MODE_INCREMENTAL, "--since", self.base)

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(
            json.loads(result.stdout),
            plan_drift_audit(root, mode=MODE_INCREMENTAL,
                             since=self.base).to_dict(),
        )

    def test_a_plan_it_cannot_derive_exits_one_and_says_why(self):
        root = self.drift_repo()

        result = run_command("drift-plan", "--repo", root, "--mode",
                             MODE_INCREMENTAL)

        self.assertEqual(result.returncode, 1)
        self.assertIn("drift-missing-baseline", result.stderr)


class TheAuditCommand(DriftCommandTestCase):
    def test_it_prints_what_the_library_audited(self):
        root = self.drift_repo()
        payload = self.verdicts_for(root, self.verdict(root))
        path = self.verdicts_file(root, payload)

        result = run_command("drift-audit", "--repo", root, "--verdicts", path)

        self.assertEqual(json.loads(result.stdout),
                         audit_drift(root, mode=MODE_FULL,
                                     verdicts=payload).to_dict())

    def test_findings_are_data_rather_than_a_gate(self):
        root = self.drift_repo()
        path = self.verdicts_file(root, self.verdicts_for(
            root, self.verdict(root)))

        result = run_command("drift-audit", "--repo", root, "--verdicts", path)

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout)["status"], "findings")

    def test_a_partial_run_exits_four_and_names_what_it_skipped(self):
        root = self.drift_repo()
        path = self.verdicts_file(root, {"documents": [{
            "path": LIVING, "status": "failed", "reason": "the worker died",
        }]})

        result = run_command("drift-audit", "--repo", root, "--verdicts", path)

        self.assertEqual(result.returncode, 4)
        self.assertIn("the worker died", result.stderr)

    def test_an_audit_with_no_verdicts_still_checks_the_anchors(self):
        root = self.drift_repo()

        result = run_command("drift-audit", "--repo", root)

        self.assertEqual(result.returncode, 4)
        self.assertNotIn(NARRATIVE, result.stderr)

    def test_the_declared_scope_reaches_the_payload(self):
        root = self.drift_repo()

        result = run_command("drift-audit", "--repo", root)

        self.assertEqual(json.loads(result.stdout)["scope"]["documents"],
                         [NARRATIVE, LIVING])

    def test_a_verdicts_file_that_is_not_there_exits_one(self):
        root = self.drift_repo()

        result = run_command("drift-audit", "--repo", root, "--verdicts",
                             os.path.join(root, "absent.json"))

        self.assertEqual(result.returncode, 1)
        self.assertIn("drift-verdicts-unreadable", result.stderr)

    def test_a_verdicts_file_that_is_not_json_exits_one(self):
        root = self.drift_repo()
        path = os.path.join(root, "verdicts.json")
        with open(path, "w", encoding="utf-8") as fh:
            fh.write("{not json")

        result = run_command("drift-audit", "--repo", root, "--verdicts", path)

        self.assertEqual(result.returncode, 1)
        self.assertIn("drift-verdicts-unreadable", result.stderr)

    def test_the_evidence_boundary_is_declared_on_the_command_line(self):
        root = self.drift_repo()

        result = run_command("drift-audit", "--repo", root, "--evidence",
                             "src/**", "--exclude-evidence", "src/vendor/**")

        boundary = json.loads(result.stdout)["lineage"]["evidence_boundary"]
        self.assertEqual(boundary,
                         {"sources": ["src/**"], "excluded": ["src/vendor/**"]})

    def test_a_run_the_engine_cannot_trust_exits_one_with_no_report(self):
        root = self.drift_repo()
        path = self.verdicts_file(root, {"documents": [{
            "path": NARRATIVE, "status": "ok", "verdicts": [],
        }]})

        result = run_command("drift-audit", "--repo", root, "--verdicts", path)

        self.assertEqual(result.returncode, 1)
        self.assertEqual(json.loads(result.stdout)["status"], "invalid")
        self.assertIn("drift-verdict-on-narrative-document", result.stderr)


if __name__ == "__main__":
    unittest.main(verbosity=2)
