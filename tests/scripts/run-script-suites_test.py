#!/usr/bin/env python3
"""Black-box tests for run-script-suites.py (aj604/toolshed#99). See that
script's docstring for what it does and why.

Every test here passes an explicit `--dir` pointing at a throwaway fixture
directory. Never the real `tests/scripts/` (the default): this test file lives
*inside* that directory, so the real runner (run when CI invokes it with no
`--dir`) will glob this very file up and execute it — invoking the real
default dir from within one of this file's own tests would recurse.

Run: python3 tests/scripts/run-script-suites_test.py
"""

import os
import subprocess
import sys
import tempfile
import unittest

SCRIPT = os.path.join(
    os.path.dirname(__file__), "..", "..",
    ".github", "scripts", "run-script-suites.py",
)


def run(scripts_dir):
    return subprocess.run(
        [sys.executable, SCRIPT, "--dir", scripts_dir],
        capture_output=True, text=True,
    )


def write_suite(dir_path, name, exit_code):
    path = os.path.join(dir_path, name)
    with open(path, "w", encoding="utf-8") as f:
        f.write(f"import sys\nsys.exit({exit_code})\n")
    return path


class EmptyDirectoryRefusal(unittest.TestCase):
    def test_no_suites_found_is_a_loud_failure(self):
        with tempfile.TemporaryDirectory() as tmp:
            result = run(tmp)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("no", result.stderr.lower())
        self.assertIn("_test.py", result.stderr)

    def test_dir_with_only_non_matching_files_is_still_empty(self):
        with tempfile.TemporaryDirectory() as tmp:
            write_suite(tmp, "helper.py", 0)  # doesn't end in _test.py
            result = run(tmp)
        self.assertNotEqual(result.returncode, 0)


class AllSuitesPass(unittest.TestCase):
    def test_exit_zero_when_every_suite_passes(self):
        with tempfile.TemporaryDirectory() as tmp:
            write_suite(tmp, "alpha_test.py", 0)
            write_suite(tmp, "beta_test.py", 0)
            result = run(tmp)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("2/2", result.stdout)


class AnySuiteFails(unittest.TestCase):
    def test_exit_nonzero_when_one_suite_fails(self):
        with tempfile.TemporaryDirectory() as tmp:
            write_suite(tmp, "alpha_test.py", 0)
            write_suite(tmp, "beta_test.py", 1)
            result = run(tmp)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("beta_test.py", result.stdout + result.stderr)

    def test_one_failure_does_not_stop_the_rest_from_running(self):
        with tempfile.TemporaryDirectory() as tmp:
            write_suite(tmp, "alpha_test.py", 1)
            write_suite(tmp, "beta_test.py", 0)
            write_suite(tmp, "gamma_test.py", 0)
            result = run(tmp)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("beta_test.py", result.stdout)
        self.assertIn("gamma_test.py", result.stdout)
        self.assertIn("2/3", result.stdout)


class Discovery(unittest.TestCase):
    def test_only_globs_test_suffixed_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            write_suite(tmp, "alpha_test.py", 0)
            # Would fail the run if the glob picked it up.
            write_suite(tmp, "not_a_suite.py", 1)
            result = run(tmp)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("1/1", result.stdout)


if __name__ == "__main__":
    unittest.main()
