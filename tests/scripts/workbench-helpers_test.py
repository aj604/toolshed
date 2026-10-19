"""Exercise the imported workbench helpers through their CLI surfaces, offline."""

import json
import os
from pathlib import Path
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

if __name__ == "__main__":
    unittest.main()
