#!/usr/bin/env python3
"""Static guards for doc-apply.yml (aj604/toolshed#72) beyond the generic suites.

`workflow-permissions_test.py` and `marketplace-pin_test.py` glob over every
`plugins/doc-lifecycle/skills/scheduling-doc-sync/*.yml`, so doc-apply.yml
already inherits: model jobs read-only, credential-free, and
`persist-credentials: false`; workflow-level permissions granting no write;
write jobs running no model and never `git add -A`; and a marketplace pin that
is a local checkout or a `.git`-suffixed URL. This suite covers what is new to
the apply lane — the one lane that writes:

1. Every third-party action is pinned to an immutable 40-hex commit SHA, the
   same bar doc-audit.yml meets.
2. The job shape the acceptance criteria describe: `revalidate` (deterministic,
   no write scope), `plan` (the only model, no credential), `apply`
   (credentialed, no model) — and `apply` runs only when both of the others
   succeeded, so a refusal at revalidation creates no branch and no PR.
3. No dispatch input is ever interpolated into a `run:` block. Inputs travel
   through `env:` (a quoted shell variable) or an action's `with:`, so a
   dispatched string is data, never something the runner splices into a script.
4. Staging is the verified apply result's path list and nothing else: the
   credentialed job stages via `--pathspec-from-file` of the file
   `render-apply-summary.py staged-paths` wrote, then re-checks what git
   actually staged (`verify-staged`) before committing.
5. The PR body and title come from that same tested renderer via `--body-file`,
   never from inline YAML templating — and the PR is real, never a draft.
6. Only the credentialed job pushes or opens a PR, and every artifact it
   downloads lands in `${{ runner.temp }}` rather than the work tree, which the
   applier's whole-diff confinement check would (correctly) refuse to run
   against.

Parsed with the same line-scanner approach as workflow-permissions_test.py,
whose helpers are reused here rather than re-implemented.

Run: python3 tests/scripts/apply-workflow_test.py
"""

import importlib.util
import os
import re
import sys
import unittest

ROOT = os.path.join(os.path.dirname(__file__), "..", "..")
WORKFLOW = os.path.join(
    ROOT, "plugins", "doc-lifecycle", "skills", "scheduling-doc-sync",
    "doc-apply.yml",
)

USES_LINE = re.compile(r"uses:\s*([^\s#]+)")
SHA_PINNED = re.compile(r"^[^@]+@[0-9a-f]{40}$")
DISPATCH_INPUT = re.compile(r"\$\{\{\s*(inputs|github\.event\.inputs)\.")
RUN_BLOCK = re.compile(r"^(\s*)run:\s*\|")


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


def run_block_lines(source):
    """Every line inside a `run: |` block, with its 1-based line number."""
    out, indent = [], None
    for number, line in enumerate(source, 1):
        if indent is not None:
            if line.strip() and WPT.indent_of(line) <= indent:
                indent = None
            else:
                out.append((number, line))
                continue
        match = RUN_BLOCK.match(line)
        if match:
            indent = len(match.group(1))
    return out


class FileExists(unittest.TestCase):
    def test_template_exists(self):
        self.assertTrue(
            os.path.isfile(WORKFLOW),
            "doc-apply.yml is missing — did the scheduling-doc-sync layout move?")


class ThirdPartyActionsAreShaPinned(unittest.TestCase):
    def test_every_uses_line_pins_a_commit_sha(self):
        offenders = []
        for lineno, line in enumerate(lines(), 1):
            match = USES_LINE.search(line)
            if not match:
                continue
            value = match.group(1).strip().strip("'\"")
            if not SHA_PINNED.match(value):
                offenders.append(f"{lineno}: uses: {value}")
        self.assertEqual(
            offenders, [],
            "doc-apply.yml has action reference(s) not pinned to an immutable "
            "commit SHA:\n  " + "\n  ".join(offenders))

    def test_some_actions_are_actually_checked(self):
        self.assertTrue([l for l in lines() if USES_LINE.search(l)],
                        "no `uses:` lines found — did the file move?")


class JobShape(unittest.TestCase):
    def test_exactly_revalidate_plan_and_apply_jobs(self):
        self.assertEqual(set(jobs()), {"revalidate", "plan", "apply"})

    def test_revalidate_holds_no_write_scope(self):
        perms = WPT.mapping_under(jobs()["revalidate"], "permissions", 4)
        self.assertIsNotNone(perms, "revalidate declares no permissions block")
        self.assertEqual(WPT.write_scopes(perms), {})

    def test_only_the_plan_job_invokes_a_model(self):
        with_model = {name for name, body in jobs().items()
                      if any(WPT.MODEL_ACTION in line for line in body)}
        self.assertEqual(with_model, {"plan"})

    def test_the_apply_job_is_the_only_credentialed_one(self):
        credentialed = {
            name for name, body in jobs().items()
            if set(WPT.write_scopes(
                WPT.mapping_under(body, "permissions", 4) or {})) - {"id-token"}
        }
        self.assertEqual(credentialed, {"apply"})

    def test_the_apply_job_grants_exactly_what_a_pr_needs(self):
        perms = WPT.mapping_under(jobs()["apply"], "permissions", 4)
        self.assertEqual(perms, {"contents": "write",
                                 "pull-requests": "write"})

    def test_apply_runs_only_when_revalidation_and_planning_succeeded(self):
        body = jobs()["apply"]
        needs = [l.strip() for l in body if l.strip().startswith("needs:")]
        self.assertTrue(needs, "the apply job declares no `needs:`")
        self.assertIn("revalidate", needs[0])
        self.assertIn("plan", needs[0])

    def test_the_apply_job_declares_no_run_anyway_condition(self):
        # A refusal upstream must leave no branch and no pull request; a job
        # that runs `if: always()` (or `!cancelled()`) would write anyway.
        body = jobs()["apply"]
        offenders = [l.strip() for l in body
                     if l.strip().startswith("if:")
                     and WPT.indent_of(l) == 4]
        self.assertEqual(offenders, [])


class DispatchInputsNeverReachAShell(unittest.TestCase):
    def test_no_run_block_interpolates_a_dispatch_input(self):
        offenders = [f"{n}: {l.strip()}" for n, l in run_block_lines(lines())
                     if DISPATCH_INPUT.search(l)]
        self.assertEqual(
            offenders, [],
            "a dispatch input is spliced into a shell script — pass it through "
            "`env:` and quote it instead:\n  " + "\n  ".join(offenders))

    def test_the_inputs_that_exist_are_actually_used_somewhere(self):
        text = "\n".join(lines())
        for name in ("report_run_id", "report_digest", "records", "base"):
            self.assertIn(f"inputs.{name}", text,
                          f"input {name} is declared but never consumed")

    def test_the_record_selection_is_validated_before_it_becomes_argv(self):
        body = "\n".join(jobs()["revalidate"])
        self.assertIn("record-args", body)
        # The validated file is what supplies argv, never the raw input.
        self.assertIn("record-args.txt", body)


class StagingIsLimitedToTheApplyResult(unittest.TestCase):
    def test_staging_reads_the_path_list_the_renderer_wrote(self):
        body = "\n".join(jobs()["apply"])
        self.assertIn("staged-paths", body)
        self.assertIn("--pathspec-from-file", body)
        self.assertIn("--pathspec-file-nul", body)

    def test_what_git_staged_is_re_checked_before_the_commit(self):
        body = jobs()["apply"]
        text = "\n".join(body)
        self.assertIn("verify-staged", text)
        verify = next(i for i, l in enumerate(body) if "verify-staged" in l)
        commit = next(i for i, l in enumerate(body) if "git commit" in l)
        self.assertLess(verify, commit,
                        "the staged set is checked after the commit is made")

    def test_no_job_but_apply_pushes_or_opens_a_pull_request(self):
        for name, body in jobs().items():
            if name == "apply":
                continue
            text = "\n".join(body)
            self.assertNotIn("git push", text, f"job '{name}' pushes")
            self.assertNotIn("gh pr create", text, f"job '{name}' opens a PR")

    def test_downloaded_artifacts_never_land_in_the_work_tree(self):
        # The applier refuses a working tree holding any change at all, and an
        # artifact downloaded into the checkout is one.
        for name in ("revalidate", "apply"):
            body = jobs()[name]
            downloads = [i for i, l in enumerate(body)
                         if "actions/download-artifact@" in l]
            self.assertTrue(downloads, f"job '{name}' downloads nothing")
            for i in downloads:
                window = "\n".join(body[i:i + 8])
                self.assertIn("path: ${{ runner.temp }}", window,
                              f"job '{name}' downloads into the work tree")


class ProvenanceTravelsWithTheChange(unittest.TestCase):
    def test_the_pr_body_is_rendered_by_the_tested_renderer(self):
        body = "\n".join(jobs()["apply"])
        self.assertIn("render-apply-summary.py pr-body", body)
        self.assertIn("--body-file", body)

    def test_the_pr_title_and_commit_message_are_rendered_too(self):
        body = "\n".join(jobs()["apply"])
        self.assertIn("render-apply-summary.py pr-title", body)
        self.assertIn("render-apply-summary.py commit-message", body)
        self.assertIn("git commit -F", body)

    def test_the_approval_summary_and_trailers_come_from_the_engine(self):
        revalidate = "\n".join(jobs()["revalidate"])
        self.assertIn("render-approval", revalidate)
        self.assertIn("--trailers", revalidate)

    def test_the_pull_request_is_real_not_a_draft(self):
        self.assertNotIn("--draft", "\n".join(lines()))

    def test_the_body_is_never_templated_inline(self):
        text = "\n".join(lines())
        self.assertNotIn("--body ", text)
        self.assertNotIn('jq -r', text)


class RefusalsReachTheRunSurface(unittest.TestCase):
    def test_every_engine_exit_code_is_gated_by_the_renderer(self):
        text = "\n".join(lines())
        for stage in ("revalidation", "minting", "apply"):
            self.assertIn(f"gate --stage {stage}", text,
                          f"the {stage} stage's exit code is not gated")

    def test_the_report_artifact_is_bound_to_the_dispatched_digest(self):
        self.assertIn("verify-report", "\n".join(jobs()["revalidate"]))

    def test_configuration_drift_is_compared_rather_than_skipped(self):
        text = "\n".join(lines())
        self.assertIn("config-digest", text)
        self.assertIn("--audit-config-digest", text)


class ConcurrencyDeclared(unittest.TestCase):
    def test_concurrency_group_declared_without_cancellation(self):
        text = "\n".join(lines())
        self.assertIn("concurrency:", text)
        self.assertIn("cancel-in-progress: false", text)


if __name__ == "__main__":
    unittest.main()
