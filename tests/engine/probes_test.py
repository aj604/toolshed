#!/usr/bin/env python3
"""Public-seam tests for the closed deterministic probe vocabulary."""

import hashlib
import json
import os
import subprocess
import sys
import time
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from support import RepoTestCase  # noqa: E402
from doclifecycle.paths import RepositoryReadHandle  # noqa: E402
from doclifecycle.probes import execute_probe  # noqa: E402


def digest(text):
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


class ProbeVocabulary(RepoTestCase):
    def repo_with(self, files):
        repo = self.repo(files)
        return repo

    def dep(self, path, text):
        return [{"path": path, "digest": digest(text)}]

    def test_all_file_probe_kinds_record_observations_and_dependency_digests(self):
        source = "class App:\n    def run(self):\n        return True\n"
        config = '{"service":{"enabled":true}}\n'
        repo = self.repo_with({
            "src/app.py": source,
            "config.json": config,
        })
        cases = (
            ({"kind": "path_exists", "args": {"path": "src/app.py", "kind": "file"}, "expect": {}},
             self.dep("src/app.py", source), "resolved_paths"),
            ({"kind": "content_match", "args": {"path": "src/app.py", "pattern": "return True"},
              "expect": {"presence": "present", "count": 1}},
             self.dep("src/app.py", source), "matched_text"),
            ({"kind": "json_value", "args": {"path": "config.json", "pointer": "/service/enabled"},
              "expect": {"equals": True}}, self.dep("config.json", config), "value"),
            ({"kind": "symbol_defined", "args": {
                "path": "src/app.py", "language": "python", "name": "App.run"},
              "expect": {}}, self.dep("src/app.py", source), "defined"),
        )
        for probe, deps, evidence_key in cases:
            with self.subTest(kind=probe["kind"]):
                outcome = execute_probe(repo, probe, deps)
                self.assertTrue(outcome.passed, outcome)
                self.assertIsNone(outcome.problem)
                self.assertIn(evidence_key, outcome.observed)
                self.assertEqual(outcome.observed["dependencies"], [{
                    "path": deps[0]["path"], "digest": deps[0]["digest"],
                }])

    def test_unknown_malformed_boundary_and_command_paths_refuse_before_reads(self):
        repo = self.repo_with({"safe.txt": "safe\n"})
        deps = self.dep("safe.txt", "safe\n")
        cases = (
            ({"kind": "shell", "args": {}, "expect": {}}, "probe-unknown-kind"),
            ({"kind": "content_match", "args": {}, "expect": {}}, "probe-malformed-args"),
            ({"kind": "path_exists", "args": {"glob": "[", "kind": "file"},
              "expect": {}}, "probe-malformed-args"),
            ({"kind": "content_match", "args": {"path": "other.txt", "pattern": "x"},
              "expect": {"presence": "present"}}, "probe-path-outside-boundary"),
            ({"kind": "content_match", "args": {"path": "safe.txt;echo", "pattern": "x"},
              "expect": {"presence": "present"}}, "probe-command-shaped-path"),
        )
        for probe, code in cases:
            with self.subTest(code=code), mock.patch.object(
                    RepositoryReadHandle, "read_bytes",
                    side_effect=AssertionError("unsafe probe executed")):
                outcome = execute_probe(repo, probe, deps)
                self.assertEqual(outcome.problem.code, code)

    def test_symlink_escape_refuses_before_content_read(self):
        outside = self.repo_with({"secret.txt": "secret\n"})
        repo = self.repo_with({"safe.txt": "safe\n"})
        os.symlink(os.path.join(outside, "secret.txt"), os.path.join(repo, "alias.txt"))
        probe = {
            "kind": "content_match",
            "args": {"path": "alias.txt", "pattern": "secret"},
            "expect": {"presence": "present"},
        }
        deps = [{"path": "alias.txt", "digest": digest("secret\n")}]

        with mock.patch.object(
                RepositoryReadHandle, "read_bytes",
                side_effect=AssertionError("symlink was followed")):
            outcome = execute_probe(repo, probe, deps)

        self.assertEqual(outcome.problem.code, "probe-symlink-escape")

    def test_path_swap_after_authorization_cannot_redirect_bytes_or_digest(self):
        original = "trusted evidence\n"
        outside = self.repo_with({"outside.txt": "hostile evidence\n"})
        repo = self.repo_with({"source.txt": original})
        probe = {
            "kind": "content_match",
            "args": {"path": "source.txt", "pattern": "trusted evidence"},
            "expect": {"presence": "present"},
        }
        real_read = RepositoryReadHandle.read_bytes
        swapped = False

        def swap_then_read(handle, limit=None):
            nonlocal swapped
            if not swapped:
                swapped = True
                os.rename(
                    os.path.join(repo, "source.txt"),
                    os.path.join(repo, "authorized-inode.txt"),
                )
                os.symlink(
                    os.path.join(outside, "outside.txt"),
                    os.path.join(repo, "source.txt"),
                )
            return real_read(handle, limit=limit)

        with mock.patch.object(
                RepositoryReadHandle, "read_bytes", new=swap_then_read):
            outcome = execute_probe(repo, probe, self.dep("source.txt", original))

        self.assertTrue(outcome.passed, outcome)
        self.assertEqual(outcome.observed["matched_text"], ["trusted evidence"])
        self.assertEqual(
            outcome.observed["dependencies"][0]["digest"], digest(original)
        )
        self.assertTrue(os.path.islink(os.path.join(repo, "source.txt")))

    def test_backtracking_regex_is_refused_before_read_in_constant_time(self):
        text = "a" * 30 + "!"
        repo = self.repo_with({"source.txt": text})
        patterns = (
            "(a+)+$",
            "(a|a)" * 30 + "b",
        )
        for pattern in patterns:
            with self.subTest(pattern=pattern):
                probe = {
                    "kind": "content_match",
                    "args": {"path": "source.txt", "pattern": pattern},
                    "expect": {"presence": "present"},
                }
                started = time.monotonic()
                with mock.patch.object(
                        RepositoryReadHandle, "read_bytes",
                        side_effect=AssertionError(
                            "unsafe regex reached content")):
                    outcome = execute_probe(
                        repo, probe, self.dep("source.txt", text)
                    )

                self.assertLess(time.monotonic() - started, 0.1)
                self.assertEqual(outcome.problem.code, "probe-malformed-args")

    @mock.patch("doclifecycle.probes.subprocess.run")
    def test_backtracking_tool_regex_is_refused_before_tool_execution(self, run):
        tools = '{"tools":["fake"]}\n'
        repo = self.repo_with({".doc-lifecycle/evidence-tools.json": tools})
        probe = {
            "kind": "tool_probe",
            "args": {"tool": "fake", "flag": "--version",
                     "pattern": "(a+)+$"},
            "expect": {},
        }

        outcome = execute_probe(
            repo, probe,
            self.dep(".doc-lifecycle/evidence-tools.json", tools),
        )

        self.assertEqual(outcome.problem.code, "probe-malformed-args")
        run.assert_not_called()

    def test_json_pointer_equality_is_strict_and_decodes_escaped_tokens(self):
        text = '{"a/b":{"~key":[1,true]}}\n'
        repo = self.repo_with({"value.json": text})
        deps = self.dep("value.json", text)

        number = execute_probe(repo, {
            "kind": "json_value",
            "args": {"path": "value.json", "pointer": "/a~1b/~0key/0"},
            "expect": {"equals": 1},
        }, deps)
        wrong_type = execute_probe(repo, {
            "kind": "json_value",
            "args": {"path": "value.json", "pointer": "/a~1b/~0key/0"},
            "expect": {"equals": True},
        }, deps)
        boolean = execute_probe(repo, {
            "kind": "json_value",
            "args": {"path": "value.json", "pointer": "/a~1b/~0key/1"},
            "expect": {"equals": True},
        }, deps)

        self.assertTrue(number.passed)
        self.assertFalse(wrong_type.passed)
        self.assertTrue(boolean.passed)

    def test_json_expected_value_is_validated_before_read(self):
        text = "{}\n"
        repo = self.repo_with({"value.json": text})
        probe = {
            "kind": "json_value",
            "args": {"path": "value.json", "pointer": ""},
            "expect": {"equals": ("not", "JSON")},
        }

        with mock.patch.object(
                RepositoryReadHandle, "read_bytes",
                side_effect=AssertionError("invalid expectation reached content")):
            outcome = execute_probe(repo, probe, self.dep("value.json", text))

        self.assertEqual(outcome.problem.code, "probe-malformed-args")

    @mock.patch("doclifecycle.probes.shutil.which", return_value="/usr/bin/fake")
    @mock.patch("doclifecycle.probes.subprocess.run")
    def test_tool_probe_is_declared_help_or_version_scrubbed_and_versioned(self,
                                                                          run, _which):
        tools = '{"tools":["fake"]}\n'
        repo = self.repo_with({".doc-lifecycle/evidence-tools.json": tools})
        deps = self.dep(".doc-lifecycle/evidence-tools.json", tools)
        run.side_effect = (
            subprocess.CompletedProcess([], 0, "usage: fake --safe\n", ""),
            subprocess.CompletedProcess([], 0, "fake 1.2.3\n", ""),
        )
        probe = {
            "kind": "tool_probe",
            "args": {"tool": "fake", "flag": "--help", "pattern": "--safe"},
            "expect": {},
        }

        with mock.patch.dict(os.environ, {"GH_TOKEN": "secret", "SAFE": "also hidden"}):
            outcome = execute_probe(repo, probe, deps)

        self.assertTrue(outcome.passed)
        self.assertEqual(outcome.observed["version"], "fake 1.2.3")
        self.assertEqual([call.args[0] for call in run.call_args_list], [
            ["/usr/bin/fake", "--help"], ["/usr/bin/fake", "--version"],
        ])
        for call in run.call_args_list:
            self.assertFalse(call.kwargs["shell"])
            self.assertNotIn("GH_TOKEN", call.kwargs["env"])
            self.assertNotIn("SAFE", call.kwargs["env"])

    @mock.patch("doclifecycle.probes.subprocess.run")
    def test_undeclared_tool_never_executes(self, run):
        tools = '{"tools":[]}\n'
        repo = self.repo_with({".doc-lifecycle/evidence-tools.json": tools})
        outcome = execute_probe(repo, {
            "kind": "tool_probe",
            "args": {"tool": "fake", "flag": "--version", "pattern": "fake"},
            "expect": {},
        }, self.dep(".doc-lifecycle/evidence-tools.json", tools))

        self.assertEqual(outcome.problem.code, "probe-tool-not-declared")
        run.assert_not_called()


if __name__ == "__main__":
    unittest.main(verbosity=2)
