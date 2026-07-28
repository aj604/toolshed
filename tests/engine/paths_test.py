#!/usr/bin/env python3
"""Tests for path authorization: the single owner of path safety.

Two seams, and the module owns both halves of "what is a repository path":

- `authorize_path(path, repo_root=, roots=, target_class=)` — one candidate
  path in, one typed authorization or typed refusal out.
- `path_references(text)` — the recognizer: which tokens in a piece of prose a
  reader would take as naming a file or directory in this repository. It
  authorizes nothing and touches no filesystem.

Nothing below either seam is tested directly.

Run: python3 tests/engine/paths_test.py
"""

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from support import RepoTestCase  # noqa: E402  (also puts the engine on sys.path)

from doclifecycle.paths import authorize_path, path_references  # noqa: E402


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

    def test_a_single_file_root_authorizes_nothing_beneath_itself(self):
        repo = self.repo({"CLAUDE.md": "# Claude\n"})

        decision = authorize_path(
            "CLAUDE.md/evil.md", repo_root=repo, roots=("CLAUDE.md",)
        )

        self.assertEqual(decision.problem.code, "path-not-a-file")

    def test_a_declared_root_that_is_not_in_the_repository_refuses(self):
        # Otherwise every path under the absent root reads as an authorizable
        # create-document target, including paths beneath a file-shaped root.
        repo = self.repo({"CLAUDE.md": "# Claude\n"})

        decision = authorize_path("docs/a.md", repo_root=repo, roots=("docs",))

        self.assertEqual(decision.problem.code, "root-missing")
        self.assertEqual(decision.problem.location, "docs")

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
    ("docs/requirements.txt", "configuration"),
    ("docs/robots.txt", "configuration"),
    # The filesystems this runs on fold case, so the classifier must too — a
    # capitalized spelling of the wiring is the same file as the wiring.
    ("docs/.GIT/hooks/pre-commit.md", "hook"),
    ("docs/.GitHub/workflows/ci.md", "workflow"),
    ("docs/.Husky/pre-push.md", "hook"),
    ("docs/.Claude/Hooks/session-start.md", "hook"),
    ("docs/JENKINSFILE", "workflow"),
    ("docs/.Env", "credential"),
    ("docs/ID_RSA", "credential"),
    ("docs/deploy.KEY", "credential"),
    ("docs/publish.SH", "executable"),
    ("docs/generate.PY", "source"),
    ("docs/settings.JSON", "configuration"),
    ("docs/MAKEFILE", "configuration"),
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

    def test_a_hardlinked_document_is_refused(self):
        # The other alias. A hardlink to the wiring is a documentation-looking
        # path whose bytes are the wiring's bytes; writing it edits both.
        repo = self.repo({".github/workflows/ci.yml": "on: push\n", "docs/a.md": "#\n"})
        os.link(
            os.path.join(repo, ".github", "workflows", "ci.yml"),
            os.path.join(repo, "docs", "innocent.md"),
        )

        decision = authorize_path("docs/innocent.md", repo_root=repo, roots=("docs",))

        self.assertEqual(decision.problem.code, "path-hardlinked")

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

    def test_a_path_that_is_not_a_regular_file_is_refused(self):
        repo = self.repo({"docs/a.md": "# A\n"})
        os.mkfifo(os.path.join(repo, "docs", "pipe.md"))

        decision = authorize_path("docs/pipe.md", repo_root=repo, roots=("docs",))

        self.assertEqual(decision.problem.code, "path-not-a-file")

    def test_a_directory_that_cannot_be_listed_refuses_rather_than_assumes(self):
        # The collision check is the only thing standing between a create and
        # an existing case-folded twin, so it must never fail open.
        if os.geteuid() == 0:
            self.skipTest("root can list any directory")
        repo = self.repo({"docs/locked/README.md": "# Readme\n"})
        locked = os.path.join(repo, "docs", "locked")
        os.chmod(locked, 0o000)
        self.addCleanup(os.chmod, locked, 0o755)

        decision = authorize_path(
            "docs/locked/readme.md", repo_root=repo, roots=("docs",)
        )

        self.assertEqual(decision.problem.code, "path-unreadable")

    def test_a_document_that_does_not_exist_yet_is_authorizable(self):
        # create-document is a real operation: the applier must be able to
        # authorize a path before anything is written there.
        repo = self.repo({"docs/a.md": "# A\n"})

        decision = authorize_path(
            "docs/new/deep/runbook.md", repo_root=repo, roots=("docs",)
        )

        self.assertTrue(decision.authorized, decision.problem)
        self.assertEqual(decision.path, "docs/new/deep/runbook.md")


class WhatProseNamesAsAFile(unittest.TestCase):
    """`path_references`: the file names a sentence puts in front of a reader.

    Generous on purpose. Its one consumer refuses eligibility when a reference
    turns up, so a token this misses is a refusal that does not happen, and a
    token it over-reads is a human looking at one more record.
    """

    def references(self, text):
        return set(path_references(text))

    def test_a_repository_path_inside_backticks_is_a_reference(self):
        text = ("This repository's own gate record, criteria and verdict, is "
                "`docs/plans/2026-07-27-shadow-parity-gate-rerun.md`.")

        self.assertEqual(self.references(text),
                         {"docs/plans/2026-07-27-shadow-parity-gate-rerun.md"})

    def test_a_sentence_naming_two_documents_names_both(self):
        text = ("is `docs/plans/b.md` (the first, now superseded, is "
                "`docs/plans/a.md`).")

        self.assertEqual(self.references(text),
                         {"docs/plans/a.md", "docs/plans/b.md"})

    def test_a_bare_filename_with_a_known_suffix_is_a_reference(self):
        self.assertEqual(self.references("see SKILL.md for the shape"),
                         {"SKILL.md"})

    def test_a_markdown_link_target_is_a_reference(self):
        self.assertEqual(self.references("[the guide](docs/guides/tour.md)"),
                         {"docs/guides/tour.md"})

    def test_a_directory_is_a_reference(self):
        self.assertEqual(self.references("the records live under `docs/plans/`"),
                         {"docs/plans/"})

    def test_slash_separated_prose_is_not_a_path(self):
        # The knob list that DRIFT-021's fix edits: slashes, but no file.
        text = "beyond the cron/cap/bloat-cron/upgrade-cron/audit-cron knobs"

        self.assertEqual(self.references(text), set())

    def test_an_owner_slash_repository_is_not_a_path(self):
        self.assertEqual(self.references("upstream in the plugin (aj604/toolshed)"),
                         set())

    def test_a_dotted_symbol_is_not_a_path(self):
        # `approval.ApprovedRecord.targets()` and `report.current_lineage()`
        # are the two DRIFT records whose fixes rewrite a symbol. Reading a
        # symbol as a file would refuse the fixes this policy exists to admit.
        text = ("one record authorizes (`approval.ApprovedRecord.targets()`), "
                "and `report.current_lineage()` supplies the rest")

        self.assertEqual(self.references(text), set())

    def test_an_abbreviation_is_not_a_path(self):
        self.assertEqual(self.references("unique within the report (e.g. `B1`)"),
                         set())

    def test_a_trailing_sentence_period_is_not_part_of_the_name(self):
        self.assertEqual(self.references("It moved to docs/reference/api.md."),
                         {"docs/reference/api.md"})

    def test_a_reference_is_reported_once_however_often_it_is_written(self):
        text = "`a/b.md` and `a/b.md` again, plus a/b.md"

        self.assertEqual(path_references(text), ("a/b.md",))

    def test_text_that_names_nothing_has_no_references(self):
        self.assertEqual(path_references("The service charges a 2% fee."), ())

    def test_the_same_text_is_read_the_same_way_twice(self):
        text = "moved from `docs/a.md` to `docs/b.md`"

        self.assertEqual(path_references(text), path_references(text))


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
