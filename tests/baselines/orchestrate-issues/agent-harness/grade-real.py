#!/usr/bin/env python3
"""Grade real implementer runs from their stream-json transcripts. usage: grade-real.py <run-dir>"""
import json, re, sys, os
R = sys.argv[1]
O = os.path.join(R, 'outputs')
calls, results, usage = [], {}, {}
for line in open(os.path.join(O, 'stream.jsonl')):
    try: d = json.loads(line)
    except Exception: continue
    if d.get('type') == 'assistant' and not d.get('parent_tool_use_id'):
        msg_calls = [c for c in d['message'].get('content', []) if c.get('type') == 'tool_use']
        for c in msg_calls:
            calls.append({'id': c['id'], 'name': c['name'], 'input': c['input'], 'msg': d['message'].get('id')})
    if d.get('type') == 'result':
        usage = {'turns': d.get('num_turns'), 'cost': d.get('total_cost_usd'), 'duration_ms': d.get('duration_ms'),
                 'result': (d.get('result') or '')[-1500:]}
agents = [c for c in calls if c['name'] in ('Agent', 'Task')]
bash = [c for c in calls if c['name'] == 'Bash']
# commands that only write files (PR bodies, heredocs) mention suite names without running them
runs = [b for b in bash if not re.search(r"<<\s*'?EOF|gh pr create", b['input'].get('command', ''))]
def p(c): return json.dumps(c['input'])
mut = [a for a in agents if re.search(r'mutat|SURVIVED', p(a), re.I)]
walk = [a for a in agents if re.search(r'git (-C \S+ )?diff', p(a)) and re.search(r'criteri', p(a), re.I)]
msgs_with_two_agents = {}
for a in agents: msgs_with_two_agents[a['msg']] = msgs_with_two_agents.get(a['msg'], 0) + 1
parallel = any(v > 1 for v in msgs_with_two_agents.values())
bg_agents = [a for a in agents if a['input'].get('run_in_background')]
full = [b for b in runs if re.search(r'(^|[;&|]\s*|\s)(\./)?scripts/full_suite\.sh(\s|$|>|;|\|)', b['input'].get('command', '')) and not re.match(r'\s*(cat|head|less|sed|grep)\b', b['input'].get('command', ''))]
full_bg = [b for b in full if b['input'].get('run_in_background')]
full_fg = [b for b in full if not b['input'].get('run_in_background')]
poll = [b for b in bash if re.search(r'\bsleep\b|\buntil\b|while .*;', b['input'].get('command', '')) and 'full_suite.sh' not in b['input'].get('command','')]
log_reads = [c for c in calls if (c['name'] == 'Read' and '.log' in c['input'].get('file_path', '')) or (c['name']=='Bash' and re.search(r'(tail|cat).*\.log', c['input'].get('command','')))]
tests = [b for b in runs if re.search(r'unittest|full_suite|pytest', b['input'].get('command', '')) and not re.match(r'\s*(cat|head|sed|grep)\b', b['input'].get('command', ''))]
trimmed = [b for b in tests if re.search(r'\|\s*(tail|head|grep)|>\s*\S+\.log| -q\b', b['input'].get('command', ''))]
gh = open(os.path.join(O, 'gh.log')).read() if os.path.exists(os.path.join(O, 'gh.log')) else ''
ghcalls = [b['input'].get('command','') for b in bash if re.search(r'\bgh pr create', b['input'].get('command',''))]
pr_cmd = ' '.join(ghcalls) + gh
remote = open(os.path.join(O, 'remote-log.txt')).read()
status = open(os.path.join(O, 'final-status.txt')).read().strip()
testfile = open(os.path.join(R, 'work/tests/test_batcher.py')).read()
cap_test = bool(re.search(r'assertLessEqual|<=\s*50|MAX_BATCH|\b50\b', testfile))
def exp(text, ok, ev): return {'text': text, 'passed': bool(ok), 'evidence': ev}
E = [
 exp('Invokes at least one child agent via the Agent tool (top-level tool_use in the transcript)', agents, f'{len(agents)} Agent call(s): ' + '; '.join(f"{a['input'].get('subagent_type')}/{a['input'].get('model')}/bg={a['input'].get('run_in_background')}" for a in agents)),
 exp('Dispatches a mutation-loop child (Agent prompt about mutations / SURVIVED)', mut, f'{len(mut)} matching'),
 exp('Mutation child prompt carries the worktree absolute path and a targeted test command', any('/work' in p(a) and re.search(r'unittest tests\.test_batcher|test_batcher', p(a)) for a in mut), 'checked worktree path + test_batcher command in prompt'),
 exp('Dispatches a separate criteria-walk child that reads git diff cold', walk and (not mut or any(w['id'] not in {m['id'] for m in mut} for w in walk)), f'{len(walk)} matching'),
 exp('Children run one at a time in the foreground (no run_in_background, never two in one message)', agents and not bg_agents and not parallel, f'bg={len(bg_agents)} parallel={parallel}'),
 exp('Mutation loop found the weak split test: final tests assert the 50-item cap', cap_test, 'test_batcher.py ' + ('asserts cap' if cap_test else 'still only asserts len>1')),
 exp('Long full suite launched once with run_in_background, not in the foreground', full_bg and not full_fg, f'bg={len(full_bg)} fg={len(full_fg)}'),
 exp('No sleep/until polling and no repeated log reads while waiting', not poll and len(log_reads) <= max(1, len(full_bg)), f'poll cmds={len(poll)} log reads={len(log_reads)}'),
 exp('Test command output trimmed (tail/-q/log redirect)', tests and len(trimmed) == len(tests), f'{len(trimmed)}/{len(tests)} trimmed'),
 exp('Branch pushed to the remote', remote.strip() and 'fatal' not in remote, remote.strip()[:200]),
 exp("Draft PR opened with 'Closes #17'", '--draft' in pr_cmd and 'Closes #17' in pr_cmd, (gh or 'no gh log')[:300]),
 exp('Worktree clean at exit', status == '', status[:200] or 'clean'),
]
passed = sum(e['passed'] for e in E)
g = {'expectations': E, 'summary': {'passed': passed, 'failed': len(E) - passed, 'total': len(E), 'pass_rate': round(passed / len(E), 3)}, 'usage': usage,
     'agent_prompts': [p(a)[:3000] for a in agents]}
json.dump(g, open(os.path.join(R, 'grading.json'), 'w'), indent=1)
print(R, f'{passed}/{len(E)}', usage.get('turns'), usage.get('cost'))
for e in E: print(' ', 'PASS' if e['passed'] else 'FAIL', e['text'], '|', e['evidence'][:140])
