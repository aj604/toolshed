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

    def committed_repo(self, changed=False, first_assertion_at_ordinal_zero=False):
        repo = self.sync_repo()
        if first_assertion_at_ordinal_zero:
            self.write(repo, "docs/architecture.md", (
                "The service has a newly judged contract.\n"
            ))
        elif changed:
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
    def test_zero_based_ordinal_flows_through_phase_two(self):
        repo = self.committed_repo(first_assertion_at_ordinal_zero=True)
        work = plan_sync(repo, AS_OF).work_order.to_dict()
        judgment = self.valid_judgment(work["units"][0])

        result = accept_sync_judgments(
            repo, work, self.envelope(work, [judgment]), AS_OF
        )

        self.assertEqual(work["units"][0]["ordinal"], 0)
        self.assertNotIsInstance(result, Invalid, result)

    def test_empty_order_flows_through_phase_two_without_a_request(self):
        repo = self.committed_repo()
        plan = plan_sync(repo, AS_OF)
        adapter = FakeJudgmentAdapter.partial()
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
        judgment = self.valid_judgment(work["units"][0])
        first_adapter = FakeJudgmentAdapter.valid([judgment])
        first = accept_sync_judgments(
            repo, work, first_adapter.request(work), AS_OF,
        )
        self.assertEqual(first_adapter.request_count, 1)
        self.assertEqual(self.read_bytes(repo), before)
        second_adapter = FakeJudgmentAdapter.valid([judgment])
        second = accept_sync_judgments(
            repo, work, second_adapter.request(work), AS_OF,
        )
        self.assertEqual(second_adapter.request_count, 1)
        self.assertEqual(self.read_bytes(repo), before)

        self.assertNotIsInstance(first, Invalid, first)
        report, proposal = first
        self.assertEqual(report.to_dict(), second[0].to_dict())
        self.assertEqual(proposal.to_dict(), second[1].to_dict())
        self.assertEqual(proposal.jsonl, second[1].jsonl)
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

    def test_classification_only_non_assertive_unit_is_valid_without_a_ledger_entry(self):
        repo = self.committed_repo(changed=True)
        work = plan_sync(repo, AS_OF).work_order.to_dict()
        before = self.read_bytes(repo)
        classification = {
            "doc": work["units"][0]["doc"],
            "unit": work["units"][0]["unit"],
            "assertion_class": "non-assertive",
        }
        adapter = FakeJudgmentAdapter.valid([classification])

        report, proposal = accept_sync_judgments(
            repo, work, adapter.request(work), AS_OF,
        )

        self.assertEqual(adapter.request_count, 1)
        self.assertEqual(report.status, "clean")
        examined = report.to_dict()["examined"][0]["verified"][0]
        self.assertEqual(examined["assertion_class"], "non-assertive")
        self.assertEqual(proposal.additions, ())
        self.assertEqual(self.read_bytes(repo), before)

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
        unasked_adapter = FakeJudgmentAdapter.unasked_unit(unasked)
        self.assert_refused(accept_sync_judgments(
            self.repo_root, self.work, unasked_adapter.request(self.work), AS_OF
        ), "sync-judgment-unasked-unit")
        self.assertEqual(unasked_adapter.request_count, 1)
        malformed = dict(self.judgment)
        malformed.pop("verdict")
        malformed_adapter = FakeJudgmentAdapter.malformed(
            self.envelope(self.work, [malformed])
        )
        self.assert_refused(accept_sync_judgments(
            self.repo_root, self.work, malformed_adapter.request(self.work), AS_OF
        ), "drift-verdict-invalid-shape")
        self.assertEqual(malformed_adapter.request_count, 1)

    def test_non_scalar_model_identities_are_typed_not_tracebacks(self):
        for field in ("doc", "unit"):
            with self.subTest(field=field):
                malformed = dict(self.judgment, **{field: []})
                adapter = FakeJudgmentAdapter.malformed(
                    self.envelope(self.work, [malformed])
                )
                self.assert_refused(accept_sync_judgments(
                    self.repo_root, self.work, adapter.request(self.work), AS_OF
                ), "sync-judgment-invalid-identity")
                self.assertEqual(adapter.request_count, 1)

    def test_work_order_numeric_bindings_are_type_exact(self):
        cases = (
            ("chunk-bool", lambda work: work.update(total_chunk_count=True),
             "sync-work-order-invalid-chunk-count"),
            ("chunk-float", lambda work: work.update(total_chunk_count=1.0),
             "sync-work-order-invalid-chunk-count"),
            ("ordinal-bool", lambda work: work["units"][0].update(ordinal=True),
             "sync-work-order-invalid-unit-metadata"),
            ("ordinal-negative", lambda work: work["units"][0].update(ordinal=-1),
             "sync-work-order-invalid-unit-metadata"),
            ("line-float", lambda work: work["units"][0].update(
                line=float(work["units"][0]["line"])),
             "sync-work-order-invalid-unit-metadata"),
        )
        for name, mutate, code in cases:
            with self.subTest(name=name):
                work = json.loads(json.dumps(self.work))
                mutate(work)
                adapter = FakeJudgmentAdapter.partial()
                self.assert_refused(accept_sync_judgments(
                    self.repo_root, work, adapter.request(work), AS_OF,
                ), code)
                self.assertEqual(adapter.request_count, 1)

        custom = plan_sync(
            self.repo_root, AS_OF, session_id="session-types",
            chunk_id="chunk-types", total_chunk_count=2,
        ).work_order.to_dict()
        for count in (True, 2.0):
            with self.subTest(expected_count=count):
                adapter = FakeJudgmentAdapter.partial()
                self.assert_refused(accept_sync_judgments(
                    self.repo_root, custom, adapter.request(custom), AS_OF,
                    expected_session_id="session-types",
                    expected_chunk_id="chunk-types",
                    expected_total_chunk_count=count,
                ), "sync-invalid-expected-binding")
                self.assertEqual(adapter.request_count, 1)

    def test_partial_and_denied_are_partial_without_an_extra_request(self):
        adapter = FakeJudgmentAdapter.partial()
        response = adapter.request(self.work)
        report, _ = accept_sync_judgments(
            self.repo_root, self.work, response, AS_OF
        )
        self.assertEqual(adapter.request_count, 1)
        self.assertEqual(report.status, "partial")
        self.assertEqual(len(report.incomplete), len(self.work["units"]))
        self.assertEqual(self.read_bytes(self.repo_root), self.before)

        denied_adapter = FakeJudgmentAdapter.denied()
        denied_report, _ = accept_sync_judgments(
            self.repo_root, self.work, denied_adapter.request(self.work), AS_OF
        )
        self.assertEqual(denied_adapter.request_count, 1)
        self.assertEqual(denied_report.status, "partial")
        self.assertTrue(all("denied" in item.reason for item in denied_report.incomplete))
        self.assertEqual(self.read_bytes(self.repo_root), self.before)

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

    def test_caller_assigned_orchestration_requires_all_trusted_expectations(self):
        for field, value, code in (
            ("session_id", "attacker-session", "sync-wrong-session"),
            ("chunk_id", "attacker-chunk", "sync-stale-chunk"),
            ("total_chunk_count", 99, "sync-stale-chunk"),
        ):
            with self.subTest(tampered=field):
                tampered = json.loads(json.dumps(self.work))
                tampered[field] = value
                tampered_adapter = FakeJudgmentAdapter.partial()
                self.assert_refused(accept_sync_judgments(
                    self.repo_root, tampered,
                    tampered_adapter.request(tampered), AS_OF,
                ), code)
                self.assertEqual(tampered_adapter.request_count, 1)

        custom = plan_sync(
            self.repo_root, AS_OF, session_id="session-7", chunk_id="chunk-b",
            total_chunk_count=3,
        ).work_order.to_dict()
        untrusted_adapter = FakeJudgmentAdapter.partial()
        self.assert_refused(accept_sync_judgments(
            self.repo_root, custom, untrusted_adapter.request(custom), AS_OF,
        ), "sync-wrong-session")
        self.assertEqual(untrusted_adapter.request_count, 1)

        trusted_adapter = FakeJudgmentAdapter.partial()
        report, _ = accept_sync_judgments(
            self.repo_root, custom, trusted_adapter.request(custom), AS_OF,
            expected_session_id="session-7", expected_chunk_id="chunk-b",
            expected_total_chunk_count=3,
        )
        self.assertEqual(trusted_adapter.request_count, 1)
        self.assertEqual(report.status, "partial")
        self.assertEqual(self.read_bytes(self.repo_root), self.before)

        self.assert_refused(accept_sync_judgments(
            self.repo_root, custom, FakeJudgmentAdapter.partial().request(custom),
            AS_OF, expected_session_id="session-7", expected_chunk_id="chunk-b",
            expected_total_chunk_count=2,
        ), "sync-wrong-chunk-count")

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
