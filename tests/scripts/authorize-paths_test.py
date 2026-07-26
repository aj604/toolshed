#!/usr/bin/env python3
"""Black-box tests for scheduling-doc-sync's authorize-paths.py.

Tests the script as a subprocess against fixtures built in tempdirs. Covers
per-lane derivation from a report (drift STALE locations, prune docs +
extract targets, distill docs/policy files/merge targets/decision log), the
refusals that make the derived set an authority (wiring paths, repo escapes,
non-documentation files), exact vs scope mode, the workflow-state flag, and
reading an edit set out of real git patches.

Run: python3 tests/scripts/authorize-paths_test.py
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
    "scripts", "authorize-paths.py",
)

GIT_ENV = {**os.environ,
           "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@t",
           "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@t"}


def run(*args, cwd=None):
    return subprocess.run([sys.executable, SCRIPT, *args],
                          capture_output=True, text=True, cwd=cwd, env=GIT_ENV)


def write(root, relpath, text):
    full = os.path.join(root, relpath)
    os.makedirs(os.path.dirname(full), exist_ok=True)
    with open(full, "w", encoding="utf-8") as f:
        f.write(text)
    return full


def drift_record(location, verdict="STALE"):
    return {"claim": "c", "location": location, "kind": "path", "tier": 1,
            "verdict": verdict, "evidence": "e",
            "fix": "f" if verdict == "STALE" else None}


def bloat_record(rid, verdict, doc, location=None, proposal=None,
                 status=None, files=None):
    return {"id": rid, "doc": doc, "location": location, "verdict": verdict,
            "evidence": "e", "proposal": proposal, "status": status,
            "files": files}


def report(root, records, name="report.json"):
    return write(root, name, json.dumps({"schema": 2, "records": records}))


def expected(root, records, lane, config=None, out="expected.json"):
    """Run `expected`; return (proc, parsed-out-or-None)."""
    args = ["expected", "--report", report(root, records),
            "--lane", lane, "--out", os.path.join(root, out)]
    if config is not None:
        args += ["--config", write(root, "scope.json", json.dumps(config))]
    proc = run(*args, cwd=root)
    path = os.path.join(root, out)
    data = None
    if os.path.exists(path):
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
    return proc, data


def authority(root, paths, mode="exact", scope=None, name="expected.json"):
    """Write an authority file directly, for check-side tests."""
    return write(root, name, json.dumps(
        {"lane": "drift", "mode": mode, "paths": paths,
         "scope": scope or {"exclude": [], "include": []}}))


def check(root, auth, *args):
    return run("check", "--expected", auth, *args, cwd=root)


class Derivation(unittest.TestCase):
    def test_drift_takes_stale_locations_only(self):
        with tempfile.TemporaryDirectory() as root:
            proc, data = expected(root, [
                drift_record("README.md:3"),
                drift_record("docs/guides/a.md:12"),
                drift_record("README.md:40"),
                drift_record("CLAUDE.md:1", "VERIFIED"),
                drift_record("NOTES.md:2", "UNVERIFIABLE"),
            ], "drift")
            self.assertEqual(proc.returncode, 0, proc.stderr)
            self.assertEqual(data["paths"], ["README.md", "docs/guides/a.md"])
            self.assertEqual(data["mode"], "exact")

    def test_prune_takes_docs_and_extract_targets(self):
        with tempfile.TemporaryDirectory() as root:
            proc, data = expected(root, [
                bloat_record("B1", "CUT", "docs/a.md", location="docs/a.md:4"),
                bloat_record("B2", "EXTRACT-AND-MOVE", "docs/a.md",
                             location="docs/a.md:9",
                             proposal={"target": "docs/reference/b.md",
                                       "text": "t"}),
                # distill-lane records are another lane's authority, not this one
                bloat_record("B3", "RETIRE-DOC", "docs/plans/old.md"),
            ], "prune")
            self.assertEqual(proc.returncode, 0, proc.stderr)
            self.assertEqual(data["paths"],
                             ["docs/a.md", "docs/reference/b.md"])
            self.assertEqual(data["mode"], "exact")

    def test_distill_takes_docs_targets_policy_files_and_the_decision_log(self):
        with tempfile.TemporaryDirectory() as root:
            proc, data = expected(root, [
                bloat_record("B1", "DISTILL", "docs/plans/p.md",
                             status="ready"),
                bloat_record("B2", "DISTILL", "docs/plans/later.md",
                             status="pending-implementation"),
                bloat_record("B3", "MERGE-DOC", "docs/x.md",
                             proposal={"target": "docs/y.md"}),
                bloat_record("B4", "POLICY", "docs/superpowers",
                             proposal="retire", files=["docs/superpowers/a.md",
                                                       "docs/superpowers/b.md"]),
                bloat_record("B5", "CUT", "docs/a.md", location="docs/a.md:4"),
            ], "distill")
            self.assertEqual(proc.returncode, 0, proc.stderr)
            self.assertEqual(data["paths"], [
                "docs/decisions.md",
                "docs/plans/p.md",
                "docs/superpowers/a.md",
                "docs/superpowers/b.md",
                "docs/x.md",
                "docs/y.md",
            ])
            # The distiller picks where residue lands, so the lane authorizes
            # the documentation scope rather than an exact list.
            self.assertEqual(data["mode"], "scope")

    def test_pending_implementation_distill_is_not_authorized(self):
        with tempfile.TemporaryDirectory() as root:
            _, data = expected(root, [
                bloat_record("B1", "DISTILL", "docs/plans/later.md",
                             status="pending-implementation"),
            ], "distill")
            self.assertEqual(data["paths"], ["docs/decisions.md"])


class DerivationRefusals(unittest.TestCase):
    def assert_refused(self, root, records, lane, needle):
        proc, data = expected(root, records, lane)
        self.assertEqual(proc.returncode, 1, proc.stdout)
        self.assertIsNone(data, "an unauthorized record must write no authority")
        self.assertIn(needle, proc.stderr)
        self.assertIn("no PR, nothing staged", proc.stderr)

    def test_wiring_paths_are_never_authorized(self):
        for path in (".github/workflows/doc-sync.yml",
                     ".github/doc-sync/sync-gate.py",
                     ".git/config"):
            with tempfile.TemporaryDirectory() as root:
                self.assert_refused(root, [drift_record(f"{path}:2")],
                                    "drift", "never model-writable")

    def test_repo_escapes_are_never_authorized(self):
        for path, needle in (("../outside.md", "escapes the repository"),
                             ("/etc/passwd.md", "absolute path"),
                             ("docs/../../x.md", "normalized")):
            with tempfile.TemporaryDirectory() as root:
                self.assert_refused(root, [drift_record(f"{path}:2")],
                                    "drift", needle)

    def test_non_documentation_files_are_never_authorized(self):
        with tempfile.TemporaryDirectory() as root:
            self.assert_refused(root, [drift_record("src/app.py:2")],
                                "drift", "not a documentation file")

    def test_include_glob_re_adds_a_non_md_doc(self):
        with tempfile.TemporaryDirectory() as root:
            proc, data = expected(root, [drift_record("docs/api.txt:2")],
                                  "drift", config={"include": ["docs/*.txt"]})
            self.assertEqual(proc.returncode, 0, proc.stderr)
            self.assertEqual(data["paths"], ["docs/api.txt"])

    def test_record_with_no_usable_path_is_refused(self):
        with tempfile.TemporaryDirectory() as root:
            self.assert_refused(root, [bloat_record("B1", "CUT", "",
                                                    location=":4")],
                                "prune", "no usable path")


class CheckExact(unittest.TestCase):
    def test_authorized_paths_print_for_explicit_staging(self):
        with tempfile.TemporaryDirectory() as root:
            auth = authority(root, ["docs/b.md", "docs/a.md"])
            write(root, "changed.txt", "docs/b.md\ndocs/a.md\ndocs/a.md\n")
            proc = check(root, auth, "--paths", os.path.join(root, "changed.txt"))
            self.assertEqual(proc.returncode, 0, proc.stderr)
            self.assertEqual(proc.stdout.split(), ["docs/a.md", "docs/b.md"])

    def test_unexpected_path_fails_loudly(self):
        with tempfile.TemporaryDirectory() as root:
            auth = authority(root, ["docs/a.md"])
            write(root, "changed.txt", "docs/a.md\ndocs/sneaky.md\n")
            proc = check(root, auth, "--paths", os.path.join(root, "changed.txt"))
            self.assertEqual(proc.returncode, 1)
            self.assertIn("docs/sneaky.md: not named by any record",
                          proc.stderr)
            self.assertIn("nothing staged, no PR", proc.stderr)
            self.assertEqual(proc.stdout, "")

    def test_reads_the_path_list_from_stdin(self):
        with tempfile.TemporaryDirectory() as root:
            auth = authority(root, ["docs/a.md"])
            proc = subprocess.run(
                [sys.executable, SCRIPT, "check", "--expected", auth,
                 "--paths", "-"],
                input="docs/a.md\n", capture_output=True, text=True, cwd=root)
            self.assertEqual(proc.returncode, 0, proc.stderr)
            self.assertEqual(proc.stdout.split(), ["docs/a.md"])

    def test_workflow_state_needs_the_flag(self):
        with tempfile.TemporaryDirectory() as root:
            auth = authority(root, ["docs/a.md"])
            write(root, "changed.txt",
                  "docs/a.md\n.github/doc-sync-marker\n"
                  ".github/doc-sync/last-stales.json\n")
            paths = os.path.join(root, "changed.txt")
            self.assertEqual(check(root, auth, "--paths", paths).returncode, 1)
            proc = check(root, auth, "--paths", paths,
                         "--allow-workflow-state")
            self.assertEqual(proc.returncode, 0, proc.stderr)
            self.assertIn(".github/doc-sync-marker", proc.stdout)

    def test_malformed_authority_is_bad_input(self):
        with tempfile.TemporaryDirectory() as root:
            bad = write(root, "expected.json", json.dumps({"paths": []}))
            write(root, "changed.txt", "docs/a.md\n")
            proc = check(root, bad, "--paths", os.path.join(root, "changed.txt"))
            self.assertEqual(proc.returncode, 2)

    def test_no_input_source_is_bad_input(self):
        with tempfile.TemporaryDirectory() as root:
            proc = check(root, authority(root, []))
            self.assertEqual(proc.returncode, 2)


class CheckScope(unittest.TestCase):
    def scope_authority(self, root):
        return authority(root, ["docs/plans/p.md", "docs/decisions.md"],
                         mode="scope",
                         scope={"exclude": ["tests/fixtures/**"],
                                "include": []})

    def check_paths(self, root, *paths):
        write(root, "changed.txt", "".join(p + "\n" for p in paths))
        return check(root, self.scope_authority(root), "--paths",
                     os.path.join(root, "changed.txt"))

    def test_residue_in_an_unlisted_doc_is_authorized(self):
        with tempfile.TemporaryDirectory() as root:
            proc = self.check_paths(root, "docs/guides/new-guide.md",
                                    "docs/decisions.md")
            self.assertEqual(proc.returncode, 0, proc.stderr)

    def test_code_is_not_authorized_even_in_scope_mode(self):
        with tempfile.TemporaryDirectory() as root:
            proc = self.check_paths(root, "src/app.py")
            self.assertEqual(proc.returncode, 1)
            self.assertIn("not a documentation file", proc.stderr)

    def test_excluded_docs_are_outside_the_audited_scope(self):
        with tempfile.TemporaryDirectory() as root:
            proc = self.check_paths(root, "tests/fixtures/taskflow/README.md")
            self.assertEqual(proc.returncode, 1)
            self.assertIn("outside the audited documentation scope",
                          proc.stderr)

    def test_wiring_is_not_authorized_even_in_scope_mode(self):
        with tempfile.TemporaryDirectory() as root:
            proc = self.check_paths(root, ".github/doc-sync/notes.md")
            self.assertEqual(proc.returncode, 1)
            self.assertIn("never model-writable", proc.stderr)


def git(repo, *args):
    return subprocess.run(["git", "-C", repo, *args], capture_output=True,
                          text=True, env=GIT_ENV, check=True)


def repo_with_docs(root):
    repo = os.path.join(root, "repo")
    os.makedirs(repo)
    git(repo, "init", "-q")
    write(repo, "docs/a.md", "one\n")
    write(repo, "docs/old.md", "gone\n")
    git(repo, "add", "-A")
    git(repo, "commit", "-qm", "init")
    return repo


def patch_of(repo, out):
    git(repo, "add", "-A")
    diff = git(repo, "diff", "--cached", "--binary", "--no-renames").stdout
    with open(out, "w", encoding="utf-8") as f:
        f.write(diff)
    return out


class CheckPatches(unittest.TestCase):
    def test_edits_creations_and_deletions_are_all_checked(self):
        with tempfile.TemporaryDirectory() as root:
            repo = repo_with_docs(root)
            write(repo, "docs/a.md", "two\n")
            write(repo, "docs/b.md", "new\n")
            os.remove(os.path.join(repo, "docs/old.md"))
            patch = patch_of(repo, os.path.join(root, "edits.patch"))

            auth = authority(root, ["docs/a.md", "docs/old.md"])
            proc = check(root, auth, "--patch", patch, "--repo", repo)
            self.assertEqual(proc.returncode, 1)
            self.assertIn("docs/b.md", proc.stderr)

            auth = authority(root, ["docs/a.md", "docs/b.md", "docs/old.md"])
            proc = check(root, auth, "--patch", patch, "--repo", repo)
            self.assertEqual(proc.returncode, 0, proc.stderr)
            self.assertEqual(proc.stdout.split(),
                             ["docs/a.md", "docs/b.md", "docs/old.md"])

    def test_a_patch_reaching_into_the_wiring_fails_loudly(self):
        with tempfile.TemporaryDirectory() as root:
            repo = repo_with_docs(root)
            write(repo, "docs/a.md", "two\n")
            write(repo, ".github/workflows/pwn.yml", "on: push\n")
            patch = patch_of(repo, os.path.join(root, "edits.patch"))
            proc = check(root, authority(root, ["docs/a.md"]),
                         "--patch", patch, "--repo", repo)
            self.assertEqual(proc.returncode, 1)
            self.assertIn(".github/workflows/pwn.yml", proc.stderr)
            self.assertIn("never model-writable", proc.stderr)
            self.assertEqual(proc.stdout, "")

    def test_a_rename_record_is_refused_rather_than_half_checked(self):
        with tempfile.TemporaryDirectory() as root:
            repo = repo_with_docs(root)
            write(repo, "docs/a.md", "x\ny\nz\nq\nw\ne\nr\nt\n")
            git(repo, "add", "-A")
            git(repo, "commit", "-qm", "grow")
            git(repo, "mv", "docs/a.md", "docs/moved.md")
            # Rename detection on: `git apply --numstat` reports the
            # destination only, so the source path would go unchecked.
            diff = git(repo, "diff", "--cached", "--binary").stdout
            patch = os.path.join(root, "rename.patch")
            with open(patch, "w", encoding="utf-8") as f:
                f.write(diff)
            proc = check(root, authority(root, ["docs/moved.md"]),
                         "--patch", patch, "--repo", repo)
            self.assertEqual(proc.returncode, 1)
            self.assertIn("--no-renames", proc.stderr)
            self.assertEqual(proc.stdout, "")

    def test_empty_patch_authorizes_nothing_and_succeeds(self):
        with tempfile.TemporaryDirectory() as root:
            repo = repo_with_docs(root)
            patch = os.path.join(root, "edits.patch")
            open(patch, "w", encoding="utf-8").close()
            proc = check(root, authority(root, ["docs/a.md"]),
                         "--patch", patch, "--repo", repo)
            self.assertEqual(proc.returncode, 0, proc.stderr)
            self.assertEqual(proc.stdout, "")

    def test_patches_dir_walks_the_group_series(self):
        with tempfile.TemporaryDirectory() as root:
            repo = repo_with_docs(root)
            write(repo, "docs/a.md", "two\n")
            git(repo, "add", "-A")
            git(repo, "commit", "-qm", "one")
            write(repo, "docs/b.md", "new\n")
            git(repo, "add", "-A")
            git(repo, "commit", "-qm", "two")
            patches = os.path.join(root, "patches", "g-1")
            git(repo, "format-patch", "-2", "--no-renames", "-o", patches)

            proc = check(root, authority(root, ["docs/a.md"]),
                         "--patches-dir", os.path.join(root, "patches"),
                         "--repo", repo)
            self.assertEqual(proc.returncode, 1)
            self.assertIn("docs/b.md", proc.stderr)

            proc = check(root, authority(root, ["docs/a.md", "docs/b.md"]),
                         "--patches-dir", os.path.join(root, "patches"),
                         "--repo", repo)
            self.assertEqual(proc.returncode, 0, proc.stderr)

    def test_a_patches_dir_with_no_series_authorizes_nothing(self):
        # A lane whose every group failed lands no patches — an empty
        # authorized set, not bad input.
        with tempfile.TemporaryDirectory() as root:
            os.makedirs(os.path.join(root, "patches"))
            proc = check(root, authority(root, ["docs/a.md"]),
                         "--patches-dir", os.path.join(root, "patches"))
            self.assertEqual(proc.returncode, 0, proc.stderr)
            self.assertEqual(proc.stdout, "")


class VendoredLayout(unittest.TestCase):
    """The install flattens every script into .github/doc-sync/; the plugin
    tree keeps each under its owning skill. Both layouts must resolve the
    imported helpers."""

    def test_runs_from_a_flat_vendored_directory(self):
        import shutil
        skills = os.path.join(os.path.dirname(SCRIPT), "..", "..")
        with tempfile.TemporaryDirectory() as root:
            flat = os.path.join(root, "doc-sync")
            os.makedirs(flat)
            for rel in ("scheduling-doc-sync/scripts/authorize-paths.py",
                        "scheduling-doc-sync/scripts/sync-gate.py",
                        "detecting-doc-bloat/scripts/plan-chunks.py"):
                shutil.copyfile(os.path.join(skills, rel),
                                os.path.join(flat, os.path.basename(rel)))
            proc = subprocess.run(
                [sys.executable, os.path.join(flat, "authorize-paths.py"),
                 "expected", "--report",
                 report(root, [bloat_record("B1", "CUT", "docs/a.md",
                                            location="docs/a.md:4")]),
                 "--lane", "prune", "--out", os.path.join(root, "e.json")],
                capture_output=True, text=True, cwd=root)
            self.assertEqual(proc.returncode, 0, proc.stderr)


if __name__ == "__main__":
    unittest.main()
