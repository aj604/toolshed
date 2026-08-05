#!/usr/bin/env python3
"""The apply lane recovers from a half-finished attempt (aj604/toolshed#198).

A push that lands while `gh pr create` fails strands the approval: the branch
is on the remote, nothing reviews it, and the approval set is an untracked
artifact that expires. Re-running the dispatch has to pick that up rather than
either failing on the ref that is already there or overwriting it — the branch
name is derived from the approval digest, so a re-run aims at exactly the same
ref, and a deterministic name is not authority to overwrite a commit this run
did not make.

So this suite runs the lane, not a model of it. Every step of `doc-apply.yml`'s
credentialed job from the staged path list onward is lifted out of the workflow
and executed under `bash -e` against real git repositories — a bare `origin`
and a checkout cloned from it — with a `gh` stub standing in for the forge.
What the steps run is the lane's own text: a step edited in the YAML is a step
this suite executes differently. Only `apply-plan` is left out, because it needs
the engine and a model-authored plan; its `ApplyResult` is synthesized exactly
as `verify-apply-bytes_test.py` synthesizes one, and everything downstream of it
is the lane.

The six scenarios are the acceptance criteria of #198:

1. a first run: no branch on the remote, so one is created and the pull request
   opened;
2. a push that lands while the pull request creation fails — the branch stands
   and nothing reviews it;
3. a re-run against that: the branch matches, no pull request is open, so the
   branch is reused untouched and the pull request opened;
4. a re-run against a matching open pull request: idempotent success, and
   nothing is created twice;
5. an existing branch whose tree conflicts: a typed refusal, and nothing is
   pushed or opened;
6. an existing pull request bound to another approval: a typed refusal, and no
   second pull request is opened beside it.

One lane is executed rather than both: `apply-lane-parity_test.py` holds every
`run:` block of the two credentialed jobs byte identical, so a recovery path
proven here is the policy lane's too, and a lane that drifted fails there.

Run: python3 tests/scripts/apply-recovery_test.py
"""

import hashlib
import importlib.util
import json
import os
import pathlib
import re
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[2]
SCRIPTS = ROOT / "plugins" / "doc-lifecycle" / "skills" / "scheduling-doc-sync"
WORKFLOW = SCRIPTS / "doc-apply.yml"

RUN_BLOCK = re.compile(r"^(\s*)run:\s*\|")
STEP = re.compile(r"^\s{6}- name:\s*(.+?)\s*$")

# The apply result this run certifies, and the approval that authorized it.
APPROVAL_DIGEST = "1a" * 32
OTHER_APPROVAL_DIGEST = "2b" * 32
REPORT_DIGEST = "3c" * 32
PLAN_DIGEST = "4d" * 32
BRANCH = f"doc-lifecycle/apply-{APPROVAL_DIGEST[:12]}"

BASE_TREE = {
    "docs/kept.md": "kept\n",
    "docs/edited.md": "before\n",
    "docs/retired.md": "planning artifact\n",
}
AFTER = "after\n"
CHANGED = ["docs/edited.md", "docs/retired.md"]

# What the forge stub answers `gh pr list` with when nothing is open.
NO_PULL_REQUESTS = []

GH_STUB = """#!/usr/bin/env bash
set -u
echo "$*" >> "$GH_CALLS"
if [ "${1:-}" = "pr" ] && [ "${2:-}" = "list" ]; then
  cat "$GH_PR_LIST"
  exit 0
fi
if [ "${1:-}" = "pr" ] && [ "${2:-}" = "create" ]; then
  if [ -n "${GH_PR_CREATE_FAILS:-}" ]; then
    echo "gh: pull request creation failed" >&2
    exit 1
  fi
  echo "https://github.com/owner/repo/pull/41"
  exit 0
fi
echo "gh: unexpected invocation: $*" >&2
exit 1
"""


def load_permissions_test():
    path = os.path.join(os.path.dirname(__file__), "workflow-permissions_test.py")
    spec = importlib.util.spec_from_file_location("workflow_permissions_test", path)
    mod = importlib.util.module_from_spec(spec)
    sys.dont_write_bytecode = True
    spec.loader.exec_module(mod)
    return mod


WPT = load_permissions_test()


def apply_steps():
    """The apply job's `(step name, script)` pairs, in order.

    Dedented as the runner hands a `run:` block to bash, so what this suite
    executes is the lane's own text and nothing rewritten for testing.
    """
    body = WPT.jobs_of(str(WORKFLOW))["apply"]
    steps, name, current, indent = [], None, None, None
    for line in body:
        named = STEP.match(line)
        if named:
            name = named.group(1)
        opened = RUN_BLOCK.match(line)
        if opened:
            current, indent = [], len(opened.group(1)) + 2
            steps.append((name, current))
            continue
        if current is None:
            continue
        if line.strip() and WPT.indent_of(line) < indent:
            current, indent = None, None
            continue
        current.append(line[indent:] if line.strip() else "")
    return [(n, "\n".join(b).rstrip() + "\n") for n, b in steps]


STEPS = apply_steps()
# Everything from the staged path list onward: the applier's own step is the
# one seam this suite stands in for.
FIRST = next(i for i, (_, script) in enumerate(STEPS)
             if "staged-paths" in script)


def sha256(text):
    return hashlib.sha256(text.encode()).hexdigest()


class ApplyRun:
    """One run of the lane: a checkout, a runner temp, and a forge stub."""

    def __init__(self, case, label, pull_requests, pr_create_fails):
        self.case = case
        # A re-run happens later, and this run's commit must differ from the
        # one already on the remote for "reuse" to mean anything. Git dates
        # are second-resolution, and two runs of this suite are milliseconds
        # apart, so the clock is stated rather than raced.
        self.stamp = case.next_stamp()
        self.repo = os.path.join(case.tmp, label)
        self.temp = os.path.join(case.tmp, f"{label}-temp")
        self.summary = os.path.join(self.temp, "summary.md")
        self.calls = os.path.join(self.temp, "gh-calls.txt")
        self.pr_list = os.path.join(self.temp, "gh-pr-list.json")
        self.pr_create_fails = pr_create_fails
        self.results = []

        subprocess.run(["git", "clone", "-q", case.origin, self.repo],
                       check=True, capture_output=True, env=case.git_env())
        os.makedirs(os.path.join(self.temp, "apply"))
        with open(self.pr_list, "w", encoding="utf-8") as fh:
            json.dump(pull_requests, fh)
        open(self.calls, "w", encoding="utf-8").close()
        self._write_bundle()
        self._apply_on_disk()

    # -- the artifacts the revalidate job would have uploaded -----------------

    def _bundle(self, name, text):
        with open(os.path.join(self.temp, "apply", name), "w",
                  encoding="utf-8") as fh:
            fh.write(text)

    def _write_bundle(self):
        approval = {
            "artifact": "approval-set",
            "digest": APPROVAL_DIGEST,
            "report_digest": REPORT_DIGEST,
            "status": "clean",
            "minter": {"kind": "human", "id": "reviewer", "policy_digest": None},
            "records": [{"id": "DRIFT-1", "code": "STALE-PASSAGE",
                         "path": "docs/edited.md", "digest": "5e" * 32}],
            "skipped": [],
            "scope": {"roots": ["docs"], "paths": CHANGED},
            "lineage": {"repository": "owner/repo", "base_commit": "0" * 40,
                        "audit_mode": "full", "registry_digest": "6f" * 32,
                        "inventory_digest": "70" * 32,
                        "audit_config_digest": "81" * 32,
                        "ruleset_version": "1", "plugin_version": "0.46.8"},
        }
        report = {"artifact": "drift-report", "digest": REPORT_DIGEST,
                  "status": "findings", "lineage": approval["lineage"],
                  "incomplete": []}
        self._bundle("approval.json", json.dumps(approval))
        self._bundle("drift-report.json", json.dumps(report))
        self._bundle("approval-summary.md", "## Approval\n\nOne record.\n")
        self._bundle("config-digest.txt", "81" * 32)
        self._bundle("branch.txt", f"{BRANCH}\n")
        self._bundle(
            "trailers.txt",
            f"Doc-Lifecycle-Approval: {APPROVAL_DIGEST}\n"
            f"Doc-Lifecycle-Report: {REPORT_DIGEST}\n"
            f"Doc-Lifecycle-Approval-State: clean\n"
            f"Doc-Lifecycle-Records: 1 approved, 0 skipped\n")

    def _apply_on_disk(self):
        """What the engine's applier would have left on disk, and certified."""
        self.case.write(self.repo, "docs/edited.md", AFTER)
        os.remove(os.path.join(self.repo, "docs/retired.md"))
        result = {
            "status": "clean", "schema_version": 1,
            "approval_digest": APPROVAL_DIGEST, "plan_digest": PLAN_DIGEST,
            "applied": [], "changed_paths": CHANGED, "already_applied": False,
            "postimages": {"docs/edited.md": sha256(AFTER),
                           "docs/retired.md": None},
        }
        with open(os.path.join(self.temp, "apply-result.json"), "w",
                  encoding="utf-8") as fh:
            json.dump(result, fh)

    # -- running the lane ----------------------------------------------------

    def env(self):
        env = self.case.git_env(self.stamp)
        env.update({
            "PATH": f"{self.case.stub_dir}{os.pathsep}{os.environ['PATH']}",
            "RUNNER_TEMP": self.temp,
            "GITHUB_STEP_SUMMARY": self.summary,
            "GH_TOKEN": "stub-token",
            "GH_CALLS": self.calls,
            "GH_PR_LIST": self.pr_list,
            "BASE": "main",
        })
        if self.pr_create_fails:
            env["GH_PR_CREATE_FAILS"] = "1"
        return env

    def execute(self):
        """Every step from the staged path list on, stopping at the first
        failure — which is what the runner does, and what leaves the world in
        the state the next scenario starts from."""
        for name, script in STEPS[FIRST:]:
            path = os.path.join(self.temp, "step.sh")
            with open(path, "w", encoding="utf-8") as fh:
                fh.write(script)
            completed = subprocess.run(
                ["bash", "-e", path], cwd=self.repo, env=self.env(),
                capture_output=True, text=True)
            self.results.append((name, completed))
            if completed.returncode != 0:
                break
        return self

    # -- what happened -------------------------------------------------------

    def surface(self):
        if not os.path.exists(self.summary):
            return ""
        with open(self.summary, encoding="utf-8") as fh:
            return fh.read()

    def gh_calls(self):
        with open(self.calls, encoding="utf-8") as fh:
            return [line.strip() for line in fh if line.strip()]

    def failure(self):
        """The (name, completed) of the step that failed, or None."""
        for name, completed in self.results:
            if completed.returncode != 0:
                return name, completed
        return None

    def transcript(self):
        return "\n".join(
            f"--- {name} (exit {c.returncode})\n{c.stdout}{c.stderr}"
            for name, c in self.results) + "\n\nSURFACE:\n" + self.surface()


class ApplyRecoveryTestCase(unittest.TestCase):
    """A bare `origin`, a base commit, and whatever the scenario does to it."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.stamps = 0
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        self.stub_dir = os.path.join(self.tmp, "bin")
        os.makedirs(self.stub_dir)
        stub = os.path.join(self.stub_dir, "gh")
        with open(stub, "w", encoding="utf-8") as fh:
            fh.write(GH_STUB)
        os.chmod(stub, 0o755)

        self.origin = os.path.join(self.tmp, "origin.git")
        subprocess.run(["git", "init", "-q", "--bare", "-b", "main",
                        self.origin], check=True, capture_output=True,
                       env=self.git_env())
        seed = os.path.join(self.tmp, "seed")
        subprocess.run(["git", "init", "-q", "-b", "main", seed], check=True,
                       capture_output=True, env=self.git_env())
        for rel, text in BASE_TREE.items():
            self.write(seed, rel, text)
        # The install the lane runs from: the two scripts, byte for byte from
        # the plugin, exactly where `.doc-lifecycle/wiring/` puts them.
        for script in ("render-apply-summary.py", "verify-apply-bytes.py"):
            target = os.path.join(seed, ".doc-lifecycle", "wiring", script)
            os.makedirs(os.path.dirname(target), exist_ok=True)
            shutil.copyfile(SCRIPTS / "scripts" / script, target)
        self.git(seed, "add", "-A")
        self.git(seed, "commit", "-qm", "base")
        self.git(seed, "remote", "add", "origin", self.origin)
        self.git(seed, "push", "-q", "origin", "main")
        self.base = self.git(seed, "rev-parse", "HEAD").strip()
        self.seed = seed

    # -- the repositories ----------------------------------------------------

    def next_stamp(self):
        self.stamps += 1
        return self.stamps

    def git_env(self, stamp=0):
        when = f"2026-08-{10 + stamp:02d}T12:00:00+0000"
        return {**os.environ,
                "HOME": self.tmp, "GIT_CONFIG_NOSYSTEM": "1",
                "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@t",
                "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@t",
                "GIT_AUTHOR_DATE": when, "GIT_COMMITTER_DATE": when}

    def git(self, repo, *args):
        return subprocess.run(["git", "-C", repo, *args], check=True,
                              capture_output=True, text=True,
                              env=self.git_env()).stdout

    def write(self, repo, rel, text):
        path = os.path.join(repo, rel)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8", newline="") as fh:
            fh.write(text)

    def run_lane(self, label, pull_requests=NO_PULL_REQUESTS,
                 pr_create_fails=False):
        return ApplyRun(self, label, pull_requests, pr_create_fails).execute()

    def remote_tip(self, ref=None):
        """What `origin` holds at the derived branch, or None."""
        listing = self.git(self.seed, "ls-remote", "--heads", "origin",
                           f"refs/heads/{ref or BRANCH}")
        return listing.split("\t")[0] if listing.strip() else None

    def plant(self, message, tree=None, base=None):
        """Push a commit onto the derived branch, as an earlier run would."""
        work = os.path.join(self.tmp, f"plant-{abs(hash(message)) % 10000}")
        subprocess.run(["git", "clone", "-q", self.origin, work], check=True,
                       capture_output=True, env=self.git_env())
        if base is not None:
            self.git(work, "checkout", "-q", base)
        self.git(work, "switch", "-q", "-c", BRANCH)
        for rel, text in (tree or {"docs/edited.md": AFTER}).items():
            self.write(work, rel, text)
        os.remove(os.path.join(work, "docs/retired.md"))
        self.git(work, "add", "-A")
        self.git(work, "commit", "-qm", message)
        self.git(work, "push", "-q", "origin", f"HEAD:refs/heads/{BRANCH}")
        return self.git(work, "rev-parse", "HEAD").strip()

    def approved_message(self, digest=APPROVAL_DIGEST):
        return (f"docs: apply 1 approved record(s) [approval {digest[:12]}]\n\n"
                f"Doc-Lifecycle-Approval: {digest}\n"
                f"Doc-Lifecycle-Report: {REPORT_DIGEST}\n"
                f"Doc-Lifecycle-Approval-State: clean\n")

    # -- assertions ----------------------------------------------------------

    def assert_clean(self, run):
        for name, completed in run.results:
            self.assertEqual(completed.returncode, 0,
                             f"{name} failed:\n{run.transcript()}")
        self.assertEqual(len(run.results), len(STEPS) - FIRST,
                         run.transcript())

    def assert_refused(self, run, code):
        failed = run.failure()
        self.assertIsNotNone(failed, f"nothing refused:\n{run.transcript()}")
        self.assertIn(f"`{code}`", run.surface(), run.transcript())
        self.assertNotIn("gh pr create", " ".join(run.gh_calls()))


class TheStepsUnderTestAreTheLanesOwn(ApplyRecoveryTestCase):
    def test_the_recovery_steps_were_actually_lifted_out_of_the_workflow(self):
        # Guard against a parser that silently found nothing and then "passed".
        scripts = "\n".join(script for _, script in STEPS[FIRST:])
        for seam in ("render-apply-summary.py remote-branch",
                     "verify-apply-bytes.py reuse",
                     "render-apply-summary.py existing-pull-request",
                     "--state branch-created", "--state branch-reused",
                     "--state pull-request-already-open",
                     "git push origin", "gh pr create"):
            self.assertIn(seam, scripts, f"{seam} is not in the executed steps")


class AFirstRun(ApplyRecoveryTestCase):
    def test_a_first_run_creates_the_branch_and_opens_the_pull_request(self):
        run = self.run_lane("first")
        self.assert_clean(run)
        self.assertIn("## Doc apply: branch created", run.surface())
        self.assertIn(BRANCH, run.surface())
        # The commit the tree verification certified is the one that landed.
        with open(os.path.join(run.temp, "verified-commit.txt"),
                  encoding="utf-8") as fh:
            verified = fh.read().strip()
        self.assertEqual(self.remote_tip(), verified)
        self.assertTrue(any(call.startswith("pr create")
                            for call in run.gh_calls()), run.gh_calls())


class APushThatLandsWhileThePullRequestFails(ApplyRecoveryTestCase):
    def test_the_branch_stands_and_nothing_reviews_it(self):
        run = self.run_lane("stranded", pr_create_fails=True)
        failed = run.failure()
        self.assertIsNotNone(failed, run.transcript())
        self.assertIn("Open the pull request", failed[0])
        # The push landed: this is precisely the stranded approval #198 exists
        # for, and the state the re-run below starts from.
        self.assertIsNotNone(self.remote_tip(), "the push did not land")
        self.assertIn("## Doc apply: branch created", run.surface())


class ARerunAgainstAMatchingBranch(ApplyRecoveryTestCase):
    def test_the_branch_is_reused_and_the_pull_request_opened(self):
        first = self.run_lane("stranded", pr_create_fails=True)
        self.assertIsNotNone(first.failure())
        landed = self.remote_tip()

        rerun = self.run_lane("rerun")
        self.assert_clean(rerun)
        self.assertIn("## Doc apply: branch reused", rerun.surface())
        self.assertIn("Existing branch verified", rerun.surface())
        # Reuse means reuse: the branch still points at the first attempt's
        # commit, and this run's own commit — a different id, made seconds
        # later — never left the runner.
        self.assertEqual(self.remote_tip(), landed)
        with open(os.path.join(rerun.temp, "verified-commit.txt"),
                  encoding="utf-8") as fh:
            self.assertNotEqual(fh.read().strip(), landed)
        self.assertTrue(any(call.startswith("pr create")
                            for call in rerun.gh_calls()), rerun.gh_calls())


class ARerunWithThePullRequestAlreadyOpen(ApplyRecoveryTestCase):
    def open_pull_request(self, digest=APPROVAL_DIGEST, base="main"):
        return [{"number": 41, "headRefName": BRANCH, "baseRefName": base,
                 "body": f"- Approval digest: `{digest}`\n"}]

    def test_an_open_pull_request_for_this_approval_is_idempotent_success(self):
        stranded = self.run_lane("stranded", pr_create_fails=True)
        self.assertIsNotNone(stranded.failure())

        rerun = self.run_lane("rerun", pull_requests=self.open_pull_request())
        self.assert_clean(rerun)
        self.assertIn("## Doc apply: branch reused", rerun.surface())
        self.assertIn("## Doc apply: pull request already open",
                      rerun.surface())
        self.assertIn("#41", rerun.surface())
        self.assertNotIn("pr create", " ".join(rerun.gh_calls()),
                         "a second pull request was opened for one approval")


class AnExistingBranchThatConflicts(ApplyRecoveryTestCase):
    def test_a_matching_approval_on_a_conflicting_tree_is_refused(self):
        planted = self.plant(self.approved_message(),
                             tree={"docs/edited.md": "not what was approved\n"})
        run = self.run_lane("conflicting-tree")
        self.assert_refused(run, "apply-bytes-not-certified")
        self.assertIn("REFUSED at branch reuse", run.surface())
        self.assertEqual(self.remote_tip(), planted,
                         "a refused run moved the branch it refused")

    def test_a_branch_carrying_no_approval_trailer_is_refused(self):
        planted = self.plant("someone else's work")
        run = self.run_lane("foreign-branch")
        self.assert_refused(run, "apply-branch-approval-conflict")
        self.assertEqual(self.remote_tip(), planted)

    def test_a_branch_carrying_another_approvals_trailer_is_refused(self):
        planted = self.plant(self.approved_message(OTHER_APPROVAL_DIGEST))
        run = self.run_lane("other-approval")
        self.assert_refused(run, "apply-branch-approval-conflict")
        self.assertEqual(self.remote_tip(), planted)

    def test_the_same_postimages_on_another_base_are_refused(self):
        # The tree the applier certified, on a base this run did not apply
        # onto: what it changes against the base under review is not what this
        # run verified, so it is a conflict rather than a reuse.
        self.write(self.seed, "docs/kept.md", "moved on\n")
        self.git(self.seed, "add", "-A")
        self.git(self.seed, "commit", "-qm", "base moves")
        self.git(self.seed, "push", "-q", "origin", "main")
        planted = self.plant(self.approved_message(), base=self.base)
        run = self.run_lane("other-base")
        self.assert_refused(run, "apply-branch-lineage-conflict")
        self.assertEqual(self.remote_tip(), planted)


class AnExistingPullRequestThatConflicts(ApplyRecoveryTestCase):
    def test_an_open_pull_request_for_another_approval_is_refused(self):
        stranded = self.run_lane("stranded", pr_create_fails=True)
        self.assertIsNotNone(stranded.failure())
        landed = self.remote_tip()

        rerun = self.run_lane(
            "rerun",
            pull_requests=[{"number": 9, "headRefName": BRANCH,
                            "baseRefName": "main",
                            "body": f"- Approval digest: "
                                    f"`{OTHER_APPROVAL_DIGEST}`\n"}])
        self.assert_refused(rerun, "apply-pull-request-conflict")
        self.assertEqual(self.remote_tip(), landed)

    def test_an_open_pull_request_aimed_at_another_base_is_refused(self):
        stranded = self.run_lane("stranded", pr_create_fails=True)
        self.assertIsNotNone(stranded.failure())
        rerun = self.run_lane(
            "rerun",
            pull_requests=[{"number": 9, "headRefName": BRANCH,
                            "baseRefName": "release",
                            "body": f"- Approval digest: "
                                    f"`{APPROVAL_DIGEST}`\n"}])
        self.assert_refused(rerun, "apply-pull-request-conflict")

    def test_two_open_pull_requests_on_one_branch_are_refused(self):
        stranded = self.run_lane("stranded", pr_create_fails=True)
        self.assertIsNotNone(stranded.failure())
        body = f"- Approval digest: `{APPROVAL_DIGEST}`\n"
        rerun = self.run_lane(
            "rerun",
            pull_requests=[{"number": 9, "headRefName": BRANCH,
                            "baseRefName": "main", "body": body},
                           {"number": 10, "headRefName": BRANCH,
                            "baseRefName": "release", "body": body}])
        self.assert_refused(rerun, "apply-pull-request-conflict")


if __name__ == "__main__":
    unittest.main()
