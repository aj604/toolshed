#!/usr/bin/env python3
"""Public-contract guards for the scheduled, read-only bloat audit (#144)."""

import os
import re
import unittest


ROOT = os.path.join(os.path.dirname(__file__), "..", "..")
WORKFLOW = os.path.join(
    ROOT, "plugins", "doc-lifecycle", "skills", "scheduling-doc-sync",
    "doc-bloat-audit.yml",
)


class ScheduledBloatAuditContract(unittest.TestCase):
    def workflow_text(self):
        with open(WORKFLOW, encoding="utf-8") as stream:
            return stream.read()

    def test_lane_preflights_then_budget_dispatches_and_reports_typed_gaps(self):
        text = self.workflow_text()

        self.assertIn('- cron: "{{BLOAT_AUDIT_CRON}}"', text)
        self.assertIn("concurrency:\n  group: doc-bloat-audit", text)
        self.assertNotRegex(text, re.compile(r"\bgit\s+(commit|push)\b"))
        self.assertNotIn("contents: write", text)

        registry = text.index("test -f .doc-lifecycle/registry.json")
        public_plan = text.index(" bloat-plan ")
        model = text.index("anthropics/claude-code-action@")
        self.assertLess(registry, public_plan)
        self.assertLess(public_plan, model)

        self.assertIn("--results-dir \"${BLOAT_DIR}/chunks\"", text)
        self.assertIn("--emit-prompt", text)
        self.assertIn("--emit-turns", text)
        self.assertRegex(text, r'--allowedTools "[^"]*\bTask\b')
        self.assertIn("fresh Task", text)
        self.assertIn("max_turns", text)

        self.assertIn("--allow-partial", text)
        self.assertIn("--unswept-out \"${BLOAT_DIR}/unswept.json\"", text)
        self.assertIn(" bloat-audit ", text)
        self.assertIn("render-audit-summary.py summary --kind bloat", text)

        # Plans, chunk results, envelopes, reports, and cost data all live in
        # runner.temp. The checkout is evidence only, never artifact storage.
        self.assertIn("BLOAT_DIR: ${{ runner.temp }}/doc-bloat-audit", text)
        for name in ("manifest.json", "bloat-verdicts.json", "unswept.json",
                     "bloat-report.json", "audit-cost.json"):
            self.assertIn(f'${{BLOAT_DIR}}/{name}', text)
        self.assertNotRegex(text, r">\s*(?:manifest|bloat-(?:verdicts|report)|audit-cost)\.json")

    def test_every_action_is_sha_pinned_and_the_model_has_no_repo_credential(self):
        text = self.workflow_text()
        uses = re.findall(r"^\s*uses:\s*([^\s#]+)", text, re.MULTILINE)
        self.assertTrue(uses)
        for action in uses:
            self.assertRegex(action, r"^[^@]+@[0-9a-f]{40}$")
        self.assertNotIn("GH_TOKEN", text)
        self.assertIn("persist-credentials: false", text)
        self.assertIn("contents: read", text)

    def test_public_plan_is_a_real_preflight_and_tool_grant_is_closed(self):
        text = self.workflow_text()
        commands = "\n".join(
            line for line in text.splitlines()
            if not line.lstrip().startswith("#")
        )
        self.assertRegex(
            commands,
            r"python3 .*doc-lifecycle\.py bloat-plan --repo \.\s*\\",
        )
        self.assertIn(
            '--allowedTools "Task,Skill,Read,Grep,Glob,Write,'
            'Bash(git *),Bash(python3 *)"',
            text,
        )


if __name__ == "__main__":
    unittest.main(verbosity=2)
