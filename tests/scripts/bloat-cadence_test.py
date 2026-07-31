#!/usr/bin/env python3
"""Trusted orchestration seam tests for the scheduled bloat cadence (#144)."""

import json
import os
import stat
import subprocess
import sys
import tempfile
import unittest


ROOT = os.path.join(os.path.dirname(__file__), "..", "..")
SCRIPT = os.path.join(
    ROOT, "plugins", "doc-lifecycle", "skills", "scheduling-doc-sync",
    "scripts", "bloat-cadence.py",
)


def write(path, text):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as stream:
        stream.write(text)


def fixture_manifest(path):
    write(path, json.dumps({
        "schema": 1,
        "chunks": [
            {"id": "c-a", "turns": 20, "docs": []},
            {"id": "c-b", "turns": 24, "docs": []},
        ],
        "pending": ["c-a", "c-b"],
    }))


def helper(path, body):
    write(path, "#!/usr/bin/env python3\n" + body)
    os.chmod(path, os.stat(path).st_mode | stat.S_IXUSR)


class BloatCadence(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.manifest = os.path.join(self.tmp.name, "manifest.json")
        self.results = os.path.join(self.tmp.name, "chunks")
        self.prompts = os.path.join(self.tmp.name, "prompts")
        self.prompt = os.path.join(self.tmp.name, "coordinator.md")
        self.retry_prompt = os.path.join(self.tmp.name, "retry.md")
        self.outputs = os.path.join(self.tmp.name, "github-output")
        fixture_manifest(self.manifest)

        self.planner = os.path.join(self.tmp.name, "planner.py")
        helper(self.planner, """
import sys
chunk_id = sys.argv[sys.argv.index('--emit-readonly-prompt') + 1] \\
    if '--emit-readonly-prompt' in sys.argv else None
if chunk_id:
    print(f'read-only task prompt for {chunk_id}')
else:
    requested = sys.argv[sys.argv.index('--emit-turns') + 1]
    print({'c-a': 20, 'c-b': 24}[requested])
""")
        self.validator = os.path.join(self.tmp.name, "validator.py")
        helper(self.validator, """
import json
import sys
path = sys.argv[sys.argv.index('--chunk') + 1]
with open(path, encoding='utf-8') as stream:
    payload = json.load(stream)
raise SystemExit(2 if payload.get('invalid') else 0)
""")

    def invoke(self, *args, structured=None):
        env = dict(os.environ)
        if structured is not None:
            env["MODEL_STRUCTURED_OUTPUT"] = json.dumps(structured)
        return subprocess.run(
            [sys.executable, SCRIPT, *args], capture_output=True, text=True,
            env=env,
        )

    def test_prepare_renders_exact_tasks_and_budgets(self):
        result = self.invoke(
            "prepare", "--manifest", self.manifest, "--planner", self.planner,
            "--root", self.tmp.name, "--out", self.prompt,
            "--prompts-dir", self.prompts,
            "--github-output", self.outputs,
        )

        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        with open(self.prompt, encoding="utf-8") as stream:
            prompt = stream.read()
        self.assertIn(os.path.join(self.prompts, "c-a.md"), prompt)
        self.assertIn(os.path.join(self.prompts, "c-b.md"), prompt)
        with open(os.path.join(self.prompts, "c-a.md"), encoding="utf-8") as stream:
            self.assertIn("read-only task prompt for c-a", stream.read())
        with open(self.outputs, encoding="utf-8") as stream:
            key, value = stream.read().strip().split("=", 1)
        self.assertEqual(key, "schema")
        self.assertEqual(
            json.loads(value)["required"], ["schema_version", "chunks"],
        )
        schema = json.loads(value)

        def assert_closed_objects(node):
            if not isinstance(node, dict):
                return
            if node.get("type") == "object":
                self.assertIs(node.get("additionalProperties"), False)
            for child in node.values():
                if isinstance(child, dict):
                    assert_closed_objects(child)
                elif isinstance(child, list):
                    for member in child:
                        assert_closed_objects(member)

        assert_closed_objects(schema)
        self.assertIn("max_turns: 20", prompt)
        self.assertIn("max_turns: 24", prompt)
        self.assertIn("fresh Task", prompt)
        self.assertIn("schema_version", prompt)

    def collect(self, structured, retry=True):
        args = [
            "collect", "--manifest", self.manifest,
            "--results-dir", self.results, "--validator", self.validator,
            "--github-output", self.outputs,
        ]
        if retry:
            args += [
                "--retry-prompt", self.retry_prompt,
                "--planner", self.planner, "--root", self.tmp.name,
                "--prompts-dir", self.prompts,
            ]
        return self.invoke(*args, structured=structured)

    def test_collect_extracts_supported_output_and_selects_only_invalid_retry(self):
        result = self.collect({
            "schema_version": 1,
            "chunks": [
                {"id": "c-a", "result_json": json.dumps({
                    "chunk": "c-a", "verdicts": [],
                })},
                {"id": "c-b", "result_json": json.dumps({
                    "chunk": "c-b", "invalid": True,
                })},
            ],
        })

        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertTrue(os.path.isfile(os.path.join(self.results, "c-a.json")))
        self.assertFalse(os.path.exists(os.path.join(self.results, "c-b.json")))
        with open(self.retry_prompt, encoding="utf-8") as stream:
            retry = stream.read()
        self.assertNotIn(os.path.join(self.prompts, "c-a.md"), retry)
        self.assertIn(os.path.join(self.prompts, "c-b.md"), retry)
        with open(self.outputs, encoding="utf-8") as stream:
            self.assertIn("retry=true", stream.read())

    def test_invalid_execution_seam_retries_every_still_pending_chunk(self):
        result = self.invoke(
            "collect", "--manifest", self.manifest,
            "--results-dir", self.results, "--validator", self.validator,
            "--github-output", self.outputs,
            "--retry-prompt", self.retry_prompt, "--planner", self.planner,
            "--root", self.tmp.name, "--prompts-dir", self.prompts,
            structured={"schema_version": 1, "chunks": [
                {"id": "c-nope", "result_json": json.dumps({
                    "chunk": "c-nope", "verdicts": [],
                })},
            ]},
        )

        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        with open(self.retry_prompt, encoding="utf-8") as stream:
            retry = stream.read()
        self.assertIn(os.path.join(self.prompts, "c-a.md"), retry)
        self.assertIn(os.path.join(self.prompts, "c-b.md"), retry)

    def test_outer_id_must_match_the_inner_chunk_identity(self):
        result = self.collect({
            "schema_version": 1,
            "chunks": [
                {"id": "c-a", "result_json": json.dumps({
                    "chunk": "c-b", "verdicts": [],
                })},
            ],
        })

        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertFalse(os.path.exists(os.path.join(self.results, "c-a.json")))
        self.assertFalse(os.path.exists(os.path.join(self.results, "c-b.json")))
        self.assertIn("chunk identity mismatch", result.stderr)
        with open(self.retry_prompt, encoding="utf-8") as stream:
            retry = stream.read()
        self.assertIn(os.path.join(self.prompts, "c-a.md"), retry)
        self.assertIn(os.path.join(self.prompts, "c-b.md"), retry)

    def test_invalid_retry_preserves_valid_first_pass_and_leaves_partial_truth(self):
        first = self.collect({
            "schema_version": 1,
            "chunks": [
                {"id": "c-a", "result_json": json.dumps({
                    "chunk": "c-a", "verdicts": [],
                })},
            ],
        })
        self.assertEqual(first.returncode, 0, first.stdout + first.stderr)

        second = self.collect({
            "schema_version": 1,
            "chunks": [
                {"id": "c-b", "result_json": json.dumps({
                    "chunk": "c-b", "invalid": True,
                })},
            ],
        }, retry=False)

        self.assertEqual(second.returncode, 0, second.stdout + second.stderr)
        self.assertTrue(os.path.isfile(os.path.join(self.results, "c-a.json")))
        self.assertFalse(os.path.exists(os.path.join(self.results, "c-b.json")))


if __name__ == "__main__":
    unittest.main(verbosity=2)
