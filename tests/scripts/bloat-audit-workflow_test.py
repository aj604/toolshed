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
BLOAT_GUIDE = os.path.join(ROOT, "docs", "guides", "auditing-doc-bloat.md")
PRINCIPLES_GUIDE = os.path.join(ROOT, "docs", "guides", "principles.md")


class ScheduledBloatAuditContract(unittest.TestCase):
    def workflow_text(self):
        with open(WORKFLOW, encoding="utf-8") as stream:
            return stream.read()

    def step_text(self, name):
        """One top-level audit-job step, through the next sibling step."""
        lines = self.workflow_text().splitlines()
        marker = f"      - name: {name}"
        start = lines.index(marker)
        end = next(
            (i for i in range(start + 1, len(lines))
             if lines[i].startswith("      - name: ")),
            len(lines),
        )
        return "\n".join(lines[start:end])

    def step_script(self, name):
        body = self.step_text(name).splitlines()
        run = body.index("        run: |")
        return "\n".join(
            line[10:] if line.startswith("          ") else line
            for line in body[run + 1:]
        ) + "\n"

    def test_public_guides_name_the_scheduled_report_and_human_apply_boundary(self):
        with open(BLOAT_GUIDE, encoding="utf-8") as stream:
            bloat_guide = stream.read()
        with open(PRINCIPLES_GUIDE, encoding="utf-8") as stream:
            principles = stream.read()

        for guide in (bloat_guide, principles):
            self.assertNotIn("There is no scheduled bloat sweep", guide)
            self.assertNotIn("unattended lane covers **drift** only", guide)

        self.assertRegex(
            bloat_guide,
            r"(?s)weekly, read-only scheduled bloat audit.*typed report",
        )
        self.assertIn(
            "[scheduling guide](scheduling-doc-sync.md)", bloat_guide,
        )
        self.assertRegex(bloat_guide, r"No scheduled lane\s+applies")

        self.assertIn("five GitHub Actions", principles)
        for workflow in (
                "doc-audit.yml", "doc-bloat-audit.yml", "doc-apply.yml",
                "doc-policy-apply.yml", "doc-sync-upgrade.yml"):
            self.assertIn(workflow, principles)
        self.assertRegex(
            principles,
            r"(?s)weekly bloat audit.*read-only.*published report",
        )
        self.assertRegex(
            principles,
            r"(?s)bloat findings.*person.*approve.*`fixing-docs`",
        )

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
        self.assertRegex(text, r'bloat-cadence\.py"\s+prepare')
        self.assertIn("coordinator-prompt.md", text)
        self.assertRegex(text, r'--allowedTools "[^"]*\bTask\b')
        self.assertIn("fresh Task", text)
        self.assertIn("--max-turns", text)

        self.assertIn("--allow-partial", text)
        self.assertIn("--unswept-out \"${BLOAT_DIR}/unswept.json\"", text)
        self.assertIn(" bloat-audit ", text)
        self.assertIn(
            "render-audit-summary.py summary --audit-surface bloat", text,
        )

        # Plans, chunk results, envelopes, reports, and cost data all live in
        # runner.temp. The checkout is evidence only, never artifact storage.
        # `runner` is step-scoped, so both jobs export the root from a step;
        # naming it above step scope made GitHub reject the file (#174).
        self.assertNotIn("BLOAT_DIR: ${{ runner.temp }}", text)
        self.assertEqual(
            2, text.count(
                'echo "BLOAT_DIR=${RUNNER_TEMP}/doc-bloat-audit" '
                '>> "${GITHUB_ENV}"'),
            "each job must resolve the artifact root before using it",
        )
        for name in ("manifest.json", "bloat-verdicts.json", "unswept.json",
                     "bloat-report.json", "audit-cost.json"):
            self.assertIn(f'${{BLOAT_DIR}}/{name}', text)
        self.assertNotRegex(text, r">\s*(?:manifest|bloat-(?:verdicts|report)|audit-cost)\.json")

    def test_actions_are_pinned_and_workflow_passes_no_explicit_repo_credential(self):
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
            '--allowedTools "Task,Read,Grep,Glob"',
            text,
        )
        model_grants = re.findall(r'--allowedTools "([^"]+)"', text)
        self.assertEqual(model_grants, ["Task,Read,Grep,Glob"] * 2)
        model_inventories = re.findall(r'--tools "([^"]+)"', text)
        self.assertEqual(model_inventories, ["Task,Read,Grep,Glob"] * 2)
        self.assertEqual(
            re.findall(r"--setting-sources ([^\s]+)", text),
            ["user", "user"],
        )
        self.assertEqual(text.count('CLAUDE_CODE_DISABLE_AUTO_MEMORY: "1"'), 2)
        self.assertEqual(
            re.findall(r'--disallowedTools "([^"]+)"', text),
            ["mcp__*", "mcp__*"],
        )
        self.assertEqual(
            re.findall(
                r"CLAUDE_CONFIG_DIR: "
                r"\$\{\{ runner\.temp \}\}/doc-bloat-audit/"
                r"(claude-config-[a-z]+)",
                text,
            ),
            ["claude-config-first", "claude-config-retry"],
        )
        prepare = self.step_script("Render trusted read-only coordinator prompt")
        self.assertIn("rm -rf", prepare)
        self.assertIn("mkdir -p", prepare)
        for config in ("claude-config-first", "claude-config-retry"):
            self.assertEqual(prepare.count(config), 2)
        self.assertEqual(text.count("--add-dir"), 2)
        self.assertNotIn('--add-dir "${{ runner.temp }}"', text)
        self.assertIn(
            '--add-dir "${{ runner.temp }}/doc-bloat-audit"', text,
        )
        for forbidden in ("Write", "Bash", "Skill"):
            self.assertNotIn(
                forbidden, " ".join(model_grants + model_inventories),
            )

    def test_supported_action_outputs_feed_trusted_collection_and_one_retry(self):
        text = self.workflow_text()
        first = text.index("- name: Dispatch bounded bloat workers")
        preserve_first = text.index(
            "- name: Preserve first-pass execution telemetry",
        )
        collect = text.index("- name: Validate worker returns and select retries")
        retry = text.index("- name: Retry invalid bloat chunks once")
        preserve_retry = text.index("- name: Preserve retry execution telemetry")
        final = text.index("- name: Validate retry returns")
        assembly = text.index("- name: Assemble chunk completion evidence")
        self.assertLess(first, preserve_first)
        self.assertLess(preserve_first, collect)
        self.assertLess(collect, retry)
        self.assertLess(retry, preserve_retry)
        self.assertLess(preserve_retry, final)
        self.assertLess(retry, final)
        self.assertLess(final, assembly)

        self.assertEqual(text.count("anthropics/claude-code-action@"), 2)
        self.assertEqual(text.count("--json-schema"), 2)
        self.assertIn("steps.model.outputs.structured_output", text)
        self.assertIn("steps.retry_model.outputs.structured_output", text)
        self.assertIn("steps.retry_model.outputs.execution_file", text)
        self.assertRegex(text, r'bloat-cadence\.py"\s+collect')
        self.assertIn(
            "if: ${{ always() && !cancelled() && "
            "steps.collect.outputs.retry == 'true' }}",
            self.step_text("Retry invalid bloat chunks once"),
        )

        first_copy = self.step_text("Preserve first-pass execution telemetry")
        retry_copy = self.step_text("Preserve retry execution telemetry")
        cost = self.step_text("Extract cost and turn observability")
        self.assertIn("steps.model.outputs.execution_file", first_copy)
        self.assertIn("execution-first.json", first_copy)
        self.assertIn("steps.retry_model.outputs.execution_file", retry_copy)
        self.assertIn("execution-retry.json", retry_copy)
        self.assertNotIn("steps.model.outputs.execution_file", cost)
        self.assertNotIn("steps.retry_model.outputs.execution_file", cost)
        self.assertIn('execution-first.json"', cost)
        self.assertIn('execution-retry.json"', cost)

    def test_integrity_gate_orders_model_before_trusted_assembly(self):
        text = self.workflow_text()
        model = text.index("- name: Dispatch bounded bloat workers")
        integrity = text.index("- name: Verify repository integrity before assembly")
        assembly = text.index("- name: Assemble chunk completion evidence")
        audit = text.index("- name: Run the public bloat audit")
        self.assertLess(model, integrity)
        self.assertLess(integrity, assembly)
        self.assertLess(assembly, audit)

        expected = "if: ${{ always() && steps.integrity.outcome == 'success' }}"
        self.assertIn("id: integrity", self.step_text(
            "Verify repository integrity before assembly"))
        self.assertIn(expected, self.step_text(
            "Assemble chunk completion evidence"))
        self.assertIn(expected, self.step_text("Run the public bloat audit"))

    def test_integrity_gate_checks_without_resetting_or_laundering(self):
        # #185 moved the check itself into one shared script both audit lanes
        # run — the behavioral cases live in check-repo-integrity_test.py, and
        # what this lane owns is running it, from the release-pinned
        # marketplace rather than from the checkout it is judging.
        script = self.step_script("Verify repository integrity before assembly")
        self.assertIn('PYTHONDONTWRITEBYTECODE: "1"', self.workflow_text())
        self.assertIn(
            '"${RUNNER_TEMP}/toolshed-marketplace/plugins/doc-lifecycle/'
            'skills/scheduling-doc-sync/scripts/check-repo-integrity.py"',
            script)
        self.assertIn('--expected-head "${GITHUB_SHA}"', script)
        self.assertNotRegex(script, r"\bgit\s+(?:reset|restore|checkout|clean)\b")

    def test_this_lane_declares_no_work_tree_artifact_at_all(self):
        # Every file this lane generates lives under BLOAT_DIR, so it exempts
        # nothing: an added file in the checkout is always a mutation here.
        script = self.step_script("Verify repository integrity before assembly")
        invocation = script.split("--out", 1)[0]
        self.assertNotIn("--allow", invocation)

    def test_a_refusal_reaches_the_run_surface_as_its_own_state(self):
        text = self.workflow_text()
        self.assertIn("name: bloat-audit-integrity", text)
        self.assertIn(
            "--integrity ${BLOAT_DIR}/audit-integrity.json",
            self.step_script("Render typed bloat summary"))


if __name__ == "__main__":
    unittest.main(verbosity=2)
