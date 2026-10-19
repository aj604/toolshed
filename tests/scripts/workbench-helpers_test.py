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

    def lane_report(self):
        # A remote branch with no PR must survive reconstruction. Round 2's PR
        # deliberately targets develop instead of round 1, so it must be flagged.
        bindir = self.root / "bin"
        bindir.mkdir()
        gh = bindir / "gh"
        gh.write_text(f"#!{sys.executable}\n" + '''
import json, sys
args = sys.argv[1:]
if args[:2] == ["repo", "view"]:
    print("develop")
elif args[:2] == ["pr", "list"]:
    print(json.dumps([{"number": 12, "title": "Second increment",
        "headRefName": "lane/cli/r2", "baseRefName": "develop",
        "isDraft": True, "state": "OPEN", "url": "https://example.test/12",
        "mergedAt": None, "reviewDecision": ""}]))
elif args[0] == "api":
    print("lane/cli/r1\\nlane/cli/r2")
else:
    sys.exit("unexpected gh call: " + repr(args))
''')
        gh.chmod(0o755)
        self.env["PATH"] = str(bindir) + os.pathsep + self.env.get("PATH", "")
        return self.run_helper("incremental-enhancement-lanes", "lanes.py",
                               "--repo", "example/project", "--json")

    def test_reconstruction_keeps_a_pushed_round_without_a_pr(self):
        report = self.lane_report()
        first = report["lanes"]["cli"]["rounds"][0]
        self.assertEqual(first["branch"], "lane/cli/r1")
        self.assertEqual(first["status"], "branch pushed, no PR")
        self.assertEqual(first["expected_base"], "develop")
        self.assertTrue(any("no pull request" in p for p in report["problems"]))

    def test_reconstruction_flags_a_broken_stack_and_resumes_from_its_tip(self):
        report = self.lane_report()
        lane = report["lanes"]["cli"]
        self.assertEqual(lane["next_round"], 3)
        self.assertEqual(lane["next_base"], "lane/cli/r2")
        self.assertTrue(any("expected lane/cli/r1" in p for p in report["problems"]))

if __name__ == "__main__":
    unittest.main()
