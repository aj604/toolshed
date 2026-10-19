---
name: commit-to-pr
description: Use when the user invokes /workbench:commit-to-pr or asks to commit changes and open or update a pull request, including "ship this" or "make a PR for these changes". Not for reviewing code or deciding whether unfinished work should ship.
---

# Commit to PR

Requires git and authenticated GitHub CLI (`gh`) for pushing and opening PRs. With no remote, stop after the local commit.

Turn uncommitted work (or unpushed commits) into a pull request: survey → branch → stage → commit → push → PR.

**This skill does not review code.** No security/QA/docs agents, no coverage assessment, no release-readiness verdict. Review is a separate job when requested. Staying narrow is what makes this fast and what makes its output trustworthy: everything it writes into a PR body is something it actually observed.

## Arguments

- `[commit-message]` — use verbatim as the commit subject instead of generating one
- `[base-branch]` — PR target (default: the repo's actual default branch)
- `--draft` — open the PR as a draft

## Step 1 — Survey before touching anything

Run these together in one message:

```bash
git status --porcelain=v1 --branch
git diff --stat
git diff --staged --stat
git log --no-merges -20 --format='%s'
git log -1 --format='%b'
git branch --show-current
git remote -v
```

Twenty subjects, not five: commit conventions vary per repo and mixed histories are common, so a short sample will mislead you. The last commit body tells you whether this repo uses trailers.

What you're deciding here:

| Observation | Consequence |
|---|---|
| Nothing modified, but commits ahead of upstream | Skip steps 3–4, go straight to push + PR |
| Nothing modified, nothing ahead | Stop. Say so. There's nothing to ship |
| Detached HEAD | Stop. Ask where this work should live |
| No remote configured | Stop after committing. Explain that there's nowhere to push |
| On the default branch | You need a new branch — step 2 handles it |

## Step 2 — Get on a good branch

Follow the repository's branch naming convention. If none is documented or evident in recent branches, use `change/<slug>`:

- `<slug>` is kebab-case, 2–5 words, and names *the change* — not the area it touches. `fix-audit-exit-code`, not `audit-stuff`.
- If the work closes an issue, append the number: `change/contract-pin-22`.
- Branches already namespaced under `claude/` or `codex/` belong to another harness. Leave those prefixes alone.

Three cases:

**On the default branch** — create the branch before staging anything, so nothing gets committed to main by accident:
```bash
git checkout -b change/<slug>
```

**On an auto-generated name** — rename it. Worktree tooling names branches `<adjective>-<surname>-<hex>` (`adoring-leakey-5e0704`, `compassionate-hopper-503d24`), which tells a reviewer nothing and makes the branch list unsearchable weeks later. Detect that shape, derive a real slug from the diff, and rename:
```bash
git rev-parse --abbrev-ref '@{upstream}'   # if this FAILS, no upstream → safe to rename
git branch -m change/<better-slug>
```
Only rename when there is no upstream. Once a branch has been pushed, renaming orphans the remote branch and any open PR — in that case keep the name and mention it in your summary.

**On a meaningful name** — keep it. Don't rename branches that already say what they are.

## Step 3 — Stage deliberately

The previous version of this command ran `git add .`, which is exactly how unrelated edits, build output, and `.env` files end up in pull requests. Read before you stage.

Read the actual `git diff` — not just `--stat`. You need the content to write an honest commit message anyway, and it's the only way to notice that half the changes belong to a different piece of work.

- **Tracked modifications** that belong to this unit of work: `git add -u` when all of them do, or path-by-path when they don't.
- **Untracked files**: list them explicitly and stage only the ones that are clearly part of the work (new source files you created). Never bulk-add. When it's genuinely ambiguous, ask — one question is cheaper than a polluted PR.
- **Changes that belong to a different piece of work**: leave them unstaged and say so in your summary. Don't silently sweep them in.

Stop and report rather than staging, if you see:

- Credential-shaped paths: `.env*`, `*.pem`, `*.key`, `id_rsa*`, `*.p12`, `credentials.json`, `.npmrc`, `.netrc`
- Secret-shaped content in the staged diff: `-----BEGIN * PRIVATE KEY-----`, `sk-ant-`, `ghp_`, `github_pat_`, `AKIA[0-9A-Z]{16}`, `xox[baprs]-`
- Files over ~1 MB, or anything under `dist/`, `build/`, `node_modules/`, `.venv/`, `target/` — these almost always mean a missing `.gitignore` entry, not an intended commit

Catching one of these is the start of the job, not the end. Two follow-ups turn a warning into an answer.

**Say whether the secret needs rotating.** "I found an API key in `.env`" leaves the worst question unanswered: is it already published? Check whether that path has ever been committed:

```bash
git log --all --diff-filter=A -- <path>
```

Empty output means the file was never added on any ref you have — the key never left the machine, and nothing needs rotating. Say that explicitly, because it's the difference between deleting a line and rotating a credential across every system that uses it. If the output is *not* empty, the secret is in history: say so plainly, name the commits, and stop there. Don't rewrite history on your own initiative; that's the user's call and it breaks anyone who has already pulled.

**Close the hole so the near-miss doesn't recur.** If nothing in `.gitignore` covers what you just caught, add it — appending to the existing file, or creating one — and commit it *by itself*, ahead of the main commit:

```
chore: ignore .env and build output
```

Its own commit keeps it trivially droppable if the user disagrees, and it means the next bulk `git add` can't sweep the file in. Reporting the near-miss without fixing it just schedules the same near-miss for next week. Worth noting in your summary that the new rule only protects this branch until it merges.

## Step 4 — Commit in this repo's voice

Match the history you read in step 1. Don't impose a format the repo doesn't use — a conventional-commit prefix in a repo that writes plain prose reads as noise, and vice versa.

- Most recent subjects look like `type(scope): summary` → use conventional commits
- Most recent subjects are plain imperative sentences → write plain imperative prose
- Genuinely mixed → follow the most recent ten

Regardless of style: subject in imperative mood, under ~72 characters, saying what changed and why it matters rather than which files moved. `Bound fault-report scheduler bookkeeping` beats `Update scheduler.rs`.

Add a body only when the change needs explaining — a non-obvious decision, a constraint that forced the approach, something a reviewer would otherwise ask about. Obvious changes get a subject and nothing else.

Trailers: mirror what the repo already does. If recent commits carry `Co-Authored-By: Claude <model> <noreply@anthropic.com>`, include it with the model actually running this session. If the repo has never used trailers, don't start.

Split into multiple commits when the work contains genuinely separable units — a refactor plus a feature, or a fix plus its test-infrastructure change. Don't split a single coherent change to look tidy.

**Pre-commit hooks.** If a hook rejects the commit, read its output and fix the cause. If a hook *modified* files (formatters, linters with `--fix`), inspect those edits and re-stage only the intended paths or hunks before committing again. Never use a blanket `git add -u` when unrelated edits are present. Verify the staged diff and resulting commit contain only this unit of work; unrelated changes may remain dirty. Never pass `--no-verify` unless the user explicitly asks.

## Step 5 — Push

```bash
git push -u origin <branch>
```

- **Rejected as non-fast-forward** — the remote has commits you don't. Stop and report. Never force-push without being asked.
- **Blocked by push protection** — GitHub found a real secret. Stop. Don't try to work around it.
- **No remote** — you already caught this in step 1; the commit is safe locally, just say where it is.

## Step 6 — Open the PR

**Check for an existing PR first.** `gh pr create` fails outright if one is already open for this branch:
```bash
gh pr view --json url,state,title 2>/dev/null
```
If a PR exists, you've just pushed to it. Report the URL, and update the description if what you pushed made it stale.

**Base branch**: the user's argument if given, otherwise the repo's real default (resolve this during the survey, before deciding whether a new branch is needed):
```bash
gh repo view --json defaultBranchRef -q .defaultBranchRef.name
```

**Body.** Look at what this repo's merged PRs actually look like before writing (`gh pr list --state merged --limit 5 --json body`) and match that shape. Absent a house style, use:

```markdown
## What

[What changed and why — 2-6 lines of prose or bullets. Written for someone
who hasn't seen the diff.]

## Notes

[Only when there's something a reviewer would otherwise miss: a decision you
made and the alternative you rejected, something deliberately left out, a
known follow-up.]

🤖 Generated with [Claude Code](https://claude.com/claude-code)
```

Two rules keep this honest, and they matter more than the structure:

- **Every claim traces to something you actually did or read.** No coverage percentages, no vulnerability counts, no "all tests pass" — unless you ran the command and saw the output, in which case name the command and quote the result. The previous version of this command shipped a template full of `[X%]` and `Critical: [count]` placeholders that nothing in the workflow ever measured, which trained readers to skip the PR body entirely. A short honest body is worth more than a long fabricated one.
- **Drop sections that have nothing in them.** Empty scaffolding is worse than no scaffolding.

**Title**: the commit subject for a single commit; a line summarizing the set for several. No trailing period.

Add `--draft` if the user asked. Don't auto-apply labels — `gh pr create --label` hard-fails on labels the repo doesn't define, and guessing them adds noise.

## Step 7 — Report

Keep it to a few lines:

- Branch — and the rename, if you renamed one
- Commit subject(s)
- Anything you deliberately left unstaged, and why
- PR URL

If you stopped early, say exactly where and what's needed to continue. Work that's committed but unpushed is not lost, and the user needs to know that.

## Example usage

```bash
/workbench:commit-to-pr                            # survey, branch, commit, push, PR
/workbench:commit-to-pr "fix: audit exit code"     # supply the commit subject
/workbench:commit-to-pr "" develop                 # PR against develop
/workbench:commit-to-pr --draft                    # open as draft
```
