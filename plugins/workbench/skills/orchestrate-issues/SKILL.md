---
name: orchestrate-issues
description: >-
  Drive a whole graph of GitHub issues to completion using background subagents.
  Queries the unblocked frontier through native GitHub issue dependencies,
  dispatches one implementer per ready issue into an isolated worktree, runs a
  spec-review agent against the result, lands the PR, then re-queries as each
  merge opens new edges. Use this whenever the user wants a set of linked issues
  worked through by agents rather than by hand — "orchestrate agents to
  implement these issues", "work through the issue chain", "dispatch background
  agents for my backlog", "implement this epic/milestone end to end", "queue up
  whatever's unblocked and keep going" — and whenever they describe a dependency
  chain, DAG, blocked-by graph, or parent issue with sub-issues that needs
  implementing. Applies even when they never say "orchestrate": a request to
  work several dependent issues automatically is this skill. Not for
  implementing one issue yourself, and not for creating the issues or the
  dependency edges in the first place.
---

# Orchestrating an issue graph with subagents

You are the loop, not the labour. Your job is to keep the frontier moving:
find what's unblocked, dispatch someone to build it, get it reviewed, land it,
and let the merge open the next edge. You do this until the graph is done, a
lane needs a human, or the graph proves it can't finish.

## The one rule: you never implement

Nothing in the repo changes by your hand. No source edit, no doc, no test, no
commit, no branch merged into another from your checkout. Not "this one's
tiny." Every change goes to a subagent, including the trivial ones, and every
change is reviewed by an agent that didn't write it.

This isn't ceremony — it's what makes the loop survive:

- **Your context has to outlast the whole graph.** An implementer spends 100k
  tokens reading and rewriting files and then exits; that's the entire point of
  it being a subagent. If you spend that context yourself you can't exit — you
  *are* the loop. Three nodes in you get compacted, and a compacted orchestrator
  has forgotten which lanes are in flight and which PRs it was about to merge.
- **You're sitting in the wrong tree.** Implementers get isolated git worktrees
  so parallel lanes can't collide. The checkout you're in is not one of them.
  Edits you make there are invisible to every implementer and will fight the
  merges you're about to do.

The pull to "just fix this one small thing" is strongest right after a reviewer
reports a one-line problem. Dispatch a fixer anyway. Which fixer, and why not the
agent that wrote the code, is the next rule.

Past runs broke this rule in four shapes, each of which felt like housekeeping
rather than implementing. Each has an agent:

| What you're about to do yourself | Who does it |
|---|---|
| Write a doc, a README fix, a follow-up nobody filed | File the issue, then an implementer and a reviewer, like any node |
| Add the one test a reviewer asked for | A fixer |
| Merge the default branch into the integration branch, or one branch into another | A rebaser |
| Read the diff yourself instead of dispatching another review | A reviewer, or a verifier after a tests-only fix |

What stays yours is everything that isn't the repo's content: `gh` calls,
issues and labels, dispatching, merging PRs through `gh pr merge`.

## The second rule: one agent, one job

Every agent you dispatch does exactly one bounded thing and exits. Check the
premises. Or implement and open the PR. Or review the diff. Or fix the findings.
Never two of those, and never the same job twice.

So when review comes back `CHANGES_REQUIRED` you dispatch a **fresh** fixer. You
don't wake the implementer with `SendMessage`, and you don't send the re-review
to the reviewer that wrote the findings.

That is the opposite of the obvious move — the implementer still has the
worktree and the reasoning, so reusing it looks free. It isn't:

- **Waking an agent resumes its whole context.** Round two starts from
  everything round one cost, plus the findings, plus whatever it now reads. The
  cost of a round grows monotonically, so the last round — the one where the
  lane is already in trouble — is the one running closest to the ceiling. An
  agent that dies mid-fix returns nothing and leaves a pushed branch in a state
  nobody can describe. You paid for the whole lane and learned less than if it
  had never started.
- **The re-derivation is smaller than it looks.** What made the implementer
  expensive was *exploration* — working out where the change belongs. That
  decision is now a diff on a pushed branch, and the findings are located to
  `file:line`. A fixer told the guard on line 120 is inverted opens one
  function, not a codebase.
- **Freshness restores the independence the split was for.** The agent that
  wrote the code knows what it meant and reads intent into its own diff. The
  reviewer that wrote the findings re-reviews its own list rather than the PR.
  Reuse quietly undoes the one thing the implementer/reviewer separation buys.

The honest cost: a fresh fixer has less standing to push back on a wrong
finding, because it doesn't hold the reasoning that produced the code. Its card
hands it the issue body so it can rule on whether a finding actually matches the
spec, and tells it to say so rather than change working code. Watch for it
caving anyway — that's the failure mode this trade buys, and it shows up as a
diff that grows to satisfy a misreading.

## The third rule: a question parks one lane, never the run

Once the first agent is dispatched, you do not call `AskUserQuestion`. It blocks
you, and while you're blocked nothing advances: reviews that came back don't get
fixers, green PRs don't merge, merges don't open edges. Across past runs this was
the single largest cost — more than half the wall clock, in runs where every lane
had finished and was waiting behind one question the user answered hours later.
The work then landed within minutes of the answer. And the answer was the
orchestrator's own recommendation about nine times in ten; the exceptions granted
*more* autonomy, not less.

So most of what used to be a mid-run question is settled in the run contract
(splits, fix-round budget, judgement calls — see Step 1), and the rest goes
through the lane rather than through you:

1. **Decide it yourself if the contract covers it.** Pick the option you'd have
   marked "(Recommended)", record it as a comment on the issue or PR under
   `## ORCHESTRATOR DECISION` (what, why, the alternative, how to override), and
   keep going. A recorded decision the user can reverse later costs a revert; an
   unanswered question costs every lane in the run.
2. **Otherwise park only that lane.** Post the question on the issue or PR under
   `## OWNER DECISION NEEDED`, add the `needs-human` label, and free its slot.
   Everything else keeps moving.
3. **Batch the open questions into your status line**, so the user sees them all
   at once when they look in — not one at a time across a day.

Ask (blocking) only before the first dispatch, or when the *whole* run is
genuinely stuck on one answer — every remaining node behind it. "One lane needs a
human" is never that.

## Choosing a model for each lane

Every dispatch takes a `model`. Omit it and each agent inherits yours, which is
not a decision — it's the absence of one, and it prices a premise check the same
as the reviewer standing between a wrong diff and your default branch.

**`opus` is the default for anything that writes to the repo or judges what was
written.** Drop a lane to `sonnet` only when the task passes the test below.
`haiku` is not used in this loop at all.

| Role | Model | Why |
|---|---|---|
| Implementer | `opus` | An implementer makes the decisions nobody downstream can see it making. Spec review catches a diff that contradicts the issue; it doesn't catch the better design the lane never considered. Nobody is watching this run, so buy the judgement up front. |
| Spec reviewer and re-reviewer | `opus` | The only thing between a plausible-but-wrong diff and `main`. It reads a diff instead of writing code, so it's the cheaper agent anyway — cheapening it saves little and costs the whole gate. |
| Fixer | `opus`, or `sonnet` per the test below | A located `defect` usually qualifies. A `design` finding never does. |
| Premise check | `sonnet` | Qualifies squarely: a closed list of claims, each answer checkable at a `file:line`. |
| Rebase | `sonnet` | Qualifies: one named operation, and CI says whether it worked. |
| Verifier (tests-only re-check) | `sonnet` | Qualifies: named mutations, and each one either turns a test red or it doesn't. |

### When `sonnet` is safe

All three, not two:

1. **The task is fully specified before dispatch.** No design decision is left to
   the agent — you are asking it to carry out a decision, not to make one.
2. **Success is mechanically checkable.** A test that fails if it's wrong, a
   named line to change, a claim with a `file:line` answer.
3. **Something downstream actually runs that check.** The re-review, the suite,
   CI. A confirmable task nobody confirms is just an unconfirmed task with extra
   steps, and this is the condition that quietly fails — it's easy to call work
   "confirmable" because a test *could* be written.

An issue with crisp acceptance criteria and a suite that covers the area can take
a `sonnet` implementer. Most issues can't, and the tell is whether you could
write down what the diff should contain before seeing it. If you'd have to say
"depends what's in there", that's a decision you're delegating, and it goes to
`opus`.

Keep a fixer on `opus` whenever the reviewer classified the round as `design`:
the implementation solved a different problem than the issue posed, so the fix is
a rethink, not a patch. A fixer at the tier that produced a design mistake tends
to produce another one.

`fable` sits above `opus`. Name it so you don't reach for it by reflex — it's the
escalation for a node that has already failed at `opus`, one lane at a time and
deliberately.

`haiku` stays out even where a task would technically qualify. Its context ceiling
is a fraction of what the others get, so it fails differently and worse: not a
wrong answer you can review, but an agent that stops mid-job. In an unattended
loop the saving isn't worth having.

State the per-role models when you state the run contract, and say out loud
whenever you drop a lane to `sonnet`, with which of the three conditions made you
comfortable. Escalating is unremarkable; economising is the choice that deserves
a sentence, because "which tier was this lane on" is the first thing worth
knowing when a PR comes back wrong.

## Step 1 — Preflight

**Resolve the target.** You need *two* repos, a local checkout, and a scope. Ask
only for what you can't infer:

- *Tracker repo* — where the issues live. If this repo has
  `docs/agents/issue-tracker.md` or equivalent, read it: issues often live in a
  different repo than the code, and every `gh` call then needs `--repo`.
- *Code repo* — where the implementation lands. Usually the same as the tracker,
  but never assume it.
- *Local checkout of the code repo* — see below. This is the step that silently
  breaks runs.
- *Scope* — one of: a parent issue whose sub-issues form the graph, a label, a
  milestone, or an explicit issue list.

**Confirm you are standing in the code repo.** `isolation: "worktree"` branches
the repo *you* are running in, not the repo named on the lane card. Get this wrong
and every implementer commits to the wrong repository and dies at first push —
after doing all the work, which is the expensive way to fail.

```bash
git -C . remote get-url origin      # what repo am I actually in?
```

If that doesn't match the code repo, you cannot dispatch from here. Clone it and
work from the clone:

```bash
gh repo clone OWNER/CODE-REPO ~/Repos/CODE-REPO      # if not already present
```

Then tell each implementer the absolute path to that checkout, and confirm the
first implementer's branch actually pushed before dispatching a second lane. One
cheap check beats five agents failing identically.

The trap is that the tracker repo is right there in your `gh` commands and *feels*
like the working repo. It isn't. Issues and code being the same repo is a common
case, not a safe default.

**Check the default branch still holds what the graph builds on.** The issues
and their edges were written against the repo as it was; the default branch
kept moving. Fetch it and skim what landed since the open in-scope issues were
filed — and what your checkout hasn't seen yet:

```bash
git fetch origin
git log --oneline HEAD..origin/<default>                          # what this checkout is missing
git log --oneline --since="<oldest open issue's createdAt>" origin/<default>
```

You're looking for a merge that removed, renamed, or rewrote the area the graph
targets. One like that makes every remaining node's plan moot, and per-issue
premise checks catch it only if they run before you plan — which, on a run that
starts by planning, they don't. This holds just as much for a narrow request
("get #N moving"): it names one node, but that node's blockers and target code
are still the premise. If the ground moved, that is the first thing the user
hears, ahead of any plan or contract.

**Read the graph.** One command, and it is the only graph query you need:

```bash
python3 <skill>/scripts/frontier.py --repo OWNER/REPO --parent 42
```

Selectors: `--parent N` | `--label X` | `--milestone N` | `--issues 1,2,3`.
Add `--json` when you want to branch on the result rather than read it.

It recurses into sub-issues of sub-issues, so splits you file appear without
re-scoping. It classifies every issue as **ready** (open, no open blockers,
unclaimed), **in_flight** (open, claimed or has an open PR), **blocked**,
**split** (an open issue with open sub-issues: a container, never dispatched),
**split_complete** (every child closed: close it yourself so its downstream
edges open), or **done**, and
reports cycles, blockers outside the scope, and `Blocked by: #N` prose that was
never converted into a real dependency edge.

**Take its warnings seriously.** A prose-only blocker is the dangerous one: it
reads like a gate to a human and gates nothing in the API, so the orchestrator
will happily dispatch work whose foundation doesn't exist. If warnings fire,
show them to the user and get a decision before dispatching. If
`deadlocked` or `cycles` is non-empty, stop — nothing you dispatch can fix a
cycle.

**A ready node can still belong to a human.** A `needs-human` label is the
convention: `frontier.py` reports such nodes as *ready — human* and never
offers them for dispatch, so the graph can gate on a human act — a credential
rotation, a store submission, a sign-off — without the loop re-offering that
node every cycle. But labels are triage opinions, not verified facts, so read
each issue's body before its first dispatch: if the work itself is something
only a person can do, it's human-gated no matter what the label says. Apply
`needs-human` yourself when you catch one — that's marking reality, not
authoring the graph — tell the user, and keep the durable state in the label
rather than in your memory of having noticed.

This skill consumes a graph; it doesn't author one. If the edges are missing or
wrong, that's the user's call to fix, not yours to infer. (Filing a split of an
in-scope issue under the contract's split authority is the one exception — it
refines a node the user already put in scope.)

**Size-check the whole scope up front.** Premise checks are cheap and read-only,
so dispatch them for every open in-scope issue now — in parallel, not lazily as
each one becomes ready. Run lazily, they surface an "oversized" verdict hours
apart, each one a fresh stop; run up front, every split is known before the
contract is agreed and the user rules on all of them in one sitting (or grants
split authority knowing exactly what it covers). A premise check run before its
blockers land can miss code that doesn't exist yet; re-run it only if a merge
touched what its claims are about.

**Check the machine can carry the run.** Past runs lost more time to disk, API,
and CI budget than to any review round — one sat dead six hours overnight with a
full disk. Before dispatching, look at:

```bash
df -h .                                         # each worktree may build its own target/, node_modules/, .venv
gh api rate_limit --jq .resources.core          # polling CI burns this
gh api "repos/OWNER/REPO/actions/runs?per_page=1" >/dev/null && echo ok   # Actions enabled
```

For compiled languages, multiply one build's artifact size by the number of
worktrees you'll create. If that doesn't fit, say so in the contract and plan
for it — a shared build cache on the lane cards (`BUILD:`), and pruning finished worktrees
after every merge (Step 5).

**Agree the run contract.** Before the first dispatch, state these back and get
an explicit yes — the merge authority especially, since merging is not something
you can undo. One round: an answer that changes a row ("merge into a feature
branch") is also the yes for the rest. Fill what it leaves open yourself (name
the branch, say so) rather than asking again; a second contract question has sat
unanswered overnight with nothing dispatched.

State the contract in chat and ask for the yes as a typed sentence that names
the grant: *reply `merge on green into <branch>`, or tell me what to change.*
The harness's permission check weighs the user's own words, and merges granted
only by picking a dialog option were later refused, nine hours into an
unattended run. A typed sentence is the best insurance available, though not a
guarantee (Step 5 covers a refusal). If the user's request already says it,
quote it back and don't ask again.

| Parameter | Default | Notes |
|---|---|---|
| Concurrency | 3 lanes | How many implementers run at once. |
| Integration branch | a feature branch for this scope | Where lane PRs merge. Use the one the user, the parent issue, or an earlier run on this scope names; otherwise create one off the default branch, named by the repo's convention, and state its name in the contract. The default branch only when the user says so. Off the default branch GitHub never fires `Closes #<n>`, so every landed node needs a manual close (Step 5). |
| Merge authority | `auto` into the integration branch | `auto` = merge on review-pass + green CI. `ask` = stop at "PR ready for review". Any merge into the default branch is `ask` until the user says otherwise in their own words — that covers a run whose integration branch *is* the default branch, and the landing PR. |
| Merge method | squash, delete branch | For lane PRs. |
| Landing | one PR, integration → default, merge commit, user merges | How the finished work reaches the default branch. See *Landing the integration branch* in Step 5. |
| Fix rounds | 2 | Failed reviews retried this many times, each by a fresh fixer, before the lane parks. A lane that is converging (each round closes real BLOCKING findings, and the remainder is tests-only) may take one more round on your own authority — record it as an orchestrator decision. Past runs asked for that extension every time and got it every time. |
| Split authority | split and report | When a size check says oversized, you file the split as sub-issues with native dependency edges, following the check's proposed cut, and dispatch the first one. Alternative: `ask`, which parks the lane (not the run) until the user rules. |
| Judgement calls | apply recommended | Design or contract ambiguities an implementer, reviewer, or you surface mid-run: decide, record as `## ORCHESTRATOR DECISION`, continue. Irreversible or out-of-scope choices still park their lane. |
| Scope growth | follow-ups filed, not dispatched | New issues created mid-run (by splits, reviews, or the user) — splits of in-scope issues are in scope; anything else is filed and listed in the report unless the user named a cap. |
| Models | `opus`, `sonnet` by exception | See *Choosing a model for each lane*. Name it here so a later drop to `sonnet` is visibly a decision rather than a drift. |
| Pipelining | off | `on` = dispatch an issue once every blocker has a *pushed branch*, stacking onto it, instead of waiting for the blocker to close. Faster, but builds on unreviewed code. |
| CI gate | required wherever the repo has CI | Never merge over red checks, and never read "no checks ran" as green without knowing why none ran (Step 5, *When no checks ran*). |

**Why a feature branch is the proposal.** Across recent runs the user asked for
one in nearly every contract that didn't offer it, and one run that never named
a branch squash-merged six PRs into a default branch that deploys. A feature
branch makes unattended merging cheap to grant: nothing ships until the user
merges the landing PR, and one revert undoes the lot.

**Authority belongs to the branch, not to the issue list.** `auto` into the
integration branch covers everything this run merges there: the original scope,
splits you file, and scope the user adds mid-run ("then pick up #679"). Runs
that re-asked at each new parent left green PRs idle for ten hours at a time,
for an answer that was "auto" every time. What needs a new yes is a new
*target*: another branch, or the default branch.

**Before granting yourself `auto`, read what actually guards the branch** (the
commands are in `references/github-recipes.md`, *Branch protection*). A merge
authority the machine will refuse is worth knowing about before five lanes are
in flight, not after. Two things to carry out of that:

- **`auto` never includes bypassing.** It authorizes `gh pr merge` through the
  front door and nothing else — not `--admin`, not a ruleset edit or bypass
  actor, not a repo setting changed to let a merge through, even when your token
  would let you. A merge the protection refuses escalates to the human. An
  unattended loop that can disable its own safety rail doesn't have one.
- **Blast radius scales the caution.** A public repo, a repo with other people's
  active work, or a default branch that ships on merge all mean a bad merge is
  visible and expensive. Say so when you propose `auto`, and name what you'd
  refuse to merge unattended regardless of green gates — anything touching CI
  config, release workflows, or the permission system itself belongs to the
  human, because those are the changes that break your ability to detect the
  next problem.

**An open PR this run didn't open is someone's history, not idle work.** Before
adopting one into review, read the comment thread on both the issue and the PR.
If an earlier run escalated it to the human, or the human has pushed to it
since, then it is theirs, and the human's last word decides what happens next.
Adopting it is a preflight question, not an orchestrator decision.

**Any assignee means hands off** — not just your own. An issue a human assigned
to themselves is theirs, even if nothing has been pushed yet; dispatching onto it
means two people editing the same thing and one of them doesn't know. The cost of
this rule is that a speculative self-assignment parks an issue until someone
unassigns it, which is the cheaper mistake by a wide margin.

## Step 2 — The cycle

Repeat until the frontier says `complete`, says `deadlocked`, or a lane
escalates:

1. **Query** the frontier.
2. **Fill lanes.** Dispatch ready issues until `in_flight` hits the concurrency
   cap. Lowest issue number first — earlier issues usually lay groundwork.
3. **Wait.** Background agents notify you on completion; you don't poll. A
   notice that an agent "is waiting on its own background work" is not a
   hand-back: its suite is running, usually for ten minutes or more. The turn
   it costs you resends your whole context, so spend nothing more on it: no
   tool call, no status text, at most the word "waiting". It is still that
   lane's latest sign of life, and the only thing you owe it is the next
   check: whenever something wakes you, any lane that has been silent longer
   than its role should take (about 90 minutes for an implementer, 45 for
   anything else, or 45 since its last waiting notice) gets looked at before
   you advance anything (`references/troubleshooting.md`, *A lane goes
   quiet*). Never end a turn with nothing in flight that will wake you: if every
   lane is parked on the human, that is the end of the run, and Step 6 applies.
4. **Advance** whichever lane reported back (review → land), then go to 1.
5. **Rebase the survivors.** A merge moves the integration branch under every other
   in-flight lane. See below.

A merge is what opens the next edge, so every landed PR earns a fresh query.
Don't try to predict which issues a merge unblocks — ask GitHub.

### Unblocked is not the same as independent

The dependency graph tells you what's *permitted* to run in parallel. It says
nothing about whether two issues touch the same file. Worktree isolation stops
two implementers fighting over a working tree; it does nothing about two branches
editing the same lines and colliding when the second one merges.

Before filling more than one lane, read the ready issues against each other and
look for shared ground:

- the same generated, vendored, or lock file (the classic — both regenerate it,
  both diffs are enormous, both conflict)
- a version number, changelog, or manifest that CI requires be bumped — each
  merge consumes the next lane's value and turns a green PR red
- the same interface one issue defines and another consumes
- a **sequence number** — migration files, schema versions, ADR numbers, a
  generated hash of a manifest. This was most of the rebase churn in past runs:
  every merge took the next number and made each sibling lane renumber, often
  two or three times, each rebase then re-reviewed and re-run through CI.

For sequence numbers there is a third move, better than either below: **reserve
them at dispatch.** Hand each lane its own number on its card (`RESERVED:` — "your migration is
`0024`; `0023` belongs to #468") in the order you expect them to merge, and tell it
not to take the next free one. If merge order then differs, apply one rule at
merge time only: a lane whose number is not the next one after the base's
highest renumbers to that next one, right before it merges. It never renumbers
in anticipation of a sibling. Each lane then renumbers at most once, and only
the lane that is actually merging moves.

Otherwise, where you find shared ground, say so and pick one of two moves rather
than discovering the conflict at merge time:

- **Serialize the lanes.** Right when the overlap is a whole file both issues
  rewrite — a lock file, a manifest, a generated artifact — or when one issue
  defines the interface the other consumes.
- **Fence them by region.** When two issues touch *different parts* of one large
  file, tell each implementer which region is its own and which belongs to the
  lane running beside it. Git merges distant hunks in one file without
  complaint, so two well-fenced lanes can cost nothing where serializing costs a
  whole lane's wall-clock. Fence both sides, not just one — a fence only one
  agent knows about isn't a fence.

A fence is a claim, so check it when the PRs come back: have the reviewer confirm
the diff stayed inside its region. And if a lane reports that it genuinely needs
the fenced ground, believe it and serialize — that's a real finding about how the
issues were cut, not an implementer being awkward.

Dispatching overlapping lanes together isn't wrong, but it means the second lane
will need a rebase round, so budget for it instead of treating it as a failure.

After every merge, in-flight lanes are now built on a stale base. Don't interrupt
an implementer that is still working to tell it so — let it finish and open its
PR. Then rebase **only when it's needed, and at most once per cause**:

- **A real conflict, or a merge underneath that changed code this lane calls**,
  before review: dispatch `workbench:rebaser` first (`name: "rebase-<n>"`,
  card in `references/lane-cards.md`), so the
  reviewer judges the diff that will actually merge.
- **A fix round is pending anyway**: don't dispatch a separate rebase — tell the
  fixer to merge the base in first. One push, one CI run, instead of two of each.
- **Merely behind, no conflict**: don't rebase at all until the lane has PASSed.
  Then `gh pr update-branch` (or a rebase agent if it conflicts) once, right
  before merging. Rebasing a lane every time a sibling lands costs a CI run each
  time and buys nothing.

A rebase whose only changes are mechanical — conflict-free replay, a renumbered
migration, a regenerated lock file or hash — does **not** need a fresh spec
review; CI is its check. Re-review only if resolving a conflict meant changing
what the code does, and the rebase agent's report says which it was.

That's ordinary lane maintenance, not a review failure — don't spend a fix round
on it, and don't count it against the lane.

**Mid-flight corrections are the one use of `SendMessage`.** The second rule
forbids *waking a finished agent* to do a new job. Telling a *still-running*
agent that its ground moved — a base branch it must rebase onto, a CI change
that alters what green means, an owner decision that settles the ambiguity it is
working through — is different: it's cheaper than letting it finish wrong, and
the agent's context hasn't ended. Keep these to one or two lines of fact.

## Step 3 — Dispatch an implementer

**Claim first**, so a crash leaves a legible trail and a resumed run doesn't
double-dispatch:

```bash
gh issue edit <n> --repo OWNER/REPO --add-assignee @me
```

**Resolve the base branch.** The integration branch, unless a blocker's work
hasn't landed yet — then base on that blocker's branch and target its PR, so the
implementer can actually see the code it depends on. `frontier.py` reports each
blocker's `open_pr` and `merged_pr`; if every blocker shows `merged_pr`, the
base is the integration branch. Under pipelining this is the normal case rather than
the exception.

**Check the issue's premises before you dispatch.** An issue that says "extend
the existing two-candidate search in `foo.rs`" is making a factual claim about
code that exists right now. Issues written from a triage pass, a design doc, or
another agent's summary are written *about* the codebase rather than *from* it.
They drift: the function moved, the mechanism was never there, or the file
lives only on an unmerged branch. A confident false premise makes an implementer
build, and you find out at review, having paid for the whole lane.

So extract the issue's claims and dispatch `workbench:premise-checker`
with them (card in `references/lane-cards.md`). Hand it the claims, not the
repo: a check that has to sweep the tree to find its own subject is no longer
well defined. In past runs about a third of checks found a claim materially
wrong. Skip the check for an issue that names no specific code, and for split
children (below). Verifying a parent does not verify its other children. Each
sub-issue was written separately, and each gets its own chance to be wrong.

**The size verdict matters as much as the claims.** Size means the diff a
reviewer has to judge, not just what an implementer can hold. Across 337 past
PRs, first-review pass rate was about 65–70% under 1500 changed lines and 35%
over it, and 45% of PRs were over it. Big lanes are the largest single driver
of review rounds. An issue flagged oversized gets split **before** dispatch.
The alternative is finding out four hours into a lane, from an agent too deep
in its context to hand off cleanly.

Under the default split authority, you file the split yourself
(`references/github-recipes.md`):

- sub-issues following the check's proposed cut, each with its share of the
  parent's acceptance criteria;
- `blocked_by` edges where the cut is serial;
- a decision comment on the parent.

Past runs waited hours for an approval that always came. A split child
inherits its parent's premise check; re-check it only if the cut moved it onto
code the check never read. A verdict the check itself calls *borderline* is
yours to rule on. Usually, dispatch it as one lane, and let the implementer's
stop-before-you-run-out rule do its job.

**Corrections go on the lane card, marked as corrections**
(`--- WHERE THE ISSUE IS WRONG ---`). Don't quietly rewrite the issue. The
implementer has to know the issue is wrong on that point, or it will follow
the original wording.

**Dispatch** `workbench:implementer` with `run_in_background: true`,
`isolation: "worktree"`, and `name: "impl-<n>"`. Send its lane card from
`references/lane-cards.md`, with the full issue body inlined. The agent
already knows the rest: whole-suite runs, self-mutation and a criteria walk
before opening the PR (both through its own child agents), waiting on long
commands without polling, holding its BASE, pushing after each criterion,
scratch-file naming, and a draft PR with `Closes #<n>`. Its job ends when the draft PR is open, and
nothing later in this loop messages it.

**Carry forward what earlier lanes established.** By the third node you know
things no issue body says: the protocol shape node two built, the guard node
one added, the lock that turned out not to exist. Put the few facts this lane
builds on in `--- VERIFIED CONTEXT ---`, named by identifier, never by line
number. The implementer is told to verify them rather than trust them, and
that matters, because eventually you will hand over a fact that was true two
merges ago. Don't let the block grow with every merge. That is how cards bloat
and implementer contexts creep toward the ceiling.

**Scratch files and PR bodies.** Worktree isolation covers the git checkout,
not the filesystem, so parallel agents share one scratch directory. The agents
name scratch files by issue number and read their PR body back after opening
it. Still confirm the body's only `Closes` line before you merge (Step 5). A
clobbered body closes the *wrong issue*, and review never catches it.

Every PR body and comment, the agents' and yours, goes to `gh` on stdin
(`--body-file -` with a heredoc), never through a file. A body file written
by its bare name lands in the current directory, which for an agent is its
worktree. Past runs left over eighty worktrees whose only change was an
untracked `review-*.md`, `fix-*.md` or `rebase-*.md` note, and a worktree
that looks dirty is one nobody dares delete.

**Drafts and CI.** The PR opens as a draft so CI runs while review happens.
Check once, in preflight, that the repo's workflows run on drafts at all. If
they skip drafts (`if: ...draft == false`, or a path filter), CI only starts
at `gh pr ready`, so budget the CI wait after review rather than alongside it.

Check in the same pass that they run on PRs *targeting the integration branch*.
A workflow with `on.pull_request.branches: [main]` never starts for a PR into a
feature branch, and then "no checks reported" means nothing ran, not that the
repo has no CI. If the triggers exclude the branch, the contract has to settle
it, because `auto` there would mean merging on review alone and a plain yes
doesn't grant that. Put the choice in the contract and ask for it by name:

- **The user widens the triggers** (recommended). It is a CI-config change, so
  it is theirs to make, or to put in scope as a reviewed node they merge.
- **Trailing CI.** Lane PRs merge on review PASS alone; you open the landing PR
  as a draft after the first merge, so the default branch's CI runs on the
  integration branch after each one. The next lane merges only once that run
  has finished green for the branch's current head; when it goes red you stop
  merging lanes and send a fixer first. A failure is found one merge late.

Until the user picks, dispatch and review as normal and hold the merges, with
the PRs left ready.

## Step 4 — Spec review

When an implementer reports back, dispatch `workbench:spec-reviewer`:
`run_in_background: true`, `isolation: "worktree"`, `name: "review-<n>-r1"`.
The worktree is what makes mutation testing and whole-suite runs possible. The
agent checks the PR out detached and holds no Write tool. It answers a **spec**
question: does the diff do what the issue asked, all of it, and nothing that
contradicts it?

**Fill its VERIFY block.** A reviewer handed only the issue and the diff
writes a competent summary. One told *the implementer claims X, go verify X*
comes back with something you can act on. The implementer's report is free
material: anywhere it says "I verified", "this is safe because", or "I chose
this reading", that is a claim to check. Add anything you are unsure of
yourself, such as a suspected design deviation, scope creep, or a fence. You
get a judgement instead of your own guess, and the judgement is often that
you were wrong.

**The findings go on the PR, not through you.** The reviewer posts them as a
PR comment and returns three lines (`VERDICT`, `KIND`, `POSTED`). Fixers and
later reviewers read the thread themselves, so you never hold, paste, or
garble a finding. The thread also outlives compaction, a dead orchestrator,
and a handover to a human.

`KIND` (the worst BLOCKING finding) is the field you act on:

- **defect:** a located, checkable problem. This is the one case where a
  `sonnet` fixer is safe.
- **design:** the implementer solved a different problem. That fixer stays on
  `opus`.

**Only BLOCKING findings cost a round.** The reviewer tags every finding
BLOCKING or FOLLOW-UP, and a review with only FOLLOW-UPs is a PASS. In past
runs, about one round in six was a full fix-and-re-review cycle for nothing
but nits. FOLLOW-UPs ride along to your end-of-run report.

### On `CHANGES_REQUIRED`

Dispatch a **fresh** `workbench:fixer`: `run_in_background: true`,
`isolation: "worktree"`, `name: "fix-<n>-r<k>"`, with the model chosen by
`KIND`. Point it at the issue and the PR, and it reads the findings off the PR
itself. If the base moved underneath the lane, add `CATCH UP: <base>` to the
card, and the fixer merges the base in first. That gives one push and one CI
run instead of two. Don't wake the implementer.

The fixer already knows the mechanical trap that kills fixers: the
implementer's worktree still holds the branch name. If a fixer reports
`already used by worktree`, its git procedure failed. Re-dispatch it; don't
delete the other worktree, because you don't know what is still running in it.

**Match the re-check to what the fix changed.** The fixer returns
`FILES: tests-only | production`. When the round's BLOCKING findings were all
test gaps and the fix really is tests-only (confirm with the compare call in
`references/lane-cards.md`), dispatch `workbench:verifier` to re-run
the mutations instead of a full re-review. Anything that touched production
code gets a **fresh** `spec-reviewer` at `review-<n>-r<k+1>`. It reads the
whole thread, including any finding the fixer disputed, which it rules on.
A verifier that returns `CHANGES_REQUIRED` (a mutation survived, or the push
touched production code) is followed by a full re-review too, not by another
verifier.

Past the agreed fix-round count, park the lane. Add `needs-human`, post a
comment linking the PR thread (every round is already on it), free the slot,
and keep the rest running. Say which kind of stop it is. In a lane that is
converging, each round closes real findings and the new one was only
reachable because the last fix went deeper; in a lane that is thrashing,
rounds don't close anything. The two need different answers from the user. A
converging lane whose remaining findings are tests-only may take one extra
round on your own authority, per the contract. A thrashing one parks.

## Step 5 — Land

On `PASS`, with `auto` merge authority:

```bash
gh pr update-branch <pr> --repo OWNER/REPO   # only if behind; do this FIRST, so green means green on the head you merge
gh pr ready <pr> --repo OWNER/REPO
# run_in_background: true — skip only where no checks run at all (see "When no checks ran")
gh pr checks <pr> --repo OWNER/REPO --watch --interval 60 --fail-fast
# ...then, when that background command reports back, as its own command:
gh pr view <pr> --repo OWNER/REPO --json headRefOid,mergeStateStatus,statusCheckRollup
# ...and only if that shows the whole run green, as its own command:
gh pr merge <pr> --repo OWNER/REPO --squash --delete-branch --match-head-commit <headRefOid>
```

**Green means the whole run, on the head you merge.** The watch reporting back
is a prompt to look, not a verdict. Read the rollup for the current head and
merge only when every check there has finished `SUCCESS`, `SKIPPED` or
`NEUTRAL`, the run is the one started for this head after `gh pr ready`, and
`mergeStateStatus` is `CLEAN`. `UNKNOWN` just after a push means GitHub is
still computing it: read again in a minute. Then merge that SHA with
`--match-head-commit`, so a push that lands in between fails the merge instead
of riding along.

**When no checks ran**, the reason decides, and preflight already told you
which it is:

- *The repo has no workflow that runs on pull requests.* There is no CI gate.
  Review PASS is the gate; merge.
- *Workflows exist but their triggers exclude this branch.* Follow what the
  contract settled (Step 3, *Drafts and CI*). Without that answer, the PR
  stays ready and unmerged.
- *Workflows ran and every job skipped itself by a path filter* (a docs-only
  diff). That is green, as long as it is the post-ready run for this head.

The merge is always its own command, after you have read that output. Runs
that chained it (`gh pr ready && gh pr merge`, `<watch>; gh pr merge`) merged
red five times, each a different way of mistaking "the watch ended" for green:

- `gh pr ready` and `gh pr update-branch` each start a *new* run. A watch
  started straight after one sees the previous run's results and exits 0.
- A draft's run can skip every real suite. "All checks passed" over a list of
  `skipping` rows, with the real run only just queued, is not green.
- `--fail-fast` exits on the first failure while other checks are still
  pending. That is a red run, and nothing after it should be a merge.
- Path-scoped or late-queued jobs can start after the watch has exited.

A check that is red for an outside reason (a rate-limited deploy preview, a
runner that never picked the job up) is still red. Waiving it is the user's
call, per check and in their words; park the PR and say which check. Don't
make it green by another route, such as re-triggering a deploy.

**Never watch CI in the foreground.** A foreground `--watch` blocks you exactly
like a question does — in one past run for 140 minutes, while finished lanes
queued behind it. Run it with `run_in_background: true` and advance the lane
when it reports. `--interval 60` matters too: several watches polling at the
default interval drained the API rate limit in one run, and then every `gh` call
failed.

**After every merge, reclaim the disk.** Each finished lane's worktrees
(implementer, reviewers, fixers, rebasers) hold a full checkout and, in
compiled languages, a full build directory. A run that never prunes fills the
disk around its fiftieth worktree, and then every agent dies at once. Pruning
by hand from `git worktree list` got skipped in every long run on record, and
one repo reached 144 agent worktrees, so run the script right after the merge
command, as part of landing:

```bash
python3 <skill>/scripts/prune_worktrees.py --apply --pr <pr>
```

It removes only `.claude/worktrees/agent-*` worktrees whose HEAD is in that PR,
and only when they're clean, no process is running inside them, and every
commit they hold is on GitHub. A Cargo build directory kept outside the
worktree (a per-workspace `build-dir`) survives `git worktree remove`, so the
script deletes it too, unless the main checkout builds there as well. It prints
what it kept and why. A worktree kept because a process is still running in
it (a test server, a watcher) needs that process stopped first; then run the
script again. A worktree kept
for uncommitted changes or for commits that never reached GitHub is a lane
whose agent didn't finish cleanly. Look before you delete it by hand. Then
glance at `df -h`.

Red CI on a check that is measuring *this PR* is not a review question — it
goes to a fresh fixer the same way review findings do, and the failing job's
output is the finding. Paste the failure into a PR comment first if it's long;
the fixer reads it there, same as a review. Two other kinds of red are not
fixer work, and misreading them as fixer work is how a merge train stalls —
see *Flaky and broken gates* below before dispatching anyone.

**A merge the permission system refuses parks that PR, not the run.** The
harness can deny `gh pr merge` even under an agreed contract. It has denied a
merge the user picked from a contract dialog, and one they typed. What it
accepts isn't predictable from here. When it happens:

- Leave the PR ready and green. Keep every other lane moving, and keep
  dispatching whatever doesn't depend on that merge.
- Say it in your status line, with the sentence that would unblock it:
  *"Merge of #<pr> into `<branch>` was denied. Reply `merge on green into
  <branch>` and I'll land it and everything queued behind it."* A denial that
  parks the whole graph is the one mid-run case worth ending a turn on.
- Retry once the user has spoken, with the same command. Reach the merge only
  through `gh pr merge`: a different route to the same merge is a bypass.

The same goes for any other denied action the user already asked for: report
the denial and the words that would clear it. Runs that silently handed the
task back waited nine hours for a reply the user didn't know was needed.

`Closes #<n>` closes the issue on merge **only when the PR merges into the
default branch**, which is what drops GitHub's `blocked_by` count on everything
downstream. On an integration branch — the usual case — or a stacked PR merging
into its blocker's branch, nothing closes: the work lands, the issue stays open, and
the frontier keeps everything downstream blocked while reporting nothing wrong.
So after *every* merge, verify the issue closed; if it didn't, close it
yourself with a comment naming the PR, and confirm the close **before**
re-querying the frontier — a re-query against an unclosed node just tells you
the graph is stuck, which you already knew. Deleting the merged branch also
makes GitHub retarget any PR stacked on it, which is what keeps stacks from
rotting.

### Flaky and broken gates

A red check might be measuring the diff, or it might be measuring the weather,
and both misreadings are expensive. Before dispatching anyone at red CI that
isn't plainly this PR's fault, follow the protocol in
`references/troubleshooting.md` (*Flaky and broken gates*): rerun is not a
fresh sample, update-branch is; a second strike gets a read-only
`workbench:ci-diagnostic`, not a fixer; and a broken gate is repaired
as its own reviewed node — never merged over, skipped, or bypassed.

With `ask` authority, leave the PR ready-for-review, report it, and treat that
lane as parked. Parked lanes still occupy a concurrency slot only if the user
wants ordering preserved; otherwise free the slot and keep going.

### Landing the integration branch

A run on a feature branch isn't finished when the frontier says `complete`:
the work is still one merge away from the default branch, and the user needs
something to review. Runs that stopped at "all issues closed" left the branch
with no PR for hours, until the user asked whether it was merged yet.

When the graph completes, or the run stops with work landed, open the landing
PR — one PR, integration branch into the default branch, ready for review —
unless one is already open. Its body lists each issue landed with its PR, every
`ORCHESTRATOR DECISION`, and what is still open. Then:

- **The user merges it.** A merge into the default branch is `ask` unless the
  user gave it to you in their own words, for this branch.
- **It lands as a merge commit.** A squash flattens every lane's commit into
  one, which one run had to revert and redo. If the repo forbids merge commits,
  say so in the PR body and leave the method to the user.
- **Catch the branch up if the default branch moved.** A branch that never
  took the default branch's changes hides work that already landed there; one
  run rebuilt a feature the default branch already had. Dispatch a
  `workbench:rebaser` at the landing PR (`BRANCH` the integration branch,
  `BASE` the default branch), and let CI run on the result before you call the
  PR ready. Do the same in preflight when the run reuses an integration branch
  that is already behind: open the landing PR as a draft then, so there is a
  PR to catch up.

## Step 6 — Report

Between cycles, a status line is enough — which issue landed, what it unblocked,
what's in flight. Save the detail for the end.

At the end, or on stopping, sweep every finished lane first. That catches
the worktrees a per-PR prune missed: a reviewer whose lane was force-pushed,
a lane you parked and then closed.

```bash
python3 <skill>/scripts/prune_worktrees.py --apply
```

Then report:

- The landing PR, with its link and CI state, as the first thing the user reads
- Issues landed, with PR links
- What's still open and why (blocked on what / escalated for what)
- Anything a human now owns — every `OWNER DECISION NEEDED`, batched, each with
  its link and your recommendation, so the user can clear them in one pass
- Every `ORCHESTRATOR DECISION` you made under the contract (splits filed, extra
  fix rounds, judgement calls), with links, so the user can reverse any of them
- FOLLOW-UP findings reviewers left on merged PRs, and follow-up issues filed
- Worktrees the sweep kept, with its reason for each

**Report only what you actually did.** "Both issues claimed and two lanes
dispatched" is a claim about the state of GitHub, and it is either true or it is
a lie you will believe yourself next cycle. The failure is easy to fall into:
you write the plan, the plan is good, and you narrate it in the past tense
without having run the commands. Then you resume from your own summary, skip the
claim step because you "already did it", and dispatch twice onto the same issue.

The same goes for "still running". A lane is running when the agent list
says so now, not because you dispatched it and heard nothing since. One run
told the user an implementer was "still going" twice, and carried that through
a compaction, eighteen hours after the agent had died in its first minute.
Check before every status line that names a lane as in flight.

The user is away — your report is the only thing standing between them and a
silent mess. If a step didn't run, say it didn't. If you're unsure whether a
merge went through, check before you write it down; the frontier query is cheap
and your memory of an unattended run is not evidence.

## When things go wrong

Dead or silent agents, a fixer that can't check out its branch, a dependency
summary that lags, replayed notifications, compaction mid-run, stale claims,
wrong scope, a clobbered PR body, rewritten tests, scope growth, and every
agent failing at once (disk, rate limit, Actions budget) each have a recovery
in `references/troubleshooting.md`. Read it the moment something looks off,
before improvising. Most of these have bitten a past run, and the obvious
improvised move was the wrong one.

## Reference files

- `references/lane-cards.md` — the `subagent_type` for each of the seven role
  agents, the lane card each one takes, and what each returns. Read before the
  first dispatch.
- `references/troubleshooting.md` — the flaky/broken-gate protocol and the
  recovery for each way a run has gone wrong before.
- `references/github-recipes.md` — `gh` commands for dependencies, claims, PRs,
  merges, and what to do where native dependencies aren't available.
