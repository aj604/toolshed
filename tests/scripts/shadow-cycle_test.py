#!/usr/bin/env python3
"""Black-box tests for the shadow-parity gate's harness (aj604/toolshed#76, #117).

`tests/baselines/shadow-parity-gate/shadow-cycle.py` is recorded scaffolding
rather than plugin content, but two of its subcommands *are* the gate's
instruments, and the 2026-07-26 cycle failed G1b on one of them. So they get a
suite:

  * `digest` is criterion G1b's measuring device. The re-registration
    (aj604/toolshed#117) fixes what it hashes — the repository's content as the
    repository defines it, tracked plus untracked-but-not-ignored, with
    `.pyc`/`__pycache__` excluded whatever the ignore rules happen to say — and
    requires `git status --porcelain` clean at both measurement points. Both
    halves are asserted here so the instrument cannot be quietly re-specified
    mid-cycle again.

  * `merge` folds the model workers' rounds into one verdicts file. Since
    aj604/toolshed#116 a lane answers by a unit's small integer ordinal rather
    than its 64-character digest, so the merge has to resolve ordinals — and
    resolve them to the *same* key a digest-spelled answer uses, or a repair
    round could not override a round-1 answer for the same unit.

Run: python3 tests/scripts/shadow-cycle_test.py
"""

import importlib.util
import json
import os
import subprocess
import sys
import tempfile
import unittest

SCRIPT = os.path.join(
    os.path.dirname(os.path.abspath(__file__)),
    "..", "baselines", "shadow-parity-gate", "shadow-cycle.py",
)


def run(*args, cwd=None):
    return subprocess.run([sys.executable, SCRIPT, *args],
                          capture_output=True, text=True, cwd=cwd)


def load_module():
    sys.dont_write_bytecode = True
    spec = importlib.util.spec_from_file_location("shadow_cycle", SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def git(cwd, *args):
    return subprocess.run(["git", *args], cwd=cwd, capture_output=True,
                          text=True, check=True)


def make_repo(root):
    git(root, "init", "-q")
    git(root, "config", "user.email", "t@example.com")
    git(root, "config", "user.name", "T")
    write(root, ".gitignore", "ignored/\n__pycache__/\n")
    write(root, "README.md", "hello\n")
    git(root, "add", "-A")
    git(root, "commit", "-qm", "base")
    return root


def write(root, relative, body):
    path = os.path.join(root, relative)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(body)
    return path


class DigestTest(unittest.TestCase):
    """G1b's re-registered instrument: what it hashes, and what it reports."""

    def digest(self, root):
        result = run("digest", "--repo", root)
        self.assertEqual(result.returncode, 0, result.stderr)
        return json.loads(result.stdout)

    def test_reports_digest_file_count_and_porcelain_state(self):
        with tempfile.TemporaryDirectory() as root:
            make_repo(root)
            payload = self.digest(root)
            self.assertEqual(len(payload["digest"]), 64)
            self.assertEqual(payload["files"], 2)
            self.assertTrue(payload["porcelain_clean"])
            self.assertEqual(payload["porcelain"], "")

    def test_a_pending_edit_is_reported_as_a_dirty_porcelain(self):
        with tempfile.TemporaryDirectory() as root:
            make_repo(root)
            write(root, "README.md", "edited\n")
            payload = self.digest(root)
            self.assertFalse(payload["porcelain_clean"])
            self.assertIn("README.md", payload["porcelain"])

    def test_an_untracked_but_unignored_file_counts_as_repository_content(self):
        with tempfile.TemporaryDirectory() as root:
            make_repo(root)
            before = self.digest(root)
            write(root, "NOTES.md", "new\n")
            after = self.digest(root)
            self.assertEqual(after["files"], before["files"] + 1)
            self.assertNotEqual(after["digest"], before["digest"])

    def test_an_ignored_file_is_not_repository_content(self):
        with tempfile.TemporaryDirectory() as root:
            make_repo(root)
            before = self.digest(root)
            write(root, "ignored/scratch.txt", "noise\n")
            after = self.digest(root)
            self.assertEqual(after, before)

    def test_pycache_is_excluded_even_when_the_ignore_rules_do_not_exclude_it(self):
        """The 2026-07-26 cycle's whole failure, made structural.

        A `.pyc` embeds its source's mtime, so `git checkout` of an unchanged
        file re-keys it without any process writing to the repository. G1b's
        re-registration excludes those byproducts explicitly, not by relying on
        a consumer's `.gitignore` happening to list them.
        """
        with tempfile.TemporaryDirectory() as root:
            make_repo(root)
            write(root, ".gitignore", "ignored/\n")
            git(root, "add", "-A")
            git(root, "commit", "-qm", "no pycache rule")
            before = self.digest(root)
            write(root, "pkg/__pycache__/mod.cpython-313.pyc", "\x00bytes")
            write(root, "pkg/stray.pyc", "\x00bytes")
            after = self.digest(root)
            self.assertEqual(after["digest"], before["digest"])
            self.assertEqual(after["files"], before["files"])

    def test_a_content_change_changes_the_digest(self):
        with tempfile.TemporaryDirectory() as root:
            make_repo(root)
            before = self.digest(root)
            write(root, "README.md", "hello there\n")
            self.assertNotEqual(self.digest(root)["digest"], before["digest"])

    def test_a_touched_but_unchanged_file_does_not_change_the_digest(self):
        """Content, not metadata — the instrument must not measure itself."""
        with tempfile.TemporaryDirectory() as root:
            make_repo(root)
            before = self.digest(root)
            os.utime(os.path.join(root, "README.md"), (0, 0))
            self.assertEqual(self.digest(root)["digest"], before["digest"])

    def test_git_state_alone_does_not_move_the_digest(self):
        """`.git` churns on every read; hashing it would measure the harness.

        Asking git for the content is what keeps `.git/` out — it never lists
        itself — so this pins the property rather than an exclusion rule.
        """
        with tempfile.TemporaryDirectory() as root:
            make_repo(root)
            before = self.digest(root)
            git(root, "tag", "a-tag")
            self.assertEqual(self.digest(root)["digest"], before["digest"])


class MergeTest(unittest.TestCase):
    """Folding the rounds: ordinal answers (#116) resolve to the digest key."""

    UNITS = [
        {"ordinal": 0, "digest": "a" * 64},
        {"ordinal": 1, "digest": "b" * 64},
        {"ordinal": 2, "digest": "c" * 64},
    ]

    def setUp(self):
        self.module = load_module()

    def slices(self, root, answers, name="doc.answer.json"):
        directory = os.path.join(root, "slices")
        os.makedirs(directory, exist_ok=True)
        with open(os.path.join(directory, "segments.json"), "w") as fh:
            json.dump({"documents": [{"path": "DOC.md", "units": self.UNITS}]}, fh)
        with open(os.path.join(directory, name), "w") as fh:
            json.dump({"path": "DOC.md", "verdicts": answers}, fh)
        return directory

    def merged(self, root, slices_dir, repair_dir=None):
        out = os.path.join(root, "verdicts.json")
        self.module.merge(slices_dir, repair_dir, out)
        with open(out, encoding="utf-8") as fh:
            return json.load(fh)

    def test_an_ordinal_answer_is_recorded_against_its_units_digest(self):
        with tempfile.TemporaryDirectory() as root:
            directory = self.slices(root, [{"unit": 1, "assertion_class": "factual"}])
            payload = self.merged(root, directory)
            verdicts = payload["documents"][0]["verdicts"]
            self.assertEqual([v["unit"] for v in verdicts], ["b" * 64])

    def test_a_digest_answer_is_still_accepted(self):
        with tempfile.TemporaryDirectory() as root:
            directory = self.slices(
                root, [{"unit": "c" * 64, "assertion_class": "factual"}])
            payload = self.merged(root, directory)
            self.assertEqual(
                [v["unit"] for v in payload["documents"][0]["verdicts"]],
                ["c" * 64])

    def test_an_ordinal_outside_the_documents_range_is_dropped(self):
        with tempfile.TemporaryDirectory() as root:
            directory = self.slices(root, [
                {"unit": 0, "assertion_class": "factual"},
                {"unit": 99, "assertion_class": "factual"},
            ])
            payload = self.merged(root, directory)
            self.assertEqual(
                [v["unit"] for v in payload["documents"][0]["verdicts"]],
                ["a" * 64])

    def test_a_repair_answer_overrides_the_same_unit_spelled_as_a_digest(self):
        """The two spellings must land on one key, or a repair round is a no-op."""
        with tempfile.TemporaryDirectory() as root:
            directory = self.slices(
                root, [{"unit": "a" * 64, "assertion_class": "rationale"}])
            repair = os.path.join(root, "repair")
            os.makedirs(repair)
            with open(os.path.join(repair, "doc.answer.json"), "w") as fh:
                json.dump({"path": "DOC.md",
                           "verdicts": [{"unit": 0,
                                         "assertion_class": "factual"}]}, fh)
            payload = self.merged(root, directory, repair)
            verdicts = payload["documents"][0]["verdicts"]
            self.assertEqual(len(verdicts), 1)
            self.assertEqual(verdicts[0]["assertion_class"], "factual")

    def test_a_segments_file_without_ordinals_still_merges_by_digest(self):
        """A recorded cycle predating #116 has no ordinals to resolve against.

        The module's whole purpose is re-running recorded cycles, so an older
        segments file must fold by digest rather than raise on a key the
        segmenter did not emit yet.
        """
        with tempfile.TemporaryDirectory() as root:
            directory = os.path.join(root, "slices")
            os.makedirs(directory)
            with open(os.path.join(directory, "segments.json"), "w") as fh:
                json.dump({"documents": [{"path": "DOC.md", "units": [
                    {"digest": "a" * 64}, {"digest": "b" * 64}]}]}, fh)
            with open(os.path.join(directory, "doc.answer.json"), "w") as fh:
                json.dump({"path": "DOC.md", "verdicts": [
                    {"unit": "b" * 64, "assertion_class": "factual"},
                    {"unit": 0, "assertion_class": "factual"},
                ]}, fh)
            payload = self.merged(root, directory)
            self.assertEqual(
                [v["unit"] for v in payload["documents"][0]["verdicts"]],
                ["b" * 64])

    def test_several_answer_files_for_one_document_are_folded_together(self):
        """A large document is sliced across workers; each writes its own file."""
        with tempfile.TemporaryDirectory() as root:
            directory = self.slices(
                root, [{"unit": 0, "assertion_class": "factual"}],
                name="doc-part-1.answer.json")
            with open(os.path.join(directory, "doc-part-2.answer.json"), "w") as fh:
                json.dump({"path": "DOC.md",
                           "verdicts": [{"unit": 2,
                                         "assertion_class": "normative"}]}, fh)
            payload = self.merged(root, directory)
            self.assertEqual(
                [v["unit"] for v in payload["documents"][0]["verdicts"]],
                ["a" * 64, "c" * 64])


if __name__ == "__main__":
    unittest.main(verbosity=2)
