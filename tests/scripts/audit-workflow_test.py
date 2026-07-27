#!/usr/bin/env python3
"""Static guards for doc-audit.yml (aj604/toolshed#71) beyond what the generic
suites already cover.

`workflow-permissions_test.py` and `marketplace-pin_test.py` glob over every
`plugins/doc-lifecycle/skills/scheduling-doc-sync/*.yml`, so doc-audit.yml
already inherits: model-job read-only-and-credential-free, workflow-level
permissions grant no write, write jobs run no model and never `git add -A`,
and the marketplace pin is a `.git`-suffixed URL or a local checkout path.
This suite covers what is new to this lane and specific to its acceptance
criteria (issue #71):

1. Every third-party action `doc-audit.yml` invokes is pinned to an immutable
   40-hex-character commit SHA, not a floating tag or branch — a stricter bar
   than the legacy templates (doc-sync.yml, doc-bloat.yml,
   doc-sync-upgrade.yml) currently meet; this suite is scoped to the new file
   on purpose; retrofitting the legacy templates is a separate concern.
2. No job in this workflow ever runs `git commit` or `git push` — unlike
   doc-sync.yml's marker-only commit, this lane makes no direct commit to any
   branch at all, default or otherwise.
3. The job shape the acceptance criteria describe: exactly `audit` (the
   model, read-only) and `publish` (no model, and — today — no write scope at
   all: `contents: read` only, since a job summary needs none; it stays its
   own job so any write this lane later needs to publish more than that lands
   there, never beside the model, and never `contents: write`).
4. Concurrency is declared, and both artifact uploads run unconditionally
   (`if: always()`) — a failed audit still leaves an artifact to publish
   against, per the report contract's own "never a misleading empty report".

There is deliberately no template/dogfood equivalence test for this file yet:
this ticket lands the template only (no `.doc-lifecycle/registry.json` exists
in this repository to run it against), and the dogfood install — including
its equivalence test, alongside doc-sync.yml/doc-bloat.yml's existing ones in
install-parity_test.py — is aj604/toolshed#75's job, which is blocked on this
one.

Parsed with the same line-scanner approach as workflow-permissions_test.py
(stdlib only, 2-space indented YAML); its helpers are reused here rather than
re-implemented, via the same load-by-path trick install-parity_test.py uses
for apply-upgrade.py's hyphenated module name.

Run: python3 tests/scripts/audit-workflow_test.py
"""

import importlib.util
import os
import re
import sys
import unittest

ROOT = os.path.join(os.path.dirname(__file__), "..", "..")
WORKFLOW = os.path.join(
    ROOT, "plugins", "doc-lifecycle", "skills", "scheduling-doc-sync",
    "doc-audit.yml",
)

USES_LINE = re.compile(r"uses:\s*([^\s#]+)")
SHA_PINNED = re.compile(r"^[^@]+@[0-9a-f]{40}$")
GIT_WRITE = re.compile(r"\bgit\s+(commit|push)\b")


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


class FileExists(unittest.TestCase):
    def test_template_exists(self):
        self.assertTrue(
            os.path.isfile(WORKFLOW),
            "doc-audit.yml is missing — did the scheduling-doc-sync layout move?")


class ThirdPartyActionsAreShaPinned(unittest.TestCase):
    def test_every_uses_line_pins_a_commit_sha(self):
        offenders = []
        for lineno, line in enumerate(lines(), 1):
            m = USES_LINE.search(line)
            if not m:
                continue
            value = m.group(1).strip().strip("'\"")
            if not SHA_PINNED.match(value):
                offenders.append(f"{lineno}: uses: {value}")
        self.assertEqual(
            offenders, [],
            "doc-audit.yml has action reference(s) not pinned to an immutable "
            "commit SHA:\n  " + "\n  ".join(offenders))

    def test_some_actions_are_actually_checked(self):
        found = [line for line in lines() if USES_LINE.search(line)]
        self.assertTrue(found, "no `uses:` lines found — did the file move?")


class NoDirectBranchCommits(unittest.TestCase):
    def test_no_git_commit_or_push_anywhere(self):
        offenders = [f"{i}: {line.strip()}" for i, line in enumerate(lines(), 1)
                     if GIT_WRITE.search(line) and not line.strip().startswith("#")]
        self.assertEqual(
            offenders, [],
            "doc-audit.yml commits or pushes directly — this lane publishes "
            "only a report artifact and a job summary:\n  "
            + "\n  ".join(offenders))


class JobShape(unittest.TestCase):
    def test_exactly_audit_and_publish_jobs(self):
        self.assertEqual(set(jobs()), {"audit", "publish"})

    def test_publish_holds_no_write_scope_at_all(self):
        # This lane needs no GitHub write to publish a job summary — `publish`
        # exists as its own job so the moment one *is* needed, it lands here,
        # never beside the model. Today that means exactly contents: read.
        body = jobs()["publish"]
        perms = WPT.mapping_under(body, "permissions", 4)
        self.assertIsNotNone(perms, "publish job declares no permissions block")
        self.assertEqual(perms, {"contents": "read"})
        self.assertEqual(WPT.write_scopes(perms), {})

    def test_publish_needs_audit(self):
        body = jobs()["publish"]
        needs_lines = [l for l in body if l.strip().startswith("needs:")]
        self.assertTrue(needs_lines, "publish job does not declare `needs:`")
        self.assertIn("audit", needs_lines[0])

    def test_audit_job_calls_the_engines_public_cli(self):
        body = jobs()["audit"]
        text = "\n".join(body)
        self.assertIn("drift-plan", text)
        self.assertIn("drift-audit", text)

    def test_publish_job_never_invokes_a_model(self):
        body = jobs()["publish"]
        self.assertFalse(
            any(WPT.MODEL_ACTION in line for line in body),
            "publish job holds a write scope and must never run a model")


class ConcurrencyAndFailureSurface(unittest.TestCase):
    def test_concurrency_group_declared_without_cancellation(self):
        text = "\n".join(lines())
        self.assertIn("concurrency:", text)
        self.assertIn("cancel-in-progress: false", text)

    def test_artifact_uploads_run_unconditionally(self):
        body = jobs()["audit"]
        upload_indices = [i for i, l in enumerate(body)
                           if "actions/upload-artifact@" in l]
        self.assertTrue(upload_indices, "no artifact upload steps found")
        for i in upload_indices:
            # The `if: always()` guard sits on the step, a few lines above
            # `uses:` (between the step's `- name:` and its `uses:`).
            window = body[max(0, i - 4):i]
            self.assertTrue(
                any("if: always()" in l for l in window),
                f"artifact upload near line {i} does not run unconditionally "
                f"(if: always()) — a failed audit must still publish what it "
                f"has")


class RenderScriptWired(unittest.TestCase):
    def test_publish_job_renders_through_the_tested_script(self):
        body = jobs()["publish"]
        text = "\n".join(body)
        self.assertIn("render-audit-summary.py", text)
        self.assertNotIn("GITHUB_STEP_SUMMARY\" <<", text)  # no inline heredoc templating


# GitHub Actions invokes `run:` steps under `bash -e` (or `bash -eo pipefail`
# once a step declares a bash shell); `set -uo pipefail` does not clear that
# inherited `-e`. A bare `$?` read on its own line therefore only ever runs
# after the *previous* command already succeeded — any nonzero exit, expected
# typed state or not, aborts the step first and leaves the `$?` read
# unreachable dead code (issue #107). The only shape that survives `-e` is
# capturing the code inline with `||`, e.g. `cmd || code=$?`.
CAPTURED_EXIT_CODE = re.compile(r"\|\|\s*[A-Za-z_][A-Za-z0-9_]*=\$\?")
BARE_EXIT_CODE_READ = re.compile(r"\$\?")


class NoDeadExitCodeReads(unittest.TestCase):
    def test_no_bare_dollar_question_after_a_command_dash_e_would_abort_on(self):
        offenders = []
        for lineno, line in enumerate(lines(), 1):
            if line.strip().startswith("#"):
                continue  # commentary, not a shell statement
            if not BARE_EXIT_CODE_READ.search(line):
                continue
            if CAPTURED_EXIT_CODE.search(line):
                continue  # `cmd || code=$?` — survives -e, not dead code
            offenders.append(f"{lineno}: {line.strip()}")
        self.assertEqual(
            offenders, [],
            "doc-audit.yml reads $? somewhere other than a `|| var=$?` "
            "capture — under the runner's inherited `bash -e`, a nonzero "
            "exit from the preceding command aborts the step before this "
            "line runs, making the read unreachable dead code:\n  "
            + "\n  ".join(offenders))


if __name__ == "__main__":
    unittest.main()
