#!/usr/bin/env python3
"""The two apply lanes verify identically (aj604/toolshed#191).

There are two doors onto the same write: `doc-apply.yml`, where a human
dispatches a named record subset, and `doc-policy-apply.yml`, where a standing
policy selects one off a successful scheduled audit. **Selection and trigger
are the only intended differences between them.** Everything after the approval
set exists — applying the plan, deriving the staged path list, staging it,
re-checking what git staged, verifying the staged bytes and then the commit tree
against the applier's certified postimage manifest, committing, pushing the
verified commit, and opening a real pull request — is one implementation, and a
lane that quietly drifted from the other would be a second, weaker write path
that nobody reviews as one.

So this suite compares the two `apply` jobs where it counts: the *commands*
they run. Every `run:` block in the credentialed job, in order, must be byte
identical across the lanes. Step names, the checkout ref, the `if:` guards, the
bundle artifact names, and the `BASE` the pull request opens against are where
selection and trigger legitimately live — none of them is a command — and the
suite pins that reading by checking that the differing surface is confined to
them.

`workflow-permissions_test.py` already proves each lane's write job is
model-free, token-shaped correctly, and never `git add -A`;
`apply-workflow_test.py` and `policy-workflow_test.py` prove each lane's own
shape. This is the one that proves they are the *same* lane.

Run: python3 tests/scripts/apply-lane-parity_test.py
"""

import importlib.util
import os
import re
import sys
import unittest

ROOT = os.path.join(os.path.dirname(__file__), "..", "..")
TEMPLATES = os.path.join(
    ROOT, "plugins", "doc-lifecycle", "skills", "scheduling-doc-sync")
MANUAL = os.path.join(TEMPLATES, "doc-apply.yml")
POLICY = os.path.join(TEMPLATES, "doc-policy-apply.yml")

RUN_BLOCK = re.compile(r"^(\s*)run:\s*\|")
STEP = re.compile(r"^\s{6}- name:\s*(.+?)\s*$")

# The byte verification this suite exists for: both boundaries, in both lanes,
# through the one script.
VERIFICATION_SEAMS = (
    "verify-apply-bytes.py index",
    "verify-apply-bytes.py commit",
    "--out \"${RUNNER_TEMP}/verified-commit.txt\"",
    "commit=$(cat \"${RUNNER_TEMP}/verified-commit.txt\")",
    "git push origin \"${commit}:refs/heads/${branch}\"",
)

# Recovery is one implementation too (aj604/toolshed#198): reading the remote
# before pushing, certifying an existing derived branch against this run's own
# result, and the typed terminal states. A lane that recovered on its own terms
# would be the second write path this suite exists to prevent.
RECOVERY_SEAMS = (
    "render-apply-summary.py remote-branch",
    "verify-apply-bytes.py reuse",
    # The fetched ref, bound to the id the previous step read: without it the
    # reuse checks answer about a commit rather than about the branch.
    "--ref refs/doc-lifecycle/existing",
    "render-apply-summary.py existing-pull-request",
    "--state branch-created",
    "--state branch-reused",
    "--state pull-request-already-open",
)


def load_permissions_test():
    path = os.path.join(os.path.dirname(__file__), "workflow-permissions_test.py")
    spec = importlib.util.spec_from_file_location("workflow_permissions_test", path)
    mod = importlib.util.module_from_spec(spec)
    sys.dont_write_bytecode = True
    spec.loader.exec_module(mod)
    return mod


WPT = load_permissions_test()


def apply_body(path):
    return WPT.jobs_of(path)["apply"]


def run_blocks(body):
    """Every `run: |` block in a job body, dedented, in order."""
    blocks, current, indent = [], None, None
    for line in body:
        match = RUN_BLOCK.match(line)
        if match:
            current, indent = [], len(match.group(1)) + 2
            blocks.append(current)
            continue
        if current is None:
            continue
        if line.strip() and WPT.indent_of(line) < indent:
            current, indent = None, None
            continue
        current.append(line[indent:] if line.strip() else "")
    return ["\n".join(block).rstrip() for block in blocks]


def step_names(body):
    return [match.group(1) for match in
            (STEP.match(line) for line in body) if match]


class TheTwoApplyLanesRunTheSameCommands(unittest.TestCase):
    def setUp(self):
        self.manual = apply_body(MANUAL)
        self.policy = apply_body(POLICY)

    def test_the_apply_jobs_exist_and_carry_commands(self):
        # Guard against a parser that silently found nothing and then "passed".
        self.assertTrue(run_blocks(self.manual))
        self.assertEqual(len(run_blocks(self.manual)),
                         len(run_blocks(self.policy)),
                         "the two apply lanes run a different number of steps")

    def test_every_run_block_is_identical_across_the_two_lanes(self):
        for index, (manual, policy) in enumerate(
                zip(run_blocks(self.manual), run_blocks(self.policy))):
            self.assertEqual(
                manual, policy,
                f"apply step {index} differs between the manual and policy "
                f"lanes — after the approval set exists, the two lanes are one "
                f"write path, and a difference here is a second one")

    def test_both_lanes_verify_the_bytes_at_both_git_boundaries(self):
        for name, body in (("doc-apply.yml", self.manual),
                           ("doc-policy-apply.yml", self.policy)):
            text = "\n".join(body)
            for seam in VERIFICATION_SEAMS:
                self.assertIn(seam, text,
                              f"{name}'s apply job is missing {seam!r}")

    def test_the_verification_runs_between_the_staging_and_the_push(self):
        for name, body in (("doc-apply.yml", self.manual),
                           ("doc-policy-apply.yml", self.policy)):
            def first(needle):
                return next(i for i, line in enumerate(body) if needle in line)

            staged = first("verify-staged")
            index = first("verify-apply-bytes.py index")
            committed = first("git commit -F")
            tree = first("verify-apply-bytes.py commit")
            pushed = first("git push origin")
            self.assertLess(staged, index, f"{name}: staged bytes unchecked")
            self.assertLess(index, committed,
                            f"{name}: the index is checked after the commit")
            self.assertLess(committed, tree,
                            f"{name}: the tree is checked before it exists")
            self.assertLess(tree, pushed,
                            f"{name}: the push precedes the tree verification")

    def test_the_push_names_the_verified_commit_and_never_head(self):
        # `HEAD` is whatever the last thing to run left behind; the commit id
        # the tree verification wrote is the tree that passed. Since #198 it
        # reaches the push through a variable, so the refspec and the binding
        # are asserted together — a refspec naming a variable nothing bound to
        # the verification's own file is no better than one naming `HEAD`.
        for name, body in (("doc-apply.yml", self.manual),
                           ("doc-policy-apply.yml", self.policy)):
            push = next(line for line in body if "git push origin" in line)
            self.assertIn('"${commit}:refs/heads/${branch}"', push,
                          f"{name}: {push}")
            self.assertNotIn("HEAD:refs/heads/", push, f"{name}: {push}")
            self.assertIn('commit=$(cat "${RUNNER_TEMP}/verified-commit.txt")',
                          "\n".join(body), name)

    def test_both_lanes_recover_through_the_same_seams(self):
        for name, body in (("doc-apply.yml", self.manual),
                           ("doc-policy-apply.yml", self.policy)):
            text = "\n".join(body)
            for seam in RECOVERY_SEAMS:
                self.assertIn(seam, text,
                              f"{name}'s apply job is missing {seam!r}")

    def test_the_remote_is_read_before_anything_is_pushed(self):
        # The whole point of the recovery order: a run that pushed first and
        # asked afterwards would already have overwritten what it was checking.
        for name, body in (("doc-apply.yml", self.manual),
                           ("doc-policy-apply.yml", self.policy)):
            def first(needle):
                return next(i for i, line in enumerate(body) if needle in line)

            self.assertLess(first("render-apply-summary.py remote-branch"),
                            first("verify-apply-bytes.py reuse"),
                            f"{name}: an existing branch is certified before "
                            f"the remote is read")
            self.assertLess(first("verify-apply-bytes.py reuse"),
                            first("git push origin"),
                            f"{name}: the push precedes the reuse check")


class SelectionAndTriggerAreTheOnlyDifferences(unittest.TestCase):
    """What legitimately differs, and the proof nothing else does.

    The `run:` comparison above is the load-bearing one; this pins the reading
    of it — that the surface which *does* differ is the selection (which
    approval bundle, which plan artifact) and the trigger (which ref the lane
    checks out, which base the pull request opens against, and whether the job
    runs at all).
    """

    def setUp(self):
        self.manual = apply_body(MANUAL)
        self.policy = apply_body(POLICY)

    def test_both_apply_jobs_have_the_same_number_of_steps(self):
        self.assertEqual(len(step_names(self.manual)),
                         len(step_names(self.policy)))

    def test_only_selection_and_trigger_lines_differ_outside_run_blocks(self):
        # Everything that is not a command: `uses:`, `with:`, `env:`, `if:`,
        # and the step names. A difference is allowed only where one of the
        # markers below explains it.
        allowed = (
            "- name:",            # prose, not behaviour
            "#",                  # comments
            "ref:",               # trigger: which commit the lane applies onto
            "if:",                # trigger: whether the policy lane runs at all
            "needs.revalidate",   # trigger: the policy lane's own gates
            "BASE:",              # trigger: what the pull request opens against
            "name: apply-",       # selection: the manual lane's bundles
            "name: policy-apply-",  # selection: the policy lane's bundles
        )
        manual = [l for l in self.manual if l.strip()
                  and not RUN_BLOCK.match(l)]
        policy = [l for l in self.policy if l.strip()
                  and not RUN_BLOCK.match(l)]
        for line in set(manual) ^ set(policy):
            self.assertTrue(
                any(marker in line for marker in allowed),
                f"the two apply lanes differ at a line that is neither "
                f"selection nor trigger: {line!r}")

    def test_the_two_lanes_read_their_own_bundles(self):
        self.assertIn("name: apply-approval", "\n".join(self.manual))
        self.assertIn("name: policy-apply-approval", "\n".join(self.policy))


if __name__ == "__main__":
    unittest.main()
