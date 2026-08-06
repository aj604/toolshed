#!/usr/bin/env python3
"""The subprocess half of the ``sync-plan`` tracer bullet.

Run: python3 tests/engine/sync_cli_test.py
"""

import json
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from support import run_command  # noqa: E402
from sync_support import FILES, SyncRepoTestCase  # noqa: E402

from doclifecycle.sync import plan_sync  # noqa: E402

AS_OF = "2026-08-06"


class SyncPlanCommand(SyncRepoTestCase):
    def test_payload_is_exactly_the_library_result(self):
        repo = self.sync_repo()

        result = run_command("sync-plan", "--repo", repo, "--as-of", AS_OF)

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout), plan_sync(repo, AS_OF).to_dict())
        self.assertEqual(json.loads(result.stdout)["work_order"]["units"], [])

    def test_two_fresh_interpreters_are_byte_identical(self):
        repo = self.sync_repo()
        argv = ("sync-plan", "--repo", repo, "--as-of", AS_OF)

        first = run_command(*argv)
        second = run_command(*argv)

        self.assertEqual(first.returncode, 0, first.stderr)
        self.assertEqual(first.stdout, second.stdout)

    def test_missing_ledger_is_typed_and_emits_no_work_order(self):
        repo = self.repo({
            ".doc-lifecycle/registry.json": json.dumps({
                "schema_version": 1, "roots": ["docs"],
                "rules": [{"glob": "docs/*.md", "kind": "living"}],
            }),
            "docs/a.md": "# A\n\nOne assertion.\n",
        })

        result = run_command("sync-plan", "--repo", repo, "--as-of", AS_OF)

        self.assertEqual(result.returncode, 1)
        payload = json.loads(result.stdout)
        self.assertEqual([p["code"] for p in payload["problems"]],
                         ["ledger-missing"])
        self.assertNotIn("work_order", payload)
        self.assertIn("ledger-missing", result.stderr)

    def test_recognized_future_modes_refuse_as_typed_problems(self):
        repo = self.sync_repo()
        for mode in ("bootstrap", "reconcile"):
            with self.subTest(mode=mode):
                result = run_command(
                    "sync-plan", "--repo", repo, "--as-of", AS_OF,
                    "--mode", mode,
                )
                self.assertEqual(result.returncode, 1)
                self.assertEqual(
                    json.loads(result.stdout)["problems"][0]["code"],
                    f"sync-{mode}-not-implemented",
                )

    def test_parseable_wrong_ledger_types_are_typed_not_tracebacks(self):
        cases = {
            "class": [],
            "lineage": [],
        }
        for field, value in cases.items():
            with self.subTest(field=field):
                repo = self.repo(FILES)
                records = self.ledger_records(repo)
                records[1][field] = value
                self.write_ledger(repo, records)

                result = run_command(
                    "sync-plan", "--repo", repo, "--as-of", AS_OF
                )

                self.assertEqual(result.returncode, 1, result.stderr)
                payload = json.loads(result.stdout)
                self.assertEqual(payload["status"], "invalid")
                self.assertTrue(payload["problems"])
                self.assertNotIn("work_order", payload)
                self.assertNotIn("Traceback", result.stderr)

    def test_unknown_probe_kind_escalates_its_entry_on_command_seam(self):
        repo = self.repo({**FILES, "src/app.py": "class App:\n    pass\n"})
        records = self.ledger_records(repo)
        records[1]["strategy"] = "probe"
        records[1]["probe"] = {
            "kind": "shell",
            "args": {"path": "src/app.py"},
            "expect": {},
        }
        records[1]["deps"] = [{"path": "src/app.py", "digest": "c" * 64}]
        self.write_ledger(repo, records)

        result = run_command("sync-plan", "--repo", repo, "--as-of", AS_OF)

        self.assertEqual(result.returncode, 4, result.stderr)
        payload = json.loads(result.stdout)
        self.assertEqual(len(payload["work_order"]["units"]), 1)
        refusal = payload["work_order"]["units"][0]
        self.assertEqual(refusal["reason"], "deterministic-probe-refused")
        self.assertEqual(refusal["probe_problem"]["code"],
                         "probe-unknown-kind")

    def test_as_of_is_required_on_the_command_seam(self):
        result = run_command("sync-plan", "--repo", self.sync_repo())
        self.assertEqual(result.returncode, 2)
        self.assertEqual(result.stdout, "")


if __name__ == "__main__":
    unittest.main(verbosity=2)
