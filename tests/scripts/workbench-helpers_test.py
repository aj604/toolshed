"""Exercise the imported workbench helpers through their CLI surfaces, offline."""

from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import unittest


SKILLS = Path(__file__).resolve().parents[2] / "plugins/workbench/skills"


class WorkbenchHelpers(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        home = self.root / "home"
        home.mkdir()
        self.env = dict(os.environ, HOME=str(home), GIT_CONFIG_NOSYSTEM="1",
                        GIT_CONFIG_GLOBAL=os.devnull)

    def run_helper(self, skill, script, *args, cwd=None):
        path = SKILLS / skill / "scripts" / script
        self.assertTrue(path.is_file(), f"Missing packaged helper: {path}")
        result = subprocess.run([sys.executable, str(path), *map(str, args)],
                                cwd=cwd, env=self.env, capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        return json.loads(result.stdout)

    def lane_report(self, prs, branches):
        # Stands in for `gh`: GraphQL pages and the branch list both arrive as
        # one item per line, the way `--paginate --jq` emits them.
        bindir = self.root / "bin"
        bindir.mkdir()
        (self.root / "prs.json").write_text(json.dumps(prs))
        gh = bindir / "gh"
        gh.write_text(f"#!{sys.executable}\n" + f"PRS = {str(self.root / 'prs.json')!r}\n"
                      + f"BRANCHES = {list(branches)!r}\n" + '''
import json, sys
args = sys.argv[1:]
if args[:2] == ["repo", "view"]:
    print("develop")
elif args[:2] == ["api", "graphql"]:
    assert "--paginate" in args, "pull requests must be paginated, not capped"
    for pr in json.load(open(PRS)):
        print(json.dumps(pr))
elif args[0] == "api":
    print("\\n".join(BRANCHES))
else:
    sys.exit("unexpected gh call: " + repr(args))
''')
        gh.chmod(0o755)
        self.env["PATH"] = str(bindir) + os.pathsep + self.env.get("PATH", "")
        return self.run_helper("incremental-enhancement-lanes", "lanes.py",
                               "--repo", "example/project", "--json")

    @staticmethod
    def pr(number, head, base, state="OPEN", merged=False):
        return {"number": number, "title": f"PR {number}", "headRefName": head,
                "baseRefName": base, "isDraft": False, "state": state,
                "url": f"https://example.test/{number}",
                "mergedAt": "2026-10-01T00:00:00Z" if merged else None,
                "reviewDecision": ""}

    def broken_stack_report(self):
        # A remote branch with no PR must survive reconstruction. Round 2's PR
        # deliberately targets develop instead of round 1, so it must be flagged.
        return self.lane_report([self.pr(12, "lane/cli/r2", "develop")],
                                ["lane/cli/r1", "lane/cli/r2"])

    def test_reconstruction_keeps_a_pushed_round_without_a_pr(self):
        report = self.broken_stack_report()
        first = report["lanes"]["cli"]["rounds"][0]
        self.assertEqual(first["branch"], "lane/cli/r1")
        self.assertEqual(first["status"], "branch pushed, no PR")
        self.assertEqual(first["expected_base"], "develop")
        self.assertTrue(any("no pull request" in p for p in report["problems"]))

    def test_reconstruction_flags_a_broken_stack_and_resumes_from_its_tip(self):
        report = self.broken_stack_report()
        lane = report["lanes"]["cli"]
        self.assertEqual(lane["next_round"], 3)
        self.assertEqual(lane["next_base"], "lane/cli/r2")
        self.assertTrue(any("expected lane/cli/r1" in p for p in report["problems"]))

    def test_a_child_retargeted_after_its_parent_merged_is_a_sound_stack(self):
        # r1 merged and its branch was deleted, so GitHub moved r2 onto develop.
        report = self.lane_report(
            [self.pr(11, "lane/cli/r1", "develop", state="MERGED", merged=True),
             self.pr(12, "lane/cli/r2", "develop")],
            ["lane/cli/r2"])
        rounds = report["lanes"]["cli"]["rounds"]
        self.assertFalse(rounds[0]["pushed"])
        self.assertEqual(rounds[1]["expected_base"], "develop")
        self.assertEqual(report["problems"], [])

    def test_a_child_still_on_its_merged_parent_is_told_to_delete_it(self):
        report = self.lane_report(
            [self.pr(11, "lane/cli/r1", "develop", state="MERGED", merged=True),
             self.pr(12, "lane/cli/r2", "lane/cli/r1")],
            ["lane/cli/r1", "lane/cli/r2"])
        self.assertEqual(len(report["problems"]), 1)
        self.assertIn("still targets lane/cli/r1, which merged", report["problems"][0])

    def test_rounds_beyond_two_hundred_pull_requests_are_not_lost(self):
        # The merged r1's branch is gone; its PR is the 251st, past the old cap.
        filler = [self.pr(n, f"feature/{n}", "develop") for n in range(300, 550)]
        report = self.lane_report(
            filler + [self.pr(11, "lane/cli/r1", "develop", state="MERGED", merged=True),
                      self.pr(12, "lane/cli/r2", "develop")],
            ["lane/cli/r2"])
        self.assertEqual([r["round"] for r in report["lanes"]["cli"]["rounds"]], [1, 2])
        self.assertEqual(report["problems"], [])


class PmStatusGather(unittest.TestCase):
    """gather.py against a local repo whose origin path reads as a GitHub remote, and a fake `gh`."""

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        home = self.root / "home"
        home.mkdir()
        self.env = dict(os.environ, HOME=str(home), GIT_CONFIG_NOSYSTEM="1",
                        GIT_CONFIG_GLOBAL=os.devnull, GIT_AUTHOR_NAME="t", GIT_AUTHOR_EMAIL="t@t",
                        GIT_COMMITTER_NAME="t", GIT_COMMITTER_EMAIL="t@t")
        # gather.py derives owner/repo from the origin URL, so the bare origin
        # lives at a path ending in github.com/example/project.git.
        origin = self.root / "github.com/example/project.git"
        seed = self.root / "seed"
        self.repo = self.root / "repo"
        for cmd in (["git", "init", "-q", "--bare", "-b", "main", str(origin)],
                    ["git", "init", "-q", "-b", "main", str(seed)],
                    ["git", "-C", str(seed), "commit", "-q", "--allow-empty", "-m", "init"],
                    ["git", "-C", str(seed), "push", "-q", str(origin), "main"],
                    ["git", "clone", "-q", str(origin), str(self.repo)]):
            subprocess.run(cmd, env=self.env, check=True, capture_output=True)
        self.data = self.root / "gh.json"
        bindir = self.root / "bin"
        bindir.mkdir()
        gh = bindir / "gh"
        gh.write_text(f"#!{sys.executable}\nDATA = {str(self.data)!r}\n" + '''
import json, re, sys
args = sys.argv[1:]
data = json.load(open(DATA))
if args[:2] == ["auth", "status"]:
    sys.exit(0)
if args[0] == "api":
    m = re.search(r"issues/(\\d+)/(dependencies/blocked_by|sub_issues)", args[1])
    if not m:
        sys.exit("unexpected gh api call: " + args[1])
    key = "blocked_by" if m.group(2).startswith("dep") else "sub_issues"
    if key == "sub_issues" and int(m.group(1)) in data.get("fail_sub_issues", []):
        sys.exit("HTTP 502")
    print(json.dumps(data[key].get(m.group(1), [])))
elif args[:2] == ["issue", "list"]:
    print(json.dumps(data["open_issues"] if args[args.index("--state") + 1] == "open" else []))
elif args[:2] == ["pr", "list"]:
    state = args[args.index("--state") + 1]
    print(json.dumps({"open": data["open_prs"], "merged": data.get("merged_prs", []),
                      "all": data.get("all_prs", [])}.get(state, [])))
elif args[:2] == ["run", "list"]:
    print(json.dumps(data.get("runs", {}).get(args[args.index("--branch") + 1], [])))
else:
    sys.exit("unexpected gh call: " + repr(args))
''')
        gh.chmod(0o755)
        self.env["PATH"] = str(bindir) + os.pathsep + self.env.get("PATH", "")

    @staticmethod
    def issue(number):
        return {"number": number, "title": f"Issue {number}", "url": f"https://example.test/{number}",
                "labels": [], "assignees": [], "createdAt": "2026-10-01T00:00:00Z",
                "updatedAt": "2026-10-01T00:00:00Z", "milestone": None}

    @staticmethod
    def open_pr(number, closes):
        return {"number": number, "title": f"PR {number}", "url": f"https://example.test/{number}",
                "isDraft": False, "headRefName": f"feature/{number}", "baseRefName": "main",
                "createdAt": "2026-10-01T00:00:00Z", "updatedAt": "2026-10-01T00:00:00Z",
                "reviewDecision": "", "mergeable": "MERGEABLE", "statusCheckRollup": [],
                "closingIssuesReferences": [{"number": n} for n in closes], "labels": [], "author": {"login": "t"}}

    @staticmethod
    def ref(number, state, state_reason=None):
        return {"number": number, "title": f"Issue {number}", "state": state,
                "state_reason": state_reason or ("completed" if state == "closed" else None)}

    @staticmethod
    def merged_pr(number, base):
        return {"number": number, "title": f"PR {number}", "url": f"https://example.test/{number}",
                "state": "MERGED", "mergedAt": "2026-10-01T00:00:00Z", "closedAt": "2026-10-01T00:00:00Z",
                "headRefName": f"feature/{number}", "baseRefName": base, "author": {"login": "t"},
                "additions": 1, "deletions": 0, "closingIssuesReferences": []}

    def git(self, *args, cwd=None):
        return subprocess.run(["git", *args], cwd=cwd or self.repo, env=self.env, check=True,
                              capture_output=True, text=True).stdout.strip()

    def gather(self, open_issues, open_prs=(), blocked_by=None, sub_issues=None, *args, **extra):
        self.data.write_text(json.dumps({"open_issues": open_issues, "open_prs": list(open_prs),
                                         "blocked_by": blocked_by or {}, "sub_issues": sub_issues or {},
                                         **extra}))
        path = SKILLS / "pm-status" / "scripts" / "gather.py"
        self.assertTrue(path.is_file(), f"Missing packaged helper: {path}")
        result = subprocess.run([sys.executable, str(path), *args], cwd=self.repo, env=self.env,
                                capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        return json.loads(result.stdout)

    def mark(self):
        return self.gather([], (), None, None, "--mark")

    def test_open_issues_carry_their_sub_issues(self):
        report = self.gather([self.issue(84), self.issue(86)],
                             sub_issues={"84": [self.ref(86, "open")],
                                         "86": [self.ref(91, "closed"), self.ref(92, "closed")]})
        issues = {i["number"]: i for i in report["github"]["issues_open"]}
        self.assertEqual(issues[84]["sub_issues"], [self.ref(86, "open")])
        self.assertFalse(issues[84]["children_all_closed"])
        self.assertEqual([s["number"] for s in issues[86]["sub_issues"]], [91, 92])
        self.assertTrue(issues[86]["children_all_closed"])

    def test_a_parent_issue_is_not_ready_work(self):
        # With children open it's tracked work; with all of them closed it's waiting to be closed.
        report = self.gather([self.issue(191), self.issue(35), self.issue(530)],
                             sub_issues={"191": [self.ref(530, "open"), self.ref(529, "closed")],
                                         "35": [self.ref(36, "closed")]})
        issues = {i["number"]: i for i in report["github"]["issues_open"]}
        self.assertFalse(issues[191]["ready"])
        self.assertFalse(issues[35]["ready"])
        self.assertTrue(issues[35]["children_all_closed"])
        self.assertTrue(issues[530]["ready"])

    def test_an_issue_without_sub_issues_has_no_children_verdict(self):
        report = self.gather([self.issue(5)])
        issue = report["github"]["issues_open"][0]
        self.assertEqual(issue["sub_issues"], [])
        self.assertIsNone(issue["children_all_closed"])

    def test_the_first_run_has_no_frontier_changes(self):
        self.assertIsNone(self.gather([self.issue(5)])["frontier_changes"])

    def test_frontier_changes_compare_against_the_last_marked_run(self):
        self.gather([self.issue(87), self.issue(88), self.issue(89), self.issue(90)],
                    [self.open_pr(200, [89])], {"87": [self.ref(86, "open")]})
        marked = self.mark()["marked"]
        # Since then: #86 closed so #87 is ready, #88 got a PR, #89 closed, #95 was filed.
        report = self.gather([self.issue(87), self.issue(88), self.issue(90), self.issue(95)],
                             [self.open_pr(201, [88])])
        changes = report["frontier_changes"]
        self.assertEqual(changes["since"], marked)
        self.assertEqual([(c["number"], c["from"], c["to"]) for c in changes["changes"]],
                         [(87, "blocked", "ready"), (88, "ready", "in_progress"),
                          (89, "in_progress", "closed"), (95, None, "ready")])

    def test_sub_issues_keep_why_they_closed(self):
        report = self.gather([self.issue(84)],
                             sub_issues={"84": [self.ref(86, "closed", "not_planned")]})
        child = report["github"]["issues_open"][0]["sub_issues"][0]
        self.assertEqual(child["state_reason"], "not_planned")

    def test_a_failed_sub_issue_fetch_is_unknown_not_childless(self):
        report = self.gather([self.issue(84)], fail_sub_issues=[84])
        issue = report["github"]["issues_open"][0]
        self.assertIsNone(issue["sub_issues"])
        self.assertIsNone(issue["children_all_closed"])

    def test_ready_is_unknown_when_blockers_were_not_fetched(self):
        # Past 60 open issues the per-issue dependency calls are skipped.
        issues = [self.issue(n) for n in range(1, 62)]
        report = self.gather(issues, [self.open_pr(200, [1])])
        ready = {i["number"]: i["ready"] for i in report["github"]["issues_open"]}
        self.assertFalse(ready[1])
        self.assertIsNone(ready[2])

    def test_a_never_pushed_worktree_branch_counts_its_commits_as_unpushed(self):
        tree = self.root / "wt"
        self.git("worktree", "add", "-q", "-b", "feature/x", str(tree))
        self.git("commit", "-q", "--allow-empty", "-m", "local only", cwd=tree)
        report = self.gather([])
        entry = next(t for t in report["worktrees"] if t["branch"] == "feature/x")
        self.assertIsNone(entry["upstream"])
        self.assertEqual(entry["unpushed_commits"], 1)

    def test_work_merged_into_a_non_default_branch_is_reported_as_staged(self):
        self.git("switch", "-q", "-c", "feat/84")
        for msg in ("a", "b"):
            self.git("commit", "-q", "--allow-empty", "-m", msg)
        self.git("push", "-q", "origin", "feat/84")
        report = self.gather([], merged_prs=[self.merged_pr(124, "feat/84"), self.merged_pr(125, "feat/84"),
                                             self.merged_pr(73, "main")],
                             runs={"feat/84": [{"databaseId": 77, "status": "completed", "conclusion": "failure",
                                                "workflowName": "ci", "createdAt": "2026-10-01T00:00:00Z"}]})
        self.assertEqual(report["staged_branches"], [{
            "branch": "feat/84", "merged_prs": [124, 125], "on_remote": True, "ahead": 2, "behind": 0,
            "in_window": True, "changes_on_default": True, "conflict_count": 0, "conflicts_with_default": [],
            "pr": None, "last_ci": {"id": 77, "workflow": "ci", "status": "completed", "conclusion": "failure",
                                    "at": "2026-10-01T00:00:00Z"}}])

    def test_an_open_pr_that_is_part_of_an_issue_takes_it_off_the_frontier(self):
        # Stacked sub-PRs say "Part of #N", which GitHub doesn't link as closing.
        pr = dict(self.open_pr(552, []), body="Part of #533.\n\nSee also #12.")
        report = self.gather([self.issue(533), self.issue(12)], [pr])
        issues = {i["number"]: i for i in report["github"]["issues_open"]}
        self.assertTrue(issues[533]["has_open_pr"])
        self.assertFalse(issues[533]["ready"])
        self.assertFalse(issues[12]["has_open_pr"])
        opened = report["github"]["open"][0]
        self.assertEqual(opened["works_on"], [533])
        self.assertNotIn("body", opened)

    def test_a_staged_branch_that_conflicts_with_the_default_names_the_files(self):
        (self.repo / "ci.yml").write_text("runner: 2cpu\n")
        self.git("switch", "-q", "-c", "feat/84")
        self.git("add", "ci.yml")
        self.git("commit", "-q", "-m", "stack runner")
        self.git("push", "-q", "origin", "feat/84")
        self.git("switch", "-q", "main")
        (self.repo / "ci.yml").write_text("runner: 4cpu\n")
        self.git("add", "ci.yml")
        self.git("commit", "-q", "-m", "main runner")
        self.git("push", "-q", "origin", "main")
        report = self.gather([], merged_prs=[self.merged_pr(124, "feat/84")])
        staged = report["staged_branches"][0]
        self.assertEqual((staged["conflict_count"], staged["conflicts_with_default"]), (1, ["ci.yml"]))
        self.assertFalse(staged["changes_on_default"])

    def all_pr(self, number, head, base, state="MERGED"):
        return {"number": number, "state": state, "headRefName": head, "baseRefName": base}

    def push_branch(self, name, *files):
        self.git("switch", "-q", "-c", name, "main")
        for f in files:
            (self.repo / f).write_text(f)
            self.git("add", f)
        self.git("commit", "-q", "--allow-empty", "-m", name)
        self.git("push", "-q", "origin", name)
        self.git("switch", "-q", "main")

    def test_a_stranded_stack_from_before_the_window_is_still_staged(self):
        self.push_branch("feature/ds-542", "boundary.py")    # never reached main
        self.push_branch("feature/shipped", "shipped.py")    # its own PR merged to main
        report = self.gather([], all_prs=[
            self.all_pr(643, "ds-1", "feature/ds-542"), self.all_pr(700, "s-1", "feature/shipped"),
            self.all_pr(701, "feature/shipped", "main"), self.all_pr(650, "gone-1", "feature/deleted")])
        staged = report["staged_branches"]
        self.assertEqual([(b["branch"], b["merged_prs"], b["in_window"]) for b in staged],
                         [("feature/ds-542", [643], False)])

    def test_squash_merged_work_is_recognised_as_already_on_main(self):
        for name, f in (("squashed", "a.txt"), ("unique", "b.txt")):
            self.git("switch", "-q", "-c", name)
            (self.repo / f).write_text("x\n")
            self.git("add", f)
            self.git("commit", "-q", "-m", name)
            self.git("switch", "-q", "main")
        (self.repo / "a.txt").write_text("x\n")   # what a squash merge of `squashed` leaves on main
        self.git("add", "a.txt")
        self.git("commit", "-q", "-m", "squash")
        self.git("push", "-q", "origin", "main")
        orphans = {b["branch"]: b for b in self.gather([])["orphan_branches"]}
        self.assertTrue(orphans["squashed"]["changes_on_default"])
        self.assertFalse(orphans["unique"]["changes_on_default"])

    def test_a_detached_worktree_still_reports_its_risky_work(self):
        tree = self.root / "detached"
        self.git("worktree", "add", "-q", "--detach", str(tree))
        self.git("commit", "-q", "--allow-empty", "-m", "local only", cwd=tree)
        (tree / "research.md").write_text("notes")
        entry = next(t for t in self.gather([])["worktrees"] if t["path"] and t["path"].endswith("detached"))
        self.assertTrue(entry["detached"])
        self.assertEqual(entry["uncommitted_files"], 1)
        self.assertEqual(entry["unpushed_commits"], 1)

    def test_transcripts_are_dated_by_their_last_event_not_file_mtime(self):
        root = self.gather([])["repo"]["root"]
        project = Path(self.env["HOME"]) / ".claude" / "projects" / re.sub(r"[^A-Za-z0-9]", "-", root)
        project.mkdir(parents=True)
        now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        for name, ts in (("stale", "2026-01-01T00:00:00Z"), ("fresh", now)):
            events = [{"type": "user", "timestamp": ts, "message": {"content": f"{name} prompt"}},
                      {"type": "assistant", "timestamp": ts, "message": {"content": [{"type": "text", "text": "done"}]}}]
            (project / f"{name}.jsonl").write_text("\n".join(map(json.dumps, events)))   # both touched just now
        sessions = self.gather([])["local_transcripts"]
        self.assertEqual([t["first_prompt"] for t in sessions], ["fresh prompt"])
        self.assertEqual(sessions[0]["last_activity"], now)
        self.assertEqual(sessions[0]["session_id"], "fresh")

    def test_a_long_last_reply_is_cut_at_a_word_boundary(self):
        root = self.gather([])["repo"]["root"]
        project = Path(self.env["HOME"]) / ".claude" / "projects" / re.sub(r"[^A-Za-z0-9]", "-", root)
        project.mkdir(parents=True)
        now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        reply = "word " * 1000 + "FINDING: max_tokens caps thinking."
        events = [{"type": "user", "timestamp": now, "message": {"content": "audit prompts"}},
                  {"type": "assistant", "timestamp": now, "message": {"content": [{"type": "text", "text": reply}]}}]
        (project / "s.jsonl").write_text("\n".join(map(json.dumps, events)))
        last = self.gather([])["local_transcripts"][0]["last_reply"]
        self.assertTrue(last.startswith("word "), last[:20])
        self.assertTrue(last.endswith("FINDING: max_tokens caps thinking."))

    def test_an_issue_number_ending_a_pr_branch_name_takes_it_off_the_frontier(self):
        prs = [dict(self.open_pr(684, []), headRefName="codex/implement-ticket-672"),
               dict(self.open_pr(685, []), headRefName="f05-1-design-contracts-80"),
               dict(self.open_pr(686, []), headRefName="release-2")]
        report = self.gather([self.issue(672), self.issue(80), self.issue(1), self.issue(3)], prs)
        issues = {i["number"]: i for i in report["github"]["issues_open"]}
        self.assertEqual([(p["number"], p["works_on"]) for p in report["github"]["open"]],
                         [(684, [672]), (685, [80]), (686, [])])
        self.assertFalse(issues[672]["ready"])
        self.assertTrue(issues[1]["ready"])   # the "-1-" in f05-1-... isn't the last number

    def test_default_branch_ci_keeps_the_newest_run_per_workflow(self):
        def run(workflow, conclusion, at):
            return {"workflowName": workflow, "status": "completed", "conclusion": conclusion, "createdAt": at}
        report = self.gather([], runs={"main": [run("ci", "failure", "2026-10-03T00:00:00Z"),
                                                run("docs", "success", "2026-10-02T00:00:00Z"),
                                                run("ci", "success", "2026-10-01T00:00:00Z")]})
        self.assertEqual([(r["workflow"], r["conclusion"]) for r in report["github"]["default_ci"]],
                         [("ci", "failure"), ("docs", "success")])

    def test_a_mark_without_a_preceding_gather_records_no_frontier(self):
        self.mark()
        self.assertIsNone(self.gather([self.issue(5)])["frontier_changes"])


class PmStatusCheckReport(unittest.TestCase):
    """check_report.py against small drafted reports."""

    GOOD = """## shop: since last run (Oct 17 → now)

Main is green and #12 is ready to merge.

**Landed on main**
- #10 retry budget for the fetcher

**In flight:** nothing.

**Needs you**
- **#12 is green and waiting on review.** It unblocks #14, and every day it waits the branch drifts further from main.

**Next up**
1. **Merge #12:** it frees #14 for the next run (see Needs you).
2. **Start #15:** ready, unclaimed, and it unblocks #16.

**Cleanup:** 3 worktrees whose branches merged.
"""

    def check(self, text, facts=None):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        draft = Path(temp.name) / "draft.md"
        draft.write_text(text)
        args = [str(draft)]
        if facts is not None:
            (Path(temp.name) / "facts.json").write_text(json.dumps(facts))
            args += ["--facts", str(Path(temp.name) / "facts.json")]
        path = SKILLS / "pm-status" / "scripts" / "check_report.py"
        result = subprocess.run([sys.executable, str(path), *args], capture_output=True, text=True)
        return result.returncode, result.stdout

    def test_a_report_within_every_limit_passes(self):
        self.assertEqual(self.check(self.GOOD), (0, "ok: within every limit\n"))

    def test_a_three_sentence_verdict_is_flagged(self):
        code, out = self.check(self.GOOD.replace("ready to merge.", "ready to merge. Nothing broke. Two lanes idle."))
        self.assertEqual(code, 1)
        self.assertIn("verdict: 3 sentences", out)

    def test_a_long_needs_you_bullet_is_flagged(self):
        code, out = self.check(self.GOOD.replace("further from main.", "further from main " + "and more " * 15 + "."))
        self.assertIn("(Needs you)", out)

    def test_a_next_up_line_over_25_words_is_flagged(self):
        code, out = self.check(self.GOOD.replace("unblocks #16.", "unblocks #16 " + "and also more " * 6 + "."))
        self.assertRegex(out, r"line \d+ \(Next up\): \d+ words")

    def test_a_next_up_reason_that_repeats_its_needs_you_bullet_is_flagged(self):
        code, out = self.check(self.GOOD.replace("it frees #14 for the next run (see Needs you).",
                                                 "green and waiting on review, the branch drifts from main."))
        self.assertIn("repeats Needs-you bullet", out)

    def test_a_next_up_action_that_names_nothing_concrete_is_flagged(self):
        code, out = self.check(self.GOOD.replace("**Start #15:**", "**Delete the old workflows:**"))
        self.assertIn("names no PR, issue, branch", out)

    def test_cleanup_with_bullets_under_it_is_flagged(self):
        code, out = self.check(self.GOOD + "- worktree a\n- worktree b\n")
        self.assertIn("Cleanup is one line", out)

    def test_an_open_pr_without_its_ci_state_is_flagged(self):
        facts = {"github": {"open": [{"number": 12}, {"number": 30}]}}
        code, out = self.check(self.GOOD.replace("3 worktrees whose branches merged.",
                                                 "3 worktrees whose branches merged; PR #30 (target gone)."), facts)
        self.assertIn("PR #30: open PR shown without its CI state", out)
        self.assertNotIn("PR #12", out)


if __name__ == "__main__":
    unittest.main()
