#!/usr/bin/env python3
"""Docs A/B experiment runner (design: docs/plans/2026-07-11-docs-ab-experiment.md).

Builds per-variant workspace templates from tests/fixtures/taskflow, then runs
headless `claude -p` once per (variant, task, trial) cell and records the CLI's
JSON result. Judgment-free: all grading lives in collect-facts.py / analyze.py.

Isolation invariants (why the layout is what it is):
  - Work dirs live OUTSIDE any git repo / CLAUDE.md-bearing ancestor tree
    (Claude Code walks ancestors for CLAUDE.md; the variant docs must be the
    only doc lever). Default: ~/.cache/toolshed-docs-ab/.
  - `--setting-sources project` keeps user-scope settings (plugins, hooks) out.
  - DATABASE_URL / PORT / WORKER_INTERVAL_MS are scrubbed from the child env.

Usage:
  run-experiment.py --smoke                 # 2 runs: orientation-quiz x none/plugin-shaped
  run-experiment.py --trials 3              # full matrix
  run-experiment.py --variants stale --tasks run-tests --trials 1
Re-running skips cells whose result.json already parses (validity-checked resume).
"""

import argparse
import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO_ROOT = HERE.parent.parent
FIXTURE = REPO_ROOT / "tests" / "fixtures" / "taskflow"
VARIANT_DIR = HERE / "variants"
RESULTS_ROOT = REPO_ROOT / "skill-workspaces" / "docs-ab" / "runs"
WORK_ROOT = Path.home() / ".cache" / "toolshed-docs-ab"

ALLOWED_TOOLS = ["Bash", "Read", "Write", "Edit", "Glob", "Grep"]
DISALLOWED_TOOLS = ["Task", "WebFetch", "WebSearch"]
SCRUB_ENV = ["DATABASE_URL", "PORT", "WORKER_INTERVAL_MS"]


def load_battery():
    battery = json.loads((HERE / "tasks.json").read_text())
    return battery["variants"], {t["id"]: t for t in battery["tasks"]}


def build_template(variant: str, rebuild: bool) -> Path:
    template = WORK_ROOT / "templates" / variant
    if template.exists():
        if not rebuild:
            return template
        shutil.rmtree(template)
    template.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(
        FIXTURE, template, symlinks=True,
        ignore=shutil.ignore_patterns("node_modules", ".taskflow-state.json"),
    )
    src = VARIANT_DIR / variant
    if src.is_dir():
        for doc in src.iterdir():
            shutil.copy2(doc, template / doc.name)
    subprocess.run(["npm", "install", "--no-fund", "--no-audit"],
                   cwd=template, check=True, capture_output=True)
    subprocess.run(["git", "init", "-q"], cwd=template, check=True)
    subprocess.run(["git", "add", "-A"], cwd=template, check=True)
    subprocess.run(
        ["git", "-c", "user.email=ab@experiment", "-c", "user.name=ab",
         "commit", "-qm", "workspace baseline"],
        cwd=template, check=True,
    )
    return template


def run_cell(variant: str, task: dict, trial: int, model: str, rebuild: bool) -> dict:
    run_id = f"{variant}__{task['id']}__t{trial}"
    result_dir = RESULTS_ROOT / run_id
    result_file = result_dir / "result.json"
    if result_file.exists():
        try:
            if json.loads(result_file.read_text()).get("type") == "result":
                return {"run_id": run_id, "status": "skipped (already complete)"}
        except (json.JSONDecodeError, OSError):
            pass  # invalid prior result -> rerun
    result_dir.mkdir(parents=True, exist_ok=True)

    work_dir = WORK_ROOT / "work" / run_id
    if work_dir.exists():
        shutil.rmtree(work_dir)
    shutil.copytree(build_template(variant, rebuild), work_dir, symlinks=True)

    env = {k: v for k, v in os.environ.items() if k not in SCRUB_ENV}
    cmd = [
        "claude", "-p", task["prompt"],
        "--output-format", "json",
        "--model", model,
        "--setting-sources", "project",
        "--allowedTools", *ALLOWED_TOOLS,
        "--disallowedTools", *DISALLOWED_TOOLS,
    ]
    meta = {
        "run_id": run_id, "variant": variant, "task": task["id"], "trial": trial,
        "model": model, "work_dir": str(work_dir), "timeout_s": task["timeout_s"],
        "started": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
    }
    timed_out = False
    try:
        proc = subprocess.run(cmd, cwd=work_dir, env=env, capture_output=True,
                              text=True, timeout=task["timeout_s"])
        stdout, stderr, returncode = proc.stdout, proc.stderr, proc.returncode
    except subprocess.TimeoutExpired as exc:
        timed_out = True
        stdout = (exc.stdout or b"").decode() if isinstance(exc.stdout, bytes) else (exc.stdout or "")
        stderr = (exc.stderr or b"").decode() if isinstance(exc.stderr, bytes) else (exc.stderr or "")
        returncode = None
    # Best-effort: kill anything the agent left running in the workspace.
    # Agents start services with relative paths, so match entrypoints too
    # (runs are serial; nothing else legitimately runs these fixtures).
    for pattern in (str(work_dir), "services/api/server.js", "services/worker/worker.js"):
        subprocess.run(["pkill", "-f", pattern], capture_output=True)

    meta.update({
        "ended": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "timed_out": timed_out, "returncode": returncode,
    })
    (result_dir / "run.json").write_text(json.dumps(meta, indent=2))
    (result_dir / "stderr.txt").write_text(stderr or "")
    try:
        parsed = json.loads(stdout)
        result_file.write_text(json.dumps(parsed, indent=2))
        status = f"done (turns={parsed.get('num_turns')}, cost=${parsed.get('total_cost_usd', 0):.2f})"
    except json.JSONDecodeError:
        (result_dir / "stdout-raw.txt").write_text(stdout or "")
        status = "TIMED OUT (no result)" if timed_out else f"FAILED (exit {returncode}, no JSON result)"
    return {"run_id": run_id, "status": status}


def main():
    all_variants, tasks_by_id = load_battery()
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--variants", nargs="+", default=all_variants, choices=all_variants)
    ap.add_argument("--tasks", nargs="+", default=list(tasks_by_id), choices=list(tasks_by_id))
    ap.add_argument("--trials", type=int, default=3)
    ap.add_argument("--model", default="claude-sonnet-5")
    ap.add_argument("--smoke", action="store_true",
                    help="orientation-quiz x {none, plugin-shaped} x 1 trial")
    ap.add_argument("--rebuild-templates", action="store_true")
    args = ap.parse_args()

    if args.smoke:
        args.variants, args.tasks, args.trials = ["none", "plugin-shaped"], ["orientation-quiz"], 1

    cells = [(v, tasks_by_id[t], n) for v in args.variants for t in args.tasks
             for n in range(1, args.trials + 1)]
    print(f"{len(cells)} runs -> {RESULTS_ROOT}", flush=True)
    for variant, task, trial in cells:
        started = time.time()
        outcome = run_cell(variant, task, trial, args.model, args.rebuild_templates)
        print(f"  {outcome['run_id']}: {outcome['status']} [{time.time() - started:.0f}s]", flush=True)
    print(f"next: python3 {HERE / 'collect-facts.py'} && python3 {HERE / 'analyze.py'}")


if __name__ == "__main__":
    sys.exit(main())
