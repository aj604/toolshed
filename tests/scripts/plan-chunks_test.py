#!/usr/bin/env python3
"""Black-box tests for detecting-doc-bloat's plan-chunks.py.

Tests the script as a subprocess against fixtures built in a tempdir — no
dependence on the real repo except FixtureEndToEnd, which pins the committed
plan-swarm fixture. Covers the inventory layer absorbed from list-docs.py
(git ls-files path and walk fallback, exclude/include globs), doc-kind hints,
affinity grouping under the caps, policy-scope chunks, resume planning, and
the max_chunks ceiling. Run: python3 tests/scripts/plan-chunks_test.py
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
    "scripts", "plan-chunks.py",
)


def write(root, rel, text="x"):
    full = os.path.join(root, rel)
    os.makedirs(os.path.dirname(full) or full, exist_ok=True)
    with open(full, "w", encoding="utf-8") as f:
        f.write(text)


def git_init(root):
    env = {**os.environ,
           "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@t",
           "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@t"}
    subprocess.run(["git", "init", "-q"], cwd=root, check=True, env=env)
    subprocess.run(["git", "add", "-A"], cwd=root, check=True, env=env)
    subprocess.run(["git", "commit", "-qm", "init"], cwd=root, check=True, env=env)


def config(root, obj, name="scope.json"):
    path = os.path.join(root, name)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(obj, f)
    return path


def run(root, cfg=None, results_dir=None, out=None):
    cmd = [sys.executable, SCRIPT, "--root", root]
    if cfg is not None:
        cmd += ["--config", cfg]
    if results_dir is not None:
        cmd += ["--results-dir", results_dir]
    if out is not None:
        cmd += ["--out", out]
    return subprocess.run(cmd, capture_output=True, text=True)


def manifest(result):
    return json.loads(result.stdout)


def sweep_chunks(m):
    return [c for c in m["chunks"] if c["kind"] == "sweep"]


def policy_chunks(m):
    return [c for c in m["chunks"] if c["kind"] == "policy"]


def paths_of(chunk):
    return [d["path"] for d in chunk["docs"]]


def all_sweep_paths(m):
    return sorted(p for c in sweep_chunks(m) for p in paths_of(c))


class InventoryDefaults(unittest.TestCase):
    def build(self, root):
        write(root, "README.md")
        write(root, "docs/guide.md")
        write(root, "src/app.py")
        write(root, "notes.txt")

    def test_md_only_git_path(self):
        with tempfile.TemporaryDirectory() as root:
            self.build(root)
            git_init(root)
            r = run(root)
            self.assertEqual(r.returncode, 0, r.stderr)
            self.assertEqual(all_sweep_paths(manifest(r)),
                             ["README.md", "docs/guide.md"])

    def test_md_only_walk_fallback(self):
        with tempfile.TemporaryDirectory() as root:
            self.build(root)  # no git init => filesystem-walk fallback
            r = run(root)
            self.assertEqual(r.returncode, 0, r.stderr)
            self.assertEqual(all_sweep_paths(manifest(r)),
                             ["README.md", "docs/guide.md"])

    def test_exclude_include_whitelist_wins(self):
        with tempfile.TemporaryDirectory() as root:
            self.build(root)
            write(root, "tests/baselines/red/a.md")
            write(root, "tests/fixtures/b.md")
            write(root, "Makefile", "m1\nm2")
            git_init(root)
            cfg = config(root, {"exclude": ["tests/**"],
                                "include": ["tests/fixtures/b.md", "Makefile"]})
            r = run(root, cfg)
            self.assertEqual(r.returncode, 0, r.stderr)
            self.assertEqual(all_sweep_paths(manifest(r)),
                             ["Makefile", "README.md", "docs/guide.md",
                              "tests/fixtures/b.md"])

    def test_stdout_is_pure_json_report_on_stderr(self):
        with tempfile.TemporaryDirectory() as root:
            self.build(root)
            git_init(root)
            r = run(root)
            self.assertEqual(r.returncode, 0, r.stderr)
            m = manifest(r)  # would raise if stdout were not pure JSON
            self.assertEqual(m["schema"], 1)
            self.assertIn("doc(s)", r.stderr)
            self.assertIn("chunk(s)", r.stderr)

    def test_out_writes_file_instead_of_stdout(self):
        with tempfile.TemporaryDirectory() as root:
            self.build(root)
            git_init(root)
            out = os.path.join(root, "manifest.json")
            r = run(root, out=out)
            self.assertEqual(r.returncode, 0, r.stderr)
            self.assertEqual(r.stdout, "")
            with open(out, encoding="utf-8") as f:
                m = json.load(f)
            self.assertEqual(m["schema"], 1)


class Hints(unittest.TestCase):
    def hint_of(self, m, path):
        for c in sweep_chunks(m):
            for d in c["docs"]:
                if d["path"] == path:
                    return d["hint"]
        raise AssertionError(f"{path} not in any sweep chunk")

    def test_as_of_anchor_is_narrative_wherever_it_sits(self):
        with tempfile.TemporaryDirectory() as root:
            write(root, "docs/plans/walkthrough.md", "> As of 2026-01-01 (x)\n\nbody")
            git_init(root)
            r = run(root)
            self.assertEqual(self.hint_of(manifest(r), "docs/plans/walkthrough.md"),
                             "narrative")

    def test_plans_or_specs_segment_is_planning(self):
        with tempfile.TemporaryDirectory() as root:
            write(root, "docs/plans/a.md", "# a design")
            write(root, "specs/b.md", "# b spec")
            write(root, "docs/plansX/c.md", "# not plans")
            git_init(root)
            m = manifest(run(root))
            self.assertEqual(self.hint_of(m, "docs/plans/a.md"), "planning")
            self.assertEqual(self.hint_of(m, "specs/b.md"), "planning")
            self.assertEqual(self.hint_of(m, "docs/plansX/c.md"), "living")

    def test_everything_else_is_living(self):
        with tempfile.TemporaryDirectory() as root:
            write(root, "README.md", "# readme")
            write(root, "docs/guide.md", "# guide")
            git_init(root)
            m = manifest(run(root))
            self.assertEqual(self.hint_of(m, "README.md"), "living")
            self.assertEqual(self.hint_of(m, "docs/guide.md"), "living")

    def test_docs_carry_line_counts(self):
        with tempfile.TemporaryDirectory() as root:
            write(root, "README.md", "a\nb\nc")
            git_init(root)
            m = manifest(run(root))
            (chunk,) = sweep_chunks(m)
            self.assertEqual(chunk["docs"][0]["lines"], 3)


class MalformedConfig(unittest.TestCase):
    def assert_config_error(self, root, obj_or_text, fragment):
        cfg = os.path.join(root, "scope.json")
        with open(cfg, "w", encoding="utf-8") as f:
            if isinstance(obj_or_text, str):
                f.write(obj_or_text)
            else:
                json.dump(obj_or_text, f)
        r = run(root, cfg)
        self.assertEqual(r.returncode, 2, r.stdout + r.stderr)
        self.assertIn(fragment, r.stderr)

    def test_malformed_cases(self):
        with tempfile.TemporaryDirectory() as root:
            write(root, "README.md")
            git_init(root)
            self.assert_config_error(root, "{not json", "scope.json")
            self.assert_config_error(root, {"exclude": "tests/**"}, "exclude")
            self.assert_config_error(root, {"include": {"a": 1}}, "include")
            self.assert_config_error(root, {"policy_scope": "docs"}, "policy_scope")
            self.assert_config_error(root, {"chunking": []}, "chunking")
            self.assert_config_error(root, {"chunking": {"max_docs": 0}}, "max_docs")
            self.assert_config_error(
                root, {"chunking": {"max_chunks": "many"}}, "max_chunks")

    def test_missing_config_uses_defaults(self):
        with tempfile.TemporaryDirectory() as root:
            write(root, "README.md")
            git_init(root)
            r = run(root, os.path.join(root, "does-not-exist.json"))
            self.assertEqual(r.returncode, 0, r.stderr)

    def test_default_config_path_discovered(self):
        with tempfile.TemporaryDirectory() as root:
            write(root, "README.md")
            write(root, "tests/x.md")
            write(root, ".github/doc-sync/audit-scope.json",
                  json.dumps({"exclude": ["tests/**"]}))
            git_init(root)
            r = run(root)  # no --config
            self.assertEqual(r.returncode, 0, r.stderr)
            self.assertEqual(all_sweep_paths(manifest(r)), ["README.md"])


class Grouping(unittest.TestCase):
    def test_max_docs_splits_a_directory(self):
        with tempfile.TemporaryDirectory() as root:
            for i in range(7):
                write(root, f"docs/d{i}.md", "line")
            git_init(root)
            cfg = config(root, {"chunking": {"max_docs": 3}})
            m = manifest(run(root, cfg))
            sizes = [len(paths_of(c)) for c in sweep_chunks(m)]
            self.assertEqual(sorted(sizes, reverse=True), [3, 3, 1])
            for c in sweep_chunks(m):
                self.assertEqual(paths_of(c), sorted(paths_of(c)))

    def test_max_lines_splits_and_oversized_doc_isolated(self):
        with tempfile.TemporaryDirectory() as root:
            write(root, "docs/big.md", "\n".join("x" * 1 for _ in range(25)))
            write(root, "docs/s1.md", "\n".join(["y"] * 6))
            write(root, "docs/s2.md", "\n".join(["z"] * 6))
            git_init(root)
            cfg = config(root, {"chunking": {"max_lines": 10}})
            m = manifest(run(root, cfg))
            for c in sweep_chunks(m):
                if "docs/big.md" in paths_of(c):
                    self.assertEqual(paths_of(c), ["docs/big.md"])

    def test_different_hints_never_share_a_chunk(self):
        with tempfile.TemporaryDirectory() as root:
            write(root, "docs/x.md", "# living")
            write(root, "docs/plans/p.md", "# a plan")
            git_init(root)
            m = manifest(run(root))
            for c in sweep_chunks(m):
                hints = {d["hint"] for d in c["docs"]}
                self.assertEqual(len(hints), 1)
            self.assertEqual(len(sweep_chunks(m)), 2)

    def test_same_hint_small_dirs_coalesce_under_caps(self):
        with tempfile.TemporaryDirectory() as root:
            write(root, "a/x.md", "# x")
            write(root, "b/y.md", "# y")
            git_init(root)
            m = manifest(run(root))
            self.assertEqual(len(sweep_chunks(m)), 1)
            self.assertEqual(all_sweep_paths(m), ["a/x.md", "b/y.md"])

    def test_ids_deterministic_and_membership_addressed(self):
        with tempfile.TemporaryDirectory() as root:
            write(root, "a/x.md", "# x")
            write(root, "b/y.md", "# y")
            git_init(root)
            ids1 = [c["id"] for c in manifest(run(root))["chunks"]]
            ids2 = [c["id"] for c in manifest(run(root))["chunks"]]
            self.assertEqual(ids1, ids2)
            write(root, "b/z.md", "# z")
            git_init_add = subprocess.run(
                ["git", "add", "-A"], cwd=root, capture_output=True)
            self.assertEqual(git_init_add.returncode, 0)
            ids3 = [c["id"] for c in manifest(run(root))["chunks"]]
            self.assertNotEqual(ids1, ids3)


class PolicyChunks(unittest.TestCase):
    def swarm(self, root):
        for i in range(10):
            write(root, f"docs/superpowers/plans/p{i}.md", "# ephemeral")
        write(root, "README.md", "# readme")

    def test_policy_dir_becomes_single_chunk_with_files(self):
        with tempfile.TemporaryDirectory() as root:
            self.swarm(root)
            git_init(root)
            cfg = config(root, {"policy_scope": ["docs/superpowers"]})
            m = manifest(run(root, cfg))
            (p,) = policy_chunks(m)
            self.assertEqual(p["dir"], "docs/superpowers")
            self.assertEqual(len(p["files"]), 10)
            self.assertEqual(p["files"], sorted(p["files"]))
            self.assertEqual(all_sweep_paths(m), ["README.md"])

    def test_policy_scope_respects_exclude(self):
        with tempfile.TemporaryDirectory() as root:
            self.swarm(root)
            git_init(root)
            cfg = config(root, {"policy_scope": ["docs/superpowers"],
                                "exclude": ["docs/superpowers/plans/p0.md"]})
            m = manifest(run(root, cfg))
            (p,) = policy_chunks(m)
            self.assertEqual(len(p["files"]), 9)
            self.assertNotIn("docs/superpowers/plans/p0.md", p["files"])

    def test_declared_dir_with_no_docs_notes_and_omits(self):
        with tempfile.TemporaryDirectory() as root:
            write(root, "README.md", "# readme")
            git_init(root)
            cfg = config(root, {"policy_scope": ["docs/empty"]})
            r = run(root, cfg)
            self.assertEqual(r.returncode, 0, r.stderr)
            self.assertEqual(policy_chunks(manifest(r)), [])
            self.assertIn("docs/empty", r.stderr)

    def test_longest_prefix_wins_for_nested_scopes(self):
        with tempfile.TemporaryDirectory() as root:
            write(root, "docs/superpowers/plans/a.md", "# a")
            write(root, "docs/superpowers/specs/b.md", "# b")
            git_init(root)
            cfg = config(root, {"policy_scope": ["docs/superpowers",
                                                 "docs/superpowers/specs"]})
            m = manifest(run(root, cfg))
            by_dir = {p["dir"]: p["files"] for p in policy_chunks(m)}
            self.assertEqual(by_dir["docs/superpowers"],
                             ["docs/superpowers/plans/a.md"])
            self.assertEqual(by_dir["docs/superpowers/specs"],
                             ["docs/superpowers/specs/b.md"])


class ResumeAndCeiling(unittest.TestCase):
    def test_pending_excludes_chunks_with_results(self):
        with tempfile.TemporaryDirectory() as root:
            write(root, "a/x.md", "# x")
            write(root, "docs/plans/p.md", "# plan")
            git_init(root)
            m1 = manifest(run(root))
            self.assertEqual(len(m1["chunks"]), 2)
            done_id = m1["chunks"][0]["id"]
            results = os.path.join(root, "chunks")
            os.makedirs(results)
            write(root, f"chunks/{done_id}.json",
                  json.dumps({"chunk": done_id, "records": []}))
            r = run(root, results_dir=results)
            m2 = manifest(r)
            self.assertEqual(len(m2["chunks"]), 2)  # chunks always complete
            self.assertNotIn(done_id, m2["pending"])
            self.assertEqual(len(m2["pending"]), 1)
            self.assertIn("resume", r.stderr)

    def test_pending_equals_all_ids_without_results_dir(self):
        with tempfile.TemporaryDirectory() as root:
            write(root, "a/x.md", "# x")
            git_init(root)
            m = manifest(run(root))
            self.assertEqual(m["pending"], [c["id"] for c in m["chunks"]])

    def test_max_chunks_ceiling_exits_2(self):
        with tempfile.TemporaryDirectory() as root:
            for d in ("a", "b", "c", "d", "e"):
                write(root, f"{d}/x.md", "# x")
            git_init(root)
            cfg = config(root, {"chunking": {"max_docs": 1, "max_chunks": 2}})
            r = run(root, cfg)
            self.assertEqual(r.returncode, 2, r.stdout + r.stderr)
            self.assertIn("max_chunks", r.stderr)
            self.assertIn("5", r.stderr)


def run_emit(root, manifest_path, flag, chunk_id):
    return subprocess.run(
        [sys.executable, SCRIPT, "--root", root, flag, chunk_id,
         "--manifest", manifest_path],
        capture_output=True, text=True)


class ContentAddressedIds(unittest.TestCase):
    def test_content_edit_changes_chunk_id_even_at_same_line_count(self):
        with tempfile.TemporaryDirectory() as root:
            write(root, "docs/a.md", "alpha\nbeta")
            git_init(root)
            id1 = manifest(run(root))["chunks"][0]["id"]
            write(root, "docs/a.md", "alpha\nbetX")  # same path, same 2 lines
            id2 = manifest(run(root))["chunks"][0]["id"]
            self.assertNotEqual(id1, id2)

    def test_content_edit_invalidates_prior_result_on_resume(self):
        with tempfile.TemporaryDirectory() as root:
            write(root, "docs/a.md", "alpha")
            git_init(root)
            m1 = manifest(run(root))
            done_id = m1["chunks"][0]["id"]
            results = os.path.join(root, "chunks")
            os.makedirs(results)
            write(root, f"chunks/{done_id}.json", "{}")
            write(root, "docs/a.md", "alpha edited")
            m2 = manifest(run(root, results_dir=results))
            self.assertEqual(m2["pending"], [m2["chunks"][0]["id"]])

    def test_resume_ignores_garbage_or_mismatched_result_files(self):
        # An invalid result that survived a failed CI retry must not mask the
        # chunk as done — resume trusts a result only if it parses and names
        # this chunk.
        with tempfile.TemporaryDirectory() as root:
            write(root, "docs/a.md", "alpha")
            git_init(root)
            m1 = manifest(run(root))
            cid = m1["chunks"][0]["id"]
            results = os.path.join(root, "chunks")
            os.makedirs(results)
            write(root, f"chunks/{cid}.json", "{not json")
            m2 = manifest(run(root, results_dir=results))
            self.assertEqual(m2["pending"], [cid])
            write(root, f"chunks/{cid}.json",
                  json.dumps({"chunk": "c-someoneelse", "records": []}))
            m3 = manifest(run(root, results_dir=results))
            self.assertEqual(m3["pending"], [cid])
            write(root, f"chunks/{cid}.json",
                  json.dumps({"chunk": cid, "records": []}))
            m4 = manifest(run(root, results_dir=results))
            self.assertEqual(m4["pending"], [])

    def test_unchanged_tree_yields_stable_ids_without_git(self):
        with tempfile.TemporaryDirectory() as root:
            write(root, "docs/a.md", "alpha")  # walk fallback, no git
            id1 = manifest(run(root))["chunks"][0]["id"]
            id2 = manifest(run(root))["chunks"][0]["id"]
            self.assertEqual(id1, id2)


class TurnBudgets(unittest.TestCase):
    def turns_of(self, m, member_path):
        for c in m["chunks"]:
            paths = (c["files"] if c["kind"] == "policy"
                     else [d["path"] for d in c["docs"]])
            if member_path in paths:
                return c["turns"]
        raise AssertionError(f"{member_path} not in any chunk")

    def test_small_living_chunk_clamps_to_floor_20(self):
        with tempfile.TemporaryDirectory() as root:
            write(root, "docs/a.md", "x")  # 12 + 2*1 = 14 -> clamp 20
            git_init(root)
            m = manifest(run(root))
            self.assertEqual(self.turns_of(m, "docs/a.md"), 20)

    def test_planning_docs_cost_more_per_doc(self):
        with tempfile.TemporaryDirectory() as root:
            for i in range(6):  # 12 + 4*6 = 36, no line bonus
                write(root, f"docs/plans/p{i}.md", "one line")
            git_init(root)
            m = manifest(run(root))
            self.assertEqual(self.turns_of(m, "docs/plans/p0.md"), 36)

    def test_line_volume_adds_one_turn_per_full_600_lines(self):
        with tempfile.TemporaryDirectory() as root:
            # single planning doc, 1250 lines: 12 + 4 + 2 = 18 -> clamp 20;
            # use 8 living docs of 300 lines: 12 + 16 + 4 = 32
            for i in range(8):
                write(root, f"docs/d{i}.md", "\n".join(["x"] * 300))
            git_init(root)
            cfg = config(root, {"chunking": {"max_lines": 2400}})
            m = manifest(run(root, cfg))
            self.assertEqual(self.turns_of(m, "docs/d0.md"), 32)

    def test_ceiling_clamps_to_40(self):
        with tempfile.TemporaryDirectory() as root:
            for i in range(8):  # planning: 12 + 4*8 = 44 -> clamp 40
                write(root, f"docs/plans/p{i}.md", "one line")
            git_init(root)
            m = manifest(run(root))
            self.assertEqual(self.turns_of(m, "docs/plans/p0.md"), 40)

    def test_policy_chunk_gets_flat_20(self):
        with tempfile.TemporaryDirectory() as root:
            for i in range(30):
                write(root, f"docs/superpowers/plans/p{i}.md", "# e")
            git_init(root)
            cfg = config(root, {"policy_scope": ["docs/superpowers"]})
            m = manifest(run(root, cfg))
            self.assertEqual(
                self.turns_of(m, "docs/superpowers/plans/p0.md"), 20)


class EmitPrompt(unittest.TestCase):
    def plan_to_file(self, root):
        out = os.path.join(root, "manifest.json")
        r = run(root, out=out)
        assert r.returncode == 0, r.stderr
        with open(out, encoding="utf-8") as f:
            return out, json.load(f)

    def test_sweep_prompt_carries_slice_verbatim_no_manifest_hunt(self):
        with tempfile.TemporaryDirectory() as root:
            write(root, "docs/plans/p.md", "\n".join(["x"] * 40))
            write(root, "docs/guide.md", "# guide")
            git_init(root)
            path, m = self.plan_to_file(root)
            chunk = next(c for c in m["chunks"]
                         if c["docs"][0]["path"] == "docs/plans/p.md")
            r = run_emit(root, path, "--emit-prompt", chunk["id"])
            self.assertEqual(r.returncode, 0, r.stderr)
            prompt = r.stdout
            self.assertIn("docs/plans/p.md", prompt)
            self.assertIn("40", prompt)          # line count shown
            self.assertIn("planning", prompt)    # hint shown
            self.assertIn(f"chunks/{chunk['id']}.json", prompt)
            self.assertIn("doc-lifecycle:detecting-doc-bloat", prompt)
            self.assertNotIn("manifest.json", prompt)
            self.assertNotIn("docs/guide.md", prompt)  # other chunks excluded

    def test_policy_prompt_lists_files_verbatim_and_names_policy(self):
        with tempfile.TemporaryDirectory() as root:
            for i in range(3):
                write(root, f"docs/superpowers/plans/p{i}.md", "# e")
            write(root, ".github/doc-sync/audit-scope.json",
                  json.dumps({"policy_scope": ["docs/superpowers"]}))
            git_init(root)
            path, m = self.plan_to_file(root)
            (p,) = [c for c in m["chunks"] if c["kind"] == "policy"]
            r = run_emit(root, path, "--emit-prompt", p["id"])
            self.assertEqual(r.returncode, 0, r.stderr)
            self.assertIn("POLICY", r.stdout)
            self.assertIn("docs/superpowers", r.stdout)
            for i in range(3):
                self.assertIn(f"docs/superpowers/plans/p{i}.md", r.stdout)
            # Same scope fence as the sweep prompt — GREEN run (b) showed an
            # executor enumerating the tree when the policy variant lacked it.
            self.assertIn("do not enumerate", r.stdout)

    def test_emit_turns_prints_the_budget(self):
        with tempfile.TemporaryDirectory() as root:
            write(root, "docs/a.md", "x")
            git_init(root)
            path, m = self.plan_to_file(root)
            r = run_emit(root, path, "--emit-turns", m["chunks"][0]["id"])
            self.assertEqual(r.returncode, 0, r.stderr)
            self.assertEqual(r.stdout.strip(), str(m["chunks"][0]["turns"]))

    def test_unknown_chunk_id_exits_2_naming_it(self):
        with tempfile.TemporaryDirectory() as root:
            write(root, "docs/a.md", "x")
            git_init(root)
            path, _ = self.plan_to_file(root)
            r = run_emit(root, path, "--emit-prompt", "c-nope")
            self.assertEqual(r.returncode, 2)
            self.assertIn("c-nope", r.stderr)


class FixtureEndToEnd(unittest.TestCase):
    def test_plan_swarm_fixture_plans_as_answer_key_says(self):
        root = os.path.normpath(os.path.join(
            os.path.dirname(__file__), "..", "fixtures", "plan-swarm"))
        r = run(root)
        self.assertEqual(r.returncode, 0, r.stderr)
        m = manifest(r)
        policy = policy_chunks(m)
        self.assertEqual(len(policy), 1)
        self.assertEqual(policy[0]["dir"], "docs/superpowers")
        self.assertEqual(len(policy[0]["files"]), 10)
        sweep = sweep_chunks(m)
        self.assertEqual(len(sweep), 3)
        self.assertEqual(len(m["pending"]), 4)


if __name__ == "__main__":
    unittest.main()
