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
from doclifecycle.approval import mint_approval_set
from doclifecycle.digest import sha256_canonical
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
        record = self.finding("BLOAT-001", "CUT", DOC_A, [units[1]])
        report, approval = self.approve([record])
        # Delete the refunds sentence (line 5) and insert a line after the
        # heading — two ops from one record, disjoint spans.
        post_lines = DOC_A_TEXT.split("\n")
        del post_lines[4]
        post_lines[1:1] = ["Fees are billed monthly."]
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
                "after_line": 1,
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
        units = self.units(self.repo, PLAN_DOC)
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
        plan = self.plan(approval, [op], {new_doc: sha256_text(content)})
        result = self.apply(plan, approval, report=report)
        self.assertEqual(result.status, STATE_CLEAN, result)
        self.assertEqual(self.read(self.repo, new_doc), content)
        self.assertEqual(self.status_paths(self.repo), [new_doc])

    def test_retire_document_lands(self):
        units = self.units(self.repo, PLAN_DOC)
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

    def test_applier_module_grants_no_shell_or_git_capability(self):
        """The applier itself runs no subprocess: its one git read goes
        through `repository.py`, and nothing upstream reaches a shell."""
        path = os.path.join(ENGINE, "doclifecycle", "applier.py")
        with open(path, encoding="utf-8") as fh:
            source = fh.read()
        self.assertNotIn("subprocess", source)
        self.assertNotIn("os.system", source)
        self.assertNotIn("eval(", source)
        self.assertNotIn("exec(", source)


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
        report, approval, plan, _ = self.replace_fixture()
        plan["operations"][0]["start_line"] = 40
        plan["operations"][0]["end_line"] = 40
        plan = self.plan(approval, plan["operations"], plan["postimages"])
        before = self.tree(self.repo)
        result = self.apply(plan, approval, report=report)
        self.assert_untouched(before, result, ["apply-preimage-mismatch"])

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

    def test_create_over_an_existing_document_is_refused(self):
        units = self.units(self.repo, PLAN_DOC)
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
        plan = self.plan(approval, [op], {DOC_B: sha256_text("clobbered\n")})
        before = self.tree(self.repo)
        result = self.apply(plan, approval, report=report)
        self.assert_untouched(before, result, ["apply-create-exists"])

    def test_create_with_empty_content_is_refused(self):
        new_doc = "docs/empty.md"
        units = self.units(self.repo, PLAN_DOC)
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


if __name__ == "__main__":
    unittest.main()
