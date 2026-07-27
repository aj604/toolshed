#!/usr/bin/env python3
"""Tests for the git reads: identity, position, and what a commit range touched.

Seam: the library functions in `doclifecycle.repository`, which the engine
README names as its public surface (`lineage`, `resolve_commit`,
`changed_paths`, `last_change`, `tracked_files`). Every one of them is a
question about a real repository, so every repository here is a real one with
real commits.

The module's own README line is "Nothing here writes to a repository", and the
suite holds it to that: an argument reaching git in flag position is the one way
a read-only helper turns into a writer, so the arguments are probed with the
spellings git would read as options.

Run: python3 tests/engine/repository_test.py
"""

import os
import subprocess
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from support import RepoTestCase  # noqa: E402

from doclifecycle import repository  # noqa: E402

GIT_ENV = {
    "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@example.com",
    "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@example.com",
}

# Spellings that reach `git` where an option would. The first is the one that
# wrote a file: `git diff --output=PWNED..HEAD` is a redirect, not a revision.
FLAG_SPELLINGS = (
    "--output=PWNED",
    "-o PWNED",
    "--all",
    "--end-of-options",
    "--exit-code",
)


class RepositoryTestCase(RepoTestCase):
    def git(self, root, *argv):
        return subprocess.run(
            ["git", "-C", root, "-c", "commit.gpgsign=false", *argv],
            check=True, capture_output=True, text=True,
            env=dict(os.environ, **GIT_ENV),
        ).stdout.strip()

    def commit(self, root, message="change"):
        self.git(root, "add", "-A")
        self.git(root, "commit", "-q", "-m", message)
        return self.git(root, "rev-parse", "HEAD")

    def history(self):
        """A repository with two commits; returns (root, first commit id)."""
        root = self.repo({"a.txt": "one\n"})
        self.git(root, "init", "-q", "-b", "main")
        first = self.commit(root, "initial")
        with open(os.path.join(root, "b.txt"), "w", encoding="utf-8") as fh:
            fh.write("two\n")
        self.commit(root, "add b")
        return root, first

    def tree(self, root):
        return sorted(
            name for name in os.listdir(root) if name != ".git"
        )


class ChangedPaths(RepositoryTestCase):
    def test_a_commit_range_names_what_it_touched(self):
        root, first = self.history()

        self.assertEqual(repository.changed_paths(root, first), (("b.txt",), None))

    def test_a_baseline_that_is_a_flag_is_refused_before_git_sees_it(self):
        """The reviewer's probe on PR #87: `changed_paths(root, "--output=PWNED")`
        returned `((), None)` and left a file called `PWNED..HEAD` in the
        repository — a write, from the module whose contract is that it never
        writes. The baseline is interpolated into `<since>..HEAD`, which lands
        in flag position, so the gate is that it must already be a resolved
        object id.
        """
        root, _ = self.history()
        before = self.tree(root)

        paths, problem = repository.changed_paths(root, "--output=PWNED")

        self.assertIsNone(paths)
        self.assertEqual(problem.code, "repository-state-unavailable")
        self.assertEqual(self.tree(root), before)

    def test_no_flag_spelling_of_a_baseline_reaches_git(self):
        root, _ = self.history()
        before = self.tree(root)

        for spelling in FLAG_SPELLINGS:
            with self.subTest(since=spelling):
                paths, problem = repository.changed_paths(root, spelling)

                self.assertIsNone(paths)
                self.assertIsNotNone(problem)
                self.assertEqual(self.tree(root), before)

    def test_a_revision_that_is_not_a_resolved_id_is_refused(self):
        """`HEAD~1` names a commit, and is still refused: the caller must put it
        through `resolve_commit` first, because "looks like a revision" is not a
        property this helper can check and "is forty hex characters" is."""
        root, _ = self.history()

        paths, problem = repository.changed_paths(root, "HEAD~1")

        self.assertIsNone(paths)
        self.assertIn("resolve_commit", problem.message)

    def test_what_resolve_commit_returns_is_what_changed_paths_accepts(self):
        """The two helpers compose: the gate's output is the gate's contract."""
        root, _ = self.history()

        resolved, problem = repository.resolve_commit(root, "HEAD~1")
        self.assertIsNone(problem)

        self.assertEqual(repository.changed_paths(root, resolved),
                         (("b.txt",), None))

    def test_a_baseline_that_is_not_a_string_is_refused(self):
        root, _ = self.history()

        paths, problem = repository.changed_paths(root, None)

        self.assertIsNone(paths)
        self.assertIsNotNone(problem)


class ResolveCommit(RepositoryTestCase):
    def test_a_revision_resolves_to_its_full_commit_id(self):
        root, first = self.history()

        self.assertEqual(repository.resolve_commit(root, "HEAD~1"),
                         (first, None))

    def test_no_flag_spelling_resolves_or_writes(self):
        root, _ = self.history()
        before = self.tree(root)

        for spelling in FLAG_SPELLINGS:
            with self.subTest(revision=spelling):
                resolved, problem = repository.resolve_commit(root, spelling)

                self.assertIsNone(resolved)
                self.assertIsNotNone(problem)
                self.assertEqual(self.tree(root), before)

    def test_a_revision_the_repository_does_not_have_is_refused(self):
        root, _ = self.history()

        resolved, problem = repository.resolve_commit(root, "0" * 40)

        self.assertIsNone(resolved)
        self.assertEqual(problem.code, "repository-state-unavailable")


class LastChange(RepositoryTestCase):
    def test_a_tracked_path_reports_the_commit_that_last_touched_it(self):
        root, _ = self.history()

        change, problem = repository.last_change(root, "b.txt")

        self.assertIsNone(problem)
        self.assertEqual(len(change[0]), len("YYYY-MM-DD"))

    def test_a_path_with_no_history_is_a_different_answer_from_a_failure(self):
        root, _ = self.history()
        with open(os.path.join(root, "c.txt"), "w", encoding="utf-8") as fh:
            fh.write("untracked\n")

        self.assertEqual(repository.last_change(root, "c.txt"), (None, None))

    def test_a_flag_shaped_path_is_read_as_a_path(self):
        """`--` is already in this invocation, so a path that looks like an
        option is a path. It answers "no history" rather than acting on it."""
        root, _ = self.history()
        before = self.tree(root)

        change, problem = repository.last_change(root, "--output=PWNED")

        self.assertIsNone(problem)
        self.assertIsNone(change)
        self.assertEqual(self.tree(root), before)


class TrackedFiles(RepositoryTestCase):
    def test_reports_every_path_the_repository_tracks(self):
        root, _ = self.history()

        paths, problem = repository.tracked_files(root)

        self.assertIsNone(problem)
        self.assertEqual(paths, ("a.txt", "b.txt"))

    def test_an_untracked_file_is_not_a_tracked_path(self):
        root, _ = self.history()
        with open(os.path.join(root, "generated.txt"), "w", encoding="utf-8") as fh:
            fh.write("built, not committed\n")

        paths, problem = repository.tracked_files(root)

        self.assertIsNone(problem)
        self.assertNotIn("generated.txt", paths)

    def test_a_path_git_would_quote_is_reported_as_it_is_spelled(self):
        """git renders a non-ASCII path as `"a\\303\\251.txt"` unless it is
        asked for raw output, and a caller comparing that against a real path
        would decide the file is not tracked."""
        root, _ = self.history()
        with open(os.path.join(root, "café notes.txt"), "w",
                  encoding="utf-8") as fh:
            fh.write("accented\n")
        self.commit(root, "add accented")

        paths, problem = repository.tracked_files(root)

        self.assertIsNone(problem)
        self.assertIn("café notes.txt", paths)

    def test_a_path_whose_name_begins_with_a_space_keeps_it(self):
        """The whole listing arrives as one string, so trimming that string
        eats the first path's leading whitespace — and a caller comparing the
        trimmed spelling against the tree decides the file is not there."""
        root, _ = self.history()
        with open(os.path.join(root, " leading.txt"), "w", encoding="utf-8") as fh:
            fh.write("space\n")
        self.commit(root, "add leading space")

        paths, problem = repository.tracked_files(root)

        self.assertIsNone(problem)
        self.assertIn(" leading.txt", paths)

    def test_a_directory_with_no_repository_is_a_problem_not_an_empty_listing(self):
        """The distinction is load-bearing: a caller that read "no tracked
        files" from an unreadable repository would report a corpus as fully
        covered precisely when it could not check."""
        root = self.repo({"a.txt": "one\n"})

        paths, problem = repository.tracked_files(root)

        self.assertIsNone(paths)
        self.assertEqual(problem.code, "repository-listing-unavailable")

    def test_reads_the_repository_it_was_named_rather_than_an_enclosing_one(self):
        root, _ = self.history()
        nested = os.path.join(root, "nested")
        os.makedirs(nested)
        with open(os.path.join(nested, "inner.txt"), "w", encoding="utf-8") as fh:
            fh.write("inner\n")
        self.commit(root, "add nested")

        paths, problem = repository.tracked_files(nested)

        self.assertIsNone(problem)
        self.assertEqual(paths, ("inner.txt",))


if __name__ == "__main__":
    unittest.main(verbosity=2)
