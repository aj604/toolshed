#!/usr/bin/env python3
"""Static guards for `doc-sync-upgrade.yml` — the upgrade lane's trust split.

`workflow-permissions_test.py` already asserts the generic contract over every
shipped template (model jobs hold no write authority, write jobs run no model,
staging is explicit). This suite asserts what is specific to the upgrade lane,
which is the one lane whose input is a *release of executable code* rather than
a document (aj604/toolshed#127):

1. Only one job runs the target release's `apply-upgrade.py`, and that job holds
   `contents: read`, no `GH_TOKEN`, and a checkout that persists no credential.
2. The credentialed job runs nothing out of the clone or the scratch tree —
   every program it invokes comes from the install's own checkout — and it
   stages the manifest's path set, verified after staging.
3. Execution is dispatch-gated. The scheduled job never clones and never runs
   the release's code; the regenerating job runs only on a dispatch carrying a
   target, and the dispatch input reaches no shell as a substitution.
4. The lane still runs no model, and the workflow YAML carries no version — the
   lockfile remains the pin.
5. Every run-surface string it emits — summaries, the PR body, the PR title,
   the commit subject — comes from `render-report.py`, never from a literal in
   the YAML (aj604/toolshed#189).

Read against the published template only; `install-parity_test.py` is what ties
the dogfooded install to it.

Run: python3 tests/scripts/upgrade-workflow_test.py
"""

import importlib.util
import os
import re
import sys
import unittest

ROOT = os.path.join(os.path.dirname(__file__), "..", "..")
WORKFLOW = os.path.join(
    ROOT, "plugins", "doc-lifecycle", "skills", "scheduling-doc-sync",
    "doc-sync-upgrade.yml",
)

USES_LINE = re.compile(r"uses:\s*([^\s#]+)")
SHA_PINNED = re.compile(r"^[^@]+@[0-9a-f]{40}$")
DISPATCH_INPUT = re.compile(r"\$\{\{\s*(inputs|github\.event\.inputs)\.")
RUN_BLOCK = re.compile(r"^(\s*)run:\s*\|")
# The untrusted tree the target release is cloned into, and the scratch copy it
# writes. A program invoked out of either is the release executing here.
UNTRUSTED_ROOTS = ("toolshed-marketplace", "scratch")
SEMVER = re.compile(r"\b\d+\.\d+\.\d+\b")


def load_permissions_test():
    path = os.path.join(os.path.dirname(__file__), "workflow-permissions_test.py")
    spec = importlib.util.spec_from_file_location("workflow_permissions_test", path)
    mod = importlib.util.module_from_spec(spec)
    sys.dont_write_bytecode = True
    spec.loader.exec_module(mod)
    return mod


WPT = load_permissions_test()


def lines():
    with open(WORKFLOW, encoding="utf-8") as fh:
        return fh.read().splitlines()


def jobs():
    return WPT.jobs_of(WORKFLOW)


def run_block_lines(body):
    """Every line inside a `run: |` block of one job body."""
    out, indent = [], None
    for line in body:
        if indent is not None:
            if line.strip() and WPT.indent_of(line) <= indent:
                indent = None
            else:
                out.append(line)
                continue
        match = RUN_BLOCK.match(line)
        if match:
            indent = len(match.group(1))
    return out


def code_lines(body):
    """Run-block lines that are not comments."""
    return [ln for ln in run_block_lines(body) if not ln.strip().startswith("#")]


def job_if(body):
    for line in body:
        if WPT.indent_of(line) == 4 and line.strip().startswith("if:"):
            return line.strip()[3:].strip()
    return None


class FileExists(unittest.TestCase):
    def test_the_template_is_where_the_installer_looks(self):
        self.assertTrue(os.path.isfile(WORKFLOW),
                        f"{WORKFLOW} is missing — did the template move?")


class JobShape(unittest.TestCase):
    def setUp(self):
        self.jobs = jobs()

    def test_the_lane_is_three_jobs_split_by_trust(self):
        self.assertEqual(sorted(self.jobs), ["detect", "land", "regenerate"])

    def test_only_the_landing_job_is_credentialed(self):
        credentialed = {
            name for name, body in self.jobs.items()
            if WPT.write_scopes(WPT.mapping_under(body, "permissions", 4) or {})
        }
        self.assertEqual(credentialed, {"detect", "land"})
        self.assertEqual(
            WPT.mapping_under(self.jobs["land"], "permissions", 4),
            {"contents": "write", "pull-requests": "write"})

    def test_the_detecting_job_holds_only_the_notification_scope(self):
        # It never clones and never runs the release's code, so `issues: write`
        # buys a notice and nothing that can change this repository.
        self.assertEqual(
            WPT.mapping_under(self.jobs["detect"], "permissions", 4),
            {"contents": "read", "issues": "write"})

    def test_the_job_that_runs_the_release_holds_no_write_scope(self):
        self.assertEqual(
            WPT.mapping_under(self.jobs["regenerate"], "permissions", 4),
            {"contents": "read"})

    def test_the_job_that_runs_the_release_carries_no_token(self):
        self.assertNotIn("GH_TOKEN",
                         WPT.mapping_under(self.jobs["regenerate"], "env", 4) or {})
        for line in self.jobs["regenerate"]:
            self.assertNotIn("secrets.", line,
                             "the regenerating job must reference no secret")

    def test_the_job_that_runs_the_release_persists_no_checkout_credential(self):
        body = self.jobs["regenerate"]
        checkouts = sum(1 for line in body if "actions/checkout@" in line)
        dropped = sum(1 for line in body
                      if line.strip().startswith("persist-credentials: false"))
        self.assertEqual(checkouts, dropped)
        self.assertGreater(checkouts, 0)

    def test_landing_needs_the_regeneration_and_does_not_run_past_its_failure(self):
        self.assertIn("needs: regenerate",
                      [line.strip() for line in self.jobs["land"]])
        self.assertIsNone(job_if(self.jobs["land"]),
                          "a job-level if: on the landing job could let it run "
                          "after the regeneration refused")

    def test_no_job_runs_a_model(self):
        # The 2026-07-07 deterministic-upgrade decision: this lane makes no
        # model call, so its write scopes never sit behind a model process.
        with open(WORKFLOW, encoding="utf-8") as fh:
            text = fh.read()
        self.assertNotIn(WPT.MODEL_ACTION, text)
        self.assertNotIn("id-token", text)

    def test_third_party_actions_are_sha_pinned(self):
        found = 0
        for line in lines():
            match = USES_LINE.search(line)
            if not match:
                continue
            found += 1
            self.assertRegex(match.group(1), SHA_PINNED,
                             f"unpinned action: {line.strip()}")
        self.assertGreater(found, 0, "no `uses:` found — did the layout move?")

    def test_concurrency_queues_rather_than_cancels(self):
        body = lines()
        self.assertIn("concurrency:", body)
        self.assertIn("  cancel-in-progress: false", body)


class ExecutionIsHumanInitiated(unittest.TestCase):
    """A version comparison must not be what causes the release to run here."""

    def setUp(self):
        self.jobs = jobs()

    def test_the_workflow_takes_a_target_dispatch_input(self):
        body = lines()
        self.assertIn("  workflow_dispatch:", body)
        self.assertIn("      target:", body)

    def test_the_scheduled_job_runs_only_without_a_target(self):
        self.assertEqual(job_if(self.jobs["detect"]), "inputs.target == ''")

    def test_the_regenerating_job_runs_only_with_one(self):
        self.assertEqual(job_if(self.jobs["regenerate"]), "inputs.target != ''")

    def test_the_scheduled_job_neither_clones_nor_runs_the_release(self):
        for line in code_lines(self.jobs["detect"]):
            self.assertNotIn("git clone", line)
            self.assertNotIn("apply-upgrade.py", line)
            for root in UNTRUSTED_ROOTS:
                self.assertNotIn(root, line)

    def test_the_dispatch_input_never_reaches_a_shell(self):
        for job, body in self.jobs.items():
            for line in run_block_lines(body):
                self.assertIsNone(
                    DISPATCH_INPUT.search(line),
                    f"job '{job}' splices a dispatch input into a shell: "
                    f"{line.strip()} — pass it through env: and shape-check it")

    def test_the_target_names_a_ref_only_after_the_gate_normalized_it(self):
        body = "\n".join(code_lines(self.jobs["regenerate"]))
        self.assertIn("upgrade-gate.py normalize", body)
        # The clone reads the step output, never the raw dispatch value.
        self.assertRegex(body, r'git clone[^\n]*\n?[^\n]*"v\$\{TARGET\}"')
        self.assertIn("TARGET: ${{ steps.target.outputs.target }}",
                      "\n".join(self.jobs["regenerate"]))

    def test_a_dispatch_may_not_rewind_the_pin(self):
        body = "\n".join(code_lines(self.jobs["regenerate"]))
        self.assertIn("upgrade-gate.py compare", body)
        self.assertIn('!= "upgrade"', body)


class TheCredentialedJobRunsNothingUntrusted(unittest.TestCase):
    def setUp(self):
        self.jobs = jobs()

    def test_it_never_invokes_a_program_from_the_clone_or_scratch_tree(self):
        for line in code_lines(self.jobs["land"]):
            for root in UNTRUSTED_ROOTS:
                self.assertNotIn(
                    root, line,
                    f"the credentialed job reaches into {root}: {line.strip()}")

    # The bug this replaced a weaker check for: the bundle legitimately carries
    # the target release's own `.doc-lifecycle/wiring/*.py`, so a credentialed step
    # invoking one out of the work tree *after* the transfer runs the release's
    # code with the push token — the split defeated two steps later.
    def test_no_program_it_runs_can_have_been_overwritten_by_the_transfer(self):
        for job in ("regenerate", "land"):
            body = code_lines(self.jobs[job])
            copy = next(i for i, ln in enumerate(body)
                        if "cp .doc-lifecycle/wiring/*.py" in ln)
            for i, line in enumerate(body[copy:], copy):
                for call in re.findall(r'python3 "?([^\s"]+)', line):
                    self.assertNotIn(
                        ".doc-lifecycle/wiring/", call,
                        f"job '{job}' runs {call} out of the work tree after "
                        f"the trusted copy was taken — the regeneration "
                        f"overwrites that path with the release's own copy, so "
                        f"run it from ${{RUNNER_TEMP}}/trusted instead")

    def test_both_jobs_copy_their_tooling_out_before_anything_writes(self):
        for job, writer in (("regenerate", "apply-upgrade.py"),
                            ("land", "stage-upgrade.py\" apply")):
            body = code_lines(self.jobs[job])
            copy = next(i for i, ln in enumerate(body)
                        if "cp .doc-lifecycle/wiring/*.py" in ln)
            write = next(i for i, ln in enumerate(body) if writer in ln)
            self.assertLess(
                copy, write,
                f"job '{job}' takes its trusted copy after {writer} ran")

    def test_it_stages_the_manifest_path_set_and_nothing_else(self):
        body = code_lines(self.jobs["land"])
        joined = "\n".join(body)
        self.assertIn("--pathspec-from-file=", joined)
        self.assertIn("--pathspec-file-nul", joined)
        self.assertNotIn("git add -A", joined)
        self.assertNotIn("git add --all", joined)

    def test_the_staged_set_is_verified_before_the_commit(self):
        body = code_lines(self.jobs["land"])
        verify = next(i for i, ln in enumerate(body)
                      if 'stage-upgrade.py" verify' in ln)
        commit = next(i for i, ln in enumerate(body) if "git commit" in ln)
        self.assertLess(verify, commit,
                        "the staged set must be verified before it is committed")

    def test_the_bundle_lands_outside_the_work_tree(self):
        body = "\n".join(self.jobs["land"])
        self.assertIn("path: ${{ runner.temp }}/upgrade-bundle", body)

    def test_the_bundle_is_bound_to_the_dispatched_version(self):
        joined = "\n".join(code_lines(self.jobs["land"]))
        self.assertRegex(joined, r'stage-upgrade\.py"? apply[\s\S]*--target')

    def test_no_other_job_pushes_or_opens_a_pull_request(self):
        for name in ("detect", "regenerate"):
            for line in code_lines(self.jobs[name]):
                self.assertNotIn("git push", line)
                self.assertNotIn("gh pr create", line)


class TheLockfileRemainsThePin(unittest.TestCase):
    def test_the_workflow_yaml_carries_no_version(self):
        # The 2026-07-07 deterministic-upgrade decision: the YAML is
        # byte-identical across versions, so an upgrade that changes only the
        # pin never has to push a workflow file.
        for number, line in enumerate(lines(), 1):
            if line.strip().startswith("#"):
                continue
            self.assertIsNone(
                SEMVER.search(line.split("#")[0]),
                f"{WORKFLOW}:{number} pins a version in the YAML: "
                f"{line.strip()} — installed-version is the pin")

    def test_every_job_reads_the_lockfile_rather_than_a_literal(self):
        for name in ("detect", "regenerate"):
            self.assertIn(
                "cat .doc-lifecycle/installed-version",
                "\n".join(code_lines(jobs()[name])))


class RefusalsReachTheRunSurface(unittest.TestCase):
    def setUp(self):
        self.jobs = jobs()

    def test_no_dead_exit_code_reads(self):
        # The runner's shell is `bash -e`, and `set -uo pipefail` does not clear
        # that: a bare `$?` read only ever runs after the previous command
        # already succeeded, so it is unreachable dead code. The one shape that
        # survives is `cmd || var=$?` (aj604/toolshed#107).
        captured = re.compile(r"\|\|\s*[A-Za-z_][A-Za-z0-9_]*=\$\?")
        offenders = []
        for number, line in enumerate(lines(), 1):
            if line.strip().startswith("#") or "$?" not in line:
                continue
            if captured.search(line):
                continue
            # Reading a captured variable back is fine; writing one is not.
            if re.search(r"=\$\?", line):
                offenders.append(f"{number}: {line.strip()}")
        self.assertEqual(offenders, [],
                         "a $? read outside a `|| var=$?` capture is dead code")

    def test_the_manifest_refusal_reaches_the_run_surface(self):
        body = "\n".join(code_lines(self.jobs["regenerate"]))
        self.assertIn("|| code=$?", body)
        self.assertIn("--status refused", body)
        # Only the authority's own refusal (1) claims the release reached
        # outside the wiring; bad input (2) must not be laundered as that.
        self.assertIn('"${code}" -eq 1', body)

    def test_every_terminal_state_renders_a_summary(self):
        joined = "\n".join("\n".join(code_lines(body))
                           for body in self.jobs.values())
        for status in ("available", "notified", "refused", "noop",
                       "opened", "pending"):
            self.assertIn(f"--status {status}", joined,
                          f"no run-surface summary for the {status!r} outcome")

    def test_the_blocked_status_comes_from_the_path_authority(self):
        # Both a template change and the one-time relocation out of
        # `.github/doc-sync/` are blocked by the same push restriction, and the
        # summary has to say which. That is decided by the code that saw the
        # change set (aj604/toolshed#133), never by grepping paths in YAML.
        body = "\n".join(code_lines(self.jobs["land"]))
        self.assertIn("--blocked-status-out", body)
        self.assertIn('--status "$(cat "${RUNNER_TEMP}/blocked-status.txt")"',
                      body)
        for literal in ("--status blocked-workflows", "--status blocked-relocation"):
            self.assertNotIn(
                literal, body,
                f"{literal} is spelled in the YAML — which blocked status this "
                f"is belongs to stage-upgrade.py, which read the manifest")

    def test_the_blocked_patch_is_the_staged_diff_so_creations_survive(self):
        # A relocation's patch is mostly creations; `git diff` before staging
        # would carry only the deletions and be unapplicable.
        body = code_lines(self.jobs["land"])
        stage = next(i for i, ln in enumerate(body)
                     if "git add --pathspec-from-file=" in ln)
        patch = next(i for i, ln in enumerate(body)
                     if "doc-sync-upgrade.patch" in ln)
        self.assertLess(stage, patch)
        self.assertIn("git diff --cached > ", body[patch])

    def test_the_blocked_workflows_patch_is_published(self):
        body = "\n".join(self.jobs["land"])
        self.assertIn("doc-sync-upgrade-patch", body)
        self.assertIn("if-no-files-found: ignore", body)


class EveryRunSurfaceStringIsRendered(unittest.TestCase):
    """Summaries, PR bodies, PR titles, commit messages — all through the script.

    The repository standard, and the reason for it: a string typed into YAML is
    a string no suite ever reads, and the lane's whole run surface is what a
    human sees of an upgrade nobody watched happen (aj604/toolshed#189).
    """

    def setUp(self):
        self.jobs = jobs()

    def test_the_landing_job_renders_its_subject_title_and_body(self):
        body = "\n".join(code_lines(self.jobs["land"]))
        for subcommand in ("upgrade-commit-subject", "upgrade-pr-title",
                           "upgrade-pr-body"):
            self.assertIn(f'render-report.py" {subcommand}', body,
                          f"the landing job does not render {subcommand}")

    def test_the_rendered_strings_come_from_the_pre_transfer_copy(self):
        # Same reason every other program in this job does: the bundle carries
        # the target release's own render-report.py, and a title rendered by
        # the release being installed is the release describing itself.
        for line in code_lines(self.jobs["land"]):
            if "render-report.py" not in line:
                continue
            self.assertIn(
                "${RUNNER_TEMP}/trusted/render-report.py", line,
                f"the landing job renders with a copy the transfer could have "
                f"overwritten: {line.strip()}")

    # Both spellings of the same option. A substring match on `git commit -m`
    # let `git commit --message "docs: upgrade…"` through the whole gate —
    # the same shape as the force-push detector's `\bgit push\b` missing
    # `git -C … push` (#198) and #194's under-scoped phrase pins. A guard that
    # names one spelling of a flag is a guard the next author bypasses without
    # meaning to. `-m` is matched as a whole word so `--message` is not
    # double-counted and an unrelated `-mtime` never trips it.
    COMMIT_MESSAGE_FLAG = re.compile(
        r"\bgit\b(?![^\n|;&]*\b--file\b)[^\n|;&]*?\bcommit\b[^\n|;&]*?"
        r"(?:\s-m\b|\s--message\b|\s-\w*m\b)")

    def test_no_commit_message_is_typed_into_the_yaml(self):
        for job, body in self.jobs.items():
            for line in code_lines(body):
                self.assertIsNone(
                    self.COMMIT_MESSAGE_FLAG.search(line),
                    f"job '{job}' types a commit message into the YAML: "
                    f"{line.strip()} — render it and commit with -F")

    def test_the_commit_message_guard_catches_both_spellings(self):
        # The guard's own regression test. Every one of these is a real way to
        # smuggle a run-surface string past a substring match, and each was
        # confirmed against the live template before this pattern landed.
        for smuggled in (
                'git commit -m "docs: upgrade"',
                'git commit --message "docs: upgrade"',
                'git -C "${dir}" commit -m "docs: upgrade"',
                'git -C "${dir}" commit --message "docs: upgrade"',
                'git commit -am "docs: upgrade"',
                'git commit --quiet --message "docs: upgrade"'):
            self.assertIsNotNone(
                self.COMMIT_MESSAGE_FLAG.search(smuggled),
                f"the guard does not catch: {smuggled}")

        # And it does not fire on the spelling the lane is required to use.
        for allowed in (
                'git commit -F "${RUNNER_TEMP}/commit-message.txt"',
                'git commit --file "${RUNNER_TEMP}/commit-message.txt"'):
            self.assertIsNone(
                self.COMMIT_MESSAGE_FLAG.search(allowed),
                f"the guard wrongly refuses the rendered path: {allowed}")

    def test_no_title_is_typed_into_the_yaml(self):
        # Every `--title` argument reads a rendered value; a literal one is a
        # run-surface string no test can hold to account.
        for job, body in self.jobs.items():
            for line in code_lines(body):
                for value in re.findall(r'--title\s+"([^"]*)', line):
                    self.assertTrue(
                        value.startswith("$"),
                        f"job '{job}' types a title into the YAML: "
                        f"{line.strip()} — render it through render-report.py")


if __name__ == "__main__":
    unittest.main()
