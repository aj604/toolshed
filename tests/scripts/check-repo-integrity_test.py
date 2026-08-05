#!/usr/bin/env python3
"""The audit lanes' shared repository-integrity gate (#185).

Both read-only lanes run this one script, so its behavior is tested once here
against real git repositories rather than twice against two copies of inline
shell. The workflow-side wiring — where the gate sits, what it exempts, and
that nothing downstream runs without it — is asserted in
audit-workflow_test.py and bloat-audit-workflow_test.py.
"""

import json
import os
import subprocess
import sys
import tempfile
import unittest


ROOT = os.path.join(os.path.dirname(__file__), "..", "..")
SCRIPT = os.path.join(
    ROOT, "plugins", "doc-lifecycle", "skills", "scheduling-doc-sync",
    "scripts", "check-repo-integrity.py",
)

VERIFIED, REFUSED, UNVERIFIABLE = 0, 2, 1


def git(repo, *args):
    subprocess.run(["git", "-C", repo, *args], check=True,
                   capture_output=True, text=True)


def write(path, text):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as stream:
        stream.write(text)


class RepositoryIntegrityGate(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.out = os.path.join(self.tmp.name, "audit-integrity.json")

    def repository(self):
        """A checkout shaped like one an audit lane reads: documents plus the
        non-document sources a drift verdict cites as evidence."""
        root = tempfile.mkdtemp(dir=self.tmp.name)
        git(root, "init", "-q")
        git(root, "config", "user.email", "audit@example.test")
        git(root, "config", "user.name", "Audit Test")
        write(os.path.join(root, ".gitignore"), "*.ignored\n")
        write(os.path.join(root, "README.md"), "the api runs on port 8080\n")
        write(os.path.join(root, "src", "server.py"), "PORT = 8080\n")
        git(root, "add", ".")
        git(root, "commit", "-q", "-m", "fixture")
        head = subprocess.check_output(
            ["git", "-C", root, "rev-parse", "HEAD"], text=True).strip()
        return root, head

    def run_gate(self, repo, expected_head, *allow):
        argv = [sys.executable, SCRIPT, "--repo", repo,
                "--expected-head", expected_head, "--out", self.out]
        for path in allow:
            argv += ["--allow", path]
        return subprocess.run(argv, capture_output=True, text=True)

    def verdict(self):
        with open(self.out, encoding="utf-8") as stream:
            return json.load(stream)

    def codes(self):
        return [p["code"] for p in self.verdict()["problems"]]

    # -- the clean case ------------------------------------------------------

    def test_an_untouched_checkout_verifies(self):
        repo, head = self.repository()
        result = self.run_gate(repo, head)
        self.assertEqual(result.returncode, VERIFIED, result.stdout + result.stderr)
        self.assertEqual(self.verdict()["status"], "verified")
        self.assertEqual(self.verdict()["problems"], [])
        self.assertEqual(self.verdict()["head"], head)

    # -- criterion 1: a dirtied non-document evidence source ------------------

    def test_a_dirtied_tracked_evidence_source_refuses_with_a_typed_reason(self):
        """HEAD unchanged, no document touched — only the *code* a verdict
        would cite as evidence. The report would look impeccable: same commit,
        same document inventory, same registry. This is the case the gate
        exists for, so it must refuse and say which file moved."""
        repo, head = self.repository()
        write(os.path.join(repo, "src", "server.py"), "PORT = 9090\n")

        result = self.run_gate(repo, head)
        self.assertEqual(result.returncode, REFUSED, result.stdout)
        verdict = self.verdict()
        self.assertEqual(verdict["status"], "refused")
        self.assertEqual(verdict["head"], head, "HEAD never moved")
        self.assertEqual(self.codes(), ["evidence-integrity-tracked-modified"])
        self.assertEqual(
            verdict["problems"][0]["location"], "src/server.py")
        self.assertIn("evidence-integrity-tracked-modified", result.stdout)

    # -- criterion 2: the refusal cannot be laundered afterwards --------------

    def test_a_fresh_checkout_cannot_re_derive_the_failure(self):
        """A fresh checkout of the same commit is byte-identical whether or
        not the run that read it dirtied its own copy, so nothing downstream
        can re-derive the mutation: the report contract digests documents,
        registry, and lineage, never the non-document sources a verdict cites,
        and `base_commit` is a plain `rev-parse HEAD`. The refusal is
        therefore only available before assembly — which is why the gate is
        terminal and the lanes publish no report at all after it."""
        repo, head = self.repository()
        write(os.path.join(repo, "src", "server.py"), "PORT = 9090\n")
        self.assertEqual(self.run_gate(repo, head).returncode, REFUSED)
        dirty_codes = self.codes()

        fresh = tempfile.mkdtemp(dir=self.tmp.name)
        subprocess.run(["git", "clone", "-q", repo, fresh], check=True,
                       capture_output=True)
        git(fresh, "checkout", "-q", head)

        self.assertEqual(
            self.run_gate(fresh, head).returncode, VERIFIED,
            "a fresh checkout of the same commit is clean — after the fact "
            "there is nothing left to detect")
        self.assertEqual(self.verdict()["status"], "verified")
        self.assertEqual(dirty_codes, ["evidence-integrity-tracked-modified"])

    # -- criterion 3: exactly the declared artifact is exempt -----------------

    def test_only_the_declared_artifact_is_exempt(self):
        repo, head = self.repository()
        write(os.path.join(repo, "verdicts.json"), '{"documents": []}\n')

        self.assertEqual(self.run_gate(repo, head).returncode, REFUSED)
        self.assertEqual(self.codes(), ["evidence-integrity-untracked-added"])

        self.assertEqual(
            self.run_gate(repo, head, "verdicts.json").returncode, VERIFIED)
        self.assertEqual(self.verdict()["allowed"], ["verdicts.json"])

    def test_an_allowlist_exempts_nothing_but_its_own_path(self):
        repo, head = self.repository()
        write(os.path.join(repo, "verdicts.json"), '{"documents": []}\n')
        write(os.path.join(repo, "scratch.json"), "{}\n")

        self.assertEqual(
            self.run_gate(repo, head, "verdicts.json").returncode, REFUSED)
        problems = self.verdict()["problems"]
        self.assertEqual(
            [p["location"] for p in problems], ["scratch.json"])

    def test_an_allowed_name_is_no_licence_to_edit_repository_content(self):
        """The lane declared it would *add* a file, never that it would edit
        content that already exists — so the same name, tracked and modified,
        is still a mutation."""
        repo, head = self.repository()
        git(repo, "mv", "README.md", "verdicts.json")
        git(repo, "commit", "-q", "-m", "a repository that tracks the name")
        head = subprocess.check_output(
            ["git", "-C", repo, "rev-parse", "HEAD"], text=True).strip()
        write(os.path.join(repo, "verdicts.json"), "rewritten\n")

        self.assertEqual(
            self.run_gate(repo, head, "verdicts.json").returncode, REFUSED)
        self.assertEqual(self.codes(), ["evidence-integrity-tracked-modified"])

    # -- every mutation surface ----------------------------------------------

    def test_every_repository_mutation_surface_is_named(self):
        cases = {
            "evidence-integrity-tracked-modified":
                lambda repo: write(os.path.join(repo, "README.md"), "moved\n"),
            "evidence-integrity-untracked-added":
                lambda repo: write(os.path.join(repo, "new.md"), "new\n"),
            # A mutation hidden behind a .gitignore rule is still a mutation.
            "ignored-untracked":
                lambda repo: write(os.path.join(repo, "cache.ignored"), "x\n"),
        }
        for label, mutate in cases.items():
            with self.subTest(label=label):
                repo, head = self.repository()
                mutate(repo)
                self.assertEqual(self.run_gate(repo, head).returncode, REFUSED)
                if label.startswith("evidence-integrity-"):
                    self.assertEqual(self.codes(), [label])

    def test_a_staged_change_is_refused_even_with_a_clean_work_tree(self):
        repo, head = self.repository()
        write(os.path.join(repo, "README.md"), "staged\n")
        git(repo, "add", "README.md")
        self.assertEqual(self.run_gate(repo, head).returncode, REFUSED)
        self.assertIn("evidence-integrity-staged-change", self.codes())

    def test_a_moved_head_is_refused_and_names_where_it_moved_to(self):
        repo, head = self.repository()
        git(repo, "commit", "-q", "--allow-empty", "-m", "moved")
        moved = subprocess.check_output(
            ["git", "-C", repo, "rev-parse", "HEAD"], text=True).strip()

        self.assertEqual(self.run_gate(repo, head).returncode, REFUSED)
        verdict = self.verdict()
        self.assertEqual(self.codes(), ["evidence-integrity-head-moved"])
        self.assertEqual(verdict["problems"][0]["location"], moved)
        self.assertEqual(verdict["expected_head"], head)

    def test_every_problem_is_named_not_just_the_first(self):
        repo, head = self.repository()
        write(os.path.join(repo, "README.md"), "moved\n")
        write(os.path.join(repo, "src", "server.py"), "PORT = 9090\n")
        write(os.path.join(repo, "new.md"), "new\n")
        git(repo, "commit", "-q", "--allow-empty", "-m", "moved")

        self.assertEqual(self.run_gate(repo, head).returncode, REFUSED)
        self.assertEqual(sorted(set(self.codes())), [
            "evidence-integrity-head-moved",
            "evidence-integrity-tracked-modified",
            "evidence-integrity-untracked-added",
        ])
        self.assertEqual(
            sorted(p["location"] for p in self.verdict()["problems"]
                   if p["code"] == "evidence-integrity-tracked-modified"),
            ["README.md", "src/server.py"])

    # -- fail closed ---------------------------------------------------------

    def test_the_gate_never_repairs_what_it_refuses(self):
        repo, head = self.repository()
        write(os.path.join(repo, "src", "server.py"), "PORT = 9090\n")
        self.assertEqual(self.run_gate(repo, head).returncode, REFUSED)
        with open(os.path.join(repo, "src", "server.py"), encoding="utf-8") as f:
            self.assertEqual(f.read(), "PORT = 9090\n")
        self.assertNotEqual(
            subprocess.check_output(
                ["git", "-C", repo, "status", "--porcelain"], text=True), "")

    def test_a_directory_that_is_not_a_repository_is_unverifiable(self):
        plain = tempfile.mkdtemp(dir=self.tmp.name)
        result = self.run_gate(plain, "0" * 40)
        self.assertEqual(result.returncode, UNVERIFIABLE, result.stdout)
        self.assertEqual(self.verdict()["status"], "refused")
        self.assertEqual(self.codes(), ["evidence-integrity-unverifiable"])


if __name__ == "__main__":
    unittest.main()
