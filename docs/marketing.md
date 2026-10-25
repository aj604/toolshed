# Workbench launch copy

Audience: developers using Claude Code, especially those running several
agent sessions and losing track of the resulting branches and PRs.

## Positioning

**Name:** Workbench

**Tagline:** Put your coding agents to work.

**One sentence:** Five Claude Code skills for turning repo work into pull
requests and keeping track of what shipped.

**GitHub About:** Workbench: five Claude Code skills to ship improvements,
orchestrate GitHub issues, build parallel PR stacks, open PRs, and catch up on
what shipped.

Lead with a concrete job and show the result: an improvement PR, a dependency
becoming unblocked, a stack you can review, or a status report that tells you
what needs attention. Use the repo link as the call to action:
https://github.com/aj604/toolshed

## Artwork

Attach [`social-card.png`](../assets/social-card.png) to the launch post.
It also serves as the README hero and the replacement GitHub OG image.
The [asset guide](../assets/README.md) covers the editable source, square icon,
and the separate GitHub social-preview upload.

## X launch post

```text
I built Workbench: 5 Claude Code skills for shipping with agents.

Pick an improvement. Run agents across linked issues. Build parallel PR stacks. Open a PR. Catch up on what shipped.

Install in two commands:
https://github.com/aj604/toolshed
```

## Follow-up: install

```text
In Claude Code:

/plugin marketplace add aj604/toolshed
/plugin install workbench@toolshed

Then, inside your repo:

/workbench:pm-status

What landed, what's stuck, what needs you, and what to do next.
```

## Skill spotlights

Each block is a standalone post. Pair it with the corresponding demo below.

### Enhance

```text
"Find something worth building in this repo."

/workbench:enhance

Reads the code and recent direction, picks one improvement, builds it, verifies it, and opens a PR.

Give it an area like "the CLI" to narrow the search.

https://github.com/aj604/toolshed
```

### Issue orchestration

```text
Have an epic split into linked GitHub issues?

/workbench:orchestrate-issues

Agents take unblocked issues in isolated worktrees. Separate agents review the PRs. Merges unblock the next issues.

You agree scope and merge authority up front.

https://github.com/aj604/toolshed
```

### Enhancement lanes

```text
"Improve the CLI, tests, and error paths. Two rounds each."

/workbench:incremental-enhancement-lanes

Each area gets a stack of spec-reviewed PRs. Each round builds on the last. The stacks stay open for you to accept or drop.

https://github.com/aj604/toolshed
```

### Commit to PR

```text
Changes ready. Still need a branch, commits, a push, and a PR?

/workbench:commit-to-pr

Reads your diff, follows the repo's commit conventions, and opens or updates the PR. Bring validation from your development workflow.

https://github.com/aj604/toolshed
```

### PM status

```text
Sent agents off to work, then lost track of where it all ended up?

/workbench:pm-status 3d

What landed. What's in flight. What needs you. What next.

It checks PRs, issues, CI, worktrees, branches, and available session history.

https://github.com/aj604/toolshed
```

## Demo shots to capture

Use a public or disposable repo and show an actual run. Pair the prompt with
its resulting artifact:

- **PM status:** a short report with Landed, In flight, Needs you, and Next up.
  This makes a useful first screenshot for developers already running agents.
- **Enhance:** the chosen improvement and its resulting PR diff.
- **Issue orchestration:** a blocked issue becoming ready after its blocker's
  PR merges, with the separate review visible.
- **Enhancement lanes:** two independent PR stacks, each with at least two
  rounds, left open for human review.
- **Commit to PR:** the initial diff and the new or updated PR.

Keep the command and result legible. Report timings or quality claims only
when the captured run supports them. Agent work uses the user's model access;
parallel lanes dispatch multiple implementers and reviewers.

## Before launch

- Land the Workbench docs and version bump before linking people to `main`.
- Try the published marketplace install in a fresh Claude Code session.
- Capture one real workflow result and attach it to the launch post.
- Upload the Workbench [social preview](../assets/social-card.png) in GitHub
  settings; the repo file and GitHub's uploaded OG image are separate.
- Keep the `toolshed` marketplace and `workbench@toolshed` installation names.
- Follow [release naming and compatibility notes](migration.md) if publishing
  a Workbench GitHub release.
