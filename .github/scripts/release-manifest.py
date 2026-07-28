#!/usr/bin/env python3
"""The release manifest guard (aj604/toolshed#77).

Discovery wires a new suite the moment its file lands (#99) — but only if the
file lands where the discovery step can see it. Three ways it silently does
not, every one of which leaves CI green:

1. A suite in a `tests/engine/` subdirectory with no `__init__.py`.
   `unittest discover` skips the directory without a word and reports OK.
2. A suite whose name the discovery pattern misses (`test_foo.py`), or a
   pattern narrowed in `release.yml` so it stops matching what it used to.
3. A suite in a directory no discovery step reaches at all.

The guard closes all three the same way: it reads `release.yml` for the
discovery steps CI actually runs, computes the set of suites those steps would
really execute, and requires that set to cover every suite in the tree.
Deriving the commands rather than restating them is the point — narrowing a
glob in `release.yml` moves the guard's own baseline, and is caught rather
than obeyed.

It also carries the release manifest: the gate criteria issue #77 names, each
mapped to the suites that discharge it. Discovery running a shrinking set of
suites is green; discovery no longer running `install-parity_test.py` is not.

Detection is structural, not name-based: a file is a suite when it declares a
TestCase subclass carrying test methods. A rename that hides a suite from
discovery must not also hide it from the guard.

Repo-CI infrastructure, not published plugin content — lives outside plugins/
on purpose (see CLAUDE.md).

Run: python3 .github/scripts/release-manifest.py
"""

import argparse
import ast
import importlib.util
import json
import os
import re
import subprocess
import sys

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))

# Declared NON-gate roots. The RED/GREEN skill baselines are retained as the
# methodology for skill edits and never gate a release (issue #57's distilled
# decisions, 2026-07-26; issue #77's fifth criterion), and the fixtures are
# sample repositories, not suites. A suite under either is not required to be
# wired — and, checked the other way, must not be swept into the gate.
NON_GATE_ROOTS = ("tests/baselines", "tests/fixtures")

# The release manifest: each gate criterion #77 names, and the suites that
# discharge it. Every path must exist AND be in the set the release pipeline's
# discovery actually runs. Discovery alone cannot notice a suite that was
# deleted rather than unwired; this can.
GATE_MANIFEST = {
    "acceptance seam": [
        "tests/engine/acceptance/scenario_one_test.py",
        "tests/engine/acceptance/scenario_two_test.py",
        "tests/engine/acceptance/scenario_drift_test.py",
        "tests/engine/acceptance/scenario_bloat_test.py",
        "tests/engine/acceptance/scenario_cache_test.py",
        "tests/engine/acceptance/scenario_approval_test.py",
    ],
    # The hostile corpus the acceptance fixture builds, and the refusals it
    # must produce: hostile filenames and malformed input that change nothing
    # (scenario one, scenario drift), the applier's and approval set's forgery
    # refusals, path authorization, and the static no-shell/no-exec capability
    # assertion over the one component that writes.
    "adversarial corpus": [
        "tests/engine/acceptance/scenario_one_test.py",
        "tests/engine/acceptance/scenario_drift_test.py",
        "tests/engine/applier_test.py",
        "tests/engine/approval_test.py",
        "tests/engine/paths_test.py",
        "tests/scripts/engine-capability_test.py",
    ],
    # The auto-apply policy's can-mint / cannot-mint cases.
    "auto-apply can-mint and cannot-mint": [
        "tests/engine/acceptance/scenario_policy_test.py",
        "tests/engine/policy_test.py",
    ],
    "workflow permission checks": [
        "tests/scripts/workflow-permissions_test.py",
        "tests/scripts/audit-workflow_test.py",
        "tests/scripts/apply-workflow_test.py",
    ],
    "template/dogfood equivalence": [
        "tests/scripts/install-parity_test.py",
    ],
    "migration dry run": [
        "tests/engine/migrate_test.py",
        "tests/engine/migrate_cli_test.py",
    ],
}


# --- what the tree holds -------------------------------------------------

def _read(path):
    with open(path, encoding="utf-8") as handle:
        return handle.read()


def _rel(path, repo_root):
    # realpath on both sides: a discovery subprocess reports a module's
    # resolved __file__, and a repository under a symlinked root (macOS
    # /var → /private/var) would otherwise never compare equal.
    return os.path.relpath(os.path.realpath(path),
                           os.path.realpath(repo_root)).replace(os.sep, "/")


def _test_classes(tree):
    """Every class in one module that is, transitively, a TestCase subclass."""
    classes = {node.name: node for node in tree.body
               if isinstance(node, ast.ClassDef)}
    known = set()
    changed = True
    while changed:
        changed = False
        for name, node in classes.items():
            if name in known:
                continue
            for base in node.bases:
                spelling = ast.unparse(base)
                if spelling.split(".")[-1].endswith("TestCase") or spelling in known:
                    known.add(name)
                    changed = True
                    break
    return [classes[name] for name in known]


def declares_tests(path):
    """True when this file declares a TestCase subclass carrying test methods.

    Structural rather than name-based, so `support.py` and `fixture.py` —
    which declare TestCase bases with no test methods of their own — are
    correctly not suites, while a suite named `checks.py` still is one.
    """
    try:
        tree = ast.parse(_read(path))
    except (SyntaxError, UnicodeDecodeError):
        return False
    for node in _test_classes(tree):
        for item in node.body:
            if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)) \
                    and item.name.startswith("test"):
                return True
    return False


def suites_in_tree(repo_root, non_gate_roots=NON_GATE_ROOTS):
    """Every suite under `tests/`, as repo-relative paths, minus the declared
    non-gate roots."""
    tests_dir = os.path.join(repo_root, "tests")
    found = set()
    for dirpath, dirnames, filenames in os.walk(tests_dir):
        dirnames.sort()
        for name in sorted(filenames):
            if not name.endswith(".py"):
                continue
            full = os.path.join(dirpath, name)
            rel = _rel(full, repo_root)
            if any(rel.startswith(root + "/") for root in non_gate_roots):
                continue
            if declares_tests(full):
                found.add(rel)
    return found


# --- what the release pipeline actually runs -----------------------------

# `python3 -m unittest discover -s <dir> -p <pattern>`, quoted however.
_DISCOVER = re.compile(
    r"unittest\s+discover\s+-s\s+(?P<dir>\S+)\s+-p\s+"
    r"(?P<q>['\"]?)(?P<pattern>[^'\"\s]+)(?P=q)")
_SCRIPT_RUNNER = re.compile(
    r"(?P<script>\S*run-script-suites\.py)(?:\s+--dir[= ](?P<dir>\S+))?")


def release_discovery_steps(release_yml):
    """The discovery commands `release.yml` runs, read off the workflow.

    A line scanner rather than a YAML library, like the other workflow guards
    in this suite: stdlib-only, and what matters here is the command text.
    """
    steps = {"unittest": [], "script_runner": []}
    for line in _read(release_yml).splitlines():
        if line.lstrip().startswith("#"):
            continue
        found = _DISCOVER.search(line)
        if found:
            steps["unittest"].append(
                {"dir": found.group("dir"), "pattern": found.group("pattern")})
        found = _SCRIPT_RUNNER.search(line)
        if found:
            steps["script_runner"].append(
                {"script": found.group("script"), "dir": found.group("dir")})
    return steps


# Discovery runs out of process: importing suite modules must not reach the
# guard's own interpreter, and two synthetic trees must not collide in
# sys.modules.
_COLLECT = r"""
import json, sys, unittest
start, pattern = sys.argv[1], sys.argv[2]
loader = unittest.TestLoader()
suite = loader.discover(start, pattern=pattern)
files, broken = set(), [str(e) for e in getattr(loader, "errors", [])]
def walk(s):
    for item in s:
        if isinstance(item, unittest.TestSuite):
            walk(item)
        elif item.__class__.__name__ == "_FailedTest":
            broken.append(item.id())
        else:
            module = sys.modules.get(item.__class__.__module__)
            path = getattr(module, "__file__", None)
            if path:
                files.add(path)
            else:
                broken.append(item.id())
walk(suite)
print(json.dumps({"files": sorted(files), "broken": broken}))
"""


def unittest_discovered(start_dir, pattern, repo_root):
    """The suite files `unittest discover -s start_dir -p pattern` loads."""
    result = subprocess.run(
        [sys.executable, "-c", _COLLECT, start_dir, pattern],
        capture_output=True, text=True, cwd=repo_root)
    if result.returncode != 0:
        return set(), [f"discovery over {start_dir!r} failed: "
                       f"{result.stderr.strip().splitlines()[-1:]}"]
    payload = json.loads(result.stdout)
    return ({_rel(path, repo_root) for path in payload["files"]},
            payload["broken"])


def script_runner_discovered(script, scripts_dir, repo_root):
    """What the script-suite runner would run — asked of the runner itself,
    so the guard cannot drift from the glob CI uses."""
    path = os.path.normpath(os.path.join(repo_root, script))
    if not os.path.exists(path):
        return set(), [f"release.yml runs {script}, which does not exist"]
    spec = importlib.util.spec_from_file_location("_suite_runner", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    target = os.path.join(repo_root, scripts_dir) if scripts_dir \
        else module.DEFAULT_DIR
    return {_rel(found, repo_root) for found in module.discover(target)}, []


class Report:
    """What the guard found. Every field is a list, and empty is good."""

    def __init__(self, gate, unwired, missing_steps, manifest_missing,
                 broken, swept):
        self.gate = gate
        self.unwired = unwired
        self.missing_steps = missing_steps
        self.manifest_missing = manifest_missing
        self.broken = broken
        self.swept = swept

    @property
    def ok(self):
        return not (self.unwired or self.missing_steps
                    or self.manifest_missing or self.broken or self.swept)

    def render(self):
        lines = []
        if self.missing_steps:
            lines.append("release.yml no longer runs a discovery step:")
            lines += [f"  - {step}" for step in self.missing_steps]
        if self.unwired:
            lines.append(
                "these suites exist but no release.yml discovery step runs "
                "them (a subdirectory missing __init__.py, a name the "
                "pattern misses, or a directory nothing discovers):")
            lines += [f"  - {path}" for path in self.unwired]
        if self.manifest_missing:
            lines.append(
                "these gate criteria lost a suite the release manifest "
                "requires:")
            lines += [f"  - {criterion}: {path}"
                      for criterion, path in self.manifest_missing]
        if self.broken:
            lines.append("discovery could not load these suites:")
            lines += [f"  - {item}" for item in self.broken]
        if self.swept:
            lines.append(
                "these are retained as methodology, not gate suites, and "
                "must not be in the gate:")
            lines += [f"  - {path}" for path in self.swept]
        if not lines:
            lines.append(
                f"release manifest guard: {len(self.gate)} suite(s) wired, "
                f"every gate criterion covered.")
        return "\n".join(lines)


def audit(repo_root=ROOT, manifest=None, release_yml=None):
    """Compare the suites the tree holds against the suites CI runs."""
    repo_root = os.path.abspath(repo_root)
    manifest = GATE_MANIFEST if manifest is None else manifest
    release_yml = release_yml or os.path.join(
        repo_root, ".github", "workflows", "release.yml")

    steps = release_discovery_steps(release_yml)
    missing_steps = []
    if not steps["script_runner"]:
        missing_steps.append(
            "run-script-suites.py — the tests/scripts suites would stop running")
    if not steps["unittest"]:
        missing_steps.append(
            "unittest discover — the engine suites would stop running")

    gate, broken = set(), []
    for step in steps["unittest"]:
        files, errors = unittest_discovered(step["dir"], step["pattern"],
                                            repo_root)
        gate |= files
        broken += errors
    for step in steps["script_runner"]:
        files, errors = script_runner_discovered(step["script"], step["dir"],
                                                 repo_root)
        gate |= files
        broken += errors

    tree = suites_in_tree(repo_root)
    manifest_missing = [
        (criterion, path)
        for criterion, paths in sorted(manifest.items())
        for path in paths
        if not os.path.exists(os.path.join(repo_root, path)) or path not in gate
    ]
    swept = sorted(path for path in gate
                   if any(path.startswith(root + "/") for root in NON_GATE_ROOTS))
    return Report(gate=sorted(gate), unwired=sorted(tree - gate),
                  missing_steps=missing_steps,
                  manifest_missing=manifest_missing, broken=broken, swept=swept)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", default=ROOT)
    args = parser.parse_args(argv)
    report = audit(args.repo)
    print(report.render(), file=sys.stdout if report.ok else sys.stderr)
    return 0 if report.ok else 1


if __name__ == "__main__":
    sys.exit(main())
