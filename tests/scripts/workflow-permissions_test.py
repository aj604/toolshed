#!/usr/bin/env python3
"""Guards the trust split every shipped workflow depends on: the model steps
hold no repository write authority.

Contract asserted, over both the published templates and this repo's dogfooded
install:

1. A job that invokes `anthropics/claude-code-action` declares job-level
   permissions, grants `contents: read`, and grants no write scope other than
   `id-token: write` (the OAuth exchange, not repo write).
2. Such a job carries no `GH_TOKEN` in its environment — job-level or
   workflow-level.
3. Every `actions/checkout` in such a job sets `persist-credentials: false`,
   so the checkout leaves no write-capable credential in `.git/config`.
4. A job holding a write scope invokes no model, and never stages with a broad
   `git add -A` — the credentialed jobs stage an explicit authorized path list.
5. The workflow-level `permissions:` block grants no write scope, so a job that
   forgets to declare its own inherits nothing dangerous.
6. No `--allowedTools` grant names a Bash executable beyond `git` and
   `python3` — those patterns are prefix-matched, so naming a program grants
   all of it (aj604/toolshed#118).

(4) has no exceptions left. `doc-sync-upgrade.yml`'s write job held the last
one, staging a deterministic script's output wholesale; aj604/toolshed#77 took
`git add -A` out of it and #127 split the lane so the write job stages the path
set `stage-upgrade.py` authorized.

Parsed with a line scanner rather than a YAML library: the test suite is
stdlib-only, and the shipped workflows are uniformly 2-space indented.

Run: python3 tests/scripts/workflow-permissions_test.py
"""

import glob
import os
import re
import unittest

ROOT = os.path.join(os.path.dirname(__file__), "..", "..")

WORKFLOW_GLOBS = [
    # Published templates the scheduling-doc-sync skill installs.
    "plugins/doc-lifecycle/skills/scheduling-doc-sync/*.yml",
    # This repo's own dogfooded install.
    ".github/workflows/doc-*.yml",
]

MODEL_ACTION = "anthropics/claude-code-action"
# `git add -A` / `git add --all`, in any surrounding shell.
BROAD_ADD = re.compile(r"git add\s+(-A|--all)\b")


def workflow_files():
    seen, files = set(), []
    for pattern in WORKFLOW_GLOBS:
        for path in sorted(glob.glob(os.path.join(ROOT, pattern))):
            real = os.path.realpath(path)
            if real in seen:
                continue
            seen.add(real)
            files.append(path)
    return files


def indent_of(line):
    return len(line) - len(line.lstrip(" "))


def block_at(lines, start, indent):
    """Lines strictly more indented than `indent`, starting at `start`."""
    out = []
    for line in lines[start:]:
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        if indent_of(line) <= indent:
            break
        out.append(line)
    return out


def mapping_under(lines, key, indent):
    """The `key:`-introduced mapping at `indent`, as {name: value}."""
    for i, line in enumerate(lines):
        if indent_of(line) == indent and line.strip() == f"{key}:":
            entries = {}
            for entry in block_at(lines, i + 1, indent):
                name, _, value = entry.strip().partition(":")
                entries[name.strip()] = value.strip()
            return entries
    return None


def jobs_of(path):
    """{job name: [body lines]} for one workflow file."""
    with open(path, encoding="utf-8") as fh:
        lines = fh.read().splitlines()
    try:
        start = lines.index("jobs:") + 1
    except ValueError:
        return {}
    jobs, name = {}, None
    for line in lines[start:]:
        if indent_of(line) == 2 and line.rstrip().endswith(":") and line.strip():
            name = line.strip().rstrip(":")
            jobs[name] = []
        elif name is not None:
            jobs[name].append(line)
    return jobs


def write_scopes(permissions):
    return {k: v for k, v in (permissions or {}).items() if v == "write"}


class ModelJobsAreReadOnly(unittest.TestCase):
    def setUp(self):
        self.files = workflow_files()
        # Guard against the globs silently matching nothing (renamed dirs).
        self.assertTrue(self.files, "no workflow files found — did the layout move?")

    def model_jobs(self):
        found = []
        for path in self.files:
            for name, body in jobs_of(path).items():
                if any(MODEL_ACTION in line for line in body):
                    found.append((os.path.relpath(path, ROOT), name, body))
        return found

    def test_some_model_jobs_exist(self):
        self.assertTrue(self.model_jobs(),
                        "no claude-code-action job found — did the action move?")

    def test_model_jobs_grant_only_read_and_id_token(self):
        for path, name, body in self.model_jobs():
            perms = mapping_under(body, "permissions", 4)
            self.assertIsNotNone(
                perms, f"{path}: job '{name}' runs a model with no job-level "
                       f"permissions — it would inherit the workflow's")
            self.assertEqual(
                perms.get("contents"), "read",
                f"{path}: job '{name}' runs a model with contents: "
                f"{perms.get('contents')!r}")
            self.assertEqual(
                set(write_scopes(perms)) - {"id-token"}, set(),
                f"{path}: job '{name}' runs a model with write scopes "
                f"{sorted(write_scopes(perms))}")

    def test_model_jobs_carry_no_gh_token(self):
        for path, name, body in self.model_jobs():
            self.assertNotIn(
                "GH_TOKEN", mapping_under(body, "env", 4) or {},
                f"{path}: job '{name}' runs a model with GH_TOKEN in its env")
        for path in self.files:
            with open(path, encoding="utf-8") as fh:
                lines = fh.read().splitlines()
            self.assertNotIn("GH_TOKEN", mapping_under(lines, "env", 0) or {},
                             f"{os.path.relpath(path, ROOT)}: a workflow-level "
                             f"GH_TOKEN reaches every job, model jobs included")

    def test_model_jobs_drop_the_checkout_credential(self):
        for path, name, body in self.model_jobs():
            checkouts = sum(1 for line in body if "actions/checkout@" in line)
            dropped = sum(1 for line in body if line.strip().startswith(
                "persist-credentials: false"))
            self.assertEqual(
                checkouts, dropped,
                f"{path}: job '{name}' runs a model with {checkouts} "
                f"checkout(s) but {dropped} persist-credentials: false")


class WriteJobsRunNoModel(unittest.TestCase):
    def setUp(self):
        self.files = workflow_files()
        self.assertTrue(self.files)

    def write_jobs(self):
        found = []
        for path in self.files:
            for name, body in jobs_of(path).items():
                perms = mapping_under(body, "permissions", 4) or {}
                if set(write_scopes(perms)) - {"id-token"}:
                    found.append((os.path.relpath(path, ROOT), name, body))
        return found

    def test_some_write_jobs_exist(self):
        self.assertTrue(self.write_jobs(),
                        "no credentialed job found — did the layout move?")

    def test_write_jobs_invoke_no_model(self):
        for path, name, body in self.write_jobs():
            self.assertFalse(
                any(MODEL_ACTION in line for line in body),
                f"{path}: job '{name}' holds write scopes and runs a model")

    def test_write_jobs_stage_explicit_paths(self):
        for path, name, body in self.write_jobs():
            offenders = [line.strip() for line in body
                         if BROAD_ADD.search(line)
                         and not line.strip().startswith("#")]
            self.assertEqual(
                offenders, [],
                f"{path}: job '{name}' holds write scopes and stages broadly "
                f"({offenders}) — stage the authorized path list instead")


class ModelToolGrantsStayLocal(unittest.TestCase):
    """No model step may shell out to a program beyond git and python3.

    `--allowedTools` patterns are prefix-matched, so `Bash(gh *)` is not a
    grant for `gh <sub> --help` — it is a grant for `gh api` and `gh pr list`
    too, i.e. GitHub API surface declared for a job the suite above keeps
    deliberately token-free. aj604/toolshed#118 decided the audit lane reaches
    Tier-2 tool evidence through a script under the existing `Bash(python3 *)`
    allowance instead (`scripts/probe-evidence-tool.py`, which enumerates both
    which programs and how), so this list is the decision written down where a
    future widening has to argue with it.
    """

    ALLOWED_EXECUTABLES = {"git", "python3"}
    GRANT = re.compile(r'--allowedTools\s+"([^"]*)"')
    BASH_ENTRY = re.compile(r"Bash\(([^)]*)\)")

    def test_some_grants_exist(self):
        found = [p for p in workflow_files()
                 if self.GRANT.search(open(p, encoding="utf-8").read())]
        self.assertTrue(found, "no --allowedTools grant found — did it move?")

    def test_no_grant_names_an_executable_beyond_git_and_python3(self):
        for path in workflow_files():
            with open(path, encoding="utf-8") as fh:
                text = fh.read()
            for grant in self.GRANT.findall(text):
                for entry in self.BASH_ENTRY.findall(grant):
                    executable = entry.split()[0] if entry.split() else entry
                    self.assertIn(
                        executable, self.ALLOWED_EXECUTABLES,
                        f"{os.path.relpath(path, ROOT)}: a model step grants "
                        f"Bash({entry}) — prefix matching makes that the whole "
                        f"program, not one subcommand. Reach a new tool "
                        f"through probe-evidence-tool.py under the existing "
                        f"python3 allowance, or argue the widening on its own "
                        f"(aj604/toolshed#118)")


class WorkflowDefaultsAreReadOnly(unittest.TestCase):
    def test_workflow_level_permissions_grant_no_write(self):
        for path in workflow_files():
            with open(path, encoding="utf-8") as fh:
                lines = fh.read().splitlines()
            perms = mapping_under(lines, "permissions", 0)
            self.assertIsNotNone(
                perms, f"{os.path.relpath(path, ROOT)}: no workflow-level "
                       f"permissions block")
            self.assertEqual(
                write_scopes(perms), {},
                f"{os.path.relpath(path, ROOT)}: workflow-level permissions "
                f"grant {sorted(write_scopes(perms))} to every job")


class EnvValuesReferenceAvailableContexts(unittest.TestCase):
    """GitHub validates context availability per workflow key, and a violation
    makes the whole file unprocessable: the schedule never registers, and every
    push produces a zero-job failure run named after the file's path rather than
    its `name:` (aj604/toolshed#174).

    `runner`, `steps`, and `job` resolve only once a step is executing on a
    runner, so they are available in step-level `env:` and nowhere above it.
    Workflow-level `env:` additionally cannot see the job-scoped contexts.
    """

    STEP_ONLY = ("runner", "steps", "job")
    JOB_ONLY = ("needs", "matrix", "strategy")

    def assert_no_contexts(self, entries, contexts, where):
        for name, value in (entries or {}).items():
            for context in contexts:
                self.assertNotRegex(
                    value, r"\$\{\{[^}]*\b%s\." % context,
                    f"{where}: env value `{name}` references the `{context}` "
                    f"context, which is not available there — GitHub rejects "
                    f"the whole workflow file")

    def test_env_blocks_above_step_scope_avoid_step_scoped_contexts(self):
        for path in workflow_files():
            rel = os.path.relpath(path, ROOT)
            with open(path, encoding="utf-8") as fh:
                lines = fh.read().splitlines()
            self.assert_no_contexts(
                mapping_under(lines, "env", 0),
                self.STEP_ONLY + self.JOB_ONLY,
                f"{rel}: workflow-level env")
            for job, body in jobs_of(path).items():
                self.assert_no_contexts(
                    mapping_under(body, "env", 4),
                    self.STEP_ONLY,
                    f"{rel}: job `{job}` env")


if __name__ == "__main__":
    unittest.main()
