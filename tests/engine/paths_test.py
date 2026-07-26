#!/usr/bin/env python3
"""Tests for path authorization: the single owner of path safety.

Seam: doclifecycle.paths.authorize_path(path, repo_root=, roots=, target_class=)
— one candidate path in, one typed authorization or typed refusal out. Nothing
below the seam is tested directly.

Run: python3 tests/engine/paths_test.py
"""

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from support import RepoTestCase  # noqa: E402  (also puts the engine on sys.path)

from doclifecycle.paths import authorize_path  # noqa: E402


class Authorized(RepoTestCase):
    def test_a_canonical_document_under_a_declared_root_is_authorized(self):
        repo = self.repo({"docs/architecture.md": "# Architecture\n"})

        decision = authorize_path(
            "docs/architecture.md", repo_root=repo, roots=("docs",)
        )

        self.assertTrue(decision.authorized)
        self.assertIsNone(decision.problem)
        self.assertEqual(decision.path, "docs/architecture.md")
        self.assertEqual(decision.root, "docs")
        self.assertEqual(decision.target_class, "documentation")


SPELLING_REFUSALS = [
    # (candidate path, expected problem code)
    ("", "path-empty"),
    ("   ", "path-empty"),
    ("/etc/passwd", "path-absolute"),
    ("/docs/architecture.md", "path-absolute"),
    ("C:/docs/architecture.md", "path-absolute"),
    ("c:docs/architecture.md", "path-absolute"),
    ("~/docs/architecture.md", "path-absolute"),
    ("docs\\architecture.md", "path-separator"),
    ("\\\\server\\share\\architecture.md", "path-separator"),
    ("docs/archi\ntecture.md", "path-control-character"),
    ("docs/archi\rtecture.md", "path-control-character"),
    ("docs/archi\ttecture.md", "path-control-character"),
    ("docs/archi\x00tecture.md", "path-control-character"),
    ("docs/archi\x1btecture.md", "path-control-character"),
    ("../secrets.md", "path-traversal"),
    ("docs/../../etc/passwd.md", "path-traversal"),
    ("docs/..", "path-traversal"),
    ("..", "path-traversal"),
    ("./docs/architecture.md", "path-non-canonical"),
    ("docs//architecture.md", "path-non-canonical"),
    ("docs/./architecture.md", "path-non-canonical"),
    ("docs/architecture.md/", "path-non-canonical"),
    (".", "path-non-canonical"),
    ("-docs/architecture.md", "path-leading-dash"),
    ("docs/-rf.md", "path-leading-dash"),
    (" docs/architecture.md", "path-whitespace"),
    ("docs/architecture.md ", "path-whitespace"),
    ("docs/my architecture.md", "path-whitespace"),
    ("docs/archi\u00a0tecture.md", "path-whitespace"),
    # NFD "café.md": the precomposed spelling is the only canonical one.
    ("docs/cafe\u0301.md", "path-unicode-non-canonical"),
]


class Spelling(RepoTestCase):
    """Ambiguous spellings are refused before the filesystem is consulted.

    Every row is a way of naming a file that either escapes the repository or
    reads differently to a shell, a git plumbing command, and a human. The
    module accepts exactly one spelling per path so authorization decisions are
    comparable.
    """

    def test_each_hostile_spelling_is_refused_with_its_typed_code(self):
        repo = self.repo({"docs/architecture.md": "# Architecture\n"})

        for candidate, code in SPELLING_REFUSALS:
            with self.subTest(path=candidate):
                decision = authorize_path(
                    candidate, repo_root=repo, roots=("docs",)
                )

                self.assertFalse(decision.authorized)
                self.assertEqual(decision.problem.code, code)
                self.assertIsNone(decision.path)
                self.assertEqual(decision.problem.location, candidate)

    def test_a_refusal_says_what_to_do_about_it(self):
        decision = authorize_path(
            "docs/../etc/passwd.md", repo_root=self.repo({}), roots=("docs",)
        )

        self.assertIn("..", decision.problem.message)
        self.assertIn("repository-relative", decision.problem.message)


class Roots(RepoTestCase):
    """Eligibility is containment in a declared root, not a string prefix."""

    def test_a_path_under_no_declared_root_is_refused(self):
        repo = self.repo({"src/main.md": "# Main\n", "docs/a.md": "# A\n"})

        decision = authorize_path("src/main.md", repo_root=repo, roots=("docs",))

        self.assertEqual(decision.problem.code, "path-outside-root")
        self.assertIn("docs", decision.problem.message)

    def test_a_sibling_sharing_a_roots_name_prefix_is_outside_it(self):
        repo = self.repo({"docsx/a.md": "# A\n", "docs/a.md": "# A\n"})

        decision = authorize_path("docsx/a.md", repo_root=repo, roots=("docs",))

        self.assertEqual(decision.problem.code, "path-outside-root")

    def test_a_single_file_root_authorizes_exactly_that_file(self):
        repo = self.repo({"CLAUDE.md": "# Claude\n"})

        decision = authorize_path("CLAUDE.md", repo_root=repo, roots=("CLAUDE.md",))

        self.assertTrue(decision.authorized)
        self.assertEqual(decision.root, "CLAUDE.md")

    def test_the_containing_root_is_named_when_several_are_declared(self):
        repo = self.repo({"guides/setup.md": "# Setup\n", "docs/a.md": "# A\n"})

        decision = authorize_path(
            "guides/setup.md", repo_root=repo, roots=("docs", "guides")
        )

        self.assertEqual(decision.root, "guides")

    def test_declaring_no_roots_authorizes_nothing(self):
        repo = self.repo({"docs/a.md": "# A\n"})

        decision = authorize_path("docs/a.md", repo_root=repo, roots=())

        self.assertEqual(decision.problem.code, "roots-undeclared")

    def test_a_root_that_is_not_itself_canonical_invalidates_the_question(self):
        # The roots are as much an input as the path; a root that could name
        # anything cannot decide whether a path is inside it.
        repo = self.repo({"docs/a.md": "# A\n"})

        for root in ("../elsewhere", "/docs", "docs/", "./docs", "docs\\deep"):
            with self.subTest(root=root):
                decision = authorize_path(
                    "docs/a.md", repo_root=repo, roots=(root,)
                )

                self.assertEqual(decision.problem.code, "roots-invalid")
                self.assertEqual(decision.problem.location, root)


FORBIDDEN_CLASSES = [
    # (path under a declared root, the class it is classified as)
    ("docs/.github/workflows/ci.yml", "workflow"),
    ("docs/.circleci/config.yml", "workflow"),
    ("docs/.gitlab-ci.yml", "workflow"),
    ("docs/Jenkinsfile", "workflow"),
    ("docs/.github/doc-sync/sync-gate.py", "workflow"),
    ("docs/.git/hooks/pre-commit", "hook"),
    ("docs/.husky/pre-push", "hook"),
    ("docs/.pre-commit-config.yaml", "hook"),
    ("docs/.git/config", "configuration"),
    ("docs/.env", "credential"),
    ("docs/.env.production", "credential"),
    ("docs/server.pem", "credential"),
    ("docs/deploy.key", "credential"),
    ("docs/.netrc", "credential"),
    ("docs/id_rsa", "credential"),
    ("docs/publish.sh", "executable"),
    ("docs/install.ps1", "executable"),
    ("docs/helper.dylib", "executable"),
    ("docs/generate.py", "source"),
    ("docs/widget.tsx", "source"),
    ("docs/parser.rs", "source"),
    ("docs/settings.json", "configuration"),
    ("docs/mkdocs.yml", "configuration"),
    ("docs/pyproject.toml", "configuration"),
    ("docs/Makefile", "configuration"),
    ("docs/Dockerfile", "configuration"),
    ("docs/.gitignore", "configuration"),
    ("docs/CMakeLists.txt", "configuration"),
    # Not documentation and not one of the named dangerous classes: still
    # refused, because eligibility is a positive list.
    ("docs/diagram.png", "other"),
    ("docs/data.csv", "other"),
]

DOCUMENTATION_PATHS = [
    "docs/architecture.md",
    "docs/guide.mdx",
    "docs/legacy.rst",
    "docs/notes.txt",
    "docs/manual.adoc",
    "docs/deep/nested/runbook.md",
    "docs/.claude/CLAUDE.md",
]


class TargetClasses(RepoTestCase):
    """A documentation root is not a licence to write whatever sits inside it.

    The wiring, the source, and the secrets are exactly what a compromised
    record would reach for, so class is decided by the path itself and living
    under `docs/` does not launder it.
    """

    def test_forbidden_classes_are_refused_under_a_documentation_root(self):
        repo = self.repo({"docs/architecture.md": "# A\n"})

        for candidate, expected_class in FORBIDDEN_CLASSES:
            with self.subTest(path=candidate):
                decision = authorize_path(
                    candidate, repo_root=repo, roots=("docs",)
                )

                self.assertFalse(decision.authorized)
                self.assertEqual(decision.problem.code, "path-forbidden-class")
                self.assertEqual(decision.target_class, expected_class)
                self.assertIsNone(decision.path)

    def test_documentation_spellings_are_eligible(self):
        files = {path: "# Doc\n" for path in DOCUMENTATION_PATHS}
        repo = self.repo(files)

        for candidate in DOCUMENTATION_PATHS:
            with self.subTest(path=candidate):
                decision = authorize_path(
                    candidate, repo_root=repo, roots=("docs",)
                )

                self.assertTrue(decision.authorized, decision.problem)
                self.assertEqual(decision.target_class, "documentation")

    def test_a_dangerous_class_cannot_be_declared_as_the_target(self):
        # The six dangerous classes are not merely off by default: a caller
        # cannot switch them on by naming one, so no record, plan, or config
        # can talk the module into authorizing the wiring.
        repo = self.repo({"docs/publish.sh": "#!/bin/sh\n", "docs/a.md": "# A\n"})

        for declared in (
            "workflow",
            "source",
            "configuration",
            "credential",
            "hook",
            "executable",
            "other",
            "anything",
        ):
            with self.subTest(target_class=declared):
                decision = authorize_path(
                    "docs/publish.sh",
                    repo_root=repo,
                    roots=("docs",),
                    target_class=declared,
                )

                self.assertEqual(decision.problem.code, "target-class-undeclarable")


class Symlinks(RepoTestCase):
    """Aliases are resolved before authorization, never after.

    A symlink is the one way a path that reads as documentation inside a root
    can write somewhere else entirely, so no component of an authorized path
    may be one.
    """

    def test_a_symlinked_document_is_refused(self):
        repo = self.repo({"docs/real.md": "# Real\n"})
        os.symlink("/etc/passwd", os.path.join(repo, "docs", "innocent.md"))

        decision = authorize_path("docs/innocent.md", repo_root=repo, roots=("docs",))

        self.assertEqual(decision.problem.code, "symlinked-path")
        self.assertEqual(decision.problem.location, "docs/innocent.md")

    def test_a_document_behind_a_symlinked_directory_is_refused(self):
        repo = self.repo({"elsewhere/secret.md": "# Secret\n", "docs/a.md": "# A\n"})
        os.symlink(os.path.join(repo, "elsewhere"), os.path.join(repo, "docs", "alias"))

        decision = authorize_path(
            "docs/alias/secret.md", repo_root=repo, roots=("docs",)
        )

        self.assertEqual(decision.problem.code, "symlinked-path")
        # The refusal names the component that is the alias, not the leaf.
        self.assertEqual(decision.problem.location, "docs/alias")

    def test_a_symlinked_root_is_refused(self):
        repo = self.repo({"elsewhere/a.md": "# A\n"})
        os.symlink(os.path.join(repo, "elsewhere"), os.path.join(repo, "docs"))

        decision = authorize_path("docs/a.md", repo_root=repo, roots=("docs",))

        self.assertEqual(decision.problem.code, "symlinked-path")
        self.assertEqual(decision.problem.location, "docs")

    def test_a_symlink_pointing_inside_the_repository_is_still_refused(self):
        # Harmless target today, a different file after one `ln -sf`. The
        # authorization is of the path, so the path must be the real one.
        repo = self.repo({"docs/real.md": "# Real\n"})
        os.symlink(
            os.path.join(repo, "docs", "real.md"), os.path.join(repo, "docs", "as.md")
        )

        decision = authorize_path("docs/as.md", repo_root=repo, roots=("docs",))

        self.assertEqual(decision.problem.code, "symlinked-path")


class OnDiskAmbiguity(RepoTestCase):
    """One file, one spelling — including the spellings the filesystem folds."""

    def test_a_case_variant_of_an_existing_document_is_refused(self):
        repo = self.repo({"docs/README.md": "# Readme\n"})

        decision = authorize_path("docs/readme.md", repo_root=repo, roots=("docs",))

        self.assertEqual(decision.problem.code, "path-case-mismatch")
        self.assertIn("README.md", decision.problem.message)

    def test_a_case_variant_of_a_directory_component_is_refused(self):
        repo = self.repo({"docs/guides/setup.md": "# Setup\n"})

        decision = authorize_path(
            "docs/Guides/setup.md", repo_root=repo, roots=("docs",)
        )

        self.assertEqual(decision.problem.code, "path-case-mismatch")

    def test_a_normalization_variant_of_an_existing_document_is_refused(self):
        decomposed = "café.md"
        composed = "café.md"
        repo = self.repo({f"docs/{decomposed}": "# Cafe\n"})
        if decomposed not in os.listdir(os.path.join(repo, "docs")):
            self.skipTest("filesystem normalizes filenames; no collision to build")

        decision = authorize_path(
            f"docs/{composed}", repo_root=repo, roots=("docs",)
        )

        self.assertEqual(decision.problem.code, "path-unicode-collision")


class WhatThePathIs(RepoTestCase):
    def test_a_directory_is_not_an_authorizable_target(self):
        repo = self.repo({"docs/guides/setup.md": "# Setup\n"})

        decision = authorize_path("docs/guides", repo_root=repo, roots=("docs",))

        self.assertEqual(decision.problem.code, "path-not-a-file")

    def test_nothing_can_be_authorized_beneath_an_existing_file(self):
        repo = self.repo({"docs/a.md": "# A\n"})

        decision = authorize_path("docs/a.md/b.md", repo_root=repo, roots=("docs",))

        self.assertEqual(decision.problem.code, "path-not-a-file")
        self.assertEqual(decision.problem.location, "docs/a.md")

    def test_a_repository_root_that_is_not_there_authorizes_nothing(self):
        # Otherwise every path looks like an authorizable create-document
        # target, and the module fails open on a mistyped checkout.
        repo = self.repo({"docs/a.md": "# A\n"})

        decision = authorize_path(
            "docs/a.md", repo_root=os.path.join(repo, "nope"), roots=("docs",)
        )

        self.assertEqual(decision.problem.code, "repo-root-missing")

    def test_a_document_marked_executable_is_refused(self):
        repo = self.repo({"docs/a.md": "# A\n"})
        os.chmod(os.path.join(repo, "docs", "a.md"), 0o755)

        decision = authorize_path("docs/a.md", repo_root=repo, roots=("docs",))

        self.assertEqual(decision.problem.code, "path-executable-mode")

    def test_a_document_that_does_not_exist_yet_is_authorizable(self):
        # create-document is a real operation: the applier must be able to
        # authorize a path before anything is written there.
        repo = self.repo({"docs/a.md": "# A\n"})

        decision = authorize_path(
            "docs/new/deep/runbook.md", repo_root=repo, roots=("docs",)
        )

        self.assertTrue(decision.authorized, decision.problem)
        self.assertEqual(decision.path, "docs/new/deep/runbook.md")


class Determinism(RepoTestCase):
    def test_the_same_inputs_give_the_same_verdict(self):
        repo = self.repo({"docs/a.md": "# A\n", "docs/deploy.sh": "#!/bin/sh\n"})

        for candidate in ("docs/a.md", "docs/deploy.sh", "../escape.md", "src/x.md"):
            with self.subTest(path=candidate):
                first = authorize_path(candidate, repo_root=repo, roots=("docs",))
                second = authorize_path(candidate, repo_root=repo, roots=("docs",))

                self.assertEqual(first, second)


if __name__ == "__main__":
    unittest.main()
