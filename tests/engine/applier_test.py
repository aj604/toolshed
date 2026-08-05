"""The applier: the only component that writes, and every way it refuses to.

Every fixture is a real git repository, because the applier's whole contract
is about a real working tree: exact preimages on disk, a whole-diff
confinement check read from `git status`, and refusal paths that must leave
the tree byte-identical to how they found it.
"""

import hashlib
import json
import os
import unittest

from support import ENGINE  # noqa: F401 (engine onto sys.path)
from approval_test import (
    CONFIG_DIGEST,
    DOC_A,
    DOC_A_TEXT,
    DOC_B,
    DOC_B_TEXT,
    FILES,
    HUMAN,
    PLAN_DOC,
    PLAN_DOC_TEXT,
    ApprovalTestCase,
)

from doclifecycle import ARTIFACT_SCHEMA_VERSION
from doclifecycle.applier import (
    ApplyResult,
    apply_edit_plan,
    load_edit_plan,
)
from doclifecycle.approval import (
    ApprovalSet,
    ApprovedRecord,
    MutationScope,
    mint_approval_set,
    validate_approval_set,
)
from doclifecycle.bloat import record_verdicts
from doclifecycle.context import build_context_index
from doclifecycle.digest import sha256_canonical
from doclifecycle.reconcile import reconcile
from doclifecycle.report import EvidenceBoundary, validate_report
from doclifecycle.results import STATE_CLEAN, STATE_STALE, Invalid

NEW_SENTENCE = "The payment service charges a flat 2.5% fee."
OLD_SENTENCE = "The payment service charges a flat 2% fee."


def sha256_text(text):
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def codes(result):
    return sorted(p.code for p in result.problems)


def reasons(result):
    return sorted(r.code for r in result.stale_reasons)


class ApplierTestCase(ApprovalTestCase):
    """Real repository, real approval set, and a plan built over both."""

    def tree(self, root):
        """Every file under `root` (git internals aside) with its bytes."""
        state = {}
        for dirpath, dirnames, filenames in os.walk(root):
            dirnames[:] = [d for d in dirnames if d != ".git"]
            for name in filenames:
                path = os.path.join(dirpath, name)
                with open(path, "rb") as fh:
                    state[os.path.relpath(path, root)] = fh.read()
        return state

    def read(self, root, rel):
        with open(os.path.join(root, rel), encoding="utf-8") as fh:
            return fh.read()

    def status_paths(self, root):
        """Changed paths (index and work tree), straight from git."""
        import subprocess
        out = subprocess.run(
            ["git", "-C", root, "status", "--porcelain=v1", "-z",
             "--untracked-files=all", "--no-renames"],
            capture_output=True, text=True, check=True,
        ).stdout
        return sorted(e[3:] for e in out.split("\0") if e)

    def staged_paths(self, root):
        import subprocess
        out = subprocess.run(
            ["git", "-C", root, "diff", "--cached", "--name-only"],
            capture_output=True, text=True, check=True,
        ).stdout
        return [line for line in out.splitlines() if line]

    def approve(self, records):
        report = self.report(records)
        approval = mint_approval_set(
            report, [r["digest"] for r in records],
            repo_root=self.repo, minter=HUMAN,
        )
        self.assertNotIsInstance(approval, Invalid)
        return report, approval

    def plan(self, approval, operations, postimages):
        content = {
            "artifact": "edit-plan",
            "schema_version": ARTIFACT_SCHEMA_VERSION,
            "approval_digest": approval.digest,
            "operations": operations,
            "postimages": postimages,
        }
        payload = dict(content)
        payload["digest"] = sha256_canonical(content)
        return payload

    def replace_fixture(self):
        """A minted approval for the fee STALE finding, plus its plan."""
        units = self.units(self.repo, DOC_A)
        record = self.finding(
            "DRIFT-001", "STALE", DOC_A, [units[0]], fix=NEW_SENTENCE,
        )
        report, approval = self.approve([record])
        post = DOC_A_TEXT.replace(OLD_SENTENCE, NEW_SENTENCE)
        op = {
            "op": "replace",
            "record": record["digest"],
            "target_class": "documentation",
            "path": DOC_A,
            "start_line": 3,
            "end_line": 3,
            "preimage": OLD_SENTENCE,
            "text": NEW_SENTENCE,
        }
        plan = self.plan(approval, [op], {DOC_A: sha256_text(post)})
        return report, approval, plan, post

    def apply(self, plan, approval, report=None, repo=None):
        return apply_edit_plan(
            self.repo if repo is None else repo, plan, approval.to_dict()
            if not isinstance(approval, dict) else approval,
            report=report, audit_config_digest=CONFIG_DIGEST,
        )

    def assert_untouched(self, before, result, expect_codes=None):
        """The refusal left the tree byte-identical, and staged nothing."""
        self.assertEqual(before, self.tree(self.repo))
        self.assertEqual(self.staged_paths(self.repo), [])
        if expect_codes is not None:
            self.assertIsInstance(result, Invalid, result)
            for code in expect_codes:
                self.assertIn(code, codes(result), codes(result))


class AppliesApprovedPlan(ApplierTestCase):
    """The honest path: an approved plan lands, confined to approved paths."""

    def test_replace_lands_and_changes_only_the_approved_document(self):
        report, approval, plan, post = self.replace_fixture()
        result = self.apply(plan, approval, report=report)
        self.assertIsInstance(result, ApplyResult, result)
        self.assertEqual(result.status, STATE_CLEAN)
        self.assertFalse(result.already_applied)
        self.assertEqual(result.changed_paths, (DOC_A,))
        self.assertEqual(self.read(self.repo, DOC_A), post)
        # The complete working-tree diff is the approved document and nothing
        # else, and nothing was staged or committed.
        self.assertEqual(self.status_paths(self.repo), [DOC_A])
        self.assertEqual(self.staged_paths(self.repo), [])

    def test_result_names_the_plan_and_the_approval(self):
        report, approval, plan, _ = self.replace_fixture()
        result = self.apply(plan, approval, report=report)
        self.assertEqual(result.approval_digest, approval.digest)
        self.assertEqual(result.plan_digest, plan["digest"])
        payload = result.to_dict()
        self.assertEqual(payload["status"], STATE_CLEAN)
        self.assertEqual(payload["changed_paths"], [DOC_A])
        self.assertEqual(len(payload["applied"]), 1)
        self.assertEqual(payload["applied"][0]["op"], "replace")
        self.assertEqual(payload["applied"][0]["path"], DOC_A)

    def test_reapplying_the_same_approval_set_is_a_noop(self):
        report, approval, plan, post = self.replace_fixture()
        first = self.apply(plan, approval, report=report)
        self.assertEqual(first.status, STATE_CLEAN)
        before = self.tree(self.repo)
        second = self.apply(plan, approval, report=report)
        self.assertIsInstance(second, ApplyResult, second)
        self.assertEqual(second.status, STATE_CLEAN)
        self.assertTrue(second.already_applied)
        self.assertEqual(second.applied, ())
        self.assertEqual(before, self.tree(self.repo))

    def test_delete_and_insert_land(self):
        units = self.units(self.repo, DOC_A)
        record = self.finding("BLOAT-001", "CONDENSE", DOC_A, units)
        report, approval = self.approve([record])
        # Delete the refunds sentence (line 5) and insert a line after the fee
        # sentence — two ops from one record, disjoint spans, both inside the
        # passage the record's units are.
        post_lines = DOC_A_TEXT.split("\n")
        del post_lines[4]
        post_lines[3:3] = ["Fees are billed monthly."]
        post = "\n".join(post_lines)
        ops = [
            {
                "op": "delete",
                "record": record["digest"],
                "target_class": "documentation",
                "path": DOC_A,
                "start_line": 5,
                "end_line": 5,
                "preimage": "Refunds reverse the fee at the rate charged.",
            },
            {
                "op": "insert",
                "record": record["digest"],
                "target_class": "documentation",
                "path": DOC_A,
                "after_line": 3,
                "text": "Fees are billed monthly.",
            },
        ]
        plan = self.plan(approval, ops, {DOC_A: sha256_text(post)})
        result = self.apply(plan, approval, report=report)
        self.assertEqual(result.status, STATE_CLEAN, result)
        self.assertEqual(self.read(self.repo, DOC_A), post)

    def test_create_document_lands(self):
        new_doc = "docs/adr-fees.md"
        content = "# ADR: flat fees\n\nWe charge a flat rate.\n"
        units = self.whole_units(self.repo, PLAN_DOC)
        record = self.finding(
            "BLOAT-002", "DISTILL", PLAN_DOC, units,
            destination={"path": new_doc},
        )
        report, approval = self.approve([record])
        op = {
            "op": "create-document",
            "record": record["digest"],
            "target_class": "documentation",
            "path": new_doc,
            "text": content,
        }
        # DISTILL owes its retirement as well as its creation, so the plan
        # carries both legs; a creation alone is `plan-remedy-incomplete`.
        retire_op = {
            "op": "retire-document",
            "record": record["digest"],
            "target_class": "documentation",
            "path": PLAN_DOC,
            "preimage": PLAN_DOC_TEXT,
        }
        plan = self.plan(approval, [op, retire_op], {
            new_doc: sha256_text(content), PLAN_DOC: None,
        })
        result = self.apply(plan, approval, report=report)
        self.assertEqual(result.status, STATE_CLEAN, result)
        self.assertEqual(self.read(self.repo, new_doc), content)
        self.assertEqual(
            self.status_paths(self.repo), sorted([new_doc, PLAN_DOC])
        )

    def test_retire_document_lands(self):
        units = self.whole_units(self.repo, PLAN_DOC)
        record = self.finding("BLOAT-003", "RETIRE-DOC", PLAN_DOC, units)
        report, approval = self.approve([record])
        op = {
            "op": "retire-document",
            "record": record["digest"],
            "target_class": "documentation",
            "path": PLAN_DOC,
            "preimage": PLAN_DOC_TEXT,
        }
        plan = self.plan(approval, [op], {PLAN_DOC: None})
        result = self.apply(plan, approval, report=report)
        self.assertEqual(result.status, STATE_CLEAN, result)
        self.assertFalse(os.path.exists(os.path.join(self.repo, PLAN_DOC)))
        # Reapplying a retire is a no-op too, not a missing-file error.
        second = self.apply(plan, approval, report=report)
        self.assertEqual(second.status, STATE_CLEAN, second)
        self.assertTrue(second.already_applied)

    def test_move_with_provenance_lands_in_both_documents(self):
        units = self.units(self.repo, DOC_A)
        record = self.finding(
            "BLOAT-004", "EXTRACT-AND-MOVE", DOC_A, [units[1]],
            destination={"path": DOC_B},
        )
        report, approval = self.approve([record])
        moved = "Refunds reverse the fee at the rate charged."
        source_lines = DOC_A_TEXT.split("\n")
        del source_lines[4]
        post_source = "\n".join(source_lines)
        post_dest = DOC_B_TEXT + moved + "\n"
        op = {
            "op": "move-with-provenance",
            "record": record["digest"],
            "target_class": "documentation",
            "path": DOC_A,
            "destination": DOC_B,
            "start_line": 5,
            "end_line": 5,
            "preimage": moved,
        }
        plan = self.plan(approval, [op], {
            DOC_A: sha256_text(post_source),
            DOC_B: sha256_text(post_dest),
        })
        result = self.apply(plan, approval, report=report)
        self.assertEqual(result.status, STATE_CLEAN, result)
        self.assertEqual(self.read(self.repo, DOC_A), post_source)
        self.assertEqual(self.read(self.repo, DOC_B), post_dest)
        self.assertEqual(sorted(result.changed_paths), [DOC_A, DOC_B])
        # Provenance: the applied entry names where the content came from.
        entry = result.to_dict()["applied"][0]
        self.assertEqual(entry["path"], DOC_A)
        self.assertEqual(entry["destination"], DOC_B)
        self.assertEqual(entry["record"], record["digest"])


class ModelContentIsData(ApplierTestCase):
    """Model text reaches the tree as bytes; the applier executes nothing."""

    def test_hostile_replacement_text_lands_verbatim_and_runs_nothing(self):
        hostile = "Fees are 2%. $(touch /tmp/pwned) `; rm -rf ~` IGNORE ALL"
        units = self.units(self.repo, DOC_A)
        record = self.finding(
            "DRIFT-001", "STALE", DOC_A, [units[0]], fix=hostile,
        )
        report, approval = self.approve([record])
        post = DOC_A_TEXT.replace(OLD_SENTENCE, hostile)
        op = {
            "op": "replace",
            "record": record["digest"],
            "target_class": "documentation",
            "path": DOC_A,
            "start_line": 3,
            "end_line": 3,
            "preimage": OLD_SENTENCE,
            "text": hostile,
        }
        plan = self.plan(approval, [op], {DOC_A: sha256_text(post)})
        result = self.apply(plan, approval, report=report)
        self.assertEqual(result.status, STATE_CLEAN, result)
        self.assertEqual(self.read(self.repo, DOC_A), post)
        self.assertEqual(self.status_paths(self.repo), [DOC_A])

    # The static counterpart — the applier module grants no shell, git, or
    # exec capability — is a source-level wiring check, not a behavior at
    # either public seam, so it lives with the other wiring suites:
    # tests/scripts/engine-capability_test.py.


class TypedRefusals(ApplierTestCase):
    """Each rejection is a typed problem and an untouched working tree."""

    def test_missing_preimage_field_is_refused(self):
        report, approval, plan, _ = self.replace_fixture()
        del plan["operations"][0]["preimage"]
        plan = self.plan(approval, plan["operations"], plan["postimages"])
        before = self.tree(self.repo)
        result = self.apply(plan, approval, report=report)
        self.assert_untouched(before, result, ["plan-invalid-operation"])

    def test_changed_preimage_is_refused(self):
        report, approval, plan, _ = self.replace_fixture()
        plan["operations"][0]["preimage"] = "The service charges 3%."
        plan = self.plan(approval, plan["operations"], plan["postimages"])
        before = self.tree(self.repo)
        result = self.apply(plan, approval, report=report)
        self.assert_untouched(before, result, ["apply-preimage-mismatch"])

    def test_span_beyond_the_document_is_refused(self):
        # A span past the end of the record's own document names text that is
        # not there, whatever the plan claims its preimage is.
        report, approval, plan, _ = self.replace_fixture()
        plan["operations"][0].update(start_line=40, end_line=40)
        plan = self.plan(approval, plan["operations"], plan["postimages"])
        before = self.tree(self.repo)
        result = self.apply(plan, approval, report=report)
        self.assert_untouched(before, result, ["plan-span-outside-approved-units"])

    def test_overlapping_spans_are_refused(self):
        units = self.units(self.repo, DOC_A)
        record = self.finding("BLOAT-001", "CUT", DOC_A, units)
        report, approval = self.approve([record])
        base = {
            "record": record["digest"],
            "target_class": "documentation",
            "path": DOC_A,
        }
        ops = [
            dict(base, op="delete", start_line=3, end_line=5,
                 preimage="\n".join(DOC_A_TEXT.split("\n")[2:5])),
            dict(base, op="replace", start_line=5, end_line=5,
                 preimage=DOC_A_TEXT.split("\n")[4], text="x"),
        ]
        plan = self.plan(approval, ops, {DOC_A: sha256_text("# Fees\n")})
        before = self.tree(self.repo)
        result = self.apply(plan, approval, report=report)
        self.assert_untouched(before, result, ["plan-overlapping-spans"])

    def test_insert_inside_a_replaced_span_is_refused(self):
        units = self.units(self.repo, DOC_A)
        record = self.finding("BLOAT-001", "CUT", DOC_A, units)
        report, approval = self.approve([record])
        base = {
            "record": record["digest"],
            "target_class": "documentation",
            "path": DOC_A,
        }
        ops = [
            dict(base, op="delete", start_line=3, end_line=5,
                 preimage="\n".join(DOC_A_TEXT.split("\n")[2:5])),
            dict(base, op="insert", after_line=3, text="sneaked in"),
        ]
        plan = self.plan(approval, ops, {DOC_A: sha256_text("x\n")})
        before = self.tree(self.repo)
        result = self.apply(plan, approval, report=report)
        self.assert_untouched(before, result, ["plan-overlapping-spans"])

    def test_two_inserts_at_one_point_are_refused(self):
        units = self.units(self.repo, DOC_A)
        record = self.finding("BLOAT-001", "CUT", DOC_A, units)
        report, approval = self.approve([record])
        base = {
            "record": record["digest"],
            "target_class": "documentation",
            "path": DOC_A,
        }
        ops = [
            dict(base, op="insert", after_line=1, text="one"),
            dict(base, op="insert", after_line=1, text="two"),
        ]
        plan = self.plan(approval, ops, {DOC_A: sha256_text("x\n")})
        before = self.tree(self.repo)
        result = self.apply(plan, approval, report=report)
        self.assert_untouched(before, result, ["plan-overlapping-spans"])

    def test_duplicate_operations_are_refused(self):
        report, approval, plan, _ = self.replace_fixture()
        op = plan["operations"][0]
        plan = self.plan(approval, [op, dict(op)], plan["postimages"])
        before = self.tree(self.repo)
        result = self.apply(plan, approval, report=report)
        self.assert_untouched(before, result, ["plan-duplicate-operation"])

    def test_disallowed_target_class_is_refused(self):
        report, approval, plan, _ = self.replace_fixture()
        plan["operations"][0]["target_class"] = "workflow"
        plan = self.plan(approval, plan["operations"], plan["postimages"])
        before = self.tree(self.repo)
        result = self.apply(plan, approval, report=report)
        self.assert_untouched(before, result, ["plan-forbidden-target-class"])

    def test_a_second_created_document_is_not_smuggled_in_on_one_record(self):
        # One record authorizes one residue document. A plan that creates the
        # approved one *and* a second alongside it is a document nobody
        # approved riding on an approval that looks satisfied.
        approved, smuggled = "docs/decisions.md", "docs/extra.md"
        units = self.whole_units(self.repo, PLAN_DOC)
        record = self.finding(
            "BLOAT-005", "DISTILL", PLAN_DOC, units,
            destination={"path": approved},
        )
        report, approval = self.approve([record])
        ops = [
            {
                "op": "create-document",
                "record": record["digest"],
                "target_class": "documentation",
                "path": path,
                "text": f"# Residue\n\nAuthored into {path}.\n",
            }
            for path in (approved, smuggled)
        ]
        plan = self.plan(approval, ops, {
            path: sha256_text(f"# Residue\n\nAuthored into {path}.\n")
            for path in (approved, smuggled)
        })
        before = self.tree(self.repo)
        result = self.apply(plan, approval, report=report)
        self.assert_untouched(before, result, ["plan-target-not-record-target"])

    def test_a_positioned_edit_on_a_records_destination_is_refused(self):
        # A positioned edit is bounded by the passage the record's units are,
        # and those units segment the record's own document — a destination has
        # no such passage. Without this the span edits in DISTILL's remedy set
        # would reach any line of the destination document, and a record naming
        # an existing document would authorize deleting an unrelated sentence
        # from it.
        units = self.whole_units(self.repo, PLAN_DOC)
        record = self.finding(
            "BLOAT-008", "DISTILL", PLAN_DOC, units,
            destination={"path": DOC_B},
        )
        report, approval = self.approve([record])
        removed = "The worker retries a failed job three times."
        op = {
            "op": "delete",
            "record": record["digest"],
            "target_class": "documentation",
            "path": DOC_B,
            "start_line": 3,
            "end_line": 3,
            "preimage": removed,
        }
        plan = self.plan(approval, [op], {
            DOC_B: sha256_text(DOC_B_TEXT.replace(removed + "\n", "")),
        })
        before = self.tree(self.repo)
        result = self.apply(plan, approval, report=report)
        self.assert_untouched(before, result, ["plan-target-not-record-target"])

    def test_a_creation_aimed_at_the_artifact_itself_is_refused(self):
        # A record's two ends are not interchangeable: the artifact is what a
        # distillation retires, and authoring over it would put unapproved
        # content at the path the same record is about.
        units = self.whole_units(self.repo, PLAN_DOC)
        record = self.finding(
            "BLOAT-007", "DISTILL", PLAN_DOC, units,
            destination={"path": "docs/decisions.md"},
        )
        report, approval = self.approve([record])
        content = "# Not the residue\n\nWritten over the artifact.\n"
        op = {
            "op": "create-document",
            "record": record["digest"],
            "target_class": "documentation",
            "path": PLAN_DOC,
            "text": content,
        }
        plan = self.plan(approval, [op], {PLAN_DOC: sha256_text(content)})
        before = self.tree(self.repo)
        result = self.apply(plan, approval, report=report)
        self.assert_untouched(before, result, ["plan-target-not-record-target"])

    def test_a_distillation_naming_no_residue_authorizes_no_creation(self):
        # The retire-only case: with no destination the record authorizes one
        # path, the artifact — so a creation attached to it is unapproved.
        units = self.whole_units(self.repo, PLAN_DOC)
        record = self.finding("BLOAT-006", "DISTILL", PLAN_DOC, units)
        report, approval = self.approve([record])
        content = "# Residue\n\nAuthored with nobody's approval.\n"
        op = {
            "op": "create-document",
            "record": record["digest"],
            "target_class": "documentation",
            "path": "docs/decisions.md",
            "text": content,
        }
        plan = self.plan(approval, [op], {"docs/decisions.md": sha256_text(content)})
        before = self.tree(self.repo)
        result = self.apply(plan, approval, report=report)
        self.assert_untouched(before, result, ["plan-target-not-record-target"])

    def test_create_over_an_existing_document_is_refused(self):
        units = self.whole_units(self.repo, PLAN_DOC)
        record = self.finding(
            "BLOAT-002", "DISTILL", PLAN_DOC, units,
            destination={"path": DOC_B},
        )
        report, approval = self.approve([record])
        op = {
            "op": "create-document",
            "record": record["digest"],
            "target_class": "documentation",
            "path": DOC_B,
            "text": "clobbered\n",
        }
        # The retirement leg keeps the plan complete, so the refusal under
        # test is the create-over-existing one and not `plan-remedy-incomplete`.
        retire_op = {
            "op": "retire-document",
            "record": record["digest"],
            "target_class": "documentation",
            "path": PLAN_DOC,
            "preimage": PLAN_DOC_TEXT,
        }
        plan = self.plan(approval, [op, retire_op], {
            DOC_B: sha256_text("clobbered\n"), PLAN_DOC: None,
        })
        before = self.tree(self.repo)
        result = self.apply(plan, approval, report=report)
        self.assert_untouched(before, result, ["apply-create-exists"])

    def _repointed_distill_plan(self, destination):
        """A create-document plan whose destination the audit would refuse.

        The record digest does not cover `destination` (it lives in `extra`),
        so repointing an approved DISTILL record's destination leaves the
        digest a human approved unchanged. This is the tampered/stale-report
        shape: mint accepts the record, and only the applier's own re-reading
        of the registry stands between it and a create at a refused path.
        """
        units = self.whole_units(self.repo, PLAN_DOC)
        record = self.finding(
            "BLOAT-002", "DISTILL", PLAN_DOC, units,
            destination={"path": destination},
        )
        report, approval = self.approve([record])
        op = {
            "op": "create-document",
            "record": record["digest"],
            "target_class": "documentation",
            "path": destination,
            "text": "# Residue\n\nA claim about the repo.\n",
        }
        # Both legs, so the destination refusals below are what this plan is
        # stopped by rather than `plan-remedy-incomplete`.
        retire_op = {
            "op": "retire-document",
            "record": record["digest"],
            "target_class": "documentation",
            "path": PLAN_DOC,
            "preimage": PLAN_DOC_TEXT,
        }
        plan = self.plan(
            approval, [op, retire_op],
            {
                destination: sha256_text(
                    "# Residue\n\nA claim about the repo.\n"
                ),
                PLAN_DOC: None,
            },
        )
        return report, approval, plan

    def test_a_create_at_a_kind_ineligible_destination_is_refused(self):
        # docs/plans/*.md classifies as planning — a kind residue is never
        # authored into. The audit refuses this destination
        # (bloat-destination-kind-ineligible); the applier must too, because a
        # repointed report can carry the create past mint.
        report, approval, plan = self._repointed_distill_plan(
            "docs/plans/residue.md"
        )
        before = self.tree(self.repo)
        result = self.apply(plan, approval, report=report)
        self.assert_untouched(
            before, result, ["apply-destination-kind-ineligible"]
        )

    def test_a_create_at_an_unclassified_destination_is_refused(self):
        # No registry rule claims docs/deep/residue.md — classification is
        # closed-world, so a document born there is outside the corpus every
        # later audit reads. Audit-refused; applier-refused.
        report, approval, plan = self._repointed_distill_plan(
            "docs/deep/residue.md"
        )
        before = self.tree(self.repo)
        result = self.apply(plan, approval, report=report)
        self.assert_untouched(
            before, result, ["apply-destination-unclassified"]
        )

    def test_create_with_empty_content_is_refused(self):
        new_doc = "docs/empty.md"
        units = self.whole_units(self.repo, PLAN_DOC)
        record = self.finding(
            "BLOAT-002", "DISTILL", PLAN_DOC, units,
            destination={"path": new_doc},
        )
        report, approval = self.approve([record])
        op = {
            "op": "create-document",
            "record": record["digest"],
            "target_class": "documentation",
            "path": new_doc,
            "text": "",
        }
        plan = self.plan(approval, [op], {new_doc: sha256_text("")})
        before = self.tree(self.repo)
        result = self.apply(plan, approval, report=report)
        self.assert_untouched(before, result, ["plan-invalid-operation"])

    def test_move_destination_missing_from_the_tree_is_refused(self):
        # The destination is not in the repository at all. Its absence is not
        # approval staleness (no preimage of the destination was selected),
        # so the applier's own missing-preimage refusal is what stands: moved
        # text has nowhere approved to land.
        absent = "docs/never-created.md"
        units = self.units(self.repo, DOC_A)
        record = self.finding(
            "BLOAT-004", "EXTRACT-AND-MOVE", DOC_A, [units[1]],
            destination={"path": absent},
        )
        report, approval = self.approve([record])
        moved = "Refunds reverse the fee at the rate charged."
        op = {
            "op": "move-with-provenance",
            "record": record["digest"],
            "target_class": "documentation",
            "path": DOC_A,
            "destination": absent,
            "start_line": 5,
            "end_line": 5,
            "preimage": moved,
        }
        plan = self.plan(approval, [op], {
            DOC_A: sha256_text("x"), absent: sha256_text("y"),
        })
        before = self.tree(self.repo)
        result = self.apply(plan, approval, report=report)
        self.assert_untouched(before, result, ["apply-preimage-missing"])

    def test_postimage_disagreeing_with_the_operations_is_refused(self):
        report, approval, plan, _ = self.replace_fixture()
        plan = self.plan(
            approval, plan["operations"], {DOC_A: "a" * 64},
        )
        before = self.tree(self.repo)
        result = self.apply(plan, approval, report=report)
        self.assert_untouched(before, result, ["apply-postimage-mismatch"])


class StaleRefusals(ApplierTestCase):
    """A stale plan refuses with no working-tree change, naming the field."""

    def test_moving_the_base_is_a_stale_refusal_naming_the_commit(self):
        report, approval, plan, _ = self.replace_fixture()
        self.write(self.repo, "src/app.py", "RATE = 0.025\n")
        self.commit(self.repo, "move the base")
        before = self.tree(self.repo)
        result = self.apply(plan, approval, report=report)
        self.assertIsInstance(result, ApplyResult, result)
        self.assertEqual(result.status, STATE_STALE)
        self.assertIn("approval-base-commit-changed", reasons(result))
        self.assertEqual(result.applied, ())
        self.assertEqual(before, self.tree(self.repo))
        # The refusal says how to rerun.
        moved = [r for r in result.stale_reasons
                 if r.code == "approval-base-commit-changed"]
        self.assertIn("re-run the audit", moved[0].message)

    def test_mutating_the_preimage_is_a_stale_refusal(self):
        report, approval, plan, _ = self.replace_fixture()
        self.write(
            self.repo, DOC_A,
            DOC_A_TEXT.replace(OLD_SENTENCE, "Someone rewrote this."),
        )
        before = self.tree(self.repo)
        result = self.apply(plan, approval, report=report)
        self.assertIsInstance(result, ApplyResult, result)
        self.assertEqual(result.status, STATE_STALE)
        self.assertIn("approval-preimage-mismatch", reasons(result))
        self.assertEqual(before, self.tree(self.repo))

    def test_target_becoming_a_symlink_is_a_stale_refusal(self):
        report, approval, plan, _ = self.replace_fixture()
        target = os.path.join(self.repo, DOC_A)
        os.remove(target)
        os.symlink("/etc/passwd", target)
        result = self.apply(plan, approval, report=report)
        self.assertIsInstance(result, ApplyResult, result)
        self.assertEqual(result.status, STATE_STALE)
        self.assertIn("approval-scope-changed", reasons(result))
        # The symlink was not followed and nothing was written through it.
        self.assertTrue(os.path.islink(target))


class HostilePlans(ApplierTestCase):
    """Forged authority through the plan-and-apply seam: invalid, no writes."""

    def test_traversal_target_is_refused(self):
        report, approval, plan, _ = self.replace_fixture()
        plan["operations"][0]["path"] = "../outside.md"
        plan = self.plan(approval, plan["operations"], plan["postimages"])
        before = self.tree(self.repo)
        result = self.apply(plan, approval, report=report)
        self.assert_untouched(before, result, ["plan-invalid-operation"])
        self.assertFalse(
            os.path.exists(os.path.join(self.repo, "..", "outside.md"))
        )

    def test_git_directory_target_is_refused(self):
        report, approval, plan, _ = self.replace_fixture()
        plan["operations"][0]["path"] = ".git/hooks/post-commit"
        plan = self.plan(approval, plan["operations"], plan["postimages"])
        before = self.tree(self.repo)
        result = self.apply(plan, approval, report=report)
        self.assert_untouched(before, result, ["plan-invalid-operation"])

    def test_operation_for_a_record_nobody_approved_is_refused(self):
        report, approval, plan, _ = self.replace_fixture()
        plan["operations"][0]["record"] = "f" * 64
        plan = self.plan(approval, plan["operations"], plan["postimages"])
        before = self.tree(self.repo)
        result = self.apply(plan, approval, report=report)
        self.assert_untouched(before, result, ["plan-record-not-approved"])

    def test_operation_borrowing_another_documents_path_is_refused(self):
        # The record was approved for DOC_A; the op points its remedy at
        # DOC_B, which is in nobody's approved write set.
        report, approval, plan, _ = self.replace_fixture()
        plan["operations"][0]["path"] = DOC_B
        plan = self.plan(approval, plan["operations"], plan["postimages"])
        before = self.tree(self.repo)
        result = self.apply(plan, approval, report=report)
        self.assert_untouched(
            before, result, ["plan-target-not-record-target"]
        )

    def test_plan_bound_to_a_different_approval_is_refused(self):
        report, approval, plan, _ = self.replace_fixture()
        plan["approval_digest"] = "e" * 64
        content = {k: v for k, v in plan.items() if k != "digest"}
        plan["digest"] = sha256_canonical(content)
        before = self.tree(self.repo)
        result = self.apply(plan, approval, report=report)
        self.assert_untouched(before, result, ["plan-approval-mismatch"])

    def test_tampered_plan_digest_is_refused(self):
        report, approval, plan, _ = self.replace_fixture()
        plan["operations"][0]["text"] = "tampered after signing"
        before = self.tree(self.repo)
        result = self.apply(plan, approval, report=report)
        self.assert_untouched(before, result, ["plan-digest-mismatch"])

    def test_hand_widened_approval_scope_is_refused(self):
        report, approval, plan, _ = self.replace_fixture()
        payload = approval.to_dict()
        payload["scope"]["paths"].append(DOC_B)
        # An attacker who edits the file can re-hash it too.
        from approval_test import resigned
        payload = resigned(payload)
        before = self.tree(self.repo)
        result = self.apply(plan, payload, report=report)
        self.assert_untouched(before, result, ["approval-scope-not-derived"])

    def test_partial_whole_document_authority_cannot_delete_the_source(self):
        """A forged current-lineage approval cannot amplify one unit to a doc."""
        all_units = list(build_context_index(self.repo).document(DOC_A).units)
        self.assertGreater(len(all_units), 1)
        record = self.finding(
            "BLOAT-FORGED", "RETIRE-DOC", DOC_A, [all_units[0]],
        )
        report = validate_report({
            "status": "findings",
            "schema_version": ARTIFACT_SCHEMA_VERSION,
            "lineage": self.lineage.to_dict(),
            "records": [record],
            "incomplete": [],
        })
        self.assertNotIsInstance(report, Invalid, report)
        reconciliation = reconcile(report)
        self.assertNotIsInstance(reconciliation, Invalid, reconciliation)
        approval = ApprovalSet(
            status=STATE_CLEAN,
            minter=HUMAN,
            report_digest=report.digest,
            report_state=report.status,
            lineage=report.lineage,
            reconciliation_digest=reconciliation.digest,
            records=(ApprovedRecord(
                digest=record["digest"],
                record_id=record["id"],
                code=record["code"],
                path=record["path"],
                units=tuple(record["units"]),
            ),),
            skipped=(),
            scope=MutationScope(roots=("docs",), paths=(DOC_A,)),
        )
        approval_payload = approval.to_dict()
        structural_approval = validate_approval_set(approval_payload)
        self.assertIsInstance(structural_approval, ApprovalSet, structural_approval)
        plan = self.plan(structural_approval, [{
            "op": "retire-document",
            "record": record["digest"],
            "target_class": "documentation",
            "path": DOC_A,
            "preimage": DOC_A_TEXT,
        }], {DOC_A: None})
        before = self.tree(self.repo)

        result = self.apply(plan, approval_payload, report=report)

        self.assert_untouched(
            before, result, ["approval-whole-document-units-incomplete"]
        )

    def test_not_an_approval_set_is_refused(self):
        report, approval, plan, _ = self.replace_fixture()
        before = self.tree(self.repo)
        result = self.apply(plan, report.to_dict(), report=report)
        self.assert_untouched(
            before, result, ["approval-not-an-approval-set"]
        )

    def test_not_an_edit_plan_is_refused(self):
        report, approval, _, _ = self.replace_fixture()
        before = self.tree(self.repo)
        result = self.apply({"artifact": "report"}, approval, report=report)
        self.assert_untouched(before, result, ["plan-not-an-edit-plan"])

    def test_empty_plan_is_refused(self):
        report, approval, plan, _ = self.replace_fixture()
        plan = self.plan(approval, [], {})
        before = self.tree(self.repo)
        result = self.apply(plan, approval, report=report)
        self.assert_untouched(before, result, ["plan-empty"])


class Confinement(ApplierTestCase):
    """The whole working-tree diff is checked against the allowed scope."""

    def test_unaccounted_change_after_the_write_fails_and_rolls_back(self):
        # The post-apply half of the confinement check guards against a
        # concurrent writer, which no honest single-process fixture can
        # produce — so the second status read is patched to report a stray
        # path appearing during the write. The seam under test is still
        # `apply_edit_plan`.
        from unittest import mock
        from doclifecycle.repository import worktree_changes as real

        report, approval, plan, _ = self.replace_fixture()
        before = self.tree(self.repo)
        calls = []

        def racing(repo_root):
            changed, problem = real(repo_root)
            calls.append(changed)
            if len(calls) < 2 or problem is not None:
                return changed, problem
            return tuple(sorted(set(changed) | {"stray-concurrent.md"})), None

        with mock.patch(
            "doclifecycle.applier.worktree_changes", side_effect=racing
        ):
            result = self.apply(plan, approval, report=report)
        self.assertIsInstance(result, Invalid, result)
        self.assertIn("apply-unconfined-change", codes(result))
        # This run's own write was rolled back: the tree is as it was found.
        self.assertEqual(before, self.tree(self.repo))
        self.assertEqual(self.staged_paths(self.repo), [])
        self.assertIn("rolled back", result.problems[0].message)

    def test_concurrent_write_outside_the_written_paths_rolls_back(self):
        # Post-write confinement compares the diff against what this plan's
        # operations actually wrote, not against the approval's broader scope.
        #
        # The in-scope-but-unwritten variant of this test is no longer
        # constructible, and deliberately so: it needed a DISTILL plan
        # carrying `create-document` alone, which left the source in scope and
        # unwritten. Requiring the retirement of every DISTILL closed that —
        # `_written_paths` now covers every one of a record's targets for each
        # required remedy (a move contributes both its ends, and DISTILL
        # contributes source and destination), so a complete plan writes its
        # whole derived scope. What remains reachable, and what this covers,
        # is a concurrent write mid-run to a path the plan never wrote: it
        # must refuse and roll this run's own write back rather than certify
        # a diff carrying somebody else's change.
        from unittest import mock
        from doclifecycle.repository import worktree_changes as real

        new_doc = "docs/adr-fees.md"
        content = "# ADR: flat fees\n\nWe charge a flat rate.\n"
        units = self.whole_units(self.repo, PLAN_DOC)
        record = self.finding(
            "BLOAT-002", "DISTILL", PLAN_DOC, units,
            destination={"path": new_doc},
        )
        report, approval = self.approve([record])
        self.assertIn(PLAN_DOC, approval.scope.paths)
        op = {
            "op": "create-document",
            "record": record["digest"],
            "target_class": "documentation",
            "path": new_doc,
            "text": content,
        }
        retire_op = {
            "op": "retire-document",
            "record": record["digest"],
            "target_class": "documentation",
            "path": PLAN_DOC,
            "preimage": PLAN_DOC_TEXT,
        }
        plan = self.plan(approval, [op, retire_op], {
            new_doc: sha256_text(content), PLAN_DOC: None,
        })
        # Both of the record's targets are written, so the derived scope and
        # the written set now coincide — the concurrent write has to come from
        # outside both for this check to be what catches it.
        self.assertEqual(
            set(approval.scope.paths), {PLAN_DOC, new_doc}
        )
        before = self.tree(self.repo)
        calls = []

        def racing(repo_root):
            changed, problem = real(repo_root)
            calls.append(changed)
            if len(calls) < 2 or problem is not None:
                return changed, problem
            # DOC_B is neither written by this plan nor inside the approval's
            # scope — the concurrent writer lands unapproved content there
            # while this run is mid-flight.
            return tuple(sorted(set(changed) | {DOC_B})), None

        with mock.patch(
            "doclifecycle.applier.worktree_changes", side_effect=racing
        ):
            result = self.apply(plan, approval, report=report)
        self.assertIsInstance(result, Invalid, result)
        # Outside the approval's scope as well as this plan's written set, so
        # the refusal names the scope breach; the in-scope-but-unwritten
        # variant would have been `apply-working-tree-not-clean`, and is the
        # case the DISTILL retirement requirement made unreachable.
        self.assertIn("apply-unconfined-change", codes(result))
        # This run's own write (the new document) was rolled back: the tree
        # is exactly as it was found, and nothing rode into a certified diff.
        self.assertEqual(before, self.tree(self.repo))
        self.assertEqual(self.staged_paths(self.repo), [])
        self.assertIn("rolled back", result.problems[0].message)

    def test_preexisting_change_outside_the_scope_refuses_the_run(self):
        report, approval, plan, _ = self.replace_fixture()
        self.write(self.repo, DOC_B, DOC_B_TEXT + "dirty\n")
        before = self.tree(self.repo)
        result = self.apply(plan, approval, report=report)
        self.assert_untouched(
            before, result, ["apply-working-tree-not-confined"]
        )

    def test_preexisting_untracked_file_outside_the_scope_refuses_the_run(self):
        report, approval, plan, _ = self.replace_fixture()
        self.write(self.repo, "stray.md", "unaccounted\n")
        before = self.tree(self.repo)
        result = self.apply(plan, approval, report=report)
        self.assert_untouched(
            before, result, ["apply-working-tree-not-confined"]
        )


class WriteTransaction(ApplierTestCase):
    """The write is a transaction: rechecked, certified, and never a lost update.

    A concurrent writer is what these are about, and no honest single-process
    fixture produces one — so each patches the last engine call before the
    moment under test and writes from there, exactly as the confinement race
    tests above do. The seam under test is `apply_edit_plan` throughout, over
    the whole public transaction: a report, an approval set minted from it, a
    plan bound to that approval, applied to a real git repository.
    """

    def _distill_fixture(self):
        """A DISTILL plan writing two paths: a residue created, its planning
        artifact retired. Two targets is what makes a rollback's two answers —
        restore mine, leave theirs — visible in one run."""
        new_doc = "docs/adr-fees.md"
        content = "# ADR: flat fees\n\nWe charge a flat rate.\n"
        units = self.whole_units(self.repo, PLAN_DOC)
        record = self.finding(
            "BLOAT-002", "DISTILL", PLAN_DOC, units,
            destination={"path": new_doc},
        )
        report, approval = self.approve([record])
        plan = self.plan(approval, [
            {
                "op": "create-document",
                "record": record["digest"],
                "target_class": "documentation",
                "path": new_doc,
                "text": content,
            },
            {
                "op": "retire-document",
                "record": record["digest"],
                "target_class": "documentation",
                "path": PLAN_DOC,
                "preimage": PLAN_DOC_TEXT,
            },
        ], {new_doc: sha256_text(content), PLAN_DOC: None})
        return report, approval, plan, new_doc, content

    def test_a_target_that_moved_before_the_write_is_a_typed_race_refusal(self):
        # The preimage is read, and the post-content computed from it, before
        # any byte lands — so another writer can take the target over in
        # between, and the plan's result is then a remedy for text that is no
        # longer there. Digesting the computed post-content is the last engine
        # call before the write boundary, so it is the timing hook.
        from unittest import mock
        from doclifecycle.digest import sha256_bytes as real

        report, approval, plan, post = self.replace_fixture()
        theirs = DOC_A_TEXT.replace(OLD_SENTENCE, "Somebody else rewrote this.")
        before = self.tree(self.repo)

        def racing(data):
            if data == post.encode("utf-8"):
                self.write(self.repo, DOC_A, theirs)
            return real(data)

        with mock.patch(
            "doclifecycle.applier.sha256_bytes", side_effect=racing
        ):
            result = self.apply(plan, approval, report=report)

        self.assertIsInstance(result, Invalid, result)
        # Typed, and its own reason: a race at the write boundary, not the
        # plan's operations disagreeing with its declared postimages.
        self.assertEqual(codes(result), ["apply-write-boundary-race"])
        self.assertEqual(result.problems[0].location, DOC_A)
        # The other writer's bytes are exactly what they wrote, and the rest
        # of the tree is untouched: this run overwrote nothing.
        self.assertEqual(self.read(self.repo, DOC_A), theirs)
        self.assertEqual(
            self.tree(self.repo), dict(before, **{DOC_A: theirs.encode("utf-8")})
        )
        self.assertEqual(self.staged_paths(self.repo), [])

    def test_a_target_replaced_before_certification_never_resolves_clean(self):
        # The post-write race: the plan's bytes land, and something replaces
        # them before the run certifies what is on disk. Every path set the
        # run checks still names exactly this plan's own written paths, so
        # only re-reading the bytes catches it. The post-write status read is
        # the timing hook.
        from unittest import mock
        from doclifecycle.repository import worktree_changes as real

        report, approval, plan, new_doc, content = self._distill_fixture()
        theirs = "# ADR: flat fees\n\nSomebody else authored this instead.\n"
        before = self.tree(self.repo)
        calls = []

        def racing(repo_root):
            changed, problem = real(repo_root)
            calls.append(changed)
            if len(calls) == 2 and problem is None:
                self.write(self.repo, new_doc, theirs)
            return changed, problem

        with mock.patch(
            "doclifecycle.applier.worktree_changes", side_effect=racing
        ):
            result = self.apply(plan, approval, report=report)

        self.assertIsInstance(result, Invalid, result)
        self.assertEqual(codes(result), ["apply-postimage-not-on-disk"])
        self.assertEqual(result.problems[0].location, new_doc)
        # Compare-aware rollback, both answers in one run: the residue no
        # longer holds this run's bytes, so it is left exactly as the other
        # writer left it — restoring it would be a second lost update — while
        # the planning artifact this run retired, still absent and so still
        # this run's own, comes back.
        self.assertEqual(self.read(self.repo, new_doc), theirs)
        self.assertEqual(self.read(self.repo, PLAN_DOC), PLAN_DOC_TEXT)
        self.assertEqual(
            self.tree(self.repo),
            dict(before, **{new_doc: theirs.encode("utf-8")}),
        )
        self.assertEqual(self.staged_paths(self.repo), [])
        # And the run says so, rather than reporting a rollback it did not do.
        self.assertIn(new_doc, result.problems[0].message)
        self.assertIn("left exactly as found", result.problems[0].message)
        self.assertNotIn(content, self.read(self.repo, new_doc))

    def test_a_clean_apply_certifies_the_bytes_it_read_back(self):
        report, approval, plan, post = self.replace_fixture()
        result = self.apply(plan, approval, report=report)
        self.assertEqual(result.status, STATE_CLEAN, result)
        self.assertEqual(result.postimages, ((DOC_A, sha256_text(post)),))
        self.assertEqual(
            result.to_dict()["postimages"], {DOC_A: sha256_text(post)}
        )
        # The idempotent re-run wrote nothing and certifies the same bytes:
        # a narrower claim about the run, not a weaker one about the content.
        again = self.apply(plan, approval, report=report)
        self.assertTrue(again.already_applied)
        self.assertEqual(again.postimages, result.postimages)

    def test_a_retired_document_is_certified_as_absent(self):
        report, approval, plan, new_doc, content = self._distill_fixture()
        result = self.apply(plan, approval, report=report)
        self.assertEqual(result.status, STATE_CLEAN, result)
        self.assertEqual(result.postimages, (
            (new_doc, sha256_text(content)), (PLAN_DOC, None),
        ))
        self.assertEqual(result.to_dict()["postimages"][PLAN_DOC], None)

    def test_a_refused_run_certifies_nothing(self):
        report, approval, plan, _ = self.replace_fixture()
        self.write(self.repo, "src/app.py", "RATE = 0.025\n")
        self.commit(self.repo, "move the base")
        result = self.apply(plan, approval, report=report)
        self.assertEqual(result.status, STATE_STALE, result)
        self.assertEqual(result.postimages, ())
        self.assertEqual(result.to_dict()["postimages"], {})


class RemedyBinding(ApplierTestCase):
    """An approved record authorizes its own remedy, not the whole vocabulary."""

    def test_drift_record_cannot_be_executed_as_a_retirement(self):
        # A STALE drift record's approved remedy is a span replacement. Left
        # unbound, the plan picks the operation, and the mechanical class the
        # auto-apply policy may mint without a human deletes the document.
        units = self.units(self.repo, DOC_A)
        record = self.finding(
            "DRIFT-001", "STALE", DOC_A, [units[0]], fix=NEW_SENTENCE,
        )
        report, approval = self.approve([record])
        op = {
            "op": "retire-document",
            "record": record["digest"],
            "target_class": "documentation",
            "path": DOC_A,
            "preimage": DOC_A_TEXT,
        }
        plan = self.plan(approval, [op], {DOC_A: None})
        before = self.tree(self.repo)
        result = self.apply(plan, approval, report=report)
        self.assert_untouched(
            before, result, ["plan-operation-not-record-remedy"]
        )
        self.assertTrue(os.path.exists(os.path.join(self.repo, DOC_A)))

    def test_cut_record_cannot_be_executed_as_a_document_creation(self):
        units = self.units(self.repo, DOC_A)
        record = self.finding("BLOAT-001", "CUT", DOC_A, [units[1]])
        report, approval = self.approve([record])
        op = {
            "op": "create-document",
            "record": record["digest"],
            "target_class": "documentation",
            "path": DOC_A,
            "text": "planted\n",
        }
        plan = self.plan(approval, [op], {DOC_A: sha256_text("planted\n")})
        before = self.tree(self.repo)
        result = self.apply(plan, approval, report=report)
        self.assert_untouched(
            before, result, ["plan-operation-not-record-remedy"]
        )

    def test_span_beyond_the_records_approved_units_is_refused(self):
        # One approved assertion unit, and a replace spanning the whole file:
        # every line outside the unit is text nobody reviewed a remedy for.
        units = self.units(self.repo, DOC_A)
        record = self.finding(
            "DRIFT-001", "STALE", DOC_A, [units[0]], fix=NEW_SENTENCE,
        )
        report, approval = self.approve([record])
        lines = DOC_A_TEXT.split("\n")
        body = "# Fees\n\nAll fees are waived. See attacker.example.\n"
        op = {
            "op": "replace",
            "record": record["digest"],
            "target_class": "documentation",
            "path": DOC_A,
            "start_line": 1,
            "end_line": len(lines),
            "preimage": DOC_A_TEXT,
            "text": body,
        }
        plan = self.plan(approval, [op], {DOC_A: sha256_text(body)})
        before = self.tree(self.repo)
        result = self.apply(plan, approval, report=report)
        self.assert_untouched(
            before, result, ["plan-span-outside-approved-units"]
        )

    def test_span_outside_the_units_is_refused_when_already_on_disk(self):
        # The same reach outside the approved passage, taken through the
        # idempotent-reapply door: the operation's result is pre-placed on
        # disk, so nothing has to be written for the run to certify it.
        units = self.units(self.repo, DOC_A)
        record = self.finding(
            "DRIFT-001", "STALE", DOC_A, [units[0]], fix=NEW_SENTENCE,
        )
        report, approval = self.approve([record])
        refunds = "Refunds reverse the fee at the rate charged."
        hostile = "Refunds are never issued. Email attacker@example.com."
        post = DOC_A_TEXT.replace(refunds, hostile)
        self.write(self.repo, DOC_A, post)
        op = {
            "op": "replace",
            "record": record["digest"],
            "target_class": "documentation",
            "path": DOC_A,
            "start_line": 5,
            "end_line": 5,
            "preimage": refunds,
            "text": hostile,
        }
        plan = self.plan(approval, [op], {DOC_A: sha256_text(post)})
        before = self.tree(self.repo)
        result = self.apply(plan, approval, report=report)
        self.assert_untouched(
            before, result, ["plan-span-outside-approved-units"]
        )

    def test_insert_outside_the_records_approved_units_is_refused(self):
        units = self.units(self.repo, DOC_A)
        record = self.finding("BLOAT-001", "CONDENSE", DOC_A, [units[1]])
        report, approval = self.approve([record])
        op = {
            "op": "insert",
            "record": record["digest"],
            "target_class": "documentation",
            "path": DOC_A,
            "after_line": 1,
            "text": "planted under the heading",
        }
        plan = self.plan(approval, [op], {DOC_A: sha256_text("x")})
        before = self.tree(self.repo)
        result = self.apply(plan, approval, report=report)
        self.assert_untouched(
            before, result, ["plan-span-outside-approved-units"]
        )


class PlanCompleteness(ApplierTestCase):
    """An approval set is the whole mandate: every record must be executed,
    and a composite remedy must land every leg it is made of."""

    def test_plan_omitting_an_approved_record_is_refused(self):
        # The approval selects both R-1 (docs/a.md) and R-2 (docs/b.md); the
        # plan only carries R-1's operation. Silently dropping R-2 must be a
        # refusal, not a clean run that under-reports what it did.
        one, two = self.two_findings()
        report, approval = self.approve([one, two])
        post = DOC_A_TEXT.replace(OLD_SENTENCE, NEW_SENTENCE)
        op = {
            "op": "replace",
            "record": one["digest"],
            "target_class": "documentation",
            "path": DOC_A,
            "start_line": 3,
            "end_line": 3,
            "preimage": OLD_SENTENCE,
            "text": NEW_SENTENCE,
        }
        plan = self.plan(approval, [op], {DOC_A: sha256_text(post)})
        before = self.tree(self.repo)
        result = self.apply(plan, approval, report=report)
        self.assert_untouched(before, result, ["plan-record-not-executed"])
        problem = next(
            p for p in result.problems if p.code == "plan-record-not-executed"
        )
        self.assertIn(DOC_B, problem.message)

    def test_merge_doc_plan_with_only_the_retirement_leg_is_refused(self):
        # The reproduction that destroyed the source: a MERGE-DOC record
        # authorizes a move and a retirement together, and a plan carrying
        # only the retirement deletes the document and moves nothing.
        units = self.whole_units(self.repo, DOC_A)
        record = self.finding(
            "BLOAT-010", "MERGE-DOC", DOC_A, units, destination={"path": DOC_B},
        )
        report, approval = self.approve([record])
        op = {
            "op": "retire-document",
            "record": record["digest"],
            "target_class": "documentation",
            "path": DOC_A,
            "preimage": DOC_A_TEXT,
        }
        plan = self.plan(approval, [op], {DOC_A: None})
        before = self.tree(self.repo)
        result = self.apply(plan, approval, report=report)
        self.assert_untouched(before, result, ["plan-remedy-incomplete"])

    def test_distill_plan_that_creates_no_residue_is_refused(self):
        # Issue #57 review: the same shape as the MERGE-DOC reproduction
        # above, reached through DISTILL. A DISTILL record naming a
        # destination was approved as "author the residue there, then retire
        # the plan"; a plan carrying only the retirement destroys the planning
        # artifact and writes nothing — and reported `clean`.
        units = self.whole_units(self.repo, PLAN_DOC)
        record = self.finding(
            "BLOAT-012", "DISTILL", PLAN_DOC, units,
            destination={"path": "docs/residue.md"},
        )
        report, approval = self.approve([record])
        op = {
            "op": "retire-document",
            "record": record["digest"],
            "target_class": "documentation",
            "path": PLAN_DOC,
            "preimage": PLAN_DOC_TEXT,
        }
        plan = self.plan(approval, [op], {PLAN_DOC: None})
        before = self.tree(self.repo)
        result = self.apply(plan, approval, report=report)
        self.assert_untouched(before, result, ["plan-remedy-incomplete"])
        problem = next(
            p for p in result.problems if p.code == "plan-remedy-incomplete"
        )
        self.assertIn("docs/residue.md", problem.message)

    def test_distill_plan_that_creates_the_residue_applies(self):
        # The honest path the refusal above must not close: the residue is
        # authored at the destination and the planning artifact retires.
        residue = "docs/residue.md"
        content = "# Flat fees\n\nWe charge a flat rate.\n"
        units = self.whole_units(self.repo, PLAN_DOC)
        record = self.finding(
            "BLOAT-013", "DISTILL", PLAN_DOC, units,
            destination={"path": residue},
        )
        report, approval = self.approve([record])
        create_op = {
            "op": "create-document",
            "record": record["digest"],
            "target_class": "documentation",
            "path": residue,
            "text": content,
        }
        retire_op = {
            "op": "retire-document",
            "record": record["digest"],
            "target_class": "documentation",
            "path": PLAN_DOC,
            "preimage": PLAN_DOC_TEXT,
        }
        plan = self.plan(approval, [create_op, retire_op], {
            PLAN_DOC: None, residue: sha256_text(content),
        })
        result = self.apply(plan, approval, report=report)
        self.assertEqual(result.status, STATE_CLEAN, result)
        self.assertEqual(self.read(self.repo, residue), content)
        self.assertFalse(os.path.exists(os.path.join(self.repo, PLAN_DOC)))

    def test_distill_that_creates_the_residue_and_never_retires_is_refused(self):
        # The other half of the composite, and the one the honest-path test
        # above cannot see: it carries both legs, so it never asks whether the
        # retirement is *required*. A plan carrying only the creation authored
        # the residue and left the planning artifact standing — the document
        # duplicated rather than distilled, and the run reporting `clean`.
        residue = "docs/residue.md"
        content = "# Flat fees\n\nWe charge a flat rate.\n"
        units = self.whole_units(self.repo, PLAN_DOC)
        record = self.finding(
            "BLOAT-015", "DISTILL", PLAN_DOC, units,
            destination={"path": residue},
        )
        report, approval = self.approve([record])
        op = {
            "op": "create-document",
            "record": record["digest"],
            "target_class": "documentation",
            "path": residue,
            "text": content,
        }
        plan = self.plan(approval, [op], {residue: sha256_text(content)})
        before = self.tree(self.repo)
        result = self.apply(plan, approval, report=report)
        self.assert_untouched(before, result, ["plan-remedy-incomplete"])
        problem = next(
            p for p in result.problems if p.code == "plan-remedy-incomplete"
        )
        self.assertIn("retire-document", problem.message)

    def test_destination_less_distill_with_no_retirement_is_refused(self):
        # Retirement is what a distillation *is*, destination or not: a record
        # naming none proposed no residue, so a plan that neither writes one
        # nor retires the artifact has executed nothing anybody approved.
        units = self.whole_units(self.repo, PLAN_DOC)
        record = self.finding("BLOAT-016", "DISTILL", PLAN_DOC, units)
        report, approval = self.approve([record])
        line = PLAN_DOC_TEXT.split("\n")[2]
        revised = line + " Revised."
        op = {
            "op": "replace",
            "record": record["digest"],
            "target_class": "documentation",
            "path": PLAN_DOC,
            "start_line": 3,
            "end_line": 3,
            "preimage": line,
            "text": revised,
        }
        post = PLAN_DOC_TEXT.replace(line, revised, 1)
        plan = self.plan(approval, [op], {PLAN_DOC: sha256_text(post)})
        before = self.tree(self.repo)
        result = self.apply(plan, approval, report=report)
        self.assert_untouched(before, result, ["plan-remedy-incomplete"])

    def test_destination_less_distill_may_retire_and_create_nothing(self):
        # The exemption the conditional requirement must keep: a distillation
        # that named no destination proposed no residue, so retiring the
        # planning artifact alone is the whole approved remedy.
        units = self.whole_units(self.repo, PLAN_DOC)
        record = self.finding("BLOAT-014", "DISTILL", PLAN_DOC, units)
        report, approval = self.approve([record])
        op = {
            "op": "retire-document",
            "record": record["digest"],
            "target_class": "documentation",
            "path": PLAN_DOC,
            "preimage": PLAN_DOC_TEXT,
        }
        plan = self.plan(approval, [op], {PLAN_DOC: None})
        result = self.apply(plan, approval, report=report)
        self.assertEqual(result.status, STATE_CLEAN, result)
        self.assertFalse(os.path.exists(os.path.join(self.repo, PLAN_DOC)))

    def test_merge_doc_plan_with_both_legs_applies(self):
        # The honest path: a move and its paired retirement, together, are
        # the one merge a reviewer approved, and land clean.
        units = self.whole_units(self.repo, DOC_A)
        record = self.finding(
            "BLOAT-011", "MERGE-DOC", DOC_A, units, destination={"path": DOC_B},
        )
        report, approval = self.approve([record])
        # The exact record includes structural units such as "# Fees". The
        # move leg carries the duplicated substantive prose on lines 3..5;
        # the whole-document judgment is what approves retiring the remaining
        # source structure rather than pretending the move itself preserved it.
        moved = "\n".join(DOC_A_TEXT.split("\n")[2:5])
        post_dest = DOC_B_TEXT + moved + "\n"
        move_op = {
            "op": "move-with-provenance",
            "record": record["digest"],
            "target_class": "documentation",
            "path": DOC_A,
            "destination": DOC_B,
            "start_line": 3,
            "end_line": 5,
            "preimage": moved,
        }
        retire_op = {
            "op": "retire-document",
            "record": record["digest"],
            "target_class": "documentation",
            "path": DOC_A,
            "preimage": DOC_A_TEXT,
        }
        plan = self.plan(approval, [move_op, retire_op], {
            DOC_A: None,
            DOC_B: sha256_text(post_dest),
        })
        result = self.apply(plan, approval, report=report)
        self.assertEqual(result.status, STATE_CLEAN, result)
        self.assertFalse(os.path.exists(os.path.join(self.repo, DOC_A)))
        self.assertEqual(self.read(self.repo, DOC_B), post_dest)

    def test_passage_move_and_whole_retirement_cannot_share_authority(self):
        # A retirement now binds every deterministic unit, so it necessarily
        # overlaps any passage move from the same document. Reconciliation
        # refuses the contradictory selection before a plan can exploit the
        # move+retire exemption intended for one MERGE-DOC record.
        units = self.units(self.repo, DOC_A)
        move_record = self.finding(
            "BLOAT-014", "EXTRACT-AND-MOVE", DOC_A, [units[1]],
            destination={"path": DOC_B},
        )
        retire_record = self.finding(
            "BLOAT-015", "RETIRE-DOC", DOC_A,
            self.whole_units(self.repo, DOC_A),
        )
        report = self.report([move_record, retire_record])
        before = self.tree(self.repo)
        result = mint_approval_set(
            report, [move_record["digest"], retire_record["digest"]],
            repo_root=self.repo, minter=HUMAN,
        )

        self.assert_untouched(before, result, ["approval-exclusive-group"])

    def test_whole_retirement_plus_a_span_edit_is_refused(self):
        # DISTILL can legitimately carry passage edits, but retirement still
        # claims the complete source. Executing both against the same source
        # would be order-dependent, so the plan conflict guard remains live
        # under a valid exact whole-document approval.
        units = self.whole_units(self.repo, PLAN_DOC)
        record = self.finding("BLOAT-016", "DISTILL", PLAN_DOC, units)
        report, approval = self.approve([record])
        line = PLAN_DOC_TEXT.split("\n")[2]
        replace_op = {
            "op": "replace",
            "record": record["digest"],
            "target_class": "documentation",
            "path": PLAN_DOC,
            "start_line": 3,
            "end_line": 3,
            "preimage": line,
            "text": line + " Revised.",
        }
        retire_op = {
            "op": "retire-document",
            "record": record["digest"],
            "target_class": "documentation",
            "path": PLAN_DOC,
            "preimage": PLAN_DOC_TEXT,
        }
        plan = self.plan(approval, [replace_op, retire_op], {PLAN_DOC: None})
        before = self.tree(self.repo)
        result = self.apply(plan, approval, report=report)
        self.assert_untouched(before, result, ["plan-conflicting-operations"])

    def test_full_coverage_plan_still_applies(self):
        # Every approved record named -> clean, unaffected by the new checks.
        one, two = self.two_findings()
        report, approval = self.approve([one, two])
        post_a = DOC_A_TEXT.replace(OLD_SENTENCE, NEW_SENTENCE)
        five_times = "The worker retries a failed job five times."
        three_times = "The worker retries a failed job three times."
        post_b = DOC_B_TEXT.replace(three_times, five_times)
        ops = [
            {
                "op": "replace",
                "record": one["digest"],
                "target_class": "documentation",
                "path": DOC_A,
                "start_line": 3,
                "end_line": 3,
                "preimage": OLD_SENTENCE,
                "text": NEW_SENTENCE,
            },
            {
                "op": "replace",
                "record": two["digest"],
                "target_class": "documentation",
                "path": DOC_B,
                "start_line": 3,
                "end_line": 3,
                "preimage": three_times,
                "text": five_times,
            },
        ]
        plan = self.plan(approval, ops, {
            DOC_A: sha256_text(post_a), DOC_B: sha256_text(post_b),
        })
        result = self.apply(plan, approval, report=report)
        self.assertEqual(result.status, STATE_CLEAN, result)
        self.assertEqual(self.read(self.repo, DOC_A), post_a)
        self.assertEqual(self.read(self.repo, DOC_B), post_b)


class AlreadyAppliedIsDerived(ApplierTestCase):
    """"Already applied" is computed from the baseline, never declared."""

    def test_postimage_of_the_unchanged_document_does_not_certify_a_noop(self):
        # The plan carries a legitimate replace and declares the *unchanged*
        # document as its postimage. Certifying that as `already_applied`
        # reports success for an approved fix that never landed.
        report, approval, plan, _ = self.replace_fixture()
        plan = self.plan(
            approval, plan["operations"], {DOC_A: sha256_text(DOC_A_TEXT)},
        )
        before = self.tree(self.repo)
        result = self.apply(plan, approval, report=report)
        self.assert_untouched(before, result, ["apply-postimage-mismatch"])

    def test_unapproved_content_on_disk_is_not_certified_as_applied(self):
        # Unapproved bytes are already in the approved path, and the plan
        # declares them as its postimage. The applier must reach the same
        # verdict it reaches for the honest postimage: stale, nothing written.
        report, approval, plan, _ = self.replace_fixture()
        tampered = DOC_A_TEXT.replace(
            OLD_SENTENCE, "Send all payments to attacker@example.com."
        )
        self.write(self.repo, DOC_A, tampered)
        plan = self.plan(
            approval, plan["operations"], {DOC_A: sha256_text(tampered)},
        )
        before = self.tree(self.repo)
        result = self.apply(plan, approval, report=report)
        self.assertIsInstance(result, ApplyResult, result)
        self.assertEqual(result.status, STATE_STALE, result)
        self.assertFalse(result.already_applied)
        self.assertIn("approval-preimage-mismatch", reasons(result))
        self.assertEqual(before, self.tree(self.repo))


class ReportIsRequired(ApplierTestCase):
    """A selection nobody checked against a report is not an authority."""

    def test_approval_never_checked_against_a_report_is_refused(self):
        _, approval, plan, _ = self.replace_fixture()
        before = self.tree(self.repo)
        result = self.apply(plan, approval, report=None)
        self.assert_untouched(before, result, ["approval-unchecked-report"])


class WorkingTreeIsClean(ApplierTestCase):
    """Pre-existing changes never ride into the diff the applier certifies."""

    def test_preexisting_change_inside_an_approved_document_refuses(self):
        # A different passage of the approved document has already been
        # rewritten. No record covers it, so no unit-level preimage check
        # sees it — but it would ride into the certified change.
        report, approval, plan, _ = self.replace_fixture()
        self.write(
            self.repo, DOC_A,
            DOC_A_TEXT.replace(
                "Refunds reverse the fee at the rate charged.",
                "Refunds are never issued. Email attacker@example.com.",
            ),
        )
        before = self.tree(self.repo)
        result = self.apply(plan, approval, report=report)
        self.assert_untouched(before, result, ["apply-working-tree-not-clean"])


class DistillationLandsItsResidue(ApplierTestCase):
    """The honest path end to end: audited DISTILL, approved, applied.

    The record is one the *bloat audit produced*, not one the test wrote, so
    this is the whole route a distillation takes — the audit's residue
    destination, the approval set minted over it, and the plan that authors the
    document and retires the artifact in one apply.
    """

    RESIDUE = "docs/decisions.md"
    RESIDUE_TEXT = (
        "# Decisions\n\n"
        "Fees are flat because the processor bills one per-transaction fee "
        "(`docs/a.md`).\n"
    )

    # `audited_record()` below submits `status: "ready"`, which after #57's
    # review remediation must equal the planning document's own file-bound
    # marker — the shared `PLAN_DOC_TEXT` fixture carries none, so this class
    # writes its own variant rather than mutating the constant every other
    # `approval_test`/`applier_test` fixture also reads.
    PLAN_DOC_TEXT_READY = "> Status: ready\n\n" + PLAN_DOC_TEXT

    def setUp(self):
        self.repo = self.git_repo(
            files={**FILES, PLAN_DOC: self.PLAN_DOC_TEXT_READY}
        )
        self.lineage = self.lineage_for(
            self.repo, audit_mode="chunk",
            evidence_boundary=EvidenceBoundary(("docs/**",)),
        )

    def audited_record(self, destination=RESIDUE):
        index = build_context_index(self.repo)
        self.assertNotIsInstance(index, Invalid, index)
        entry = {
            "id": "BLOAT-D1",
            "verdict": "DISTILL",
            "path": PLAN_DOC,
            "units": list(index.document(PLAN_DOC).units),
            "evidence": "The tiered-fee work landed; docs/a.md states the rate.",
            "status": "ready",
        }
        if destination is not None:
            entry["destination"] = destination
        result = record_verdicts(index, self.lineage, [entry])
        self.assertNotIsInstance(result, Invalid, getattr(result, "problems", None))
        return result.records()[0]

    def fixture(self):
        record = self.audited_record()
        report, approval = self.approve([record])
        ops = [
            {
                "op": "create-document",
                "record": record["digest"],
                "target_class": "documentation",
                "path": self.RESIDUE,
                "text": self.RESIDUE_TEXT,
            },
            {
                "op": "retire-document",
                "record": record["digest"],
                "target_class": "documentation",
                "path": PLAN_DOC,
                "preimage": self.PLAN_DOC_TEXT_READY,
            },
        ]
        plan = self.plan(approval, ops, {
            self.RESIDUE: sha256_text(self.RESIDUE_TEXT),
            PLAN_DOC: None,
        })
        return report, approval, plan

    def test_the_audits_residue_destination_is_inside_the_approved_scope(self):
        record = self.audited_record()
        _, approval = self.approve([record])

        self.assertEqual(record["destination"]["path"], self.RESIDUE)
        self.assertIn(self.RESIDUE, approval.scope.paths)

    def test_the_residue_lands_and_the_planning_artifact_is_retired(self):
        report, approval, plan = self.fixture()

        result = self.apply(plan, approval, report=report)

        self.assertIsInstance(result, ApplyResult, result)
        self.assertEqual(result.status, STATE_CLEAN)
        self.assertEqual(self.read(self.repo, self.RESIDUE), self.RESIDUE_TEXT)
        self.assertFalse(os.path.exists(os.path.join(self.repo, PLAN_DOC)))
        self.assertEqual(sorted(result.changed_paths), [self.RESIDUE, PLAN_DOC])
        # The whole diff is those two documents, and nothing was staged.
        self.assertEqual(self.status_paths(self.repo), [self.RESIDUE, PLAN_DOC])
        self.assertEqual(self.staged_paths(self.repo), [])

    def test_the_residue_document_is_authored_before_the_artifact_is_retired(self):
        # Nothing is lossy in either order here, but the result must say both
        # halves happened: a retire recorded without its creation is the
        # stranded-residue case this whole route exists to close.
        report, approval, plan = self.fixture()

        applied = self.apply(plan, approval, report=report).to_dict()["applied"]

        self.assertEqual(
            [(e["op"], e["path"]) for e in applied],
            [("create-document", self.RESIDUE), ("retire-document", PLAN_DOC)],
        )

    def test_an_audit_that_named_no_residue_still_records_the_retirement(self):
        record = self.audited_record(destination=None)

        self.assertIsNone(record["destination"])


class CompleteWholeDocumentAuditRecordsApply(ApplierTestCase):
    """Complete RETIRE-DOC and MERGE-DOC records traverse every public gate.

    DISTILL's equivalent path is `DistillationLandsItsResidue` above. These
    records also come from the bloat audit boundary rather than test-authored
    findings, then pass human approval, plan validation, and application.
    """

    def setUp(self):
        super().setUp()
        self.lineage = self.lineage_for(
            self.repo, audit_mode="chunk",
            evidence_boundary=EvidenceBoundary(("docs/**",)),
        )

    def audited_record(self, entry):
        result = record_verdicts(
            build_context_index(self.repo), self.lineage, [entry]
        )
        self.assertNotIsInstance(result, Invalid, getattr(result, "problems", None))
        return result.records()[0]

    def test_complete_retire_doc_is_approved_and_applied(self):
        index = build_context_index(self.repo)
        record = self.audited_record({
            "id": "BLOAT-R1",
            "verdict": "RETIRE-DOC",
            "path": PLAN_DOC,
            "units": list(index.document(PLAN_DOC).units),
            "evidence": "The tiered-fee plan is superseded by docs/a.md.",
        })
        report, approval = self.approve([record])
        plan = self.plan(approval, [{
            "op": "retire-document",
            "record": record["digest"],
            "target_class": "documentation",
            "path": PLAN_DOC,
            "preimage": PLAN_DOC_TEXT,
        }], {PLAN_DOC: None})

        result = self.apply(plan, approval, report=report)

        self.assertEqual(result.status, STATE_CLEAN, result)
        self.assertFalse(os.path.exists(os.path.join(self.repo, PLAN_DOC)))

    def test_complete_merge_doc_is_approved_and_applied(self):
        source_text = "# Duplicate fees\n\n" + DOC_A_TEXT.split("\n", 2)[2]
        self.repo = self.git_repo(files={**FILES, PLAN_DOC: source_text})
        self.lineage = self.lineage_for(
            self.repo, audit_mode="chunk",
            evidence_boundary=EvidenceBoundary(("docs/**",)),
        )
        index = build_context_index(self.repo)
        record = self.audited_record({
            "id": "BLOAT-M1",
            "verdict": "MERGE-DOC",
            "path": PLAN_DOC,
            "units": list(index.document(PLAN_DOC).units),
            "evidence": "Every substantive unit already lives in docs/a.md.",
        })
        self.assertEqual(record["destination"]["path"], DOC_A)
        report, approval = self.approve([record])
        moved = source_text.rstrip("\n")
        post_destination = DOC_A_TEXT + moved + "\n"
        plan = self.plan(approval, [
            {
                "op": "move-with-provenance",
                "record": record["digest"],
                "target_class": "documentation",
                "path": PLAN_DOC,
                "destination": DOC_A,
                "start_line": 1,
                "end_line": 5,
                "preimage": moved,
            },
            {
                "op": "retire-document",
                "record": record["digest"],
                "target_class": "documentation",
                "path": PLAN_DOC,
                "preimage": source_text,
            },
        ], {PLAN_DOC: None, DOC_A: sha256_text(post_destination)})

        result = self.apply(plan, approval, report=report)

        self.assertEqual(result.status, STATE_CLEAN, result)
        self.assertFalse(os.path.exists(os.path.join(self.repo, PLAN_DOC)))
        self.assertEqual(self.read(self.repo, DOC_A), post_destination)


class LoadEditPlan(ApplierTestCase):
    """Reading the plan artifact off disk, strictly."""

    def test_reads_back_what_was_written(self):
        _, approval, plan, _ = self.replace_fixture()
        path = os.path.join(self.repo, "..", "plan.json")
        with open(path, "w", encoding="utf-8") as fh:
            json.dump(plan, fh)
        self.addCleanup(os.remove, path)
        self.assertEqual(load_edit_plan(path), plan)

    def test_unreadable_and_unparseable_are_typed(self):
        result = load_edit_plan(os.path.join(self.repo, "missing.json"))
        self.assertIsInstance(result, Invalid)
        self.assertEqual(codes(result), ["plan-unreadable"])
        path = os.path.join(self.repo, "..", "broken.json")
        with open(path, "w", encoding="utf-8") as fh:
            fh.write("{nope")
        self.addCleanup(os.remove, path)
        result = load_edit_plan(path)
        self.assertIsInstance(result, Invalid)
        self.assertEqual(codes(result), ["plan-unparseable"])

    def test_a_deeply_nested_plan_is_a_verdict_not_a_traceback(self):
        # A RecursionError is not a ValueError. On this interpreter, no
        # bomb text and no lowered recursion limit reliably makes the C
        # accelerated decoder raise one (report_test.py's equivalent
        # "decoder itself cannot survive" case only passes today via a
        # separate post-parse scan report.py has and this loader does not)
        # — so the exception is forced directly, the same way
        # `worktree_changes` is mocked elsewhere in this suite to reach an
        # otherwise-unreachable branch. Before this loader owned a
        # dedicated nesting code, a RecursionError here fell into the same
        # except tuple as a syntax error and came back mislabeled
        # `plan-unparseable`.
        from unittest import mock

        path = os.path.join(self.repo, "..", "plan.json")
        with open(path, "w", encoding="utf-8") as fh:
            fh.write("{}")
        self.addCleanup(os.remove, path)

        with mock.patch("doclifecycle.digest.json.loads",
                         side_effect=RecursionError):
            result = load_edit_plan(path)

        self.assertIsInstance(result, Invalid)
        self.assertEqual(codes(result), ["plan-nesting-too-deep"])


if __name__ == "__main__":
    unittest.main()
