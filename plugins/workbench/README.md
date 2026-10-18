# workbench

An SDLC toolkit for Claude Code. It currently ships one tool, with more to come.

## orchestrate-issues

Drive a GitHub issue dependency graph to completion with background agents.

You point it at a parent issue, label, milestone, or issue list. It reads the
graph through GitHub's native `blocked_by` dependencies, then runs this loop
until the graph is done:

1. It dispatches an implementer per unblocked issue, each in its own git
   worktree.
2. A spec reviewer checks each PR against its issue.
3. Fixers take the review findings.
4. It lands the PR.
5. It re-queries, because each merge can open new edges.

The orchestrator never edits code itself.

```
/plugin marketplace add aj604/toolshed
/plugin install workbench@toolshed
```

Then ask for it in plain words, for example: *"work through the sub-issues of
#42 with agents, auto-merge into main"*.

## What's inside

| Path | What it is |
|---|---|
| `skills/orchestrate-issues/` | The orchestrator: run contract, frontier loop, landing, reporting |
| `skills/orchestrate-issues/scripts/frontier.py` | Reads the graph: ready, in-flight, blocked, split, done, plus cycles and prose-only blockers |
| `agents/implementer.md` | Builds one issue and opens a draft PR. Mutation-checks its own tests first. |
| `agents/spec-reviewer.md` | Reviews a PR against its issue and posts BLOCKING/FOLLOW-UP findings on the PR (opus, no Write) |
| `agents/fixer.md` | Closes BLOCKING findings on an existing PR, starting cold |
| `agents/premise-checker.md` | Read-only check of an issue's claims about the code, plus a size verdict and split |
| `agents/verifier.md` | Cheap re-check after a fix that touched only tests (sonnet, no Write) |
| `agents/rebaser.md` | Merges a moved base into a PR branch, never force-pushing |
| `agents/ci-diagnostic.md` | Read-only verdict on a failing check: caused by the diff, pre-existing, or a broken gate |

## Defaults worth knowing

- **It asks before the first dispatch, then not again.** Merge authority,
  split authority, fix-round budget, and scope are agreed up front. After
  that, anything needing a human parks only its own lane (`needs-human` plus a
  comment), and the rest keep moving. Decisions it makes alone are posted as
  `## ORCHESTRATOR DECISION` comments you can reverse.
- **Merges go through the front door only.** No `--admin`, no ruleset edits,
  and never over a red check.
- **Lanes are sized for review.** Issues estimated over ~800 changed lines
  are split before dispatch, because big PRs fail first review about twice as
  often.
