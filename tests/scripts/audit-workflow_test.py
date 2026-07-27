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
import subprocess
import sys
import tempfile
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


class DeclaredEvidenceTools(unittest.TestCase):
    """How this lane reaches Tier-2 tool evidence (aj604/toolshed#118).

    A drift verdict may cite `evidence.command`, but only for a tool the
    report's `evidence_boundary.commands` declares. This lane declares those
    tools from a consumer-owned config through a tested script, under the
    model job's *existing* `Bash(python3 *)` allowance — the grant itself does
    not widen, which is the decision these guards hold in place.
    """

    EXPECTED_GRANT = ('--allowedTools '
                      '"Skill,Read,Grep,Glob,Write,Bash(git *),Bash(python3 *)"')

    def test_the_model_grant_did_not_widen_for_tool_evidence(self):
        # `workflow-permissions_test.py` already refuses any Bash executable
        # beyond git and python3 generically; this pins the audit lane's grant
        # exactly, so even a same-executable widening is a visible diff here.
        grants = [line.strip() for line in lines() if "--allowedTools" in line
                  and not line.strip().startswith("#")]
        self.assertEqual(
            [g for g in grants if g.endswith(self.EXPECTED_GRANT)], grants,
            f"doc-audit.yml's model grant changed — expected it to end "
            f"{self.EXPECTED_GRANT!r}, got {grants}")

    def test_the_boundary_is_rendered_by_the_script_not_hand_written(self):
        text = "\n".join(jobs()["audit"])
        self.assertIn("probe-evidence-tool.py declared --flags", text,
                      "the audit step must render --evidence-command from the "
                      "declared-tools config, so the boundary the report "
                      "publishes and the tools the probe will run are one list")
        hand_written = [line.strip() for line in lines()
                        if "--evidence-command" in line
                        and "probe-evidence-tool.py" not in line
                        and not line.strip().startswith("#")]
        self.assertEqual(
            hand_written, [],
            f"a tool name is hard-coded into the workflow YAML ({hand_written}) "
            f"— declare it in evidence-tools.json instead")

    def test_the_prompt_routes_command_citations_through_the_probe(self):
        prompt = "\n".join(jobs()["audit"])
        self.assertIn("probe-evidence-tool.py declared", prompt,
                      "the model has no other way to learn which tools this "
                      "run declared")
        self.assertIn("probe-evidence-tool.py run", prompt,
                      "the model has no other way to reach a declared tool")
        self.assertNotIn("This lane declares no tools", prompt,
                         "that sentence is now false whenever a consumer "
                         "declares one — the prompt must not assert it")


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


# The more general shape of #107: a step whose comment or later logic treats
# the engine CLI's non-zero exit (1 invalid, 4 partial — see EXIT_CODES in
# doclifecycle/cli.py) as a typed outcome to handle, not a crash — while the
# invocation itself carries no `||` guard. Under the runner's inherited
# `bash -e`, that invocation still aborts the step before the "handling"
# logic runs, no matter how confidently a comment on the `set` line claims
# "no -e" (a claim that is never true here — only `set +e` or an explicit
# `||` clears it). This caught both #107 sites: the drift-audit step (a
# trailing `echo "exit code: $?"`) and the publish job's "Re-validate
# freshness" step (a trailing `[ -s revalidated.json ] && mv ...` that never
# ran when `validate-report` returned its very common non-zero states).
ENGINE_CLI_INVOCATION = re.compile(r"doc-lifecycle\.py")
GUARDED_INVOCATION = re.compile(r"\|\|")
STEP_MARKER = re.compile(r"^\s*-\s*name:\s*(.*)$")
RUN_BLOCK_MARKER = re.compile(r"^\s*run:\s*\|\s*$")


def step_run_blocks():
    """[(job, step name, run-block lines)] for every step with a `run: |` block."""
    found = []
    for job_name, body in jobs().items():
        starts = [i for i, l in enumerate(body) if STEP_MARKER.match(l)]
        starts.append(len(body))
        for si in range(len(starts) - 1):
            step_lines = body[starts[si]:starts[si + 1]]
            step_name = STEP_MARKER.match(step_lines[0]).group(1).strip()
            run_at, run_indent = None, None
            for j, l in enumerate(step_lines):
                if RUN_BLOCK_MARKER.match(l):
                    run_at, run_indent = j, WPT.indent_of(l)
                    break
            if run_at is None:
                continue
            block = []
            for l in step_lines[run_at + 1:]:
                if l.strip() and WPT.indent_of(l) <= run_indent:
                    break
                block.append(l)
            found.append((job_name, step_name, block))
    return found


def logical_statements(block):
    """Merge `\\`-continued shell lines into one statement each; drop blanks
    and full-line comments (which carry no exit code of their own)."""
    statements, buf = [], ""
    for raw in block:
        text = raw.strip()
        if not text or text.startswith("#"):
            continue
        buf = f"{buf} {text}" if buf else text
        if buf.endswith("\\"):
            buf = buf[:-1].rstrip()
            continue
        statements.append(buf)
        buf = ""
    return statements


class NoUnguardedEngineExitBeforeMoreLogic(unittest.TestCase):
    def test_every_engine_cli_call_with_logic_after_it_is_dash_dash_guarded(self):
        offenders = []
        for job_name, step_name, block in step_run_blocks():
            statements = logical_statements(block)
            for i, statement in enumerate(statements):
                if not ENGINE_CLI_INVOCATION.search(statement):
                    continue
                is_last = i == len(statements) - 1
                if is_last:
                    continue  # nothing after it depends on it having "run"
                if GUARDED_INVOCATION.search(statement):
                    continue  # `cmd || code=$?` / `cmd || true` — survives -e
                offenders.append(
                    f"{job_name}/{step_name!r}: {statement}")
        self.assertEqual(
            offenders, [],
            "doc-audit.yml calls the engine CLI, then runs more shell logic "
            "that depends on it having completed, without guarding the "
            "call's exit against the runner's inherited `bash -e` — a "
            "typed non-zero exit (1 invalid, 4 partial) aborts the step "
            "before that later logic runs, no matter what the step's `set` "
            "line comment claims about -e:\n  " + "\n  ".join(offenders))


def freshness_step_script():
    """The literal `run:` body of publish's "Re-validate freshness before
    publishing" step, extracted from the real file — never re-implemented,
    so this test can't silently drift from what the runner actually
    executes."""
    for job_name, step_name, block in step_run_blocks():
        if job_name == "publish" and "Re-validate freshness" in step_name:
            return "\n".join(block)
    return None


class FreshnessRevalidationBehavior(unittest.TestCase):
    """Executes the actual "Re-validate freshness before publishing" step
    script under a real `bash --noprofile --norc -eo pipefail` — the exact
    mode GitHub Actions runs `run:` steps under — against a stubbed
    `doc-lifecycle.py validate-report`. Regression coverage for the
    escalated half of #107: a stale/partial verdict must reach
    drift-report.json rather than being laundered as the original report's
    (possibly clean-looking) status, and an empty/absent revalidated
    payload must not fail the step outright.
    """

    def setUp(self):
        self.script = freshness_step_script()
        self.assertIsNotNone(
            self.script,
            "could not locate the 'Re-validate freshness before "
            "publishing' step in doc-audit.yml — did its name or job "
            "change?")
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.repo = self.tmp.name
        os.makedirs(os.path.join(self.repo, ".github", "doc-sync", "engine"))

    def _stub_validate_report(self, stdout, exit_code):
        stub_path = os.path.join(
            self.repo, ".github", "doc-sync", "engine", "doc-lifecycle.py")
        with open(stub_path, "w", encoding="utf-8") as fh:
            fh.write(
                "#!/usr/bin/env python3\n"
                "import sys\n"
                f"sys.stdout.write({stdout!r})\n"
                f"sys.exit({exit_code})\n"
            )
        os.chmod(stub_path, 0o755)

    def _write_report(self, content):
        with open(os.path.join(self.repo, "drift-report.json"), "w",
                   encoding="utf-8") as fh:
            fh.write(content)

    def _report_content(self):
        with open(os.path.join(self.repo, "drift-report.json"),
                   encoding="utf-8") as fh:
            return fh.read()

    def _run_step(self):
        return subprocess.run(
            ["bash", "--noprofile", "--norc", "-eo", "pipefail", "-c",
             self.script],
            cwd=self.repo, capture_output=True, text=True)

    def test_a_stale_verdict_reaches_the_published_report_not_laundered_as_fresh(self):
        self._write_report('{"status": "clean"}')
        stale_payload = '{"status": "stale", "reasons": ["moved on"]}'
        self._stub_validate_report(stale_payload, 3)  # STATE_STALE
        result = self._run_step()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self._report_content(), stale_payload)

    def test_a_partial_verdict_reaches_the_published_report(self):
        self._write_report('{"status": "clean"}')
        partial_payload = '{"status": "partial", "incomplete": []}'
        self._stub_validate_report(partial_payload, 4)  # STATE_PARTIAL
        result = self._run_step()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self._report_content(), partial_payload)

    def test_an_empty_revalidated_payload_succeeds_with_the_original_report_kept(self):
        original = '{"status": "clean"}'
        self._write_report(original)
        # An uncaught crash: no stdout, and (coincidentally) the same exit
        # code Python's default traceback handler uses — indistinguishable
        # from a deliberate STATE_INVALID exit by code alone, which is
        # exactly why the step must not fail outright on it.
        self._stub_validate_report("", 1)
        result = self._run_step()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self._report_content(), original)

    def test_an_unexpected_exit_code_fails_the_step_loudly(self):
        self._write_report('{"status": "clean"}')
        self._stub_validate_report("", 2)  # argparse usage error — not typed
        result = self._run_step()
        self.assertEqual(result.returncode, 2)

    def test_already_invalid_report_skips_revalidation_entirely(self):
        self._write_report('{"status": "invalid", "problems": []}')
        # No stub configured — the `grep -q "invalid"` branch must never
        # reach validate-report at all.
        result = self._run_step()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(
            self._report_content(), '{"status": "invalid", "problems": []}')


if __name__ == "__main__":
    unittest.main()
