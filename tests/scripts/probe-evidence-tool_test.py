#!/usr/bin/env python3
"""Black-box tests for scheduling-doc-sync's probe-evidence-tool.py.

The audit lane's model job may cite `evidence.command` (aj604/toolshed#115),
but only for a tool the run declared. This script is how the lane declares and
reaches those tools without widening the model job's `--allowedTools` at all:
it runs under the existing `Bash(python3 *)` allowance, reads the declared
executables out of a consumer-owned config, and will run each one only as a
`--help`/`--version` read.

Tested as a subprocess against configs built in tempdirs, plus one direct
import for the environment scrub (a seam with no observable subprocess
surface). `python3` stands in as the declared tool throughout — a real
executable every runner has, so the honest path is exercised for real rather
than against a stub.

Run: python3 tests/scripts/probe-evidence-tool_test.py
"""

import importlib.util
import json
import os
import subprocess
import sys
import tempfile
import unittest

SCRIPT = os.path.join(
    os.path.dirname(__file__),
    "..", "..",
    "plugins", "doc-lifecycle", "skills", "scheduling-doc-sync",
    "scripts", "probe-evidence-tool.py",
)

CONFIG_RELPATH = os.path.join(".github", "doc-sync", "evidence-tools.json")


def run(*args, cwd=None, path=None):
    env = dict(os.environ)
    if path is not None:
        env["PATH"] = path + os.pathsep + env.get("PATH", "")
    return subprocess.run([sys.executable, SCRIPT, *args],
                          capture_output=True, text=True, cwd=cwd, env=env)


def install_fake_tool(root, name, body):
    """A real executable on PATH, so the probe's exec path is exercised."""
    bindir = os.path.join(root, "bin")
    os.makedirs(bindir, exist_ok=True)
    path = os.path.join(bindir, name)
    with open(path, "w", encoding="utf-8") as f:
        f.write(body)
    os.chmod(path, 0o755)
    return bindir


def load_module():
    sys.dont_write_bytecode = True
    spec = importlib.util.spec_from_file_location("probe_evidence_tool", SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def declare(root, tools):
    """Write a consumer's evidence-tools.json into an install tree."""
    path = os.path.join(root, CONFIG_RELPATH)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump({"tools": tools}, f)
    return path


class DeclaredTools(unittest.TestCase):
    def test_lists_the_declared_executables_one_per_line(self):
        with tempfile.TemporaryDirectory() as root:
            declare(root, ["gh", "python3"])
            r = run("declared", cwd=root)
            self.assertEqual(r.returncode, 0, r.stderr)
            self.assertEqual(r.stdout.split(), ["gh", "python3"])

    def test_flags_render_the_engine_arguments_for_exactly_those_tools(self):
        with tempfile.TemporaryDirectory() as root:
            declare(root, ["gh", "python3"])
            r = run("declared", "--flags", cwd=root)
            self.assertEqual(r.returncode, 0, r.stderr)
            self.assertEqual(
                r.stdout.split(),
                ["--evidence-command", "gh", "--evidence-command", "python3"])

    def test_an_absent_config_is_a_tool_free_lane_not_an_error(self):
        # A consumer who never declared a tool gets the tool-free lane by
        # default, and the workflow's `$(... declared --flags)` must render to
        # nothing rather than fail the audit step.
        with tempfile.TemporaryDirectory() as root:
            r = run("declared", "--flags", cwd=root)
            self.assertEqual(r.returncode, 0, r.stderr)
            self.assertEqual(r.stdout.strip(), "")

    def test_a_malformed_config_fails_loudly_and_declares_nothing(self):
        with tempfile.TemporaryDirectory() as root:
            path = os.path.join(root, CONFIG_RELPATH)
            os.makedirs(os.path.dirname(path), exist_ok=True)
            with open(path, "w", encoding="utf-8") as f:
                f.write("{not json")
            r = run("declared", cwd=root)
            self.assertEqual(r.returncode, 1)
            self.assertEqual(r.stdout.strip(), "")
            self.assertIn("evidence-tools.json", r.stderr)

    def test_a_tool_name_that_is_not_a_bare_executable_is_refused(self):
        # The engine's own boundary check (report.py's EXECUTABLE_NAME) would
        # refuse it later; refusing here names the config that is wrong.
        with tempfile.TemporaryDirectory() as root:
            declare(root, ["gh pr list"])
            r = run("declared", cwd=root)
            self.assertEqual(r.returncode, 1)
            self.assertIn("bare executable name", r.stderr)


class ProbeInvocation(unittest.TestCase):
    def test_a_declared_tool_runs_and_prints_the_citation_a_reader_reruns(self):
        with tempfile.TemporaryDirectory() as root:
            declare(root, ["python3"])
            r = run("run", "python3", "--version", cwd=root)
            self.assertEqual(r.returncode, 0, r.stderr)
            self.assertIn("citation: python3 --version", r.stdout)
            # The tool's own output is what settles the claim.
            self.assertIn("Python 3", r.stdout)
            # The citation names the tool, never this wrapper: `python3
            # probe-evidence-tool.py ...` is not what a reader re-runs, and its
            # first token is not what the evidence boundary declares.
            self.assertNotIn("probe-evidence-tool.py", r.stdout)

    def test_the_citation_carries_the_subcommand_words(self):
        with tempfile.TemporaryDirectory() as root:
            declare(root, ["faketool"])
            bindir = install_fake_tool(
                root, "faketool",
                '#!/bin/sh\necho "usage for: $*"\n')
            r = run("run", "faketool", "pr", "list", "--help",
                    cwd=root, path=bindir)
            self.assertEqual(r.returncode, 0, r.stderr)
            self.assertIn("citation: faketool pr list --help", r.stdout)
            self.assertIn("usage for: pr list --help", r.stdout)

    def test_an_undeclared_tool_is_refused(self):
        with tempfile.TemporaryDirectory() as root:
            declare(root, ["python3"])
            r = run("run", "git", "--version", cwd=root)
            self.assertEqual(r.returncode, 2)
            self.assertIn("tool-not-declared", r.stderr)

    def test_a_tool_is_refused_when_nothing_is_declared_at_all(self):
        with tempfile.TemporaryDirectory() as root:
            r = run("run", "python3", "--version", cwd=root)
            self.assertEqual(r.returncode, 2)
            self.assertIn("tool-not-declared", r.stderr)

    def test_an_invocation_that_is_not_a_help_or_version_read_is_refused(self):
        with tempfile.TemporaryDirectory() as root:
            declare(root, ["git"])
            for argv in (["run", "git", "log"],
                         ["run", "git", "log", "--oneline"],
                         ["run", "git", "status", "--porcelain"],
                         ["run", "git"]):
                with self.subTest(argv=argv):
                    r = run(*argv, cwd=root)
                    self.assertEqual(r.returncode, 2, r.stdout)
                    self.assertIn("not-a-probe-invocation", r.stderr)

    def test_a_subcommand_word_carrying_shell_syntax_is_refused(self):
        with tempfile.TemporaryDirectory() as root:
            declare(root, ["git"])
            for word in ("log;rm", "$(id)", "../../bin/sh", "-x"):
                with self.subTest(word=word):
                    r = run("run", "git", word, "--help", cwd=root)
                    self.assertEqual(r.returncode, 2, r.stdout)
                    self.assertIn("not-a-probe-invocation", r.stderr)

    def test_a_declared_tool_that_is_not_installed_is_named_not_guessed(self):
        with tempfile.TemporaryDirectory() as root:
            declare(root, ["definitely-not-installed-xyz"])
            r = run("run", "definitely-not-installed-xyz", "--version", cwd=root)
            self.assertEqual(r.returncode, 1)
            self.assertIn("tool-not-installed", r.stderr)

    def test_a_probe_the_tool_itself_rejects_is_reported_not_cited(self):
        # `python3 --versionn` is not a read the tool answers; the probe must
        # not hand back a citation for output that settles nothing.
        with tempfile.TemporaryDirectory() as root:
            declare(root, ["python3"])
            r = run("run", "python3", "nosuchsubcommand", "--help", cwd=root)
            self.assertEqual(r.returncode, 1)
            self.assertNotIn("citation:", r.stdout)
            self.assertIn("probe-failed", r.stderr)


class CredentialScrub(unittest.TestCase):
    """The one place this lane executes an external program.

    The model job is asserted token-free (`workflow-permissions_test.py`), so
    this is belt-and-braces rather than the boundary — but the whole reason
    this script exists instead of a wider `--allowedTools` is that what it can
    reach is enumerable, and "with no credential in its environment" is part of
    that enumeration.
    """

    def test_credential_shaped_variables_never_reach_the_probed_tool(self):
        mod = load_module()
        scrubbed = mod.probe_env({
            "PATH": "/usr/bin",
            "HOME": "/home/runner",
            "GH_TOKEN": "ghp_secret",
            "GITHUB_TOKEN": "ghs_secret",
            "ANTHROPIC_API_KEY": "sk-secret",
            "MY_SECRET": "s",
            "DB_PASSWORD": "p",
        })
        self.assertEqual(scrubbed.get("PATH"), "/usr/bin")
        self.assertEqual(scrubbed.get("HOME"), "/home/runner")
        for name in ("GH_TOKEN", "GITHUB_TOKEN", "ANTHROPIC_API_KEY",
                     "MY_SECRET", "DB_PASSWORD"):
            self.assertNotIn(name, scrubbed)


if __name__ == "__main__":
    unittest.main(verbosity=2)
