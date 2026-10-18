# Lane cards: what you send each agent

Each role is a defined agent in this plugin, with its own instructions, tools,
and default model. You don't paste a brief. You send a **lane card**: only the
facts that vary per dispatch. The agent already knows its job, its git
procedure, where its findings go, and what to return.

Dispatch every role with the Agent tool, `run_in_background: true`, and the
`subagent_type` below. Pass `model` only when you are deliberately departing
from the agent's default. Say so when you do (see *Choosing a model for each
lane* in SKILL.md).

| Role | `subagent_type` | Default model | `isolation` | `name` | Can edit? |
|---|---|---|---|---|---|
| Implementer | `workbench:implementer` | opus | `worktree` | `impl-<n>` | yes |
| Spec reviewer | `workbench:spec-reviewer` | opus | `worktree` | `review-<n>-r<k>` | mutations only (no Write) |
| Fixer | `workbench:fixer` | opus | `worktree` | `fix-<n>-r<k>` | yes |
| Premise check | `workbench:premise-checker` | sonnet | — | `premise-<n>` | no (read-only tools) |
| CI diagnostic | `workbench:ci-diagnostic` | sonnet | — | `diag-<n>` | no (read-only tools) |
| Rebase | `workbench:rebaser` | sonnet | `worktree` | `rebase-<n>` | yes |
| Verifier | `workbench:verifier` | sonnet | `worktree` | `verify-<n>-r<k>` | mutations only (no Write) |

The read-only roles hold no Edit or Write tool, so "read-only" is enforced,
not just requested. Bash remains, because they need `gh` and `git`. The two
mutation roles can Edit, because mutation testing needs it, but they cannot
Write. Their detached checkout makes a push structurally impossible.

**Inline the issue body, verbatim, on every card that takes one.** An agent
told to "go read issue #42" re-fetches what you already hold, and starts
guessing if the issue is thin.

**Fill every field you know, and omit the ones that don't apply.** An empty
optional block is noise. A missing required field becomes an agent that
guesses.

---

## Implementer

```
REPO:          <owner/repo of the code>
ISSUE TRACKER: <owner/repo of issues — omit if the same>
ISSUE:         #<n> — <title>
BRANCH:        <branch-name>
BASE:          <base-branch>   # default branch, or a blocker's branch when its work hasn't landed

--- ISSUE BODY ---
<full issue body, verbatim>
--- END ISSUE BODY ---

[--- CLARIFYING COMMENTS --- <comments that change the spec> --- END ---]
[--- WHERE THE ISSUE IS WRONG --- <premise-check corrections: claim, what is true, file + identifier> --- END ---]
[--- VERIFIED CONTEXT --- <the few facts earlier lanes established that this lane builds on, by identifier> --- END ---]
[FENCE:    <region that is yours> / <region belonging to #m, running beside you>]
[RESERVED: migration <NNNN> (<NNNN-1> is reserved for #m)]
[BUILD:    CARGO_TARGET_DIR=<shared path> | delete target/ before exiting]
```

Keep VERIFIED CONTEXT to the facts this lane actually builds on. A digest of
every earlier lane, growing with each merge, is how cards bloat. Name
identifiers, not line numbers, because line numbers are stale the moment
anything above them lands.

## Spec reviewer

```
REPO:   <owner/repo>
PR:     #<pr>
ISSUE:  #<n>
BRANCH: <branch>
ROUND:  <k>

--- ISSUE BODY ---
<full issue body, verbatim>
--- END ISSUE BODY ---

--- VERIFY ---
1. <a claim from the implementer's report: anything it said it verified, chose, or deemed safe>
2. <anything you are unsure of: suspected design deviation, scope creep, a fence it was asked to keep>
--- END ---
```

The implementer's report is free material for VERIFY. Wherever it says "I
verified", "this is safe because", or "I chose this reading", hand that over
as a claim to check. A reviewer told *the implementer claims X, go verify X*
comes back with something you can act on.

## Fixer

```
REPO:   <owner/repo>
ISSUE:  #<n>
PR:     #<pr>
BRANCH: <branch>
ROUND:  <k>   # the review round whose findings it fixes
[CATCH UP: <base-branch>]   # the base moved under this lane: merge it in before fixing

--- ISSUE BODY ---
<full issue body, verbatim>
--- END ISSUE BODY ---
```

The fixer reads the findings off the PR itself. Never paste them.

Model: `sonnet` when KIND was `defect`, because that is a located line and a
suite that fails if it is wrong. Otherwise use the default. `design` always
stays on opus, as does any lane past its first round.

## Premise check

```
REPO:  <owner/repo> — local path <path>
ISSUE: #<n> — <title>

--- ISSUE BODY ---
<full issue body, verbatim>
--- END ISSUE BODY ---

--- CLAIMS ---
1. <a file that supposedly exists / function to extend / mechanism to reuse / behaviour described as current>
...
--- END ---
```

Extract the claims yourself. A check that has to sweep the repo to find its
own subject has stopped being well defined.

## CI diagnostic

```
REPO:  <owner/repo>
PR:    #<pr> (branch <branch>)
CHECK: <failing job name>
RUNS:  <run ids — at least two strikes on fresh merge commits>
```

## Rebase

```
REPO:   <owner/repo>
PR:     #<pr>
BRANCH: <branch>
BASE:   <base-branch>
[RENUMBER: migrations/0021_x.sql -> 0022 (0021 was taken by #m)]
```

## Verifier

```
REPO:         <owner/repo>
PR:           #<pr>
BRANCH:       <branch>
ROUND:        <k>   # the review round whose test gaps the fixer closed
REVIEWED_SHA: <the head commit that round reviewed>
```

Before you dispatch it, confirm the fix touched only test files. Check the
whole range since the review, not just the latest commit, because a fixer may
push more than once:

```bash
gh api repos/OWNER/REPO/compare/<reviewed-sha>...<head-sha> --jq '[.files[].filename]'
```

---

## Reading what comes back

Every role returns a few lines, never a report, and puts its account on the PR:

| Role | Returns | You act on |
|---|---|---|
| Implementer | PR, BRANCH, SIZE, SUMMARY, CRITERIA, TESTS, MUTATIONS, JUDGEMENT, NOTED | SIZE above ~800 lines, any JUDGEMENT, and claims to put in the reviewer's VERIFY |
| Spec reviewer / verifier | VERDICT, KIND, POSTED | KIND picks the fixer's model; PASS goes on to landing |
| Fixer | PUSHED, CLOSED, FILES, TESTS, POSTED | FILES `tests-only` lets you use a verifier instead of a full re-review (confirm with the compare call) |
| Rebase | PUSHED, RESOLUTION, TESTS | `semantic` needs a re-review; `none` or `mechanical` doesn't |
| Premise check | claim verdicts, SIZE line, split | MATERIAL WRONG becomes a correction on the card; oversized goes to the split |
| CI diagnostic | VERDICT, CAUSE, EVIDENCE, FIX | See *Flaky and broken gates* in SKILL.md |

## Why these roles and not others

**The implementer/reviewer split** exists because the context that wrote the
code is the worst judge of whether it matches the spec. It knows what it
*meant*, so it reads that intent into the diff.

**The fixer is separate** for the same reason, plus one more. Reusing the
implementer would resume its entire context for round two, which pushes a lane
into the hundreds of thousands of tokens and then kills it with nothing to
show. Findings that live on the PR are what make the split cheap: nothing has
to be carried between agents.

**More reviewers** (security, performance, style) are possible, but each costs
a full agent per node. If the repo has a review agent the user already trusts,
dispatch it alongside the spec review rather than widening the spec
reviewer's question.
