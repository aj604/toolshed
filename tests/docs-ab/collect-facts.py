#!/usr/bin/env python3
"""Mechanical fact collection for docs A/B runs (no judgment; graders build on this).

For each run dir under skill-workspaces/docs-ab/runs/, inspects the recorded
work_dir and writes facts.json: per-task mechanical checks plus metrics lifted
from the CLI's result.json. `success` here is the mechanical verdict; a grader
agent may override judgment calls via grade.json (analyze.py prefers grade.json
when present).
"""

import json
import re
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
RESULTS_ROOT = HERE.parent.parent / "skill-workspaces" / "docs-ab" / "runs"

NODE_HELPER_CHECK = (
    "const m = await import(new URL('packages/shared/index.js', "
    "`file://${process.cwd()}/`).href);"
    "const f = m.normalizeStatus;"
    "if (typeof f !== 'function') { console.log('MISSING'); process.exit(0); }"
    "const ok = f(null) === 'todo' && f(undefined) === 'todo' && f('doing') === 'doing'"
    " && f('done') === 'done' && f('todo') === 'todo' && f('bogus') === 'todo';"
    "console.log(ok ? 'OK' : 'WRONG');"
)


def read_json(path: Path):
    try:
        return json.loads(path.read_text())
    except (OSError, json.JSONDecodeError):
        return None


def check_orientation_quiz(work: Path) -> dict:
    answers = read_json(work / "answers.json")
    if not isinstance(answers, dict):
        return {"success": False, "reason": "answers.json missing or unparseable"}
    checks = {}
    tc = str(answers.get("test_command", ""))
    checks["test_command"] = ("make test" in tc) or ("node --test" in tc)
    env = answers.get("required_env", [])
    checks["required_env"] = isinstance(env, list) and any(
        str(e).strip() == "DATABASE_URL" for e in env)
    order = [str(s).lower() for s in answers.get("setup_order", [])
             ] if isinstance(answers.get("setup_order"), list) else []

    def idx(*needles):
        return next((i for i, s in enumerate(order)
                     if any(n in s for n in needles)), None)

    i_install = idx("setup", "npm install", "npm ci", "npm i")
    i_migrate = idx("migrate")
    i_run = idx("dev", "start", "server.js", "worker.js", "make api")
    checks["setup_order"] = (
        i_install is not None and i_migrate is not None and i_run is not None
        and i_install < i_migrate < i_run)
    checks["node_version"] = "20.6" in str(answers.get("node_version", ""))
    return {"success": all(checks.values()), "checks": checks, "answers": answers}


def check_run_tests(work: Path) -> dict:
    f = work / "test-count.txt"
    if not f.exists():
        return {"success": False, "reason": "test-count.txt missing"}
    content = f.read_text().strip()
    m = re.search(r"\d+", content)
    count = int(m.group()) if m else None
    return {"success": count == 3, "reported_count": count, "raw": content[:80]}


def check_start_api(work: Path) -> dict:
    body = read_json(work / "health.json")
    if body is None:
        return {"success": False, "reason": "health.json missing or unparseable"}
    return {"success": isinstance(body, dict) and body.get("ok") is True
            and "tasks" in body, "body": body}


def check_run_worker(work: Path) -> dict:
    f = work / "worker-output.txt"
    if not f.exists():
        return {"success": False, "reason": "worker-output.txt missing"}
    content = f.read_text().strip()
    return {"success": "worker: started" in content, "raw": content[:120]}


def check_add_helper(work: Path) -> dict:
    checks = {}
    suite = subprocess.run(["make", "test"], cwd=work, capture_output=True,
                           text=True, timeout=120)
    checks["suite_green"] = suite.returncode == 0
    behavior = subprocess.run(
        ["node", "--input-type=module", "-e", NODE_HELPER_CHECK],
        cwd=work, capture_output=True, text=True, timeout=60)
    checks["helper_behavior"] = behavior.stdout.strip() == "OK"
    test_file = work / "packages" / "shared" / "test" / "shared.test.js"
    tests_dir = work / "packages" / "shared" / "test"
    checks["helper_tested"] = tests_dir.is_dir() and any(
        "normalizeStatus" in p.read_text()
        for p in tests_dir.glob("*.test.js") if p.is_file())
    return {"success": all(checks.values()), "checks": checks,
            "helper_probe": behavior.stdout.strip() or behavior.stderr[:120]}


CHECKERS = {
    "orientation-quiz": check_orientation_quiz,
    "run-tests": check_run_tests,
    "start-api": check_start_api,
    "run-worker": check_run_worker,
    "add-helper": check_add_helper,
}


def collect(run_dir: Path) -> dict:
    meta = read_json(run_dir / "run.json") or {}
    result = read_json(run_dir / "result.json")
    facts = {"run_id": run_dir.name, "variant": meta.get("variant"),
             "task": meta.get("task"), "trial": meta.get("trial"),
             "timed_out": meta.get("timed_out", False),
             "completed": result is not None and not result.get("is_error", False)}
    if result:
        usage = result.get("usage", {})
        facts["metrics"] = {
            "num_turns": result.get("num_turns"),
            "total_cost_usd": result.get("total_cost_usd"),
            "duration_ms": result.get("duration_ms"),
            "output_tokens": usage.get("output_tokens"),
            "input_tokens": usage.get("input_tokens"),
            "cache_read_tokens": usage.get("cache_read_input_tokens"),
        }
    work = Path(meta.get("work_dir", ""))
    checker = CHECKERS.get(meta.get("task"))
    if not work.is_dir():
        facts.update({"success": False, "reason": "work_dir missing"})
    elif checker is None:
        facts.update({"success": False, "reason": f"no checker for task {meta.get('task')}"})
    else:
        try:
            facts.update(checker(work))
        except Exception as exc:  # a broken workspace is a failed run, not a crash
            facts.update({"success": False, "reason": f"checker error: {exc}"})
    return facts


def main():
    if not RESULTS_ROOT.is_dir():
        sys.exit(f"no runs at {RESULTS_ROOT}")
    for run_dir in sorted(p for p in RESULTS_ROOT.iterdir() if p.is_dir()):
        facts = collect(run_dir)
        (run_dir / "facts.json").write_text(json.dumps(facts, indent=2))
        print(f"{run_dir.name}: success={facts.get('success')}"
              + (f" ({facts['reason']})" if facts.get("reason") else ""))


if __name__ == "__main__":
    main()
