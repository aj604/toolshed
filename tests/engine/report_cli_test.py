#!/usr/bin/env python3
"""Tests for the report commands: `validate-report` and `render-report`.

Seam: the command as a subprocess — real argv, real exit codes, real stdout.
The contract is that the command is a thin wrapper over the library, so an
interactive import and a CI invocation cannot reach different verdicts on the
same report.

Run: python3 tests/engine/report_cli_test.py
"""

import json
import os
import subprocess
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from report_test import (  # noqa: E402
    CONFIG_DIGEST,
    GitRepoTestCase,
    coverage_payload,
    lineage_payload,
    report_payload,
)
from support import ENGINE, run_command as run  # noqa: E402

from doclifecycle.render import render_report  # noqa: E402
from doclifecycle.report import load_report  # noqa: E402
from doclifecycle.report import REPORT_SCHEMA_VERSION  # noqa: E402
from doclifecycle.results import (  # noqa: E402
    STATE_CLEAN,
    STATE_PARTIAL,
)

EXIT_OK = 0
EXIT_INVALID = 1
EXIT_USAGE = 2
EXIT_STALE = 3
EXIT_PARTIAL = 4


def _no_constants(name):
    raise AssertionError(f"the engine emitted {name}, which is not JSON")


class ReportCommandTestCase(GitRepoTestCase):
    def report_file(self, payload):
        root = self.repo({"report.json": json.dumps(payload, indent=2)})
        return os.path.join(root, "report.json")


class ValidateCommand(ReportCommandTestCase):
    def test_payload_is_exactly_the_library_result(self):
        path = self.report_file(report_payload())

        result = run("validate-report", "--report", path)

        self.assertEqual(result.returncode, EXIT_OK, result.stderr)
        self.assertEqual(json.loads(result.stdout), load_report(path).to_dict())

    def test_a_clean_report_completes(self):
        path = self.report_file(report_payload(status=STATE_CLEAN, records=[]))

        result = run("validate-report", "--report", path)

        self.assertEqual(result.returncode, EXIT_OK, result.stderr)
        self.assertEqual(json.loads(result.stdout)["status"], "clean")

    def test_a_v2_report_with_per_unit_sources_reaches_the_cli_seam(self):
        payload = report_payload(
            schema_version=REPORT_SCHEMA_VERSION,
            lineage=lineage_payload(audit_mode="incremental"),
            coverage=coverage_payload(),
        )
        path = self.report_file(payload)

        result = run("validate-report", "--report", path)

        self.assertEqual(result.returncode, EXIT_OK, result.stderr)
        self.assertEqual(json.loads(result.stdout)["coverage"], coverage_payload())

    def test_a_malformed_v2_coverage_source_is_a_cli_refusal(self):
        coverage = coverage_payload()
        del coverage["units"][1]["probe"]["observed"]
        path = self.report_file(report_payload(
            schema_version=REPORT_SCHEMA_VERSION,
            lineage=lineage_payload(audit_mode="incremental"),
            coverage=coverage,
        ))

        result = run("validate-report", "--report", path)

        self.assertEqual(result.returncode, EXIT_INVALID)
        self.assertEqual(
            [problem["code"] for problem in json.loads(result.stdout)["problems"]],
            ["report-invalid-probe-coverage"],
        )
        self.assertIn("report-invalid-probe-coverage", result.stderr)

    def test_a_partial_run_is_not_a_success(self):
        path = self.report_file(report_payload(
            status=STATE_PARTIAL,
            incomplete=[{"scope": "docs/huge.md", "reason": "chunk budget"}],
        ))

        result = run("validate-report", "--report", path)

        self.assertEqual(result.returncode, EXIT_PARTIAL)
        self.assertEqual(json.loads(result.stdout)["status"], "partial")
        self.assertIn("docs/huge.md", result.stderr)

    def test_a_stale_report_has_its_own_exit_code_and_agrees_with_the_library(self):
        repo = self.git_repo()
        path = self.report_file(
            report_payload(lineage=self.fresh_lineage(repo, plugin_version="0.0.1"))
        )

        result = run(
            "validate-report", "--report", path, "--repo", repo,
            "--audit-config-digest", CONFIG_DIGEST,
        )

        self.assertEqual(result.returncode, EXIT_STALE)
        self.assertEqual(
            json.loads(result.stdout),
            load_report(path, repo_root=repo,
                        audit_config_digest=CONFIG_DIGEST).to_dict(),
        )
        self.assertIn("lineage-plugin-mismatch", result.stderr)

    def test_a_fresh_report_against_its_own_repository_completes(self):
        repo = self.git_repo()
        path = self.report_file(report_payload(lineage=self.fresh_lineage(repo)))

        result = run(
            "validate-report", "--report", path, "--repo", repo,
            "--audit-config-digest", CONFIG_DIGEST,
        )

        self.assertEqual(result.returncode, EXIT_OK, result.stderr)
        self.assertEqual(json.loads(result.stdout)["status"], "findings")

    def test_an_invalid_report_exits_one_with_typed_problems_and_no_content(self):
        lineage = lineage_payload()
        del lineage["registry_digest"]
        path = self.report_file(report_payload(lineage=lineage))

        result = run("validate-report", "--report", path)

        self.assertEqual(result.returncode, EXIT_INVALID)
        payload = json.loads(result.stdout)
        self.assertEqual(payload["status"], "invalid")
        self.assertEqual(
            [p["code"] for p in payload["problems"]], ["report-missing-lineage-field"]
        )
        self.assertNotIn("records", payload)
        self.assertNotIn("lineage", payload)

    def test_an_invalid_run_explains_itself_on_stderr(self):
        path = self.report_file(report_payload(schema_version=99))

        result = run("validate-report", "--report", path)

        self.assertEqual(result.returncode, EXIT_INVALID)
        self.assertIn("report-schema-version", result.stderr)

    def test_an_unreadable_report_is_invalid_not_a_crash(self):
        result = run("validate-report", "--report", "/nonexistent/report.json")

        self.assertEqual(result.returncode, EXIT_INVALID)
        self.assertIn("report-unreadable", result.stderr)

    def test_a_report_that_is_not_utf8_is_a_verdict_not_a_traceback(self):
        root = self.repo({"placeholder": ""})
        path = os.path.join(root, "report.json")
        with open(path, "wb") as fh:
            fh.write(b'\xff\xfe{"status": "clean"}')

        result = run("validate-report", "--report", path)

        self.assertEqual(result.returncode, EXIT_INVALID)
        self.assertNotIn("Traceback", result.stderr)
        self.assertIn("report-unreadable", result.stderr)
        self.assertEqual(json.loads(result.stdout)["status"], "invalid")

    def test_a_report_carrying_nan_is_rejected_rather_than_re_emitted(self):
        root = self.repo({"placeholder": ""})
        path = os.path.join(root, "report.json")
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(json.dumps(report_payload(records=[{
                "id": "DRIFT-001", "digest": "a" * 64, "measure": None,
            }])).replace("null", "NaN"))

        result = run("validate-report", "--report", path)

        self.assertEqual(result.returncode, EXIT_INVALID)
        self.assertIn("report-unparseable", result.stderr)
        # The engine's own output stays readable by a strict parser.
        json.loads(result.stdout, parse_constant=_no_constants)

    def test_output_survives_a_strict_parser_under_hostile_record_content(self):
        path = self.report_file(report_payload(records=[{
            "id": "DRIFT-001", "digest": "a" * 64,
            "note": "line\nbreak `tick`   😀",
            "nested": {"deep": [1, 2.5, True, None]},
        }]))

        result = run("validate-report", "--report", path)

        self.assertEqual(result.returncode, EXIT_OK, result.stderr)
        json.loads(result.stdout, parse_constant=_no_constants)

    def test_the_report_argument_is_required(self):
        result = run("validate-report")

        self.assertEqual(result.returncode, EXIT_USAGE)
        self.assertEqual(result.stdout, "")


class RenderCommand(ReportCommandTestCase):
    def test_it_prints_exactly_what_the_library_renders(self):
        path = self.report_file(report_payload())

        result = run("render-report", "--report", path)

        self.assertEqual(result.returncode, EXIT_OK, result.stderr)
        self.assertEqual(result.stdout, render_report(load_report(path)) + "\n")

    def test_malformed_input_cannot_reach_rendered_output(self):
        path = self.report_file(report_payload(schema_version=99))

        result = run("render-report", "--report", path)

        self.assertEqual(result.returncode, EXIT_INVALID)
        self.assertEqual(result.stdout, "")
        self.assertIn("report-schema-version", result.stderr)

    def test_a_stale_report_still_renders_but_keeps_its_exit_code(self):
        repo = self.git_repo()
        path = self.report_file(
            report_payload(lineage=self.fresh_lineage(repo, plugin_version="0.0.1"))
        )

        result = run(
            "render-report", "--report", path, "--repo", repo,
            "--audit-config-digest", CONFIG_DIGEST,
        )

        self.assertEqual(result.returncode, EXIT_STALE)
        self.assertIn("stale", result.stdout)


class Launcher(ReportCommandTestCase):
    """The plugin checkout entrypoint must reach the same verdict."""

    SCRIPT = os.path.join(ENGINE, "doc-lifecycle.py")

    def test_it_agrees_with_the_library_without_pythonpath(self):
        path = self.report_file(report_payload())
        env = {k: v for k, v in os.environ.items() if k != "PYTHONPATH"}

        result = subprocess.run(
            [sys.executable, self.SCRIPT, "validate-report", "--report", path],
            capture_output=True, text=True, env=env,
        )

        self.assertEqual(result.returncode, EXIT_OK, result.stderr)
        self.assertEqual(json.loads(result.stdout), load_report(path).to_dict())


if __name__ == "__main__":
    unittest.main(verbosity=2)
