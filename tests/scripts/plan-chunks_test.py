#!/usr/bin/env python3
"""Black-box tests for detecting-doc-bloat's plan-chunks.py.

Tests the script as a subprocess against fixtures built in a tempdir — no
dependence on the real repo except FixtureEndToEnd, which pins the committed
plan-swarm fixture. Covers the inventory layer absorbed from list-docs.py
(git ls-files path and walk fallback, exclude/include globs), doc-kind hints,
affinity grouping under the caps, resume planning, the max_chunks ceiling, and
the retired `policy_scope` knob (noted, never a chunk kind).
Run: python3 tests/scripts/plan-chunks_test.py
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


def paths_of(chunk):
    return [d["path"] for d in chunk["docs"]]


def all_paths(m):
    return sorted(p for c in m["chunks"] for p in paths_of(c))


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
            self.assertEqual(all_paths(manifest(r)),
                             ["README.md", "docs/guide.md"])

    def test_md_only_walk_fallback(self):
        with tempfile.TemporaryDirectory() as root:
            self.build(root)  # no git init => filesystem-walk fallback
            r = run(root)
            self.assertEqual(r.returncode, 0, r.stderr)
            self.assertEqual(all_paths(manifest(r)),
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
            self.assertEqual(all_paths(manifest(r)),
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
        for c in m["chunks"]:
            for d in c["docs"]:
                if d["path"] == path:
                    return d["hint"]
        raise AssertionError(f"{path} not in any chunk")

    def test_as_of_anchor_is_narrative_wherever_it_sits(self):
        with tempfile.TemporaryDirectory() as root:
            write(root, "docs/plans/walkthrough.md", "> As of 2026-01-01 (x)\n\nbody")
            git_init(root)
            r = run(root)
            self.assertEqual(self.hint_of(manifest(r), "docs/plans/walkthrough.md"),
                             "narrative")

    def test_as_of_anchor_under_title_is_narrative(self):
        # growing-docs' template places the anchor on the first line UNDER the
        # title; the hint must accept that placement, not just file-first-line.
        with tempfile.TemporaryDirectory() as root:
            write(root, "docs/guides/g.md", "# Guide\n\n> As of 2026-01-01 (x)\n\nbody")
            write(root, "docs/guides/h.md", "# Guide\n\nplain prose, no anchor")
            git_init(root)
            m = manifest(run(root))
            self.assertEqual(self.hint_of(m, "docs/guides/g.md"), "narrative")
            self.assertEqual(self.hint_of(m, "docs/guides/h.md"), "living")

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
            (chunk,) = m["chunks"]
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
            write(root, ".doc-lifecycle/audit-scope.json",
                  json.dumps({"exclude": ["tests/**"]}))
            git_init(root)
            r = run(root)  # no --config
            self.assertEqual(r.returncode, 0, r.stderr)
            self.assertEqual(all_paths(manifest(r)), ["README.md"])


class RetiredPolicyScope(unittest.TestCase):
    """`policy_scope` retired with POLICY; a declaring install still plans."""

    def swarm(self, root):
        for i in range(4):
            write(root, f"docs/superpowers/plans/p{i}.md", "# ephemeral")
        write(root, "README.md", "# readme")

    def test_declared_policy_scope_is_noted_and_its_docs_are_swept(self):
        with tempfile.TemporaryDirectory() as root:
            self.swarm(root)
            git_init(root)
            cfg = config(root, {"policy_scope": ["docs/superpowers"]})
            r = run(root, cfg)
            self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
            self.assertIn("policy_scope", r.stderr)
            self.assertIn("RETIRE-DOC", r.stderr)
            m = manifest(r)
            self.assertEqual(all_paths(m), sorted(
                ["README.md"] + [f"docs/superpowers/plans/p{i}.md"
                                 for i in range(4)]))
            for c in m["chunks"]:
                self.assertNotIn("kind", c)
                self.assertNotIn("files", c)
                self.assertNotIn("dir", c)

    def test_a_non_list_policy_scope_is_ignored_not_fatal(self):
        # The knob is dead: no shape of it may fail a run that would otherwise
        # plan, because a consumer's audit-scope.json is never rewritten for them.
        with tempfile.TemporaryDirectory() as root:
            write(root, "README.md", "# readme")
            git_init(root)
            cfg = config(root, {"policy_scope": "docs/superpowers"})
            r = run(root, cfg)
            self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
            self.assertIn("policy_scope", r.stderr)


class Grouping(unittest.TestCase):
    def test_max_docs_splits_a_directory(self):
        with tempfile.TemporaryDirectory() as root:
            for i in range(7):
                write(root, f"docs/d{i}.md", "line")
            git_init(root)
            cfg = config(root, {"chunking": {"max_docs": 3}})
            m = manifest(run(root, cfg))
            sizes = [len(paths_of(c)) for c in m["chunks"]]
            self.assertEqual(sorted(sizes, reverse=True), [3, 3, 1])
            for c in m["chunks"]:
                self.assertEqual(paths_of(c), sorted(paths_of(c)))

    def test_max_lines_splits_and_oversized_doc_isolated(self):
        with tempfile.TemporaryDirectory() as root:
            write(root, "docs/big.md", "\n".join("x" * 1 for _ in range(25)))
            write(root, "docs/s1.md", "\n".join(["y"] * 6))
            write(root, "docs/s2.md", "\n".join(["z"] * 6))
            git_init(root)
            cfg = config(root, {"chunking": {"max_lines": 10}})
            m = manifest(run(root, cfg))
            for c in m["chunks"]:
                if "docs/big.md" in paths_of(c):
                    self.assertEqual(paths_of(c), ["docs/big.md"])

    def test_different_hints_never_share_a_chunk(self):
        with tempfile.TemporaryDirectory() as root:
            write(root, "docs/x.md", "# living")
            write(root, "docs/plans/p.md", "# a plan")
            git_init(root)
            m = manifest(run(root))
            for c in m["chunks"]:
                hints = {d["hint"] for d in c["docs"]}
                self.assertEqual(len(hints), 1)
            self.assertEqual(len(m["chunks"]), 2)

    def test_same_hint_small_dirs_coalesce_under_caps(self):
        with tempfile.TemporaryDirectory() as root:
            write(root, "a/x.md", "# x")
            write(root, "b/y.md", "# y")
            git_init(root)
            m = manifest(run(root))
            self.assertEqual(len(m["chunks"]), 1)
            self.assertEqual(all_paths(m), ["a/x.md", "b/y.md"])

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
                  json.dumps({"chunk": done_id, "verdicts": []}))
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


def run_emit(root, manifest_path, flag, chunk_id, results_dir=None):
    cmd = [sys.executable, SCRIPT, "--root", root, flag, chunk_id,
           "--manifest", manifest_path]
    if results_dir is not None:
        cmd += ["--results-dir", results_dir]
    return subprocess.run(cmd, capture_output=True, text=True)


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
        # An invalid result that survived a failed retry must not mask the
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
                  json.dumps({"chunk": "c-someoneelse", "verdicts": []}))
            m3 = manifest(run(root, results_dir=results))
            self.assertEqual(m3["pending"], [cid])
            write(root, f"chunks/{cid}.json",
                  json.dumps({"chunk": cid, "verdicts": []}))
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
            if member_path in paths_of(c):
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
            # 8 living docs of 300 lines: 12 + 16 + 4 = 32
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


class EmitPrompt(unittest.TestCase):
    def plan_to_file(self, root):
        out = os.path.join(root, "manifest.json")
        r = run(root, out=out)
        assert r.returncode == 0, r.stderr
        with open(out, encoding="utf-8") as f:
            return out, json.load(f)

    def test_prompt_carries_slice_verbatim_no_manifest_hunt(self):
        with tempfile.TemporaryDirectory() as root, \
                tempfile.TemporaryDirectory() as results:
            write(root, "docs/plans/p.md", "\n".join(["x"] * 40))
            write(root, "docs/guide.md", "# guide")
            git_init(root)
            path, m = self.plan_to_file(root)
            chunk = next(c for c in m["chunks"]
                         if c["docs"][0]["path"] == "docs/plans/p.md")
            r = run_emit(root, path, "--emit-prompt", chunk["id"], results)
            self.assertEqual(r.returncode, 0, r.stderr)
            prompt = r.stdout
            self.assertIn("docs/plans/p.md", prompt)
            self.assertIn("40", prompt)          # line count shown
            self.assertIn("planning", prompt)    # hint shown
            # The write destination is absolute and outside the work tree —
            # not the bare relative "chunks/<id>.json" a work-tree-rooted
            # executor would resolve straight into the repository.
            expected_out = os.path.join(
                os.path.abspath(results), chunk["id"] + ".json")
            self.assertIn(expected_out, prompt)
            self.assertNotIn(f" chunks/{chunk['id']}.json", prompt)
            self.assertIn("doc-lifecycle:detecting-doc-bloat", prompt)
            self.assertNotIn("manifest.json", prompt)
            self.assertNotIn("docs/guide.md", prompt)  # other chunks excluded

    def test_prompt_requires_results_dir(self):
        with tempfile.TemporaryDirectory() as root:
            write(root, "docs/a.md", "x")
            git_init(root)
            path, m = self.plan_to_file(root)
            r = run_emit(root, path, "--emit-prompt", m["chunks"][0]["id"])
            self.assertEqual(r.returncode, 2, r.stdout + r.stderr)
            self.assertIn("--results-dir", r.stderr)

    def test_prompt_names_the_engine_verdict_seam_and_unit_source(self):
        with tempfile.TemporaryDirectory() as root, \
                tempfile.TemporaryDirectory() as results:
            write(root, "docs/a.md", "x")
            git_init(root)
            path, m = self.plan_to_file(root)
            chunk_id = m["chunks"][0]["id"]
            r = run_emit(root, path, "--emit-prompt", chunk_id, results)
            self.assertEqual(r.returncode, 0, r.stderr)
            prompt = r.stdout
            self.assertIn('"verdicts"', prompt)
            self.assertNotIn('"records"', prompt)
            self.assertIn("doclifecycle segment", prompt)
            self.assertIn("units", prompt)
            self.assertNotIn("POLICY", prompt)

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


class EngineManifestDialect(unittest.TestCase):
    """The engine's `bloat-plan` manifest: {"documents": [<path>, ...]} per
    chunk, no per-doc "lines"/"hint", no per-chunk "turns" — a different but
    legitimate work order for the same --emit-prompt/--emit-turns seam
    validate-bloat-output.py's chunk_doc_paths() already reads both dialects
    for."""

    def engine_manifest(self, root, chunk_id, documents):
        path = os.path.join(root, "engine-manifest.json")
        with open(path, "w", encoding="utf-8") as f:
            json.dump({"schema_version": 1, "chunks": [
                {"id": chunk_id, "documents": documents, "unit_count": 3},
            ]}, f)
        return path

    def test_emit_prompt_renders_bare_paths_no_lines_or_hint(self):
        with tempfile.TemporaryDirectory() as root, \
                tempfile.TemporaryDirectory() as results:
            path = self.engine_manifest(root, "c-engine1",
                                         ["README.md", "docs/guide.md"])
            r = run_emit(root, path, "--emit-prompt", "c-engine1", results)
            self.assertEqual(r.returncode, 0, r.stderr)
            self.assertIn("README.md", r.stdout)
            self.assertIn("docs/guide.md", r.stdout)
            expected_out = os.path.join(
                os.path.abspath(results), "c-engine1.json")
            self.assertIn(expected_out, r.stdout)

    def test_emit_turns_fails_loudly_not_silently_to_floor(self):
        with tempfile.TemporaryDirectory() as root:
            path = self.engine_manifest(root, "c-engine2", ["README.md"])
            r = run_emit(root, path, "--emit-turns", "c-engine2")
            self.assertEqual(r.returncode, 2, r.stdout + r.stderr)
            self.assertIn("c-engine2", r.stderr)
            self.assertIn("turns", r.stderr)

    def test_emit_turns_honors_a_stamped_turns_value_even_in_this_dialect(self):
        with tempfile.TemporaryDirectory() as root:
            path = os.path.join(root, "engine-manifest.json")
            with open(path, "w", encoding="utf-8") as f:
                json.dump({"chunks": [
                    {"id": "c-engine3", "documents": ["README.md"],
                     "turns": 25},
                ]}, f)
            r = run_emit(root, path, "--emit-turns", "c-engine3")
            self.assertEqual(r.returncode, 0, r.stderr)
            self.assertEqual(r.stdout.strip(), "25")

    def test_neither_dialect_dies_naming_the_chunk(self):
        with tempfile.TemporaryDirectory() as root, \
                tempfile.TemporaryDirectory() as results:
            path = os.path.join(root, "bad-manifest.json")
            with open(path, "w", encoding="utf-8") as f:
                json.dump({"chunks": [{"id": "c-bad"}]}, f)
            r = run_emit(root, path, "--emit-prompt", "c-bad", results)
            self.assertEqual(r.returncode, 2, r.stdout + r.stderr)
            self.assertIn("c-bad", r.stderr)


class FixtureEndToEnd(unittest.TestCase):
    def test_plan_swarm_fixture_sweeps_every_doc(self):
        root = os.path.normpath(os.path.join(
            os.path.dirname(__file__), "..", "fixtures", "plan-swarm"))
        r = run(root)
        self.assertEqual(r.returncode, 0, r.stderr)
        m = manifest(r)
        paths = all_paths(m)
        self.assertEqual(len(paths), 15)
        # The fixture's config still declares the retired knob; its docs are
        # planned as ordinary sweep members and the run says so.
        self.assertIn("policy_scope", r.stderr)
        self.assertIn("docs/superpowers/plans/2026-06-01-limiter-tests-plan.md",
                      paths)
        self.assertEqual(len(m["pending"]), len(m["chunks"]))


if __name__ == "__main__":
    unittest.main()
