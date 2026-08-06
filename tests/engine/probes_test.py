#!/usr/bin/env python3
"""Public-seam tests for the closed deterministic probe vocabulary."""

import hashlib
import json
import os
import subprocess
import sys
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from support import RepoTestCase  # noqa: E402
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
            with self.subTest(code=code), mock.patch(
                    "doclifecycle.probes._file_bytes",
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

        with mock.patch("doclifecycle.probes._file_bytes",
                        side_effect=AssertionError("symlink was followed")):
            outcome = execute_probe(repo, probe, deps)

        self.assertEqual(outcome.problem.code, "probe-symlink-escape")

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
