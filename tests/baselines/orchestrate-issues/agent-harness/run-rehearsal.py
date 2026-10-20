#!/usr/bin/env python3
"""Rehearsal runs for evals 14-16: the agent definition is loaded with --agent, all tools are
disallowed, and the agent answers with the tool calls it would make.
usage: run-rehearsal.py <plugin-dir> <out-dir> [eval-id ...]"""
import json, os, subprocess, sys, concurrent.futures as cf
H = os.path.dirname(os.path.abspath(__file__))
plugin, out_root = os.path.abspath(sys.argv[1]), os.path.abspath(sys.argv[2])
ids = [int(x) for x in sys.argv[3:]] or [14, 15, 16]
evals = [e for e in json.load(open(os.path.join(H, '..', 'evals.json')))['evals'] if e['id'] in ids]
def run(e):
    out = os.path.join(out_root, f"eval-{e['id']}-{e['name']}")
    os.makedirs(out, exist_ok=True)
    prompt = ("REHEARSAL. Nothing here is real and no tools are available to you; answer in text only.\n\n" + e['prompt'] +
              "\n\nAnswer with the exact tool calls you would make next, in order, as a numbered list: tool name and full parameters "
              "(Bash: command, timeout, run_in_background; Agent: subagent_type, model, run_in_background, prompt), each with a one-line reason "
              "and what you'd expect back (assume success). Mark where you would end your turn, and include any final report verbatim.")
    r = subprocess.run(["claude", "-p", "--plugin-dir", plugin, "--agent", f"workbench:{e['agent']}",
                        "--disallowedTools", "Bash,Edit,Write,Agent,Task,Read,Glob,Grep,NotebookEdit,WebFetch,WebSearch",
                        "--output-format", "json", prompt], capture_output=True, text=True, cwd="/tmp")
    try: j = json.loads(r.stdout)
    except ValueError: j = {"result": r.stdout + r.stderr}
    open(os.path.join(out, "response.md"), "w").write(j.get("result", ""))
    return f"{e['id']} {len(j.get('result', ''))} chars"
with cf.ThreadPoolExecutor(6) as ex:
    for s in ex.map(run, evals): print(s, flush=True)
