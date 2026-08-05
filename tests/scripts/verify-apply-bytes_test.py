#!/usr/bin/env python3
"""Tests for scheduling-doc-sync's verify-apply-bytes.py (aj604/toolshed#191).

Executed as a subprocess against real git repositories in tempdirs, because
what this script asserts is a property of git's object store — an index entry,
a commit tree — and a mocked one would prove nothing about the boundary the
lane actually crosses. Each scenario builds a base commit, plays the apply out
on disk, hands the script the postimage manifest the applier would have
certified for it, and then does to the repository what an attacker, a filter,
or a hook would.

The scenarios come straight off the acceptance criteria: an approved path
mutated after the engine's apply but before staging; index normalization by an
ordinary `clean` filter; a hook rewriting and re-staging after the index was
verified; deletions checked as absence at both boundaries; and the pushed
commit being the tree that passed, which is why a refusal must leave `--out`
unwritten.

Run: python3 tests/scripts/verify-apply-bytes_test.py
"""

import hashlib
import json
import os
import pathlib
import shutil
import subprocess
import sys
import tempfile
import unittest

SCRIPT = str(
    pathlib.Path(__file__).resolve().parents[2]
    / "plugins" / "doc-lifecycle" / "skills" / "scheduling-doc-sync"
    / "scripts" / "verify-apply-bytes.py"
)

GIT_ENV = {
    "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@t",
    "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@t",
}

BASE = {
    "docs/kept.md": "kept\n",
    "docs/edited.md": "before\n",
    "docs/retired.md": "planning artifact\n",
}
AFTER = "after\n"


def sha256(text):
    return hashlib.sha256(text.encode()).hexdigest()


def run(*argv, summary=None):
    env = {**os.environ}
    if summary is not None:
        env["GITHUB_STEP_SUMMARY"] = summary
    else:
        env.pop("GITHUB_STEP_SUMMARY", None)
    return subprocess.run([sys.executable, SCRIPT, *argv],
                          capture_output=True, text=True, env=env)


class ApplyBoundaryTestCase(unittest.TestCase):
    """One repository, one apply, and whatever the scenario does to it."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        self.repo = os.path.join(self.tmp, "repo")
        self.out = os.path.join(self.tmp, "verified-commit.txt")
        self.summary = os.path.join(self.tmp, "summary.md")
        os.makedirs(self.repo)
        self.git("init", "-q", ".")
        for rel, text in BASE.items():
            self.write(rel, text)
        self.git("add", "-A")
        self.git("commit", "-qm", "base")

    # -- the repository ------------------------------------------------------

    def git(self, *args):
        return subprocess.run(
            ["git", "-C", self.repo, *args], capture_output=True, text=True,
            env={**os.environ, **GIT_ENV}, check=True).stdout

    def write(self, rel, text):
        path = os.path.join(self.repo, rel)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8", newline="") as fh:
            fh.write(text)

    def apply(self):
        """What the engine's applier would have left on disk, and certified."""
        self.write("docs/edited.md", AFTER)
        os.remove(os.path.join(self.repo, "docs/retired.md"))
        return {"docs/edited.md": sha256(AFTER), "docs/retired.md": None}

    def result(self, postimages, **overrides):
        payload = {
            "status": "clean",
            "schema_version": 1,
            "approval_digest": "a" * 64,
            "plan_digest": "b" * 64,
            "applied": [],
            "changed_paths": ["docs/edited.md", "docs/retired.md"],
            "already_applied": False,
            "postimages": postimages,
        }
        payload.update(overrides)
        path = os.path.join(self.tmp, "apply-result.json")
        with open(path, "w", encoding="utf-8") as fh:
            json.dump(payload, fh)
        return path

    def stage(self):
        """What the lane stages: exactly the apply result's own paths."""
        self.git("add", "docs/edited.md", "docs/retired.md")

    def commit(self):
        self.git("commit", "-qm", "docs: apply")

    # -- the script ----------------------------------------------------------

    def index(self, result):
        return run("index", "--result", result, "--repo", self.repo,
                   summary=self.summary)

    def verify_commit(self, result):
        return run("commit", "--result", result, "--repo", self.repo,
                   "--out", self.out, summary=self.summary)

    def surface(self):
        """What the run surface says — empty when a step wrote nothing to it."""
        if not os.path.exists(self.summary):
            return ""
        with open(self.summary, encoding="utf-8") as fh:
            return fh.read()

    def assert_refused(self, completed, code):
        self.assertEqual(completed.returncode, 1,
                         completed.stdout + completed.stderr)
        self.assertIn(f"`{code}`", self.surface())
        self.assertIn("Nothing was pushed and no pull request was created",
                      self.surface())
        self.assertIn("could not certify", self.surface())
        self.assertFalse(
            os.path.exists(self.out),
            "a refused run left a commit id behind for the push to name")


class TheHonestPath(ApplyBoundaryTestCase):
    def test_a_faithful_index_and_commit_tree_pass_and_name_the_commit(self):
        result = self.result(self.apply())
        self.stage()
        self.assertEqual(self.index(result).returncode, 0, self.surface())
        self.commit()
        self.assertEqual(self.verify_commit(result).returncode, 0,
                         self.surface())
        with open(self.out, encoding="utf-8") as fh:
            verified = fh.read().strip()
        self.assertEqual(verified, self.git("rev-parse", "HEAD").strip(),
                         "the commit named for the push is not the one verified")
        self.assertIn("Commit tree verified", self.surface())

    def test_a_written_path_whose_bytes_did_not_change_is_still_verified(self):
        # The plan wrote `docs/kept.md` back exactly as it was, so nothing is
        # staged for it and no confinement check ever names it — but the index
        # must still hold the certified bytes for the commit to be the approved
        # change, so the manifest entry is checked all the same.
        postimages = self.apply()
        postimages["docs/kept.md"] = sha256(BASE["docs/kept.md"])
        result = self.result(postimages)
        self.stage()
        self.assertEqual(self.index(result).returncode, 0, self.surface())

    def test_a_manifest_entry_git_does_not_hold_is_refused(self):
        postimages = self.apply()
        postimages["docs/never-written.md"] = sha256("nothing\n")
        result = self.result(postimages)
        self.stage()
        self.assert_refused(self.index(result), "apply-bytes-not-certified")
        self.assertIn("the index does not carry it", self.surface())


class MutationBetweenTheApplyAndTheStaging(ApplyBoundaryTestCase):
    def test_an_approved_path_rewritten_before_staging_is_refused(self):
        result = self.result(self.apply())
        # Same path, so every path set the lane checks still names it: only
        # the bytes betray it.
        self.write("docs/edited.md", "not what was approved\n")
        self.stage()
        self.assert_refused(self.index(result), "apply-bytes-not-certified")
        self.assertIn(sha256(AFTER), self.surface())

    def test_index_normalization_by_a_clean_filter_is_refused(self):
        result = self.result(self.apply())
        self.write(".gitattributes", "docs/edited.md filter=shout\n")
        self.git("config", "filter.shout.clean", "tr a-z A-Z")
        self.stage()
        # git stored something other than the bytes the applier read back, so
        # the committed tree would not be the postimage — refused rather than
        # laundered as the approved content.
        self.assert_refused(self.index(result), "apply-bytes-not-certified")
        # And what it stored is nameable: the filter's normalization, not the
        # approved document. Asserting only the code would pass just as well
        # against a check that failed for some unrelated reason.
        self.assertEqual(self.git("show", ":docs/edited.md"), AFTER.upper())
        self.assertNotEqual(self.git("show", ":docs/edited.md"), AFTER)
        self.assertIn(sha256(AFTER), self.surface())

    def test_a_symlink_where_a_document_belongs_is_refused(self):
        result = self.result(self.apply())
        os.remove(os.path.join(self.repo, "docs/edited.md"))
        os.symlink("kept.md", os.path.join(self.repo, "docs/edited.md"))
        self.stage()
        self.assert_refused(self.index(result), "apply-bytes-not-certified")
        self.assertIn("120000", self.surface())


class DeletionsAreAbsence(ApplyBoundaryTestCase):
    def test_a_retired_document_still_in_the_index_is_refused(self):
        result = self.result(self.apply())
        self.write("docs/retired.md", "put back\n")
        self.stage()
        self.assert_refused(self.index(result), "apply-bytes-not-certified")
        self.assertIn("the index still carries it", self.surface())

    def test_a_retired_document_written_back_before_the_commit_is_refused(self):
        result = self.result(self.apply())
        self.stage()
        self.assertEqual(self.index(result).returncode, 0, self.surface())
        self.commit()
        self.write("docs/retired.md", "put back\n")
        self.git("add", "docs/retired.md")
        self.git("commit", "--amend", "-qm", "docs: apply")
        self.assert_refused(self.verify_commit(result),
                            "apply-bytes-not-certified")
        self.assertIn("the commit tree still carries it", self.surface())

    def test_a_deletion_absent_from_both_boundaries_passes(self):
        result = self.result(self.apply())
        self.stage()
        self.assertEqual(self.index(result).returncode, 0, self.surface())
        self.commit()
        self.assertEqual(self.verify_commit(result).returncode, 0,
                         self.surface())
        self.assertNotIn("docs/retired.md", self.git("ls-files"))
        self.assertNotIn("docs/retired.md",
                         self.git("ls-tree", "-r", "--name-only", "HEAD"))


class MutationAfterTheIndexWasVerified(ApplyBoundaryTestCase):
    def test_a_hook_that_rewrote_and_restaged_a_target_is_refused(self):
        result = self.result(self.apply())
        self.stage()
        self.assertEqual(self.index(result).returncode, 0, self.surface())
        self.commit()
        # What a `pre-commit` hook leaves behind: the target rewritten and
        # re-staged, so the tree that would be pushed is not the index anybody
        # checked.
        self.write("docs/edited.md", "hooked\n")
        self.git("add", "docs/edited.md")
        self.git("commit", "--amend", "-qm", "docs: apply")
        self.assert_refused(self.verify_commit(result),
                            "apply-bytes-not-certified")
        # The commit that would have been pushed carries the hook's text, and
        # the refusal names the digest the applier certified instead — the two
        # halves of "these bytes are not the approved ones".
        self.assertEqual(self.git("show", "HEAD:docs/edited.md"), "hooked\n")
        self.assertIn(sha256(AFTER), self.surface())

    def test_a_commit_carrying_an_uncertified_path_is_refused(self):
        result = self.result(self.apply())
        self.stage()
        self.assertEqual(self.index(result).returncode, 0, self.surface())
        self.commit()
        self.write("docs/smuggled.md", "rider\n")
        self.git("add", "docs/smuggled.md")
        self.git("commit", "--amend", "-qm", "docs: apply")
        self.assert_refused(self.verify_commit(result),
                            "apply-commit-not-confined")
        self.assertIn("docs/smuggled.md", self.surface())

    def test_a_merge_commit_is_refused(self):
        result = self.result(self.apply())
        self.stage()
        self.commit()
        base = self.git("rev-parse", "HEAD~1").strip()
        self.git("checkout", "-q", "-b", "side", base)
        self.write("docs/side.md", "side\n")
        self.git("add", "docs/side.md")
        self.git("commit", "-qm", "side")
        side = self.git("rev-parse", "HEAD").strip()
        self.git("checkout", "-q", "-")
        self.git("merge", "-q", "--no-ff", "-m", "merge", side)
        self.assert_refused(self.verify_commit(result),
                            "apply-commit-not-linear")


class TheManifestIsTheOnlyAuthority(ApplyBoundaryTestCase):
    def test_a_result_carrying_no_manifest_is_refused(self):
        payload = self.apply()
        result = self.result(payload)
        with open(result, encoding="utf-8") as fh:
            without = json.load(fh)
        without.pop("postimages")
        with open(result, "w", encoding="utf-8") as fh:
            json.dump(without, fh)
        self.stage()
        self.assert_refused(self.index(result), "apply-postimages-absent")

    def test_a_result_that_is_not_clean_is_refused(self):
        result = self.result(self.apply(), status="stale")
        self.stage()
        self.assert_refused(self.index(result), "apply-result-not-clean")

    def test_a_manifest_naming_an_uncanonical_path_is_refused(self):
        postimages = self.apply()
        postimages["../outside.md"] = sha256("x\n")
        result = self.result(postimages)
        self.stage()
        self.assert_refused(self.index(result), "apply-postimages-malformed")

    def test_a_manifest_entry_that_is_not_a_digest_is_refused(self):
        postimages = self.apply()
        postimages["docs/edited.md"] = "not-a-digest"
        result = self.result(postimages)
        self.stage()
        self.assert_refused(self.index(result), "apply-postimages-malformed")

    def test_a_changed_path_the_manifest_does_not_certify_is_refused(self):
        postimages = self.apply()
        result = self.result(
            postimages,
            changed_paths=["docs/edited.md", "docs/retired.md", "docs/kept.md"])
        self.stage()
        self.assert_refused(self.index(result),
                            "apply-changed-path-uncertified")

    def test_an_unreadable_result_is_refused(self):
        self.apply()
        self.stage()
        completed = self.index(os.path.join(self.tmp, "absent.json"))
        self.assert_refused(completed, "apply-result-unreadable")


class ReusingAnExistingBranch(ApplyBoundaryTestCase):
    """The recovery boundary (aj604/toolshed#198).

    A commit an earlier attempt pushed is reusable only if it is this run's own
    result: this approval's trailer, and a tree the same certification passes.
    `apply-recovery_test.py` drives this through the whole lane against a real
    remote; here it is the script's own seam, including the refusals a lane run
    cannot easily reach.
    """

    APPROVAL = "a" * 64

    def setUp(self):
        super().setUp()
        self.approval = os.path.join(self.tmp, "approval.json")
        with open(self.approval, "w", encoding="utf-8") as fh:
            json.dump({"digest": self.APPROVAL}, fh)
        self.verified_file = os.path.join(self.tmp, "verified-commit.txt")

    def message(self, digest=None):
        if digest is None:
            return "docs: apply\n\nsomebody else's work\n"
        return f"docs: apply\n\nDoc-Lifecycle-Approval: {digest}\n"

    def two_attempts(self, message, tree=None, base=None):
        """(the existing commit, the commit this run verified).

        Two applies of one approval: the same postimages, committed twice, as
        two runs seconds apart would produce.
        """
        result = self.result(self.apply())
        self.stage()
        self.commit()
        verified = self.git("rev-parse", "HEAD").strip()
        with open(self.verified_file, "w", encoding="utf-8") as fh:
            fh.write(f"{verified}\n")
        self.git("checkout", "-q", "-b", "earlier", base or "HEAD~1")
        for rel, text in (tree or {"docs/edited.md": AFTER}).items():
            self.write(rel, text)
        if os.path.exists(os.path.join(self.repo, "docs/retired.md")):
            os.remove(os.path.join(self.repo, "docs/retired.md"))
        self.git("add", "-A")
        self.git("commit", "-qm", message)
        return self.git("rev-parse", "HEAD").strip(), result

    def reuse(self, commit, result, verified=None, ref="refs/heads/earlier"):
        # `--ref` is what the lane fetched the branch into; `two_attempts`
        # builds the earlier attempt on a local branch of that name, so this is
        # the same binding the lane makes.
        return run("reuse", "--result", result, "--repo", self.repo,
                   "--commit", commit, "--ref", ref,
                   "--approval", self.approval,
                   "--verified", verified or self.verified_file,
                   summary=self.summary)

    def assert_reuse_refused(self, completed, code):
        self.assertEqual(completed.returncode, 1,
                         completed.stdout + completed.stderr)
        self.assertIn(f"`{code}`", self.surface())
        self.assertIn("REFUSED at branch reuse", self.surface())

    def test_this_runs_own_earlier_result_is_reusable(self):
        existing, result = self.two_attempts(self.message(self.APPROVAL))
        self.assertEqual(self.reuse(existing, result).returncode, 0,
                         self.surface())
        self.assertIn("Existing branch verified", self.surface())

    def test_a_commit_carrying_no_approval_trailer_is_refused(self):
        existing, result = self.two_attempts(self.message())
        self.assert_reuse_refused(self.reuse(existing, result),
                                  "apply-branch-approval-conflict")

    def test_a_commit_carrying_another_approvals_trailer_is_refused(self):
        existing, result = self.two_attempts(self.message("b" * 64))
        self.assert_reuse_refused(self.reuse(existing, result),
                                  "apply-branch-approval-conflict")

    def test_a_matching_trailer_over_different_bytes_is_refused(self):
        existing, result = self.two_attempts(
            self.message(self.APPROVAL),
            tree={"docs/edited.md": "not what was approved\n"})
        self.assert_reuse_refused(self.reuse(existing, result),
                                  "apply-bytes-not-certified")
        # The different bytes are the scenario, so they are asserted: the
        # branch a re-run would have adopted still holds content this approval
        # never authorized, and the refusal names the digest that was approved.
        self.assertEqual(self.git("show", f"{existing}:docs/edited.md"),
                         "not what was approved\n")
        self.assertIn(sha256(AFTER), self.surface())

    def test_an_id_that_is_not_a_commit_is_refused(self):
        _, result = self.two_attempts(self.message(self.APPROVAL))
        self.assert_reuse_refused(self.reuse("refs/heads/earlier", result),
                                  "apply-commit-unreadable")

    def test_an_absent_verified_commit_file_is_refused(self):
        existing, result = self.two_attempts(self.message(self.APPROVAL))
        self.assert_reuse_refused(
            self.reuse(existing, result,
                       verified=os.path.join(self.tmp, "absent.txt")),
            "apply-commit-unreadable")

    def test_a_ref_that_holds_a_descendant_of_the_read_commit_is_refused(self):
        # The fail-open shape: the branch advanced between the lane's
        # `ls-remote` and its fetch, so the id it read is still readable — as
        # an ancestor — and every other check would pass on a commit the branch
        # no longer holds.
        existing, result = self.two_attempts(self.message(self.APPROVAL))
        self.write("docs/injected.md", "smuggled\n")
        self.git("add", "-A")
        self.git("commit", "-qm", "a concurrent writer")
        advanced = self.git("rev-parse", "HEAD").strip()
        self.assertNotEqual(advanced, existing)
        self.assert_reuse_refused(self.reuse(existing, result),
                                  "apply-branch-moved")
        self.assertIn(advanced, self.surface())

    def test_a_ref_that_does_not_resolve_is_refused(self):
        existing, result = self.two_attempts(self.message(self.APPROVAL))
        self.assert_reuse_refused(
            self.reuse(existing, result, ref="refs/heads/never-fetched"),
            "apply-branch-unreadable")

    def test_a_ref_that_is_not_fully_qualified_is_refused(self):
        # `earlier` is a branch git would happily resolve; this script resolves
        # only the fully qualified ref the lane fetched into, so a shorthand —
        # or anything else that would be parsed as a revision expression — is
        # refused rather than looked up.
        existing, result = self.two_attempts(self.message(self.APPROVAL))
        self.assert_reuse_refused(self.reuse(existing, result, ref="earlier"),
                                  "apply-branch-unreadable")

    def test_a_ref_shaped_like_an_option_is_refused(self):
        existing, result = self.two_attempts(self.message(self.APPROVAL))
        completed = run("reuse", "--result", result, "--repo", self.repo,
                        "--commit", existing, "--ref=--all",
                        "--approval", self.approval,
                        "--verified", self.verified_file, summary=self.summary)
        self.assert_reuse_refused(completed, "apply-branch-unreadable")

    def test_a_result_that_is_not_clean_certifies_no_reuse(self):
        existing, _ = self.two_attempts(self.message(self.APPROVAL))
        stale = self.result(
            {"docs/edited.md": sha256(AFTER), "docs/retired.md": None},
            status="stale")
        self.assert_reuse_refused(self.reuse(existing, stale),
                                  "apply-result-not-clean")


class TheRunSurface(ApplyBoundaryTestCase):
    def test_a_refusal_falls_back_to_stdout_when_no_summary_is_set(self):
        result = self.result(self.apply())
        self.write("docs/edited.md", "moved\n")
        self.stage()
        completed = run("index", "--result", result, "--repo", self.repo)
        self.assertEqual(completed.returncode, 1)
        self.assertIn("apply-bytes-not-certified", completed.stdout)

    def test_a_usage_error_is_caught_before_any_subcommand_runs(self):
        completed = run("index")
        self.assertEqual(completed.returncode, 2)


if __name__ == "__main__":
    unittest.main()
