#!/usr/bin/env python3
"""Black-box tests for detecting-doc-bloat's list-docs.py.

Tests the script as a subprocess against fixtures built in a tempdir — no
dependence on the real repo. Covers both the git ls-files path (a temp git
repo) and the non-git filesystem-walk fallback. Run:
    python3 tests/scripts/list-docs_test.py
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
    "plugins", "doc-lifecycle", "skills", "detecting-doc-bloat",
    "scripts", "list-docs.py",
)


def write(root, rel, text="x"):
    full = os.path.join(root, rel)
    os.makedirs(os.path.dirname(full), exist_ok=True)
    with open(full, "w", encoding="utf-8") as f:
        f.write(text)


def git_init(root):
    env = {**os.environ,
           "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@t",
           "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@t"}
    subprocess.run(["git", "init", "-q"], cwd=root, check=True, env=env)
    subprocess.run(["git", "add", "-A"], cwd=root, check=True, env=env)
    subprocess.run(["git", "commit", "-qm", "init"], cwd=root, check=True, env=env)


def run(root, config=None, with_lines=False):
    cmd = [sys.executable, SCRIPT, "--root", root]
    if config is not None:
        cmd += ["--config", config]
    if with_lines:
        cmd += ["--with-lines"]
    return subprocess.run(cmd, capture_output=True, text=True)


def lines(result):
    return [l for l in result.stdout.splitlines() if l]


class Defaults(unittest.TestCase):
    def build(self, root):
        write(root, "README.md")
        write(root, "docs/guide.md")
        write(root, "src/app.py")
        write(root, "notes.txt")

    def test_git_path_finds_md_only(self):
        with tempfile.TemporaryDirectory() as root:
            self.build(root)
            git_init(root)
            r = run(root)
            self.assertEqual(r.returncode, 0, r.stderr)
            self.assertEqual(lines(r), ["README.md", "docs/guide.md"])

    def test_fallback_walk_finds_md_only(self):
        with tempfile.TemporaryDirectory() as root:
            self.build(root)  # no git init => filesystem-walk fallback
            r = run(root)
            self.assertEqual(r.returncode, 0, r.stderr)
            self.assertEqual(lines(r), ["README.md", "docs/guide.md"])

    def test_output_is_sorted(self):
        with tempfile.TemporaryDirectory() as root:
            write(root, "zed.md")
            write(root, "alpha.md")
            write(root, "mid/beta.md")
            git_init(root)
            r = run(root)
            self.assertEqual(lines(r), ["alpha.md", "mid/beta.md", "zed.md"])

    def test_case_insensitive_extension(self):
        with tempfile.TemporaryDirectory() as root:
            write(root, "READ.MD")
            git_init(root)
            r = run(root)
            self.assertEqual(lines(r), ["READ.MD"])


class WithLines(unittest.TestCase):
    def test_shape_and_counts(self):
        with tempfile.TemporaryDirectory() as root:
            write(root, "README.md", "a\nb\nc")     # 3 lines
            write(root, "docs/guide.md", "x\ny")     # 2 lines
            git_init(root)
            r = run(root, with_lines=True)
            self.assertEqual(r.returncode, 0, r.stderr)
            self.assertEqual(
                lines(r), ["README.md\t3", "docs/guide.md\t2"])

    def test_sorted_by_count_desc_then_path_asc(self):
        with tempfile.TemporaryDirectory() as root:
            write(root, "big.md", "1\n2\n3\n4")       # 4 lines
            write(root, "zed.md", "1\n2")             # 2 lines, tie
            write(root, "alpha.md", "1\n2")           # 2 lines, tie
            git_init(root)
            r = run(root, with_lines=True)
            # 4 lines first; the two 2-line docs tie-broken by path ascending.
            self.assertEqual(
                lines(r), ["big.md\t4", "alpha.md\t2", "zed.md\t2"])

    def test_exclude_include_still_apply(self):
        with tempfile.TemporaryDirectory() as root:
            write(root, "README.md", "a\nb")
            write(root, "tests/baselines/red/a.md", "x")
            write(root, "Makefile", "m1\nm2\nm3")
            git_init(root)
            cfg = os.path.join(root, "scope.json")
            with open(cfg, "w") as f:
                json.dump({"exclude": ["tests/**"], "include": ["Makefile"]}, f)
            r = run(root, cfg, with_lines=True)
            self.assertEqual(r.returncode, 0, r.stderr)
            # tests/** excluded; Makefile force-included; README kept.
            self.assertEqual(
                lines(r), ["Makefile\t3", "README.md\t2"])

    def test_default_output_is_paths_only(self):
        with tempfile.TemporaryDirectory() as root:
            write(root, "README.md", "a\nb\nc")
            git_init(root)
            r = run(root)  # no --with-lines
            self.assertEqual(r.returncode, 0, r.stderr)
            self.assertEqual(lines(r), ["README.md"])
            self.assertNotIn("\t", r.stdout)


class ExcludeInclude(unittest.TestCase):
    def build(self, root):
        write(root, "README.md")
        write(root, "docs/guide.md")
        write(root, "tests/baselines/red/a.md")
        write(root, "tests/fixtures/b.md")

    def test_exclude_double_star_drops_subtree(self):
        with tempfile.TemporaryDirectory() as root:
            self.build(root)
            git_init(root)
            cfg = os.path.join(root, "scope.json")
            with open(cfg, "w") as f:
                json.dump({"exclude": ["tests/**"]}, f)
            r = run(root, cfg)
            self.assertEqual(r.returncode, 0, r.stderr)
            self.assertEqual(lines(r), ["README.md", "docs/guide.md"])

    def test_exclude_single_star_stays_in_segment(self):
        with tempfile.TemporaryDirectory() as root:
            write(root, "a.md")
            write(root, "docs/a.md")
            git_init(root)
            cfg = os.path.join(root, "scope.json")
            with open(cfg, "w") as f:
                json.dump({"exclude": ["*.md"]}, f)  # '*' should not cross '/'
            r = run(root, cfg)
            # Only top-level a.md is dropped; docs/a.md survives.
            self.assertEqual(lines(r), ["docs/a.md"])

    def test_include_re_adds_excluded_path(self):
        with tempfile.TemporaryDirectory() as root:
            self.build(root)
            git_init(root)
            cfg = os.path.join(root, "scope.json")
            with open(cfg, "w") as f:
                json.dump({"exclude": ["tests/**"],
                           "include": ["tests/fixtures/b.md"]}, f)
            r = run(root, cfg)
            self.assertEqual(
                lines(r),
                ["README.md", "docs/guide.md", "tests/fixtures/b.md"])

    def test_include_force_adds_non_md(self):
        with tempfile.TemporaryDirectory() as root:
            write(root, "README.md")
            write(root, "Makefile")
            git_init(root)
            cfg = os.path.join(root, "scope.json")
            with open(cfg, "w") as f:
                json.dump({"include": ["Makefile"]}, f)
            r = run(root, cfg)
            self.assertEqual(lines(r), ["Makefile", "README.md"])

    def test_empty_config_object_is_defaults(self):
        with tempfile.TemporaryDirectory() as root:
            self.build(root)
            git_init(root)
            cfg = os.path.join(root, "scope.json")
            with open(cfg, "w") as f:
                json.dump({}, f)
            r = run(root, cfg)
            self.assertEqual(r.returncode, 0, r.stderr)
            self.assertEqual(len(lines(r)), 4)


class ConfigDiscovery(unittest.TestCase):
    def test_default_path_discovered(self):
        with tempfile.TemporaryDirectory() as root:
            write(root, "README.md")
            write(root, "tests/x.md")
            write(root, ".github/doc-sync/audit-scope.json",
                  json.dumps({"exclude": ["tests/**"]}))
            git_init(root)
            r = run(root)  # no --config; default path used
            self.assertEqual(r.returncode, 0, r.stderr)
            self.assertEqual(lines(r), ["README.md"])

    def test_missing_config_uses_defaults(self):
        with tempfile.TemporaryDirectory() as root:
            write(root, "README.md")
            git_init(root)
            # No config file anywhere.
            r = run(root, os.path.join(root, "does-not-exist.json"))
            self.assertEqual(r.returncode, 0, r.stderr)
            self.assertEqual(lines(r), ["README.md"])


class MalformedConfig(unittest.TestCase):
    def test_bad_json_exits_nonzero(self):
        with tempfile.TemporaryDirectory() as root:
            write(root, "README.md")
            git_init(root)
            cfg = os.path.join(root, "scope.json")
            with open(cfg, "w") as f:
                f.write("{not json")
            r = run(root, cfg)
            self.assertNotEqual(r.returncode, 0)
            self.assertIn("scope.json", r.stderr)

    def test_non_list_exclude_exits_nonzero(self):
        with tempfile.TemporaryDirectory() as root:
            write(root, "README.md")
            git_init(root)
            cfg = os.path.join(root, "scope.json")
            with open(cfg, "w") as f:
                json.dump({"exclude": "tests/**"}, f)
            r = run(root, cfg)
            self.assertNotEqual(r.returncode, 0)
            self.assertIn("exclude", r.stderr)

    def test_non_list_include_exits_nonzero(self):
        with tempfile.TemporaryDirectory() as root:
            write(root, "README.md")
            git_init(root)
            cfg = os.path.join(root, "scope.json")
            with open(cfg, "w") as f:
                json.dump({"include": {"a": 1}}, f)
            r = run(root, cfg)
            self.assertNotEqual(r.returncode, 0)
            self.assertIn("include", r.stderr)


if __name__ == "__main__":
    unittest.main()
