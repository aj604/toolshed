#!/usr/bin/env python3
"""Black-box tests for scheduling-doc-sync's render-report.py.

Tests the script as a subprocess: real argv, real exit codes, real stdout, and a
real $GITHUB_STEP_SUMMARY file for the summary subcommands.
Run: python3 tests/scripts/render-report_test.py
"""

import os
import subprocess
import sys
import tempfile
import unittest

SCRIPT = os.path.join(
    os.path.dirname(__file__),
    "..", "..",
    "plugins", "doc-lifecycle", "skills", "scheduling-doc-sync",
    "scripts", "render-report.py",
)


class UpgradeRender(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.summary_path = os.path.join(self.tmp.name, "summary.md")

    def run_script(self, *argv):
        env = dict(os.environ)
        env["GITHUB_STEP_SUMMARY"] = self.summary_path
        return subprocess.run([sys.executable, SCRIPT, *argv],
                              capture_output=True, text=True, env=env)

    def summary(self):
        with open(self.summary_path, encoding="utf-8") as f:
            return f.read()

    # -- upgrade-summary ---------------------------------------------------

    def test_current_reports_both_versions(self):
        r = self.run_script("upgrade-summary", "--status", "current",
                            "--current", "0.7.0", "--latest", "0.7.0")
        self.assertEqual(r.returncode, 0, r.stderr)
        s = self.summary()
        self.assertIn("current", s.lower())
        self.assertIn("0.7.0", s)

    def test_ahead_names_dev_pin(self):
        r = self.run_script("upgrade-summary", "--status", "ahead",
                            "--current", "0.8.0", "--latest", "0.7.0")
        self.assertEqual(r.returncode, 0, r.stderr)
        s = self.summary()
        self.assertIn("ahead", s.lower())
        self.assertIn("0.8.0", s)
        self.assertIn("0.7.0", s)

    def test_noop_states_no_wiring_change(self):
        r = self.run_script("upgrade-summary", "--status", "noop",
                            "--current", "0.7.0", "--latest", "0.8.0")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("no wiring change", self.summary().lower())

    def test_opened_includes_pr_url_and_bump(self):
        r = self.run_script("upgrade-summary", "--status", "opened",
                            "--current", "0.7.0", "--latest", "0.8.0",
                            "--pr-url", "https://gh/pr/9")
        self.assertEqual(r.returncode, 0, r.stderr)
        s = self.summary()
        self.assertIn("https://gh/pr/9", s)
        self.assertIn("0.7.0", s)
        self.assertIn("0.8.0", s)

    def test_pending_reports_open_pr(self):
        r = self.run_script("upgrade-summary", "--status", "pending",
                            "--current", "0.7.0", "--latest", "0.8.0",
                            "--pr-url", "https://gh/pr/3")
        self.assertEqual(r.returncode, 0, r.stderr)
        s = self.summary()
        self.assertIn("https://gh/pr/3", s)
        self.assertIn("already open", s.lower())

    def test_blocked_workflows_lists_files_and_apply_steps(self):
        r = self.run_script(
            "upgrade-summary", "--status", "blocked-workflows",
            "--current", "0.9.2", "--latest", "0.9.3",
            "--files", ".github/workflows/doc-audit.yml,.github/doc-sync/render-report.py")
        self.assertEqual(r.returncode, 0, r.stderr)
        s = self.summary()
        # Names the offending workflow file, the artifact to apply, and git apply steps.
        self.assertIn(".github/workflows/doc-audit.yml", s)
        self.assertIn("doc-sync-upgrade-patch", s)
        self.assertIn("git apply", s)
        self.assertIn("0.9.3", s)

    def test_blocked_relocation_says_the_install_moved(self):
        # A one-time move needs a summary a maintainer can tell apart from a
        # routine template change (aj604/toolshed#133): it must name where the
        # install went and say the configuration came with it.
        r = self.run_script(
            "upgrade-summary", "--status", "blocked-relocation",
            "--current", "0.39.0", "--latest", "0.40.0",
            "--files", ".github/workflows/doc-audit.yml,.doc-lifecycle/wiring/render-report.py")
        self.assertEqual(r.returncode, 0, r.stderr)
        s = self.summary()
        self.assertIn(".doc-lifecycle/", s)
        self.assertIn(".github/doc-sync/", s)
        self.assertIn("one-time", s)
        self.assertIn("doc-sync-upgrade-patch", s)
        self.assertIn("git apply", s)

    def test_the_apply_instructions_stage_so_creations_land(self):
        # `git apply` without --index leaves creations untracked, and
        # `commit -am` would then miss them — a relocation patch is mostly
        # creations, so the instructions have to index the patch.
        for status in ("blocked-workflows", "blocked-relocation"):
            with self.subTest(status=status):
                r = self.run_script(
                    "upgrade-summary", "--status", status,
                    "--current", "0.39.0", "--latest", "0.40.0")
                self.assertEqual(r.returncode, 0, r.stderr)
                s = self.summary()
                self.assertIn("git apply --index", s)
                self.assertNotIn("commit -am", s)

    def test_the_refusal_points_a_pre_relocation_install_at_its_door(self):
        # The lane runs the *installed* path authority, and a copy predating
        # the new layout cannot authorize a move it has never heard of — so the
        # refusal has to name the local door rather than leave a dead end.
        r = self.run_script(
            "upgrade-summary", "--status", "refused",
            "--current", "0.39.0", "--latest", "0.40.0")
        self.assertEqual(r.returncode, 0, r.stderr)
        s = self.summary()
        self.assertIn(".doc-lifecycle/", s)
        self.assertIn("Upgrade mode", s)

    def test_undeclared_paths_names_them_and_says_nothing_landed(self):
        # The upgrade lane stages apply-upgrade.py's declared set and refuses
        # anything left over; that refusal has to name what was left and be
        # unambiguous that no commit or push happened.
        r = self.run_script(
            "upgrade-summary", "--status", "undeclared-paths",
            "--current", "0.36.0", "--latest", "0.37.0",
            "--files", "docs/stray.md,.github/doc-sync/surprise.json")
        self.assertEqual(r.returncode, 0, r.stderr)
        s = self.summary()
        self.assertIn("docs/stray.md", s)
        self.assertIn(".github/doc-sync/surprise.json", s)
        self.assertIn("0.37.0", s)
        self.assertIn("nothing was committed or pushed", s.lower())

    def test_undeclared_paths_renders_without_a_file_list(self):
        r = self.run_script(
            "upgrade-summary", "--status", "undeclared-paths",
            "--current", "0.36.0", "--latest", "0.37.0")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("refused", self.summary().lower())

    def test_unknown_status_exits_2(self):
        r = self.run_script("upgrade-summary", "--status", "bogus",
                            "--current", "0.7.0", "--latest", "0.8.0")
        self.assertEqual(r.returncode, 2)

    # -- upgrade-pr-body ---------------------------------------------------

    def test_pr_body_shows_bump_and_preserved_state(self):
        r = self.run_script("upgrade-pr-body", "--current", "0.7.0",
                            "--latest", "0.8.0")
        self.assertEqual(r.returncode, 0, r.stderr)
        out = r.stdout
        self.assertIn("0.7.0", out)
        self.assertIn("0.8.0", out)
        # states what the upgrade preserves, so a reviewer trusts the diff
        self.assertIn("marker", out.lower())
        self.assertIn("audit-scope", out.lower())

    def test_pr_body_lists_changed_files_when_given(self):
        r = self.run_script("upgrade-pr-body", "--current", "0.7.0",
                            "--latest", "0.8.0",
                            "--files", ".github/workflows/doc-sync-upgrade.yml,"
                                       ".github/doc-sync/upgrade-gate.py")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("`.github/workflows/doc-sync-upgrade.yml`", r.stdout)
        self.assertIn("`.github/doc-sync/upgrade-gate.py`", r.stdout)

    # -- detection-only statuses (aj604/toolshed#127) ----------------------

    def test_available_says_nothing_ran_and_names_the_dispatch(self):
        r = self.run_script("upgrade-summary", "--status", "available",
                            "--current", "0.7.0", "--latest", "0.8.0")
        self.assertEqual(r.returncode, 0, r.stderr)
        summary = self.summary()
        self.assertIn("0.8.0", summary)
        # The whole point of the split: detection executes nothing.
        self.assertIn("none of the release's code ran", summary)
        self.assertIn("target: 0.8.0", summary)

    def test_notified_explains_why_no_second_issue_was_filed(self):
        r = self.run_script("upgrade-summary", "--status", "notified",
                            "--current", "0.7.0", "--latest", "0.8.0")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("no second one was filed", self.summary())

    def test_refused_states_that_nothing_was_staged(self):
        r = self.run_script("upgrade-summary", "--status", "refused",
                            "--current", "0.7.0", "--latest", "0.8.0")
        self.assertEqual(r.returncode, 0, r.stderr)
        summary = self.summary()
        self.assertIn("outside the wiring", summary)
        self.assertIn("no pull request was opened", summary)

    # -- upgrade-notice ----------------------------------------------------

    def notice(self, latest="0.8.0"):
        paths = {k: os.path.join(self.tmp.name, k)
                 for k in ("title.txt", "body.md")}
        r = self.run_script("upgrade-notice", "--current", "0.7.0",
                            "--latest", latest, "--repo", "acme/widgets",
                            "--title-out", paths["title.txt"],
                            "--body-out", paths["body.md"])
        read = {}
        for key, path in paths.items():
            if not os.path.exists(path):
                read[key] = ""
                continue
            with open(path, encoding="utf-8") as f:
                read[key] = f.read()
        return r, read

    def test_the_notice_title_names_the_release(self):
        r, out = self.notice()
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("0.8.0", out["title.txt"])
        # The title is the gate's dedupe key, so it travels on stdout too.
        self.assertEqual(r.stdout.strip(), out["title.txt"].strip())

    def test_the_notice_body_routes_the_reader_to_the_release_and_dispatch(self):
        _, out = self.notice()
        body = out["body.md"]
        self.assertIn("https://github.com/acme/widgets/releases/tag/v0.8.0", body)
        self.assertIn("target: 0.8.0", body)
        # It must not read as if an upgrade already happened.
        self.assertIn("Nothing has run.", body)

    def test_the_renderer_decides_nothing(self):
        # aj604/toolshed#127 review: gate decisions live in upgrade-gate.py, and
        # every run-surface string here. This subcommand writes no decision.
        r, _ = self.notice()
        self.assertNotIn("notice=", r.stdout)


if __name__ == "__main__":
    unittest.main(verbosity=1)
