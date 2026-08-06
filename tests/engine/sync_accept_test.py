#!/usr/bin/env python3
"""Phase 2 library seam: untrusted judgments become report + proposal or nothing."""

import json
import os
import subprocess
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from sync_support import SyncRepoTestCase  # noqa: E402

from doclifecycle.results import Invalid  # noqa: E402
from doclifecycle.inventory import build_inventory  # noqa: E402
from doclifecycle.sync import (  # noqa: E402
    DEFAULT_LEDGER_PATH,
    FakeJudgmentAdapter,
    accept_sync_judgments,
    load_assertion_ledger,
    plan_sync,
)

AS_OF = "2026-08-06"


class PhaseTwoRepo(SyncRepoTestCase):
    def read_bytes(self, repo, path=DEFAULT_LEDGER_PATH):
        with open(os.path.join(repo, path), "rb") as fh:
            return fh.read()

    def committed_repo(self, changed=False):
        repo = self.sync_repo()
        if changed:
            self.write(repo, "docs/architecture.md", (
                "# Architecture\n\nThe service has a newly judged contract.\n"
            ))
        subprocess.run(["git", "-C", repo, "init", "-q", "-b", "main"], check=True)
        subprocess.run([
            "git", "-C", repo, "-c", "user.name=t", "-c",
            "user.email=t@example.com", "add", "-A",
        ], check=True)
        subprocess.run([
            "git", "-C", repo, "-c", "user.name=t", "-c",
            "user.email=t@example.com", "commit", "-q", "-m", "fixture",
        ], check=True)
        return repo

    def envelope(self, work, judgments=(), **overrides):
        payload = {
            "schema_version": 1,
            "session_id": work["session_id"],
            "chunk_id": work["chunk_id"],
            "model": work["budget"]["sync_model"],
            "status": "ok",
            "judgments": list(judgments),
        }
        payload.update(overrides)
        return payload

    def valid_judgment(self, unit, **overrides):
        payload = {
            "doc": unit["doc"], "unit": unit["unit"],
            "assertion_class": "factual", "verdict": "VERIFIED",
            "kind": "behavior", "tier": 1,
            "evidence": {
                "source": unit["doc"], "line": unit["line"],
                "observed": "the current document-bound assertion was checked",
            },
            "obligation": "evidence", "strategy": "on-change",
        }
        payload.update(overrides)
        return payload


class EmptyAndComplete(PhaseTwoRepo):
    def test_empty_order_flows_through_phase_two_without_a_request(self):
        repo = self.committed_repo()
        plan = plan_sync(repo, AS_OF)
        adapter = FakeJudgmentAdapter({"this": "must not be returned"})
        before = self.read_bytes(repo)

        first = accept_sync_judgments(
            repo, plan.work_order, adapter.request(plan.work_order), AS_OF
        )
        second = accept_sync_judgments(
            repo, plan.work_order, adapter.request(plan.work_order), AS_OF
        )

        self.assertEqual(adapter.request_count, 0)
        self.assertNotIsInstance(first, Invalid)
        report, proposal = first
        self.assertEqual(report.status, "clean")
        self.assertEqual(report.to_dict(), second[0].to_dict())
        self.assertEqual(proposal.to_dict(), second[1].to_dict())
        self.assertEqual(proposal.jsonl, second[1].jsonl)
        self.assertEqual(self.read_bytes(repo), before)

    def test_full_judgment_adds_and_supersedes_with_model_lineage(self):
        repo = self.committed_repo(changed=True)
        work = plan_sync(repo, AS_OF).work_order.to_dict()
        before = self.read_bytes(repo)
        result = accept_sync_judgments(
            repo, work, self.envelope(work, [self.valid_judgment(work["units"][0])]),
            AS_OF,
        )

        self.assertNotIsInstance(result, Invalid, result)
        report, proposal = result
        self.assertEqual(report.status, "clean")
        addition = proposal.to_dict()["changes"]
        self.assertEqual(len(addition["additions"]), 1)
        self.assertEqual(len(addition["tombstones"]), 1)
        self.assertEqual(len(addition["supersedes"]), 1)
        active = [r for r in proposal.records
                  if r.get("record") == "assertion" and r["status"] == "active"]
        self.assertEqual(active[0]["provenance"], "judged")
        self.assertEqual(active[0]["lineage"]["model"], "sonnet")
        self.assertEqual(active[0]["lineage"]["date"], AS_OF)
        self.assertEqual(self.read_bytes(repo), before)
        self.write(repo, ".doc-lifecycle/proposed-ledger.jsonl", proposal.jsonl)
        loaded = load_assertion_ledger(
            repo, build_inventory(repo).registry_digest,
            ".doc-lifecycle/proposed-ledger.jsonl",
        )
        self.assertNotIsInstance(loaded, Invalid, loaded)

    def test_empty_order_preserves_deterministic_anchor_findings(self):
        repo = self.committed_repo()
        self.write(repo, "docs/guides/history.md", "# History without an anchor\n")
        subprocess.run(["git", "-C", repo, "add", "docs/guides/history.md"], check=True)
        subprocess.run([
            "git", "-C", repo, "-c", "user.name=t", "-c",
            "user.email=t@example.com", "commit", "-q", "-m", "remove anchor",
        ], check=True)
        plan = plan_sync(repo, AS_OF)
        adapter = FakeJudgmentAdapter.malformed()

        report, _ = accept_sync_judgments(
            repo, plan.work_order, adapter.request(plan.work_order), AS_OF
        )

        self.assertEqual(adapter.request_count, 0)
        self.assertEqual(report.status, "findings")
        self.assertEqual([record.extra["code"] for record in report.records], [
            "ANCHOR-MISSING",
        ])


class RefusalsAndPartial(PhaseTwoRepo):
    def setUp(self):
        self.repo_root = self.committed_repo(changed=True)
        self.work = plan_sync(self.repo_root, AS_OF).work_order.to_dict()
        self.judgment = self.valid_judgment(self.work["units"][0])
        self.before = self.read_bytes(self.repo_root)

    def assert_refused(self, result, code):
        self.assertIsInstance(result, Invalid)
        self.assertIn(code, [problem.code for problem in result.problems])
        self.assertEqual(self.read_bytes(self.repo_root), self.before)

    def test_unasked_and_malformed_judgments_fail_closed(self):
        unasked = dict(self.judgment, unit="f" * 64)
        self.assert_refused(accept_sync_judgments(
            self.repo_root, self.work, self.envelope(self.work, [unasked]), AS_OF
        ), "sync-judgment-unasked-unit")
        malformed = dict(self.judgment)
        malformed.pop("verdict")
        self.assert_refused(accept_sync_judgments(
            self.repo_root, self.work, self.envelope(self.work, [malformed]), AS_OF
        ), "sync-judgment-invalid-shape")

    def test_partial_and_denied_are_partial_without_an_extra_request(self):
        adapter = FakeJudgmentAdapter(self.envelope(self.work, []))
        response = adapter.request(self.work)
        report, _ = accept_sync_judgments(
            self.repo_root, self.work, response, AS_OF
        )
        self.assertEqual(adapter.request_count, 1)
        self.assertEqual(report.status, "partial")
        self.assertEqual(len(report.incomplete), len(self.work["units"]))

        denied = self.envelope(self.work)
        denied.pop("judgments")
        denied.update(status="denied", reason="model service denied the request")
        denied_report, _ = accept_sync_judgments(
            self.repo_root, self.work, denied, AS_OF
        )
        self.assertEqual(denied_report.status, "partial")
        self.assertTrue(all("denied" in item.reason for item in denied_report.incomplete))

    def test_stale_binding_wrong_session_and_bad_probe_are_typed(self):
        stale = json.loads(json.dumps(self.work))
        stale["bindings"]["inventory_digest"] = "0" * 64
        self.assert_refused(accept_sync_judgments(
            self.repo_root, stale, self.envelope(stale, []), AS_OF
        ), "sync-stale-binding")
        self.assert_refused(accept_sync_judgments(
            self.repo_root, self.work, self.envelope(self.work, []), AS_OF,
            expected_session_id="another-session",
        ), "sync-wrong-session")
        self.assert_refused(accept_sync_judgments(
            self.repo_root, self.work, self.envelope(self.work, []),
            "2026-08-07",
        ), "sync-as-of-mismatch")
        bad_probe = dict(self.judgment, strategy="probe", probe={
            "kind": "shell", "args": {}, "expect": {},
        }, deps=[{"path": "docs/architecture.md", "digest": "0" * 64}])
        self.assert_refused(accept_sync_judgments(
            self.repo_root, self.work,
            self.envelope(self.work, [bad_probe]), AS_OF,
        ), "sync-judgment-probe-refused")

    def test_repository_move_evidence_escape_and_normative_probe_refuse(self):
        self.write(
            self.repo_root, "docs/architecture.md",
            "# Architecture\n\nThe repository moved between phases.\n",
        )
        self.assert_refused(accept_sync_judgments(
            self.repo_root, self.work, self.envelope(self.work, []), AS_OF
        ), "sync-stale-binding")

        # Restore the planned bytes for independent judgment-boundary checks.
        self.write(
            self.repo_root, "docs/architecture.md",
            "# Architecture\n\nThe service has a newly judged contract.\n",
        )
        escaped = json.loads(json.dumps(self.judgment))
        escaped["evidence"]["source"] = "../secret"
        self.assert_refused(accept_sync_judgments(
            self.repo_root, self.work, self.envelope(self.work, [escaped]), AS_OF
        ), "drift-verdict-invalid-evidence")

        normative_probe = dict(
            self.judgment, assertion_class="normative",
            obligation="governing-source", strategy="probe",
            probe={
                "kind": "path_exists",
                "args": {"path": "docs/architecture.md", "kind": "file"},
                "expect": {},
            },
            deps=[{
                "path": "docs/architecture.md",
                "digest": build_inventory(self.repo_root).documents[0].digest,
            }],
        )
        self.assert_refused(accept_sync_judgments(
            self.repo_root, self.work,
            self.envelope(self.work, [normative_probe]), AS_OF,
        ), "ledger-forbidden-probe-class")


if __name__ == "__main__":
    unittest.main(verbosity=2)
