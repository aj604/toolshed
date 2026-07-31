#!/usr/bin/env python3
"""Static guards for doc-apply.yml (aj604/toolshed#72) beyond the generic suites.

`workflow-permissions_test.py` and `marketplace-pin_test.py` glob over every
`plugins/doc-lifecycle/skills/scheduling-doc-sync/*.yml`, so doc-apply.yml
already inherits: model jobs read-only, repository-credential-free, and
`persist-credentials: false`; workflow-level permissions granting no write;
write jobs running no model and never `git add -A`; and a marketplace pin that
is a local checkout or a `.git`-suffixed URL. This suite covers what is new to
the apply lane — the one lane that writes:

1. Every third-party action is pinned to an immutable 40-hex commit SHA, the
   same bar doc-audit.yml meets.
2. The job shape the acceptance criteria describe: `revalidate` (deterministic,
   no write scope), `plan` (the only model, no repository credential), `apply`
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


def run_blocks(source):
    """`run: |` blocks grouped, each a list of `(1-based lineno, line)`."""
    blocks, current, indent = [], None, None
    for number, line in enumerate(source, 1):
        if indent is not None:
            if line.strip() and WPT.indent_of(line) <= indent:
                blocks.append(current)
                current, indent = None, None
            else:
                current.append((number, line))
                continue
        match = RUN_BLOCK.match(line)
        if match:
            indent, current = len(match.group(1)), []
    if current is not None:
        blocks.append(current)
    return blocks


def run_block_lines(source):
    """Every line inside a `run: |` block, with its 1-based line number — the
    grouped blocks flattened, so the block-boundary scan has one owner."""
    return [pair for block in run_blocks(source) for pair in block]


def _logical_commands(block):
    """A run block's shell commands as `(first-lineno, joined-text)`.

    Backslash-continued lines are one command; blank and comment lines are
    dropped. Enough to ask which command is a run block's last, and whether a
    `gate` is chained with `|| exit`."""
    commands, buf, start = [], "", None
    for lineno, line in block:
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        if start is None:
            start = lineno
        if stripped.endswith("\\"):
            buf += stripped[:-1].strip() + " "
            continue
        buf += stripped
        commands.append((start, buf.strip()))
        buf, start = "", None
    if start is not None:
        commands.append((start, buf.strip()))
    return commands


def download_paths(body):
    """The normalized `path:` each `download-artifact` step extracts into.

    A thin projection of `download_specs` so the download-step scan has one
    owner; the RUNNER_TEMP normalization also makes two spellings of the same
    directory compare equal in the two-artifacts-one-directory guard."""
    return [path for _, path in download_specs(body) if path]


def norm_temp(text):
    """`${{ runner.temp }}` and `${RUNNER_TEMP}` collapsed to one token.

    A path the same directory is spelled two ways — `${{ runner.temp }}` in an
    action `with:` value, `${RUNNER_TEMP}` in a shell command — must compare
    equal, so the artifact layout can be checked across both."""
    text = re.sub(r"\$\{\{\s*runner\.temp\s*\}\}", "/T", text)
    return text.replace("${RUNNER_TEMP}", "/T").replace("$RUNNER_TEMP", "/T")


def upload_specs(body):
    """Each `upload-artifact` step in `body` as `(name, [path entries])`.

    A `path: |` block lists one normalized entry per following, more-indented
    line; a single-line `path: X` is a one-entry list."""
    specs = []
    for i, line in enumerate(body):
        if "actions/upload-artifact@" not in line:
            continue
        name, entries = None, []
        j = i + 1
        while j < len(body):
            stripped = body[j].strip()
            if j != i + 1 and (stripped.startswith("- name:")
                               or stripped.startswith("- uses:")):
                break
            nm = re.match(r"name:\s*(\S.+?)\s*$", stripped)
            if nm and name is None:
                name = nm.group(1)
            pm = re.match(r"path:\s*(\|)?\s*(.*)$", stripped)
            if pm:
                if pm.group(1):
                    base = WPT.indent_of(body[j])
                    k = j + 1
                    while k < len(body):
                        if not body[k].strip():
                            k += 1
                            continue
                        if WPT.indent_of(body[k]) <= base:
                            break
                        entries.append(norm_temp(body[k].strip()))
                        k += 1
                elif pm.group(2).strip():
                    entries.append(norm_temp(pm.group(2).strip()))
            j += 1
        specs.append((name, entries))
    return specs


def download_specs(body):
    """Each `download-artifact` step as `(name, normalized extract path)`."""
    specs = []
    for i, line in enumerate(body):
        if "actions/download-artifact@" not in line:
            continue
        name, path = None, None
        for follow in body[i + 1:i + 12]:
            stripped = follow.strip()
            if stripped.startswith("- name:") or stripped.startswith("- uses:"):
                break
            nm = re.match(r"name:\s*(\S.+?)\s*$", stripped)
            if nm and name is None:
                name = nm.group(1)
            pm = re.match(r"path:\s*(\S.+?)\s*$", stripped)
            if pm and path is None:
                path = norm_temp(pm.group(1))
        specs.append((name, path))
    return specs


def uploaded_internal_paths(entries):
    """The path each uploaded entry lands at *inside* the artifact.

    `upload-artifact` roots a multi-path artifact at the least-common-ancestor
    of its search paths and preserves each file's path relative to it; a single
    path is stored at its basename. This is the exact `getMultiPathLCA`
    behaviour a consumer must extract back out of."""
    if len(entries) == 1:
        return {os.path.basename(entries[0])}
    lca = os.path.commonpath(entries)
    return {os.path.relpath(e, lca) for e in entries}


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

    def test_the_report_run_id_is_shape_validated_before_it_names_a_run(self):
        # `report_run_id` reaches both a `gh api .../actions/runs/<id>` path and
        # `download-artifact`'s `run-id` (parseInt); a raw value could make the
        # two name different runs. It must be validated to decimal digits first,
        # and both consumers must read the validated step output — the raw
        # dispatch input may reach only the validation step's own env.
        body = jobs()["revalidate"]
        text = "\n".join(body)
        self.assertIn("render-apply-summary.py run-id", text,
                      "report_run_id is never shape-validated before use")
        self.assertIn("steps.runid.outputs.report_run_id", text,
                      "the validated run id is never consumed")
        raw = [l for l in body if "inputs.report_run_id" in l]
        self.assertEqual(
            len(raw), 1,
            "the raw report_run_id dispatch input is read outside the single "
            f"validation step that shape-checks it: {raw}")


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

    def test_no_job_downloads_two_artifacts_into_one_directory(self):
        # The trusted `apply-approval` bundle (trailers, approval summary,
        # branch name) and the model-authored `apply-plan` must not share a
        # download `path:`. upload-artifact roots an artifact at its upload
        # directory, so a plan job that made `edit-plan.json` a *directory*
        # bundling `trailers.txt`/`branch.txt` could, extracted second into a
        # shared dir, overwrite the revalidate job's trusted files — forging the
        # commit trailers, the PR body, and the branch a credentialed job pushes.
        for name, body in jobs().items():
            paths = download_paths(body)
            self.assertEqual(
                len(paths), len(set(paths)),
                f"job '{name}' downloads two artifacts into the same path "
                f"{paths}; a model-authored artifact extracted over a trusted "
                f"one is an overwrite — give each its own directory")

    def test_a_multi_path_upload_lists_only_siblings(self):
        # upload-artifact roots a multi-path artifact at the least-common
        # ancestor of its search paths, so an entry one directory deeper than
        # its siblings is stored under that subdirectory rather than flat. A
        # consumer that names `<download>/<basename>` then reads the wrong path
        # and the file is silently absent. Every entry of one upload list must
        # therefore share a single parent directory: one directory, one flat
        # artifact.
        offenders = []
        for name, body in jobs().items():
            for artifact, entries in upload_specs(body):
                if len(entries) < 2:
                    continue
                parents = {os.path.dirname(e) for e in entries}
                if len(parents) != 1:
                    offenders.append(
                        f"job '{name}' artifact '{artifact}': entries span "
                        f"parents {sorted(parents)} — {entries}")
        self.assertEqual(
            offenders, [],
            "a multi-path upload-artifact list mixes directories, so its "
            "artifact is not flat and a consumer reading <download>/<basename> "
            "reads the wrong path:\n  " + "\n  ".join(offenders))

    def test_every_bundle_read_resolves_to_an_uploaded_entry(self):
        # The complement of the sibling rule: model the exact extract path of
        # every uploaded entry (LCA-rooted, as upload-artifact stores it) and
        # require every path a downstream job reads out of a downloaded bundle
        # to equal one of them. This catches the read side directly — a
        # consumer naming `<download>/drift-report.json` for a report the
        # artifact actually stored at `dispatch/drift-report.json`.
        uploads = {}
        for _, body in jobs().items():
            for artifact, entries in upload_specs(body):
                if entries:
                    uploads[artifact] = uploaded_internal_paths(entries)
        offenders = []
        for name, body in jobs().items():
            text = norm_temp("\n".join(body))
            for artifact, dp in download_specs(body):
                if artifact not in uploads or not dp:
                    continue
                valid = {f"{dp}/{internal}" for internal in uploads[artifact]}
                for match in re.finditer(
                        re.escape(dp) + r"/([A-Za-z0-9._/-]+)", text):
                    ref = (dp + "/" + match.group(1)).rstrip("./,")
                    if ref not in valid:
                        offenders.append(
                            f"job '{name}' reads {ref}, which artifact "
                            f"'{artifact}' does not store — it holds "
                            f"{sorted(valid)}")
        self.assertEqual(
            sorted(set(offenders)), [],
            "a downstream job reads a bundle path the artifact never stored "
            "there:\n  " + "\n  ".join(sorted(set(offenders))))


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

    def test_no_gated_command_relies_on_a_bare_exit_status_read(self):
        # The runner's shell is `bash -e`: a command whose non-zero exit is a
        # typed verdict must be captured with `|| code=$?`, or the step is
        # already over by the time the gate would have rendered it.
        offenders = [f"{n}: {l.strip()}" for n, l in run_block_lines(lines())
                     if l.strip() == "code=$?"]
        self.assertEqual(
            offenders, [],
            "an exit code is read after a command bash -e would have aborted "
            "on:\n  " + "\n  ".join(offenders))

    def test_every_gate_reads_a_captured_exit_code(self):
        captures = sum(1 for _, l in run_block_lines(lines())
                       if "|| code=$?" in l)
        gates = sum(1 for _, l in run_block_lines(lines())
                    if "gate --stage" in l)
        self.assertGreaterEqual(
            captures, gates,
            "there are more gates than captured exit codes — one of them is "
            "gating something it did not capture")

    def test_a_partial_report_is_not_refused_at_revalidation(self):
        # `partial` (exit 4) carries records an approval set can be minted
        # from; its coverage gaps travel into the PR body.
        body = "\n".join(jobs()["revalidate"])
        self.assertIn("--accept-exit-code 4", body)

    def test_a_gate_that_is_not_a_run_blocks_last_command_exits(self):
        # A step's status is its last command's, errexit or not (cf. #107): a
        # `gate` whose refusal is followed by more commands in the same run
        # block must `|| exit`, or a later command masks the first refusal.
        offenders = []
        for block in run_blocks(lines()):
            commands = _logical_commands(block)
            for idx, (lineno, text) in enumerate(commands):
                if "gate --stage" not in text:
                    continue
                is_last = idx == len(commands) - 1
                if not is_last and "|| exit" not in text:
                    offenders.append(f"{lineno}: {text}")
        self.assertEqual(
            offenders, [],
            "a gate's refusal can be masked by a later command in the same "
            "run block — chain it with `|| exit`:\n  " + "\n  ".join(offenders))

    def test_the_report_run_is_bound_to_its_audit_lane(self):
        # `report_run_id` must name a run of *this repo's* doc-audit lane, not
        # any run that happens to publish an `audit-report` artifact. Assert
        # the executable form, not a comment that merely mentions the file:
        # deleting the whole binding step while leaving its surrounding comments
        # must fail this guard. `_logical_commands` strips comment lines, so the
        # query and the comparison below have to survive as real commands.
        commands = [text for block in run_blocks(jobs()["revalidate"])
                    for _, text in _logical_commands(block)]
        self.assertTrue(
            any("gh api" in c and "actions/runs/" in c and ".path" in c
                for c in commands),
            "the revalidate job never queries the dispatched run's workflow "
            "path (`gh api .../actions/runs/... --jq '.path'`) on a real "
            "command line")
        self.assertTrue(
            any(".github/workflows/doc-audit.yml" in c for c in commands),
            "the queried workflow path is never compared against "
            "`.github/workflows/doc-audit.yml` on a non-comment line")

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
