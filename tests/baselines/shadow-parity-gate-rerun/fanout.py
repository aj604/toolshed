#!/usr/bin/env python3
"""Fan out the shadow cycle's model workers as headless `claude -p` sessions.

The orchestrator that ran issue #117's cycle, kept as evidence rather than as
tooling: the gate record's G3 and G5 sections make claims about what the
workers were told and what their sessions cost, and `PROMPT` below is that
instruction verbatim. It ran from a directory outside the repository and wrote
nothing into it — every task slice, session record, and answer landed in
`--out` — which is half of why criterion G1b's before/after digests match; the
other half is that the workers were dispatched with no `Write` tool at all.

Each task is a contiguous run of one document's assertion-capable units,
identified by the ordinal range a worker answers for. The worker runs the
engine's own `segment` command to get the units, reads the repository to check
them, and returns the answer as its final message — there is no path by which
it could write one.

Only the scaffolding around `PROMPT` has been touched since the run: `--repo`
was made a flag whose default records the worktree the cycle ran in, so this
file is runnable somewhere else without rewriting it.
"""

import argparse
import json
import os
import re
import subprocess
import sys
import threading
import time

# The worktree the 2026-07-27 cycle ran in, kept as the default so the record
# says where it ran; `--repo` overrides it anywhere else.
REPO = "/Users/averyjones/Repos/skills/toolshed/.claude/worktrees/agent-af5ec7e63745224e2"

# doc-audit.yml's model job minus `Write`. The lane writes verdicts.json into
# the repository; a worker here has no way to write anything anywhere, which
# is what makes the write proof structural rather than procedural.
TOOLS = "Skill,Read,Grep,Glob,Bash(git *),Bash(python3 *)"

PROMPT = """\
You are one worker in a documentation drift audit of this repository. Use the
`doc-lifecycle:detecting-doc-drift` skill's verification method — its assertion
classes, its evidence tiers, its escalation rules, and its standard that
"verified" means you actually looked, not that the claim sounds right. Write
your answer in the *engine's* verdicts shape, given below, not that skill's
report shape.

YOUR DOCUMENT: {path}
YOUR UNITS: the ones with "assertion_capable": true whose "ordinal" is between
{lo} and {hi} inclusive. There are exactly {n} of them, and you owe exactly {n}
answers — no more, no fewer. Units outside that ordinal range belong to another
worker; units inside it with "assertion_capable": false need no answer.

Get the units by running, from the repository root:

    python3 plugins/doc-lifecycle/engine/doc-lifecycle.py segment --repo . --path {path}

That prints JSON whose "units" array carries, for each unit, "ordinal" (a small
integer — this is how you refer to it), "kind", "text", "line", "end_line", and
"assertion_capable". The output is large for a long document; read your slice of
it however you like, but answer only for your ordinal range.

YOUR JOB: for each of your units, decide what the unit is and — if it makes a
factual claim — whether that claim is still true of this repository right now.

Read the document itself ({path}) for context around your units — a sentence's
meaning usually depends on the paragraph, the heading, and often the file it is
describing. Then go check the claims against the actual repository: read the
code, run `git log`/`git show`, grep for the symbol, count the files. A claim
about a count, a path, a flag, a permission, or a behaviour is checkable, and
checking it is the job.

OUTPUT — print ONLY this JSON object as your final message. No prose before or
after it, no markdown fences:

{{"path": "{path}", "verdicts": [
  {{"unit": <ordinal integer>,
   "assertion_class": "factual" | "normative" | "rationale" | "non-assertive",
   "verdict": "VERIFIED" | "STALE" | "UNVERIFIABLE",
   "kind": "command" | "path" | "symbol" | "behavior" | "structure" | "value",
   "tier": 1 | 2 | 3,
   "evidence": {{"source": <repository-relative path>, "line": <int>,
                "observed": <the fact you actually read, one line>}},
   "fix": <complete replacement line — STALE only>}}
]}}

RULES, all of which the engine enforces and will reject the whole document over:

* "unit" is the ORDINAL INTEGER, never the 64-character digest. The engine maps
  it back for you.
* Every assertion_capable unit gets exactly one entry. Missing one fails the
  whole document; answering one twice fails it too.
* "assertion_class":
    - "factual"       — a checkable claim about this repository (a path, a
                        count, a flag, a behaviour, a value, a symbol).
    - "normative"     — an instruction or rule for the reader ("always X",
                        "never Y", "use Z").
    - "rationale"     — an explanation of why something is the way it is.
    - "non-assertive" — connective prose, a heading, a pointer with no claim in
                        it.
* ONLY "factual" units take "verdict"/"kind"/"tier"/"evidence". For
  "normative", "rationale", and "non-assertive" units, send ONLY
  {{"unit": N, "assertion_class": "..."}} — adding a verdict to them is rejected.
* Every factual unit MUST have all four of verdict, kind, tier, evidence.
* "evidence" is mandatory for every verdict including VERIFIED, and "observed"
  is required. VERIFIED and STALE must also cite where: either
  "source" (a repository-relative path, optionally with "line"), or "command"
  (see below). Never both. UNVERIFIABLE may carry "observed" alone.
* "source" must be a CANONICAL repository-relative path: no leading "./", no
  trailing "/", no "//", no "..", and not absolute. `plugins/doc-lifecycle`,
  not `./plugins/doc-lifecycle/`. The engine rejects the whole document over a
  non-canonical one.
* A STALE verdict MUST carry "fix": the complete replacement line, the whole
  line as it would appear in the file — never an instruction describing an edit.
  Only STALE carries a fix.
* "tier": 1 = you read the file the claim is about; 2 = you ran something (a
  git command, a script, a tool) to settle it; 3 = you reasoned across several
  sources. Be honest about which.

NON-REPOSITORY EVIDENCE. Some claims are about an external tool. This run
declares a small set of them. Run
`python3 plugins/doc-lifecycle/skills/scheduling-doc-sync/scripts/probe-evidence-tool.py declared`
to see which, and read one with
`python3 plugins/doc-lifecycle/skills/scheduling-doc-sync/scripts/probe-evidence-tool.py run <tool> <subcommand words> --help`
(or `--version`). The line it prints after "citation:" is what goes in
"command" — the tool's own command line, not that wrapper. Use
{{"command": "<that line>", "observed": "<what its output said>"}} as your
evidence, with no "source" and no "line". Nothing else is reachable: the probe
refuses an undeclared tool and any invocation that is not a --help/--version
read. A claim no declared tool and no repository file can settle is genuinely
UNVERIFIABLE — say so rather than guessing.

BE ACCURATE, NOT AGREEABLE. A STALE verdict on a claim that is actually true is
the single most expensive mistake you can make here: this audit's output feeds
an auto-apply policy. If you are not sure a claim is wrong, it is not STALE.
Equally, do not mark something VERIFIED you did not check.
"""


def load_segments(path):
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)["documents"]


def build_tasks(documents, chunk):
    tasks = []
    for document in documents:
        capable = [u for u in document["units"] if u["assertion_capable"]]
        if not capable:
            continue
        # Even parts, not fixed-size ones with a tail: a 4-unit tail pays a
        # whole session's fixed cost for almost no judgement.
        count = max(1, -(-len(capable) // chunk))
        size = -(-len(capable) // count)
        parts = [capable[i:i + size] for i in range(0, len(capable), size)]
        for n, units in enumerate(parts, 1):
            name = document["path"].replace("/", "__")
            if len(parts) > 1:
                name += f".part{n:02d}"
            tasks.append({"name": name, "path": document["path"],
                          "units": units, "part": n, "parts": len(parts)})
    return tasks


def extract_json(text):
    """The worker's final message, tolerant of a fence or a stray sentence."""
    text = text.strip()
    fenced = re.search(r"```(?:json)?\s*(.*?)```", text, re.S)
    if fenced:
        text = fenced.group(1).strip()
    start = text.find("{")
    if start < 0:
        return None
    depth, in_string, escaped = 0, False, False
    for i in range(start, len(text)):
        ch = text[i]
        if in_string:
            if escaped:
                escaped = False
            elif ch == "\\":
                escaped = True
            elif ch == '"':
                in_string = False
            continue
        if ch == '"':
            in_string = True
        elif ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                try:
                    return json.loads(text[start:i + 1])
                except json.JSONDecodeError:
                    return None
    return None


REPAIR = """

THIS IS A REPAIR ROUND. The engine refused this document's answers and named
every problem. Your answers replace the previous round's for the units you
answer, so give the FULL set for your task file again, with these fixed:

{problems}
"""


def run_task(task, outdir, model, repo, lock, log, problems=None):
    task_path = os.path.join(outdir, task["name"] + ".task.json")
    with open(task_path, "w", encoding="utf-8") as fh:
        json.dump({"path": task["path"], "units": task["units"]}, fh, indent=2)

    ordinals = [u["ordinal"] for u in task["units"]]
    prompt = PROMPT.format(path=task["path"], n=len(ordinals),
                           lo=min(ordinals), hi=max(ordinals))
    if problems:
        prompt += REPAIR.format(problems="\n".join(f"  - {p}" for p in problems))
    started = time.time()
    result = subprocess.run(
        ["claude", "-p", "--model", model, "--output-format", "json",
         "--allowedTools", TOOLS],
        input=prompt, capture_output=True, text=True, cwd=repo,
    )
    elapsed = time.time() - started

    session_path = os.path.join(outdir, task["name"] + ".session.json")
    try:
        session = json.loads(result.stdout)
    except json.JSONDecodeError:
        session = {"is_error": True, "result": result.stdout,
                   "stderr": result.stderr[-4000:], "harness_error": True}
    session["_task"] = task["name"]
    session["_path"] = task["path"]
    session["_units"] = len(task["units"])
    session["_wall_s"] = round(elapsed, 1)
    with open(session_path, "w", encoding="utf-8") as fh:
        json.dump(session, fh, indent=2)

    answer = extract_json(session.get("result") or "")
    status = "PARSE-FAIL"
    kept = 0
    if isinstance(answer, dict) and isinstance(answer.get("verdicts"), list):
        answer["path"] = task["path"]
        kept = len(answer["verdicts"])
        with open(os.path.join(outdir, task["name"] + ".answer.json"),
                  "w", encoding="utf-8") as fh:
            json.dump(answer, fh, indent=2)
        status = "ok" if kept >= len(task["units"]) else "SHORT"

    with lock:
        line = (f"{status:10s} {task['name']:70s} "
                f"{kept:4d}/{len(task['units']):4d} units  "
                f"${session.get('total_cost_usd', 0):7.4f}  "
                f"{session.get('num_turns', 0):3d} turns  "
                f"{elapsed:6.1f}s")
        print(line, flush=True)
        log.append(line)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--segments", required=True)
    parser.add_argument("--out", required=True)
    parser.add_argument("--repo", default=REPO,
                        help="the repository the workers read; the default "
                             "records the worktree this cycle ran in")
    parser.add_argument("--chunk", type=int, default=45)
    parser.add_argument("--model", default="sonnet")
    parser.add_argument("--workers", type=int, default=6)
    parser.add_argument("--only", default=None,
                        help="comma-separated task names to run (a repair round)")
    parser.add_argument("--problems", default=None,
                        help="JSON {document path: [problem, ...]}; every task "
                             "of a named document is re-run with them")
    parser.add_argument("--plan-only", action="store_true")
    args = parser.parse_args()

    problems = {}
    if args.problems:
        with open(args.problems, encoding="utf-8") as fh:
            problems = json.load(fh)

    tasks = build_tasks(load_segments(args.segments), args.chunk)
    if args.only:
        wanted = set(args.only.split(","))
        tasks = [t for t in tasks if t["name"] in wanted]
    if problems:
        tasks = [t for t in tasks if t["path"] in problems]
    if args.plan_only:
        for t in tasks:
            print(f"{t['name']:70s} {len(t['units'])} units")
        print(f"{len(tasks)} tasks, {sum(len(t['units']) for t in tasks)} units")
        return 0

    os.makedirs(args.out, exist_ok=True)
    lock, log = threading.Lock(), []
    queue = list(tasks)
    qlock = threading.Lock()

    def drain():
        while True:
            with qlock:
                if not queue:
                    return
                task = queue.pop(0)
            try:
                run_task(task, args.out, args.model, args.repo, lock, log,
                         problems.get(task["path"]))
            except Exception as exc:  # a worker dying must not stop the round
                with lock:
                    print(f"ERROR      {task['name']}: {exc}", flush=True)

    threads = [threading.Thread(target=drain) for _ in range(args.workers)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    print(f"\n{len(tasks)} tasks done")
    return 0


if __name__ == "__main__":
    sys.exit(main())
