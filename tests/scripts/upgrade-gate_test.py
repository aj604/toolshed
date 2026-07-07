#!/usr/bin/env python3
"""Black-box tests for scheduling-doc-sync's upgrade-gate.py.

Tests the script as a subprocess: real argv, real exit codes, real stdout.
Run: python3 tests/scripts/upgrade-gate_test.py
"""

import os
import subprocess
import sys
import unittest

SCRIPT = os.path.join(
    os.path.dirname(__file__),
    "..", "..",
    "plugins", "doc-lifecycle", "skills", "scheduling-doc-sync",
    "scripts", "upgrade-gate.py",
)


def run(*argv):
    return subprocess.run(
        [sys.executable, SCRIPT, *argv], capture_output=True, text=True
    )


def compare(current, latest):
    return run("compare", "--current", current, "--latest", latest)


class UpgradeGate(unittest.TestCase):
    def test_newer_patch_is_upgrade(self):
        r = compare("0.7.0", "0.7.1")
        self.assertEqual(r.returncode, 0)
        self.assertEqual(r.stdout.strip(), "upgrade")

    def test_newer_minor_is_upgrade(self):
        self.assertEqual(compare("0.7.0", "0.8.0").stdout.strip(), "upgrade")

    def test_newer_major_is_upgrade(self):
        self.assertEqual(compare("0.7.0", "1.0.0").stdout.strip(), "upgrade")

    def test_equal_is_current(self):
        r = compare("0.7.0", "0.7.0")
        self.assertEqual(r.returncode, 0)
        self.assertEqual(r.stdout.strip(), "current")

    def test_installed_newer_is_ahead(self):
        # a dev/prerelease pin past the newest release — never downgrade
        r = compare("0.8.0", "0.7.0")
        self.assertEqual(r.returncode, 0)
        self.assertEqual(r.stdout.strip(), "ahead")

    def test_patch_downgrade_is_ahead(self):
        self.assertEqual(compare("0.7.2", "0.7.1").stdout.strip(), "ahead")

    def test_compare_is_numeric_not_lexical(self):
        # 0.10.0 > 0.9.0 numerically; lexical string compare would say "ahead"
        self.assertEqual(compare("0.9.0", "0.10.0").stdout.strip(), "upgrade")

    def test_v_prefix_is_tolerated_on_either_side(self):
        # the workflow strips v, but be forgiving if a tag slips through
        self.assertEqual(compare("v0.7.0", "v0.7.1").stdout.strip(), "upgrade")

    def test_empty_latest_is_bad_input(self):
        # a repo with no releases yields an empty tagName
        self.assertEqual(compare("0.7.0", "").returncode, 2)

    def test_empty_current_is_bad_input(self):
        self.assertEqual(compare("", "0.7.0").returncode, 2)

    def test_non_numeric_is_bad_input(self):
        self.assertEqual(compare("0.7.0", "latest").returncode, 2)

    def test_short_tuple_is_bad_input(self):
        self.assertEqual(compare("0.7", "0.7.0").returncode, 2)

    def test_extra_component_is_bad_input(self):
        self.assertEqual(compare("0.7.0.1", "0.7.0").returncode, 2)


if __name__ == "__main__":
    unittest.main(verbosity=2)
