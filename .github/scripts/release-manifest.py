#!/usr/bin/env python3
"""The release manifest guard (aj604/toolshed#77).

Discovery wires a new suite the moment its file lands (#99) — but only if the
file lands where the discovery step can see it, and only if running it runs
anything. Six ways it silently does not, every one of which leaves CI green
(the last three were found by an independent review of this guard, #128):

1. A suite in a `tests/engine/` subdirectory with no `__init__.py`.
   `unittest discover` skips the directory without a word and reports OK.
2. A suite whose name the discovery pattern misses (`test_foo.py`), or a
   pattern narrowed in `release.yml` so it stops matching what it used to.
3. A suite in a directory no discovery step reaches at all — including one
   outside `tests/`, which is why the scan walks the whole repository.
4. A suite in `tests/scripts/` with no `if __name__ == "__main__"` guard.
   `run-script-suites.py` runs each as `python3 <path>`, so it runs zero
   tests and reports PASS: discovered, counted, and inert.
5. A file that does not parse. Treating a SyntaxError as "not a suite" hides
   a file exactly when it is most broken, so it is reported instead.
6. A discovery step still present in `release.yml` but gated `if: false`.

The guard closes all three the same way: it reads `release.yml` for the
discovery steps CI actually runs, computes the set of suites those steps would
really execute, and requires that set to cover every suite in the tree.
Deriving the commands rather than restating them is the point — narrowing a
glob in `release.yml` moves the guard's own baseline, and is caught rather
than obeyed.

It also carries the release manifest: the gate criteria release issues name,
each mapped to the suites that discharge it. Discovery running a shrinking set
of suites is green; discovery no longer running `install-parity_test.py` is
not.

Detection is structural, not name-based: a repository candidate is a tracked
file or an untracked file Git does not ignore, and it is a suite when it
declares a TestCase subclass carrying test methods. A rename that hides a
suite from discovery must not also hide it from the guard.

What it still cannot see, stated so nobody reads a clean run as more than it
is: it reads `release.yml`'s command *text*, so a step that runs a discovery
command through some indirection this scanner does not recognise reads as
absent, and one whose command is a no-op wrapper reads as present. And suite
detection is a single-module AST walk, so a TestCase reached through a base
class imported from elsewhere and not named `*TestCase`, or one defined inside
a conditional, is not recognised. Both are bounded by convention here rather
than by this file.

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
        "tests/engine/acceptance/scenario_human_lifecycle_test.py",
    ],
    # The one highest-level human transaction: a report produced by the audit
    # engine, strict-subset semantic approval, a valid edit plan, and the
    # public deterministic applier over a real temporary repository. Keeping
    # it as a named criterion means broad acceptance discovery cannot mask its
    # removal.
    "primary human lifecycle": [
        "tests/engine/acceptance/scenario_human_lifecycle_test.py",
    ],
    # The hostile corpus the acceptance fixture builds, and the refusals it
    # must produce: hostile filenames and malformed input that change nothing
    # (scenario one, scenario drift), the applier's and approval set's forgery
    # refusals, path authorization, and the static no-shell/no-exec capability
    # assertion over the only component that writes a repository document.
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
        # The read-only lanes' repository-integrity gate: a model job's
        # read-only permissions say what it may do, this says what the
        # checkout still was when the report was assembled (#185).
        "tests/scripts/check-repo-integrity_test.py",
    ],
    "template/dogfood equivalence": [
        "tests/scripts/install-parity_test.py",
    ],
    "migration dry run": [
        "tests/engine/migrate_test.py",
        "tests/engine/migrate_cli_test.py",
    ],
}


# --- what the repository holds ------------------------------------------

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


def _unittest_main_bindings(tree):
    """Names this file's imports bind to the `unittest` module, and names
    bound to `unittest.main` itself via `from unittest import main`.

    `import unittest.mock` (unaliased) binds the top-level name `unittest`
    too — Python's `import a.b` always binds `a` — so an unaliased dotted
    import counts. `import unittest.mock as um` does not: `um` names the
    submodule itself, which has no `.main`.
    """
    unittest_names, main_names = set(), set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name == "unittest":
                    unittest_names.add(alias.asname or alias.name)
                elif alias.asname is None \
                        and alias.name.split(".")[0] == "unittest":
                    unittest_names.add("unittest")
        elif isinstance(node, ast.ImportFrom) and node.module == "unittest":
            for alias in node.names:
                if alias.name == "main":
                    main_names.add(alias.asname or alias.name)
    return unittest_names, main_names


def _calls_unittest_main(node, unittest_names, main_names, local_funcs, seen):
    """Whether `node` calls unittest.main, directly or through a chain of
    module-level function calls (a wrapper that does setup before
    delegating to `unittest.main()` is a real idiom). `seen` guards against
    revisiting a function already on the call path."""
    for call in ast.walk(node):
        if not isinstance(call, ast.Call):
            continue
        func = call.func
        if isinstance(func, ast.Attribute) and func.attr == "main" \
                and isinstance(func.value, ast.Name) \
                and func.value.id in unittest_names:
            return True
        if isinstance(func, ast.Name):
            if func.id in main_names:
                return True
            if func.id in local_funcs and func.id not in seen:
                seen.add(func.id)
                if _calls_unittest_main(local_funcs[func.id], unittest_names,
                                         main_names, local_funcs, seen):
                    return True
    return False


def _has_main_guard(tree):
    """`if __name__ == "__main__": unittest.main()`, however it is spelled
    (`unittest.main(verbosity=2)`, `sys.exit(unittest.main())`, an aliased
    or dotted `import unittest`, `from unittest import main`, or a local
    wrapper function that calls one of the above).

    Only the script-runner's suites need one: it runs each as `python3
    <path>`, so a suite without it runs zero tests and exits 0. The call
    must resolve to unittest.main specifically — a `__main__` block that
    calls an unrelated local `main()` also runs zero tests.
    """
    unittest_names, main_names = _unittest_main_bindings(tree)
    local_funcs = {
        node.name: node for node in tree.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
    }
    for node in ast.walk(tree):
        if not isinstance(node, ast.If):
            continue
        if "__name__" not in ast.unparse(node.test):
            continue
        if any(_calls_unittest_main(stmt, unittest_names, main_names,
                                     local_funcs, set())
               for stmt in node.body):
            return True
    return False


def scan_file(path):
    """What this file is, for the gate's purposes.

    A file is a suite when it declares a TestCase subclass carrying test
    methods — structural rather than name-based, so `support.py` and
    `fixture.py` (TestCase bases with no test methods of their own) are
    correctly not suites, while a suite named `checks.py` still is one.

    A file that will not parse is `unreadable`, never "not a suite": treating
    a SyntaxError as an absence hides a file exactly when it is most broken.
    """
    try:
        tree = ast.parse(_read(path))
    except (SyntaxError, UnicodeDecodeError, ValueError):
        return {"suite": False, "unreadable": True, "main_guard": False}
    for node in _test_classes(tree):
        for item in node.body:
            if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)) \
                    and item.name.startswith("test"):
                return {"suite": True, "unreadable": False,
                        "main_guard": _has_main_guard(tree)}
    return {"suite": False, "unreadable": False, "main_guard": False}


# Directories that hold no suite of their own: version control, caches, and
# the vendored engine, which is a parity-enforced mirror of the plugin tree
# rather than a source of its own.
SKIP_DIRS = (".git", "node_modules", "__pycache__", ".doc-lifecycle/wiring/engine")


def _physical_candidates(repo_root):
    """The archive fallback when `repo_root` has no Git metadata."""
    candidates = set()
    for dirpath, dirnames, filenames in os.walk(repo_root):
        rel_dir = _rel(dirpath, repo_root)
        dirnames[:] = sorted(
            d for d in dirnames
            if d not in SKIP_DIRS
            and not _under(f"{rel_dir}/{d}".lstrip("./"), SKIP_DIRS))
        for name in filenames:
            if name.endswith(".py"):
                candidates.add(_rel(os.path.join(dirpath, name), repo_root))
    return candidates


def repository_candidates(repo_root):
    """Python files that belong to this repository's candidate set.

    Git's tracked files plus its untracked, nonignored files are the source of
    truth in a checkout. That excludes an ignored nested worktree or generated
    copy without inventing a directory-name convention, but keeps an untracked
    orphan visible to the guard. A source archive has no Git metadata, so its
    physical files are the equivalent complete candidate set.
    """
    result = subprocess.run(
        ["git", "ls-files", "--cached", "--others", "--exclude-standard", "-z"],
        capture_output=True, cwd=repo_root)
    if result.returncode:
        return _physical_candidates(repo_root)

    candidates = set()
    for item in result.stdout.decode("utf-8", "surrogateescape").split("\0"):
        if not item:
            continue
        rel = os.path.normpath(item).replace(os.sep, "/")
        if rel == ".." or rel.startswith("../") or os.path.isabs(rel):
            continue
        full = os.path.join(repo_root, rel)
        if rel.endswith(".py") and os.path.isfile(full):
            candidates.add(rel)
    return candidates


def suites_in_tree(repo_root, non_gate_roots=NON_GATE_ROOTS):
    """Every suite among repository candidates, as repo-relative paths,
    minus the declared non-gate roots.

    The whole repository, not just `tests/`: a suite in `.github/scripts/` is
    exactly as unwired as one in an undiscovered `tests/` subdirectory, and
    scanning only the directory the gate already covers would find neither.
    """
    found, unreadable = set(), set()
    for rel in sorted(repository_candidates(repo_root)):
        if _under(rel, non_gate_roots) or _under(rel, SKIP_DIRS):
            continue
        scanned = scan_file(os.path.join(repo_root, rel))
        if scanned["unreadable"]:
            unreadable.add(rel)
        elif scanned["suite"]:
            found.add(rel)
    return found, unreadable


def _under(rel, roots):
    return any(rel == root or rel.startswith(root + "/") for root in roots)


# --- what the release pipeline actually runs -----------------------------

# `python3 -m unittest discover -s <dir> -p <pattern>`, quoted however.
_DISCOVER = re.compile(
    r"unittest\s+discover\s+-s\s+(?P<dir>\S+)\s+-p\s+"
    r"(?P<q>['\"]?)(?P<pattern>[^'\"\s]+)(?P=q)")
_SCRIPT_RUNNER = re.compile(
    r"(?P<script>\S*run-script-suites\.py)(?:\s+--dir[= ](?P<dir>\S+))?")


_STEP_START = re.compile(r"^\s*-\s+(name|uses|run):")
_STEP_IF = re.compile(r"^\s*if:\s*(?P<cond>.+)$")


def _step_blocks(text):
    """The workflow's steps, as lists of lines.

    A line scanner rather than a YAML library, like the other workflow guards
    in this suite: stdlib-only, and what matters here is the command text.
    """
    blocks, current = [], []
    for line in text.splitlines():
        if line.lstrip().startswith("#"):
            continue
        if _STEP_START.match(line):
            if current:
                blocks.append(current)
            current = []
        current.append(line)
    if current:
        blocks.append(current)
    return blocks


def release_discovery_steps(release_yml):
    """The discovery commands `release.yml` runs, and whether each is gated.

    A step's `if:` is read as well as its command, because the guard reads
    text rather than watching an execution: a discovery step gated `if: false`
    runs nothing while still reading as present.
    """
    steps = {"unittest": [], "script_runner": [], "disabled": []}
    for block in _step_blocks(_read(release_yml)):
        text = "\n".join(block)
        gate = None
        for line in block:
            found = _STEP_IF.match(line)
            if found:
                gate = found.group("cond").strip()
        found = _DISCOVER.search(text)
        if found:
            entry = {"dir": found.group("dir"), "pattern": found.group("pattern")}
            if gate is None:
                steps["unittest"].append(entry)
            else:
                steps["disabled"].append(
                    f"`unittest discover -s {entry['dir']}` is gated `if: {gate}`")
        found = _SCRIPT_RUNNER.search(text)
        if found:
            entry = {"script": found.group("script"), "dir": found.group("dir")}
            if gate is None:
                steps["script_runner"].append(entry)
            else:
                steps["disabled"].append(
                    f"`{entry['script']}` is gated `if: {gate}`")
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
        last = (result.stderr.strip().splitlines() or ["no output"])[-1]
        return set(), [f"discovery over {start_dir!r} failed: {last}"]
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
                 broken, swept, inert, unreadable):
        self.gate = gate
        self.unwired = unwired
        self.missing_steps = missing_steps
        self.manifest_missing = manifest_missing
        self.broken = broken
        self.swept = swept
        self.inert = inert
        self.unreadable = unreadable

    @property
    def ok(self):
        return not (self.unwired or self.missing_steps
                    or self.manifest_missing or self.broken or self.swept
                    or self.inert or self.unreadable)

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
        if self.inert:
            lines.append(
                "these suites are run as `python3 <path>` but never call "
                "unittest.main(), so they run zero tests and report success:")
            lines += [f"  - {path}" for path in self.inert]
        if self.unreadable:
            lines.append("these files do not parse, so nothing can tell "
                         "whether they are suites:")
            lines += [f"  - {path}" for path in self.unreadable]
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


def audit(repo_root=ROOT, manifest=None, release_yml=None,
          non_gate_roots=NON_GATE_ROOTS):
    """Compare the suites the tree holds against the suites CI runs."""
    repo_root = os.path.abspath(repo_root)
    manifest = GATE_MANIFEST if manifest is None else manifest
    release_yml = release_yml or os.path.join(
        repo_root, ".github", "workflows", "release.yml")

    steps = release_discovery_steps(release_yml)
    missing_steps = list(steps["disabled"])
    if not steps["script_runner"]:
        missing_steps.append(
            "run-script-suites.py — the tests/scripts suites would stop running")
    if not steps["unittest"]:
        missing_steps.append(
            "unittest discover — the engine suites would stop running")

    gate, broken = set(), []
    by_path = set()
    for step in steps["unittest"]:
        files, errors = unittest_discovered(step["dir"], step["pattern"],
                                            repo_root)
        gate |= files
        broken += errors
    for step in steps["script_runner"]:
        files, errors = script_runner_discovered(step["script"], step["dir"],
                                                 repo_root)
        gate |= files
        by_path |= files
        broken += errors

    tree, unreadable = suites_in_tree(repo_root, non_gate_roots)
    # Only the by-path suites need a main guard; the discovered ones are
    # loaded by unittest, which calls nothing.
    inert = sorted(
        path for path in by_path
        if not scan_file(os.path.join(repo_root, path))["main_guard"])
    manifest_missing = [
        (criterion, path)
        for criterion, paths in sorted(manifest.items())
        for path in paths
        if not os.path.exists(os.path.join(repo_root, path)) or path not in gate
    ]
    swept = sorted(path for path in gate if _under(path, non_gate_roots))
    return Report(gate=sorted(gate), unwired=sorted(tree - gate),
                  missing_steps=missing_steps,
                  manifest_missing=manifest_missing, broken=broken, swept=swept,
                  inert=inert, unreadable=sorted(unreadable))


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", default=ROOT)
    args = parser.parse_args(argv)
    report = audit(args.repo)
    print(report.render(), file=sys.stdout if report.ok else sys.stderr)
    return 0 if report.ok else 1


if __name__ == "__main__":
    sys.exit(main())
