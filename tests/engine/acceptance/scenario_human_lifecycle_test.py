#!/usr/bin/env python3
"""Primary human lifecycle transaction (issue #158).

One REAL temporary repository carries a report produced by the bloat audit
engine through strict-subset human approval, edit-plan construction, and the
public deterministic applier. The approved DISTILL authors durable residue
and retires its planning artifact in one apply; the skipped finding targets a
hostile filename and remains outside mutation authority.

The companion refusals stay at those same public seams. No helper below writes
an approved mutation: helpers create the committed starting repository and
untrusted artifact data, while ``apply_edit_plan`` is the only lifecycle
component that changes repository bytes.

Run: python3 tests/engine/acceptance/scenario_human_lifecycle_test.py
"""

import os
import subprocess
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import fixture  # noqa: E402  (the real-repository acceptance fixture)
from scenario_drift_test import DriftScenarioTestCase  # noqa: E402

from doclifecycle import ARTIFACT_SCHEMA_VERSION, bloat  # noqa: E402
from doclifecycle.applier import ApplyResult, apply_edit_plan  # noqa: E402
from doclifecycle.approval import (  # noqa: E402
    ApprovalSet,
    Minter,
    mint_approval_set,
)
from doclifecycle.context import build_context_index  # noqa: E402
from doclifecycle.digest import sha256_bytes, sha256_canonical  # noqa: E402
from doclifecycle.finding import (  # noqa: E402
    FACTUAL,
    NON_ASSERTIVE,
    NORMATIVE,
    RATIONALE,
)
from doclifecycle.report import Report  # noqa: E402
from doclifecycle.results import (  # noqa: E402
    STATE_CLEAN,
    STATE_PARTIAL,
    STATE_STALE,
    Invalid,
)


APPROVER = Minter(kind="human", id="reviewer@example.com")
RESIDUE = "docs/lifecycle-decision.md"
RESIDUE_TEXT = (
    "# Fee-schedule decision\n\n"
    "Enterprise fees will use a tiered schedule; the durable policy belongs "
    "in the living documentation after implementation.\n"
)


class HumanLifecycleScenario(DriftScenarioTestCase):
    """The release gate's highest-level human transaction and its refusals."""

    def read(self, repo, path):
        with open(os.path.join(repo, path), encoding="utf-8") as handle:
            return handle.read()

    def tree(self, repo):
        """Every repository path and its exact bytes (or symlink target)."""
        state = {}
        for root, directories, files in os.walk(repo, followlinks=False):
            directories[:] = [name for name in directories if name != ".git"]
            for name in list(directories):
                absolute = os.path.join(root, name)
                if os.path.islink(absolute):
                    relative = os.path.relpath(absolute, repo)
                    state[relative] = ("symlink", os.readlink(absolute))
                    directories.remove(name)
            for name in files:
                absolute = os.path.join(root, name)
                relative = os.path.relpath(absolute, repo)
                if os.path.islink(absolute):
                    state[relative] = ("symlink", os.readlink(absolute))
                else:
                    with open(absolute, "rb") as handle:
                        state[relative] = ("file", handle.read())
        return state

    def git(self, repo, *arguments):
        return subprocess.run(
            ["git", "-C", repo, *arguments],
            check=True, capture_output=True, text=True,
        ).stdout

    def status_paths(self, repo):
        output = self.git(
            repo, "status", "--porcelain=v1", "-z",
            "--untracked-files=all", "--no-renames",
        )
        return sorted(entry[3:] for entry in output.split("\0") if entry)

    def staged_paths(self, repo):
        return self.git(repo, "diff", "--cached", "--name-only").splitlines()

    def ready_repo(self):
        """The fixture with a file-bound ready marker committed before audit."""
        repo = self.build_fixture()
        planning = self.read(repo, fixture.PLANNING_DOC)
        fixture._write(
            repo, fixture.PLANNING_DOC, "> Status: ready\n\n" + planning,
        )
        fixture._commit(repo, "Mark the follow-up plan ready to distill")
        return repo

    def complete_bloat_input(self, repo, verdicts, missing_chunk=None):
        """Complete the public deterministic plan, optionally naming one gap."""
        plan = bloat.plan_repository_chunks(
            repo, fixture.REGISTRY_PATH, max_documents=2,
        )
        self.assertNotIsInstance(plan, Invalid, plan)
        self.assertGreaterEqual(len(plan.chunks), 2)
        outcomes = []
        for chunk in plan.chunks:
            if chunk.chunk_id == missing_chunk:
                outcomes.append(bloat.ChunkOutcome.missing(
                    chunk.chunk_id, "worker result was not received",
                ))
                continue
            selected = [
                verdict for verdict in verdicts
                if verdict.get("path") in chunk.documents
            ]
            outcomes.append(bloat.ChunkOutcome.complete(
                chunk.chunk_id, selected,
            ))
        assembled = bloat.assemble_bloat_input(plan, outcomes)
        self.assertNotIsInstance(assembled, Invalid, assembled)
        return plan, assembled.to_dict()

    def bloat_verdicts(self, repo, *, complete_distill=True):
        """One approved DISTILL candidate and one hostile-path skipped CUT."""
        index = build_context_index(repo, fixture.REGISTRY_PATH)
        self.assertNotIsInstance(index, Invalid, index)
        planning_units = list(index.document(fixture.PLANNING_DOC).units)
        if not complete_distill:
            planning_units = planning_units[:-1]
        units_by_digest = {unit.digest: unit for unit in index.units}
        hostile_unit = next(
            digest
            for digest in index.document(
                fixture.HOSTILE_HOMOGLYPH_DOC
            ).units
            if units_by_digest[digest].assertion_capable
        )
        return [
            {
                "verdict": bloat.DISTILL,
                "path": fixture.PLANNING_DOC,
                "units": planning_units,
                "evidence": (
                    "The fee-schedule design is ready to become a durable "
                    "living decision."
                ),
                "status": "ready",
                "destination": RESIDUE,
            },
            {
                "verdict": bloat.CUT,
                "path": fixture.HOSTILE_HOMOGLYPH_DOC,
                "units": [hostile_unit],
                "evidence": "The placeholder sentence carries no durable value.",
            },
        ]

    def produced_report(self, repo, *, complete_distill=True):
        _, payload = self.complete_bloat_input(
            repo,
            self.bloat_verdicts(
                repo, complete_distill=complete_distill,
            ),
        )
        return bloat.audit_bloat(repo, payload, fixture.REGISTRY_PATH)

    def human_approval(self, repo, report):
        distill = next(
            record for record in report.records
            if record.extra["path"] == fixture.PLANNING_DOC
        )
        approval = mint_approval_set(
            report, [distill.digest], repo_root=repo, minter=APPROVER,
            registry_path=fixture.REGISTRY_PATH,
        )
        self.assertIsInstance(approval, ApprovalSet, approval)
        return distill, approval

    def edit_plan(self, repo, record, approval, *, retire=True,
                  hostile_record=None):
        """Construct untrusted plan data; only the public applier may write."""
        planning = self.read(repo, fixture.PLANNING_DOC)
        operations = [{
            "op": "create-document",
            "record": record.digest,
            "target_class": "documentation",
            "path": RESIDUE,
            "text": RESIDUE_TEXT,
        }]
        postimages = {
            RESIDUE: sha256_bytes(RESIDUE_TEXT.encode("utf-8")),
        }
        if retire:
            operations.append({
                "op": "retire-document",
                "record": record.digest,
                "target_class": "documentation",
                "path": fixture.PLANNING_DOC,
                "preimage": planning,
            })
            postimages[fixture.PLANNING_DOC] = None
        if hostile_record is not None:
            hostile_text = self.read(
                repo, fixture.HOSTILE_HOMOGLYPH_DOC,
            )
            hostile_line = hostile_text.splitlines()[2]
            operations.append({
                "op": "delete",
                "record": hostile_record.digest,
                "target_class": "documentation",
                "path": fixture.HOSTILE_HOMOGLYPH_DOC,
                "start_line": 3,
                "end_line": 3,
                "preimage": hostile_line,
            })
            hostile_post = hostile_text.replace(hostile_line + "\n", "", 1)
            postimages[fixture.HOSTILE_HOMOGLYPH_DOC] = sha256_bytes(
                hostile_post.encode("utf-8")
            )
        content = {
            "artifact": "edit-plan",
            "schema_version": ARTIFACT_SCHEMA_VERSION,
            "approval_digest": approval.digest,
            "operations": operations,
            "postimages": postimages,
        }
        return dict(content, digest=sha256_canonical(content))

    def transaction(self, repo):
        report = self.produced_report(repo)
        self.assertIsInstance(report, Report, report)
        record, approval = self.human_approval(repo, report)
        plan = self.edit_plan(repo, record, approval)
        return report, record, approval, plan

    def apply(self, repo, report, approval, plan):
        return apply_edit_plan(
            repo, plan, approval.to_dict(), report=report,
            registry_path=fixture.REGISTRY_PATH,
        )

    def assert_refused_untouched(self, repo, before, result):
        self.assertEqual(self.tree(repo), before)
        self.assertEqual(self.staged_paths(repo), [])
        self.assertTrue(
            isinstance(result, Invalid) or result.status == STATE_STALE,
            result,
        )

    def test_report_to_strict_human_approval_to_distill_apply(self):
        repo = self.ready_repo()

        # The same real corpus crosses the living-assertion audit boundary:
        # every assertion class is present, and each judgment obligation is
        # preserved as reviewable report data before any lifecycle write.
        drift_report = self.full_report(repo)
        architecture = next(
            entry.detail for entry in drift_report.examined
            if entry.scope == fixture.LIVING_DOC
        )
        self.assertEqual(architecture["classes"], {
            FACTUAL: 1, NON_ASSERTIVE: 1, NORMATIVE: 1, RATIONALE: 1,
        })
        self.assertEqual(architecture["obligations"], {
            "coherence": 1, "evidence": 1, "governing-source": 1,
        })

        hostile_before = {
            path: self.read(repo, path)
            for path in (*fixture.HOSTILE_DOCS, fixture.EXCLUDED_DOC,
                         fixture.LIVING_DOC)
        }
        report, record, approval, plan = self.transaction(repo)
        skipped = next(
            item for item in report.records
            if item.extra["path"] == fixture.HOSTILE_HOMOGLYPH_DOC
        )

        # Completion is produced by the public deterministic assembly, the
        # whole-document record contains every current unit, and the human took
        # exactly one of the two findings.
        self.assertEqual(report.status, STATE_PARTIAL)
        context_index = build_context_index(repo, fixture.REGISTRY_PATH)
        self.assertEqual(
            {entry.scope for entry in report.examined},
            {document.path for document in context_index.documents},
        )
        plan_digests = {
            entry.detail["plan_digest"] for entry in report.examined
        }
        self.assertEqual(len(plan_digests), 1)
        self.assertCountEqual(
            record.extra["units"],
            list(context_index.document(fixture.PLANNING_DOC).units),
        )
        self.assertEqual([item.digest for item in approval.skipped],
                         [skipped.digest])
        self.assertEqual(
            set(approval.scope.paths), {fixture.PLANNING_DOC, RESIDUE},
        )
        self.assertNotIn(fixture.HOSTILE_HOMOGLYPH_DOC,
                         approval.scope.paths)

        result = self.apply(repo, report, approval, plan)

        self.assertIsInstance(result, ApplyResult, result)
        self.assertEqual(result.status, STATE_CLEAN)
        self.assertFalse(result.already_applied)
        self.assertEqual(result.changed_paths,
                         (RESIDUE, fixture.PLANNING_DOC))
        self.assertEqual(self.read(repo, RESIDUE), RESIDUE_TEXT)
        self.assertFalse(os.path.exists(
            os.path.join(repo, fixture.PLANNING_DOC)
        ))
        self.assertEqual(
            [(item.op, item.path) for item in result.applied],
            [("create-document", RESIDUE),
             ("retire-document", fixture.PLANNING_DOC)],
        )
        self.assertEqual(
            self.status_paths(repo), sorted([RESIDUE, fixture.PLANNING_DOC]),
        )
        self.assertEqual(self.staged_paths(repo), [])
        self.assertEqual(
            {path: self.read(repo, path) for path in hostile_before},
            hostile_before,
        )

        applied_tree = self.tree(repo)
        second = self.apply(repo, report, approval, plan)
        self.assertEqual(second.status, STATE_CLEAN)
        self.assertTrue(second.already_applied)
        self.assertEqual(second.applied, ())
        self.assertEqual(second.changed_paths,
                         (RESIDUE, fixture.PLANNING_DOC))
        self.assertEqual(self.tree(repo), applied_tree)
        self.assertEqual(self.staged_paths(repo), [])

    def test_missing_completion_stays_partial_and_names_every_lost_document(self):
        repo = self.ready_repo()
        plan = bloat.plan_repository_chunks(
            repo, fixture.REGISTRY_PATH, max_documents=2,
        )
        missing = plan.chunks[0]
        _, payload = self.complete_bloat_input(
            repo, [], missing_chunk=missing.chunk_id,
        )

        report = bloat.audit_bloat(repo, payload, fixture.REGISTRY_PATH)

        self.assertIsInstance(report, Report, report)
        self.assertEqual(report.status, STATE_PARTIAL)
        gaps = {entry.scope: entry.reason for entry in report.incomplete}
        for path in missing.documents:
            self.assertIn(path, gaps)
            self.assertIn(missing.chunk_id, gaps[path])

    def test_incomplete_whole_document_verdict_is_refused_before_a_report(self):
        repo = self.ready_repo()
        before = self.tree(repo)

        result = self.produced_report(repo, complete_distill=False)

        self.assertIsInstance(result, Invalid, result)
        self.assertEqual(
            [problem.code for problem in result.problems],
            ["bloat-whole-document-units-incomplete"],
        )
        self.assert_refused_untouched(repo, before, result)

    def test_omitting_the_approved_retirement_is_invalid_and_writes_nothing(self):
        repo = self.ready_repo()
        report, record, approval, _ = self.transaction(repo)
        incomplete = self.edit_plan(repo, record, approval, retire=False)
        before = self.tree(repo)

        result = self.apply(repo, report, approval, incomplete)

        self.assertIsInstance(result, Invalid, result)
        self.assertIn("plan-remedy-incomplete",
                      [problem.code for problem in result.problems])
        self.assert_refused_untouched(repo, before, result)

    def test_a_skipped_hostile_record_cannot_expand_the_plan(self):
        repo = self.ready_repo()
        report, record, approval, _ = self.transaction(repo)
        hostile = next(
            item for item in report.records
            if item.extra["path"] == fixture.HOSTILE_HOMOGLYPH_DOC
        )
        expanded = self.edit_plan(
            repo, record, approval, hostile_record=hostile,
        )
        before = self.tree(repo)

        result = self.apply(repo, report, approval, expanded)

        self.assertIsInstance(result, Invalid, result)
        self.assertIn("plan-record-not-approved",
                      [problem.code for problem in result.problems])
        self.assert_refused_untouched(repo, before, result)

    def test_a_stale_human_transaction_is_byte_identical_and_unstaged(self):
        repo = self.ready_repo()
        report, _, approval, plan = self.transaction(repo)
        fixture._git(
            repo, "commit", "-q", "--allow-empty", "-m",
            "Advance the repository after semantic approval",
        )
        before = self.tree(repo)

        result = self.apply(repo, report, approval, plan)

        self.assertIsInstance(result, ApplyResult, result)
        self.assertEqual(result.status, STATE_STALE)
        self.assertIn(
            "approval-base-commit-changed",
            [reason.code for reason in result.stale_reasons],
        )
        self.assert_refused_untouched(repo, before, result)


if __name__ == "__main__":
    unittest.main(verbosity=2)
