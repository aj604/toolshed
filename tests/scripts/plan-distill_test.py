#!/usr/bin/env python3
"""Black-box tests for scheduling-doc-sync's plan-distill.py.

Tests the script as a subprocess against fixtures built in tempdirs. Covers
lane selection (via sync-gate's in_lane — one owner), directory-affinity
grouping under distill.max_group_records, content-addressed group ids, the
max_groups ceiling, --emit-prompt rendering, --validate-result seam rules,
and the --merge engine against real git repos (clean apply, decisions.md
union resolution, hard-conflict skip-and-continue, missing/mismatched
results). Run: python3 tests/scripts/plan-distill_test.py
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
    "scripts", "plan-distill.py",
)

GIT_ENV = {**os.environ,
           "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@t",
           "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@t"}


def rec(rid, verdict, doc, status=None, proposal=None, files=None):
    return {"id": rid, "doc": doc, "location": None, "verdict": verdict,
            "evidence": f"evidence for {rid}", "proposal": proposal,
            "status": status, "files": files}


def distill(rid, doc, status="ready"):
    return rec(rid, "DISTILL", doc, status=status)


def write(root, relpath, text):
    full = os.path.join(root, relpath)
    os.makedirs(os.path.dirname(full) or full, exist_ok=True)
    with open(full, "w", encoding="utf-8") as f:
        f.write(text)
    return full


def report_file(root, records, name="bloat-report.json"):
    return write(root, name, json.dumps({"schema": 2, "records": records}))


def run(*args, cwd=None):
    return subprocess.run([sys.executable, SCRIPT, *args],
                          capture_output=True, text=True, cwd=cwd,
                          env=GIT_ENV)


def plan(root, records, config=None):
    rpt = report_file(root, records)
    out = os.path.join(root, "manifest.json")
    args = ["--report", rpt, "--out", out]
    if config is not None:
        args += ["--config", write(root, "scope.json", json.dumps(config))]
    proc = run(*args)
    if proc.returncode != 0:
        return proc, None
    with open(out, encoding="utf-8") as f:
        return proc, json.load(f)


def git(repo, *args):
    return subprocess.run(["git", *args], cwd=repo, capture_output=True,
                          text=True, env=GIT_ENV, check=False)


def git_ok(repo, *args):
    proc = git(repo, *args)
    if proc.returncode != 0:
        raise AssertionError(f"git {args} failed: {proc.stderr}")
    return proc.stdout


class PlanLaneSelection(unittest.TestCase):
    def test_prune_verdicts_and_pending_distill_never_planned(self):
        with tempfile.TemporaryDirectory() as root:
            _, man = plan(root, [
                rec("B1", "CUT", "README.md"),
                rec("B2", "CONDENSE", "README.md", proposal="x"),
                rec("B3", "EXTRACT-AND-MOVE", "README.md",
                    proposal={"target": "docs/a.md", "text": "x"}),
                distill("B4", "docs/plans/a-design.md",
                        status="pending-implementation"),
            ])
            self.assertEqual(man["groups"], [])

    def test_mechanical_verdicts_form_one_inline_group(self):
        with tempfile.TemporaryDirectory() as root:
            _, man = plan(root, [
                rec("B1", "MERGE-DOC", "INSTALL.md",
                    proposal={"target": "README.md"}),
                rec("B2", "RETIRE-DOC", "docs/old.md"),
                rec("B3", "POLICY", "docs/swarm", proposal="retire",
                    files=["docs/swarm/a.md"]),
            ])
            self.assertEqual(len(man["groups"]), 1)
            g = man["groups"][0]
            self.assertEqual(g["kind"], "inline")
            self.assertTrue(g["id"].startswith("i-"))
            self.assertEqual([r["id"] for r in g["records"]],
                             ["B1", "B2", "B3"])

    def test_distill_groups_by_artifact_directory(self):
        with tempfile.TemporaryDirectory() as root:
            _, man = plan(root, [
                distill("B1", "docs/plans/a-design.md"),
                distill("B2", "docs/plans/b-design.md"),
                distill("B3", "docs/specs/c-spec.md"),
            ])
            kinds = [(g["kind"], [r["id"] for r in g["records"]])
                     for g in man["groups"]]
            self.assertIn(("distill", ["B1", "B2"]), kinds)
            self.assertIn(("distill", ["B3"]), kinds)
            self.assertTrue(all(g["id"].startswith("g-")
                                for g in man["groups"]))

    def test_group_packing_respects_max_group_records(self):
        with tempfile.TemporaryDirectory() as root:
            records = [distill(f"B{i}", f"docs/plans/d{i}-design.md")
                       for i in range(1, 7)]
            _, man = plan(root, records,
                          config={"distill": {"max_group_records": 2}})
            sizes = sorted(len(g["records"]) for g in man["groups"])
            self.assertEqual(sizes, [2, 2, 2])

    def test_default_max_group_records_is_four(self):
        with tempfile.TemporaryDirectory() as root:
            records = [distill(f"B{i}", f"docs/plans/d{i}-design.md")
                       for i in range(1, 6)]
            _, man = plan(root, records)
            sizes = sorted(len(g["records"]) for g in man["groups"])
            self.assertEqual(sizes, [1, 4])

    def test_manifest_carries_schema_report_and_record_fields(self):
        with tempfile.TemporaryDirectory() as root:
            _, man = plan(root, [distill("B1", "docs/plans/a-design.md")])
            self.assertEqual(man["schema"], 1)
            g = man["groups"][0]
            r = g["records"][0]
            self.assertEqual(r, {"id": "B1", "verdict": "DISTILL",
                                 "doc": "docs/plans/a-design.md"})

    def test_ids_content_addressed_and_stable(self):
        with tempfile.TemporaryDirectory() as root:
            _, man1 = plan(root, [distill("B1", "docs/plans/a-design.md")])
        with tempfile.TemporaryDirectory() as root:
            _, man2 = plan(root, [distill("B1", "docs/plans/a-design.md")])
        with tempfile.TemporaryDirectory() as root:
            _, man3 = plan(root, [distill("B1", "docs/plans/z-design.md")])
        self.assertEqual(man1["groups"][0]["id"], man2["groups"][0]["id"])
        self.assertNotEqual(man1["groups"][0]["id"], man3["groups"][0]["id"])

    def test_run_surface_report_on_stderr(self):
        with tempfile.TemporaryDirectory() as root:
            proc, _ = plan(root, [
                distill("B1", "docs/plans/a-design.md"),
                rec("B2", "RETIRE-DOC", "docs/old.md"),
            ])
            self.assertIn("2 record(s)", proc.stderr)
            self.assertIn("2 group(s)", proc.stderr)

    def test_max_groups_ceiling_trips_naming_the_knob(self):
        with tempfile.TemporaryDirectory() as root:
            proc, _ = plan(root, [
                distill("B1", "docs/plans/a-design.md"),
                distill("B2", "docs/specs/b-spec.md"),
            ], config={"distill": {"max_groups": 1}})
            self.assertEqual(proc.returncode, 2)
            self.assertIn("max_groups", proc.stderr)

    def test_malformed_distill_config_dies(self):
        with tempfile.TemporaryDirectory() as root:
            proc, _ = plan(root, [distill("B1", "docs/plans/a.md")],
                           config={"distill": {"max_group_records": 0}})
            self.assertEqual(proc.returncode, 2)

    def test_absent_config_file_is_pure_defaults(self):
        with tempfile.TemporaryDirectory() as root:
            rpt = report_file(root, [distill("B1", "docs/plans/a-design.md")])
            out = os.path.join(root, "manifest.json")
            proc = run("--report", rpt, "--out", out,
                       "--config", os.path.join(root, "nope.json"))
            self.assertEqual(proc.returncode, 0)


class EmitPrompt(unittest.TestCase):
    def _manifest(self, root):
        _, man = plan(root, [
            distill("B1", "docs/plans/a-design.md"),
            distill("B2", "docs/plans/b-design.md"),
        ])
        return os.path.join(root, "manifest.json"), man

    def test_prompt_carries_slice_report_sidecar_and_done(self):
        with tempfile.TemporaryDirectory() as root:
            mpath, man = self._manifest(root)
            gid = man["groups"][0]["id"]
            proc = run("--emit-prompt", gid, "--manifest", mpath)
            self.assertEqual(proc.returncode, 0)
            p = proc.stdout
            self.assertIn(gid, p)
            self.assertIn("B1 (DISTILL) docs/plans/a-design.md", p)
            self.assertIn("B2 (DISTILL) docs/plans/b-design.md", p)
            self.assertIn(man["report"], p)
            self.assertIn(f"distill-results/{gid}.json", p)
            flat = " ".join(p.lower().split())
            self.assertIn("one commit per applied record", flat)
            self.assertIn("never push", flat)

    def test_unknown_group_dies(self):
        with tempfile.TemporaryDirectory() as root:
            mpath, _ = self._manifest(root)
            proc = run("--emit-prompt", "g-nope", "--manifest", mpath)
            self.assertEqual(proc.returncode, 2)


class ValidateResult(unittest.TestCase):
    def _fixture(self, root):
        _, man = plan(root, [
            distill("B1", "docs/plans/a-design.md"),
            distill("B2", "docs/plans/b-design.md"),
        ])
        return os.path.join(root, "manifest.json"), man["groups"][0]

    def _check(self, root, mpath, gid, sidecar):
        path = write(root, f"distill-results/{gid}.json",
                     json.dumps(sidecar) if isinstance(sidecar, dict)
                     else sidecar)
        return run("--validate-result", path, "--manifest", mpath)

    def test_valid_result_passes(self):
        with tempfile.TemporaryDirectory() as root:
            mpath, g = self._fixture(root)
            proc = self._check(root, mpath, g["id"], {
                "group": g["id"], "applied": ["B1"],
                "skipped": [{"id": "B2", "reason": "landing re-verify failed"}],
                "failed": []})
            self.assertEqual(proc.returncode, 0, proc.stderr)

    def test_every_record_accounted_exactly_once(self):
        with tempfile.TemporaryDirectory() as root:
            mpath, g = self._fixture(root)
            missing = self._check(root, mpath, g["id"], {
                "group": g["id"], "applied": ["B1"], "skipped": [],
                "failed": []})
            self.assertEqual(missing.returncode, 2)
            doubled = self._check(root, mpath, g["id"], {
                "group": g["id"], "applied": ["B1", "B2"],
                "skipped": [{"id": "B2", "reason": "x"}], "failed": []})
            self.assertEqual(doubled.returncode, 2)
            foreign = self._check(root, mpath, g["id"], {
                "group": g["id"], "applied": ["B1", "B2", "B9"],
                "skipped": [], "failed": []})
            self.assertEqual(foreign.returncode, 2)

    def test_wrong_group_or_garbage_dies(self):
        with tempfile.TemporaryDirectory() as root:
            mpath, g = self._fixture(root)
            wrong = self._check(root, mpath, g["id"], {
                "group": "g-other", "applied": ["B1", "B2"],
                "skipped": [], "failed": []})
            self.assertEqual(wrong.returncode, 2)
            garbage = self._check(root, mpath, g["id"], "not json {")
            self.assertEqual(garbage.returncode, 2)

    def test_empty_reason_dies(self):
        with tempfile.TemporaryDirectory() as root:
            mpath, g = self._fixture(root)
            proc = self._check(root, mpath, g["id"], {
                "group": g["id"], "applied": ["B1"],
                "skipped": [{"id": "B2", "reason": ""}], "failed": []})
            self.assertEqual(proc.returncode, 2)


class Merge(unittest.TestCase):
    """--merge against real git repos: patches made on branches off base,
    merged onto a fresh branch at base."""

    def _base_repo(self, root):
        repo = os.path.join(root, "repo")
        write(repo, "docs/decisions.md", "# Decisions\n")
        write(repo, "docs/plans/a-design.md", "a design\n")
        write(repo, "docs/plans/b-design.md", "b design\n")
        write(repo, "README.md", "readme line\n")
        git_ok(repo, "init", "-q", "-b", "main")
        git_ok(repo, "add", "-A")
        git_ok(repo, "commit", "-qm", "base")
        return repo

    def _group_patch(self, repo, root, gid, rid, changes, message=None):
        """Commit `changes` on a branch off main, format-patch it into
        patches/<gid>, write a matching all-applied sidecar."""
        git_ok(repo, "checkout", "-q", "main")
        git_ok(repo, "checkout", "-qb", f"work-{gid}")
        for relpath, text in changes.items():
            if text is None:
                git_ok(repo, "rm", "-q", relpath)
            else:
                write(repo, relpath, text)
                git_ok(repo, "add", relpath)
        git_ok(repo, "commit", "-qam", message or f"docs: bloat distill {rid}")
        pdir = os.path.join(root, "patches", gid)
        os.makedirs(pdir, exist_ok=True)
        git_ok(repo, "format-patch", "-q", "-o", pdir, "main..HEAD")
        git_ok(repo, "checkout", "-q", "main")
        write(root, f"distill-results/{gid}.json", json.dumps(
            {"group": gid, "applied": [rid], "skipped": [], "failed": []}))

    def _manifest_for(self, root, groups):
        """Hand-built manifest matching plan output shape."""
        man = {"schema": 1, "report": "bloat-report.json", "groups": [
            {"id": gid, "kind": "distill",
             "records": [{"id": rid, "verdict": "DISTILL", "doc": doc}
                         for rid, doc in members]}
            for gid, members in groups]}
        return write(root, "manifest.json", json.dumps(man))

    def _merge(self, root, repo, mpath):
        git_ok(repo, "checkout", "-qb", "doc-bloat/distill", "main")
        out = os.path.join(root, "merge.json")
        proc = run("--merge", "--manifest", mpath,
                   "--results-dir", os.path.join(root, "distill-results"),
                   "--patches-dir", os.path.join(root, "patches"),
                   "--repo", repo, "--out", out)
        summary = None
        if os.path.exists(out):
            with open(out, encoding="utf-8") as f:
                summary = json.load(f)
        return proc, summary

    def test_clean_groups_all_apply(self):
        with tempfile.TemporaryDirectory() as root:
            repo = self._base_repo(root)
            self._group_patch(repo, root, "g-aaa", "B1",
                              {"docs/plans/a-design.md": None,
                               "docs/decisions.md":
                               "# Decisions\n\n## a-design\n- Decided: a\n"})
            self._group_patch(repo, root, "g-bbb", "B2",
                              {"docs/plans/b-design.md": None})
            mpath = self._manifest_for(root, [
                ("g-aaa", [("B1", "docs/plans/a-design.md")]),
                ("g-bbb", [("B2", "docs/plans/b-design.md")])])
            proc, summary = self._merge(root, repo, mpath)
            self.assertEqual(proc.returncode, 0, proc.stderr)
            self.assertEqual(sorted(summary["applied"]), ["B1", "B2"])
            self.assertEqual(summary["unapplied"], [])
            log = git_ok(repo, "log", "--oneline", "main..HEAD")
            self.assertEqual(len(log.strip().splitlines()), 2)

    def test_decisions_append_conflict_resolved_by_union(self):
        with tempfile.TemporaryDirectory() as root:
            repo = self._base_repo(root)
            self._group_patch(repo, root, "g-aaa", "B1",
                              {"docs/decisions.md":
                               "# Decisions\n\n## a-design\n- Decided: a\n"})
            self._group_patch(repo, root, "g-bbb", "B2",
                              {"docs/decisions.md":
                               "# Decisions\n\n## b-design\n- Decided: b\n"})
            mpath = self._manifest_for(root, [
                ("g-aaa", [("B1", "docs/plans/a-design.md")]),
                ("g-bbb", [("B2", "docs/plans/b-design.md")])])
            proc, summary = self._merge(root, repo, mpath)
            self.assertEqual(proc.returncode, 0, proc.stderr)
            self.assertEqual(sorted(summary["applied"]), ["B1", "B2"])
            with open(os.path.join(repo, "docs/decisions.md"),
                      encoding="utf-8") as f:
                merged = f.read()
            self.assertIn("## a-design", merged)
            self.assertIn("## b-design", merged)
            self.assertNotIn("<<<<<<<", merged)

    def test_hard_conflict_skips_record_and_continues(self):
        with tempfile.TemporaryDirectory() as root:
            repo = self._base_repo(root)
            self._group_patch(repo, root, "g-aaa", "B1",
                              {"README.md": "readme rewritten by B1\n"})
            self._group_patch(repo, root, "g-bbb", "B2",
                              {"README.md": "readme rewritten by B2\n"})
            self._group_patch(repo, root, "g-ccc", "B3",
                              {"docs/plans/b-design.md": None})
            mpath = self._manifest_for(root, [
                ("g-aaa", [("B1", "docs/plans/a-design.md")]),
                ("g-bbb", [("B2", "docs/plans/a-design.md")]),
                ("g-ccc", [("B3", "docs/plans/b-design.md")])])
            proc, summary = self._merge(root, repo, mpath)
            self.assertEqual(proc.returncode, 0, proc.stderr)
            self.assertIn("B1", summary["applied"])
            self.assertIn("B3", summary["applied"])
            unapplied = {u["id"]: u for u in summary["unapplied"]}
            self.assertIn("B2", unapplied)
            self.assertEqual(unapplied["B2"]["stage"], "merge")
            status = git_ok(repo, "status", "--porcelain")
            self.assertEqual(status.strip(), "")

    def test_missing_sidecar_drops_group(self):
        with tempfile.TemporaryDirectory() as root:
            repo = self._base_repo(root)
            self._group_patch(repo, root, "g-aaa", "B1",
                              {"docs/plans/a-design.md": None})
            os.remove(os.path.join(root, "distill-results", "g-aaa.json"))
            mpath = self._manifest_for(root, [
                ("g-aaa", [("B1", "docs/plans/a-design.md")])])
            proc, summary = self._merge(root, repo, mpath)
            self.assertEqual(proc.returncode, 0, proc.stderr)
            self.assertEqual(summary["applied"], [])
            self.assertEqual(summary["unapplied"][0]["id"], "B1")

    def test_patch_sidecar_mismatch_drops_group(self):
        with tempfile.TemporaryDirectory() as root:
            repo = self._base_repo(root)
            self._group_patch(repo, root, "g-aaa", "B1",
                              {"docs/plans/a-design.md": None})
            # Sidecar claims two applied records; only one patch exists.
            write(root, "distill-results/g-aaa.json", json.dumps(
                {"group": "g-aaa", "applied": ["B1", "B2"], "skipped": [],
                 "failed": []}))
            mpath = self._manifest_for(root, [
                ("g-aaa", [("B1", "docs/plans/a-design.md"),
                           ("B2", "docs/plans/b-design.md")])])
            proc, summary = self._merge(root, repo, mpath)
            self.assertEqual(proc.returncode, 0, proc.stderr)
            self.assertEqual(summary["applied"], [])
            self.assertEqual(len(summary["unapplied"]), 2)

    def test_out_of_order_applied_list_maps_by_commit_subject(self):
        """An executor that lists `applied` out of commit order must not
        mislabel which record a conflicting patch belongs to: the merge maps
        patch -> record id by the patch's Subject line when unambiguous."""
        with tempfile.TemporaryDirectory() as root:
            repo = self._base_repo(root)
            # One group, two per-record commits (B1 clean, B2 conflicting),
            # but the sidecar lists them in reverse order.
            git_ok(repo, "checkout", "-qb", "work-g-aaa", "main")
            git_ok(repo, "rm", "-q", "docs/plans/a-design.md")
            git_ok(repo, "commit", "-qm",
                   "docs: bloat distill B1 — docs/plans/a-design.md")
            write(repo, "README.md", "rewritten by B2\n")
            git_ok(repo, "add", "README.md")
            git_ok(repo, "commit", "-qm",
                   "docs: bloat distill B2 — docs/plans/b-design.md")
            pdir = os.path.join(root, "patches", "g-aaa")
            os.makedirs(pdir, exist_ok=True)
            git_ok(repo, "format-patch", "-q", "-o", pdir, "main..HEAD")
            git_ok(repo, "checkout", "-q", "main")
            # Conflicting base change so B2's patch fails to apply.
            write(repo, "README.md", "conflicting base edit\n")
            git_ok(repo, "commit", "-qam", "conflict setup")
            write(root, "distill-results/g-aaa.json", json.dumps(
                {"group": "g-aaa", "applied": ["B2", "B1"],  # reversed
                 "skipped": [], "failed": []}))
            mpath = self._manifest_for(root, [
                ("g-aaa", [("B1", "docs/plans/a-design.md"),
                           ("B2", "docs/plans/b-design.md")])])
            proc, summary = self._merge(root, repo, mpath)
            self.assertEqual(proc.returncode, 0, proc.stderr)
            # B1's patch applies; B2's conflicts — and must be reported as
            # B2 despite the sidecar's reversed order.
            self.assertEqual(summary["applied"], ["B1"])
            self.assertEqual([u["id"] for u in summary["unapplied"]], ["B2"])

    def test_executor_skips_and_failures_pass_through(self):
        with tempfile.TemporaryDirectory() as root:
            repo = self._base_repo(root)
            os.makedirs(os.path.join(root, "patches"), exist_ok=True)
            write(root, "distill-results/g-aaa.json", json.dumps(
                {"group": "g-aaa", "applied": [],
                 "skipped": [{"id": "B1", "reason": "re-verify failed"}],
                 "failed": [{"id": "B2", "reason": "claim unverifiable"}]}))
            mpath = self._manifest_for(root, [
                ("g-aaa", [("B1", "docs/plans/a-design.md"),
                           ("B2", "docs/plans/b-design.md")])])
            proc, summary = self._merge(root, repo, mpath)
            self.assertEqual(proc.returncode, 0, proc.stderr)
            self.assertEqual(summary["applied"], [])
            unapplied = {u["id"]: u for u in summary["unapplied"]}
            self.assertEqual(unapplied["B1"]["stage"], "executor")
            self.assertIn("re-verify failed", unapplied["B1"]["reason"])
            self.assertEqual(unapplied["B2"]["stage"], "executor")


if __name__ == "__main__":
    unittest.main()
