#!/usr/bin/env python3
"""The subprocess seam for phase-2 sync acceptance."""

import json
import os
import subprocess
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from support import run_command  # noqa: E402
from sync_support import SyncRepoTestCase  # noqa: E402

from doclifecycle.sync import SyncAcceptance, accept_sync_judgments, plan_sync  # noqa: E402

AS_OF = "2026-08-06"


class SyncAcceptCommand(SyncRepoTestCase):
    def fixture(self):
        repo = self.sync_repo()
        self.write(repo, "docs/architecture.md", (
            "# Architecture\n\nThe service has a newly judged CLI contract.\n"
        ))
        subprocess.run(["git", "-C", repo, "init", "-q", "-b", "main"], check=True)
        subprocess.run(["git", "-C", repo, "add", "-A"], check=True)
        subprocess.run([
            "git", "-C", repo, "-c", "user.name=t", "-c",
            "user.email=t@example.com", "commit", "-q", "-m", "fixture",
        ], check=True)
        work = plan_sync(repo, AS_OF).work_order.to_dict()
        unit = work["units"][0]
        judgment = {
            "doc": unit["doc"], "unit": unit["unit"],
            "assertion_class": "factual", "verdict": "VERIFIED",
            "kind": "behavior", "tier": 1,
            "evidence": {
                "source": unit["doc"], "line": unit["line"],
                "observed": "the CLI assertion was checked",
            },
            "obligation": "evidence", "strategy": "on-change",
        }
        judgments = {
            "schema_version": 1, "session_id": work["session_id"],
            "chunk_id": work["chunk_id"], "model": "sonnet",
            "status": "ok", "judgments": [judgment],
        }
        self.write(repo, "tmp/work.json", json.dumps(work))
        self.write(repo, "tmp/judgments.json", json.dumps(judgments))
        return repo, work, judgments

    def test_cli_is_the_exact_library_envelope_and_repeatable(self):
        repo, work, judgments = self.fixture()
        argv = (
            "sync-accept", "--repo", repo, "--as-of", AS_OF,
            "--work-order", os.path.join(repo, "tmp/work.json"),
            "--judgments", os.path.join(repo, "tmp/judgments.json"),
        )

        first = run_command(*argv)
        second = run_command(*argv)
        report, proposal = accept_sync_judgments(
            repo, work, judgments, AS_OF
        )

        self.assertEqual(first.returncode, 0, first.stderr)
        self.assertTrue(work["units"])
        self.assertEqual(first.stdout, second.stdout)
        self.assertEqual(
            json.loads(first.stdout), SyncAcceptance(report, proposal).to_dict()
        )

    def test_unreadable_input_is_typed_and_prints_no_traceback(self):
        repo, _, _ = self.fixture()
        result = run_command(
            "sync-accept", "--repo", repo, "--as-of", AS_OF,
            "--work-order", os.path.join(repo, "missing.json"),
            "--judgments", os.path.join(repo, "tmp/judgments.json"),
        )

        self.assertEqual(result.returncode, 1)
        self.assertEqual(
            json.loads(result.stdout)["problems"][0]["code"],
            "sync-work-order-unreadable",
        )
        self.assertNotIn("Traceback", result.stderr)

    def test_cli_requires_and_accepts_trusted_custom_chunk_topology(self):
        repo, _, judgments = self.fixture()
        work = plan_sync(
            repo, AS_OF, session_id="session-9", chunk_id="chunk-c",
            total_chunk_count=4,
        ).work_order.to_dict()
        judgments.update(
            session_id=work["session_id"], chunk_id=work["chunk_id"]
        )
        self.write(repo, "tmp/work.json", json.dumps(work))
        self.write(repo, "tmp/judgments.json", json.dumps(judgments))
        base = (
            "sync-accept", "--repo", repo, "--as-of", AS_OF,
            "--work-order", os.path.join(repo, "tmp/work.json"),
            "--judgments", os.path.join(repo, "tmp/judgments.json"),
        )

        refused = run_command(*base)
        accepted = run_command(
            *base, "--session-id", "session-9", "--chunk-id", "chunk-c",
            "--total-chunk-count", "4",
        )

        self.assertEqual(refused.returncode, 1)
        self.assertEqual(
            json.loads(refused.stdout)["problems"][0]["code"],
            "sync-wrong-session",
        )
        self.assertEqual(accepted.returncode, 0, accepted.stderr)


if __name__ == "__main__":
    unittest.main(verbosity=2)
