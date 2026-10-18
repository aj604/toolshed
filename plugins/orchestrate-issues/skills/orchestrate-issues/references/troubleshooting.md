# Troubleshooting

## Flaky and broken gates

A failing check might be measuring the diff, or it might be measuring the
weather. The protocol below exists because both misreadings are expensive in
opposite directions: treat a flake as real and you burn fixers on innocent
code; treat a real failure as a flake and you merge a defect. Work it in
order, and don't improvise past a step:

1. **One failure is one data point — and a rerun is the same data point.**
   `gh run rerun --failed` re-runs the *same merge commit*, so a second
   failure there is not independent evidence, however deterministic it looks.
2. **Move the commit to get a fresh sample.** `gh pr update-branch` creates a
   new merge commit and CI runs against genuinely new state.
3. **Second strike on a fresh commit → dispatch `orchestrate-issues:ci-diagnostic`, not a fixer.**
   Read-only, one question: what is failing, and could this diff cause it? A
   fixer dispatched here starts changing code before anyone knows whether the
   code is wrong.
4. **"Pre-existing and unrelated" plus "blocks this merge" means fix it now.**
   A failure that blocks this merge blocks every merge behind it. That makes it
   lane maintenance — a fresh agent, fixing the flake itself, immediately — not
   an out-of-scope observation to defer. Deferring it parks the whole train
   behind a cause you have already diagnosed.

Sometimes the diagnosis is worse: the gate itself is broken. A lint job killed
by an upstream release, a rotted runner image, an expired secret — red on
every PR, including PRs that couldn't possibly have caused it. "Never merge
over red" has nothing to say about this, so here is what it means in practice:

- **Repairing the gate is a first-class node, not an inline favour.** Fresh
  agent, its own PR, its own spec review, landed through the same front door
  as everything else. The gate guards the whole run; an unreviewed change to
  it is the most dangerous diff in the repo.
- **It is also a scope addition the user never agreed to, so surface it.**
  Under `ask` authority, escalate before dispatching the repair. Under `auto`,
  dispatch it and say in the next report what you decided and why — the
  alternative was every lane parked behind a gate nobody may bypass.
- **What stays forbidden either way:** merging over the red check, disabling
  or skipping the check, or using `--admin` or a ruleset edit to route around
  it. Repair the gate or wait for the human; those are the only two moves.

## When things go wrong

- **An agent dies or returns nothing.** Its `Agent` result is null. Don't read
  its transcript to find out why — for a local agent that `.output` file is a
  symlink to the full JSONL conversation and will flood your context. Check
  whether a branch or draft PR survived, then dispatch a fresh agent from that
  point. If an agent ran out of context rather than erroring, the fix is a
  smaller job, not a bigger model: split what you asked it for.
- **A fixer can't check out the branch.** `fatal: '<branch>' is already used by
  worktree at ...` means the implementer's worktree still holds it and the
  fixer skipped its own `git checkout -B <local> origin/<branch>` step.
  Re-dispatch rather than deleting the other worktree — you don't know what is
  still running in it.
- **A lane stalls with no notification.** Verify with the frontier query (does
  the PR exist?) rather than by polling the agent.
- **A node still reads blocked right after you closed its blocker.** GitHub's
  `issue_dependencies_summary` lags the live edge states — sometimes by long
  enough to stall a cycle. `frontier.py` cross-checks the summary against the
  edges themselves and warns when they disagree; on that warning, trust the
  edges and treat the node as ready. An orchestrator that trusts the summary
  alone will sit waiting on blockers that are already closed.
- **A completion notification you've seen before.** Notifications can re-fire —
  a reaped child process, a killed background watch — and each replay injects a
  full agent result into your context as if it were news. Before acting on any
  notification, check GitHub: if the PR, review comment, or merge it announces
  is already in the state you'd be advancing it to, the notification is a
  replay — drop it. GitHub dedupes your actions the same way it survives your
  compaction.
- **You get compacted mid-run.** GitHub is your state, not your memory.
  Re-query the frontier: assignees mark claims, draft PRs mark work in progress,
  merged PRs mark done. The PR comments carry every review round, so you can
  recover which lanes had failed review and how many rounds they had spent.
  Rebuild the lane table from that and continue.
- **Stale claims from an earlier run.** Issues assigned to you with no branch and
  no PR are leftovers. Raise them in preflight, before the first dispatch, as
  one question covering all of them — not mid-run, one at a time.
- **The scope was wrong.** If the frontier reports blockers outside your scope,
  say so plainly — the run can't unblock them, so those subtrees will never
  become ready.
- **A PR body that isn't the one you think.** Before merging, confirm the body's
  only `Closes` line names the issue that lane was dispatched for. A clobbered or
  copy-pasted body closes someone else's node, and the frontier then reports work
  as done that nobody did — a lie you will believe next cycle.
- **An implementer that modified existing tests.** Sometimes legitimate: the
  issue changed the behaviour those tests encoded. Sometimes it is a regression
  being laundered into a green suite. You cannot tell from the report, so make
  the reviewer diff the test file against the base itself and account for every
  removed assertion. Expect this to clear as often as it convicts — checking it
  is cheap either way.
- **A new issue appears inside your scope mid-run.** A follow-up someone files
  against the parent shows up as `ready` on the next query. It was not in the
  contract you agreed, so don't dispatch it on the strength of the frontier
  alone: check its labels (a `needs-human`-style label settles it), then apply
  the contract's scope-growth rule — a split you filed is in scope; anything
  else is listed in the report, not dispatched. In one past run the graph grew
  from 33 nodes to 42 mid-run, and that run is the one that "never finished".
- **Every agent fails at once.** Before diagnosing any one of them, check the
  machine: `df -h` (disk full — prune worktrees, kill orphaned test servers),
  `gh api rate_limit` (exhausted — wait for the reset, and lengthen watch
  intervals), Actions billing (budget out — that's the human's). A
  shared-resource failure dressed as five agent failures sends five fixers after
  a problem none of them can see.

