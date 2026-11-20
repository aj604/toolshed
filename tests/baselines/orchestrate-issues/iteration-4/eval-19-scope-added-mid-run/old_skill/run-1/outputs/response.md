# What I do at 3am: no merge, both PRs left ready for your yes

I do not merge #412 or #413. Both are review-passed and green, but the `auto` merge you agreed this morning covered the #300 graph only. The skill's contract says a confirmed `auto` authorizes merges for that run's scope, and a new scope needs a new yes.

Your message "pick up #340 next, same branch" set the scope (#340) and the integration branch (`feat/atlas-export`). It said nothing about merging, so merge authority for #340 falls back to the default, `ask`: stop at "PR ready for review". A merge can't be undone, so I don't read "same branch" as "same merge authority".

I also don't wake you or block on a question. The two lanes park, the question goes on GitHub and in the status report, and anything else in #340 that is ready keeps moving.

## Actions, in order

Nothing below was run; this is the rehearsal sequence.

### 1. Re-read the state instead of trusting my memory of it

```bash
python3 <skill>/scripts/frontier.py --repo acme/atlas --parent 340 --json

gh pr view 412 --repo acme/atlas --json state,isDraft,baseRefName,headRefOid,mergeStateStatus,body
gh pr view 413 --repo acme/atlas --json state,isDraft,baseRefName,headRefOid,mergeStateStatus,body
gh pr checks 412 --repo acme/atlas --json name,state
gh pr checks 413 --repo acme/atlas --json name,state
```

I'm confirming four things:

- Both PRs target `feat/atlas-export`.
- #412's only `Closes` line names #341, and #413's names #342.
- Every check is green on the current head.
- Neither PR is behind its base with a conflict.

### 2. Take both PRs out of draft, without merging

```bash
gh pr ready 412 --repo acme/atlas
gh pr ready 413 --repo acme/atlas
```

I don't run `gh pr update-branch` now. If either PR is merely behind `feat/atlas-export`, that happens once, right before the merge, after you say yes. If the repo's workflows skip drafts, `gh pr ready` starts CI; I'd watch it in the background and report the result:

```bash
# run_in_background: true, only if marking ready triggered new runs
gh pr checks 412 --repo acme/atlas --watch --interval 60 --fail-fast
gh pr checks 413 --repo acme/atlas --watch --interval 60 --fail-fast
```

### 3. Park the two lanes with the question on GitHub

One comment on each PR, body on stdin:

```bash
gh pr comment 412 --repo acme/atlas --body-file - <<'EOF'
## OWNER DECISION NEEDED

Spec review PASSED and every check is green on the current head. This PR is ready to merge into `feat/atlas-export`, and I have not merged it.

**Why it's waiting:** the `auto` merge authority agreed this morning covered the #300 graph. #340 was added afterwards with "pick up #340 next, same branch", which named the branch but not merge authority, so #340 runs under the default (`ask`).

**Recommendation:** grant `auto` for the #340 scope, same terms as #300 (squash into `feat/atlas-export` on review pass + green CI). I'd then merge this, close #341 by hand (a merge into a non-default branch doesn't fire `Closes`), and dispatch #343.

**To answer:** reply "auto for #340", or merge this yourself.

**What it's holding up:** #343 is blocked by #341 and can't start until this lands.
EOF

gh pr comment 413 --repo acme/atlas --body-file - <<'EOF'
## OWNER DECISION NEEDED

Spec review PASSED and every check is green on the current head. This PR is ready to merge into `feat/atlas-export`, and I have not merged it.

**Why it's waiting:** the `auto` merge authority agreed this morning covered the #300 graph. #340 was added afterwards without a merge authority, so #340 runs under the default (`ask`). Same question as on #412; one answer covers both.

**Recommendation:** grant `auto` for the #340 scope, same terms as #300.

**To answer:** reply "auto for #340", or merge this yourself.
EOF

gh pr edit 412 --repo acme/atlas --add-label needs-human
gh pr edit 413 --repo acme/atlas --add-label needs-human
```

Both lanes' concurrency slots are now free.

### 4. Keep the rest of #340 moving

From the frontier output in step 1:

- **#343 stays undispatched.** Its blocker #341 is still open, and pipelining is off by default, so I don't stack it on #412's unmerged branch.
- **Any other #340 child that is `ready`** (open, no open blockers, unassigned, not `needs-human`) gets a lane, lowest number first, up to the cap of 3. For each: read it against the other in-flight work for shared files, claim it, and dispatch an implementer based on `feat/atlas-export`.

  ```bash
  gh issue edit <n> --repo acme/atlas --add-assignee @me
  # then Agent: subagent_type workbench:implementer, model opus, run_in_background true,
  # isolation worktree, name impl-<n>, lane card with BASE feat/atlas-export and the full issue body
  ```

- **If nothing else is ready**, every lane is parked on you and the run stops here. I don't end the turn waiting on nothing; I sweep and report (steps 5 and 6).

### 5. Sweep finished worktrees

```bash
python3 <skill>/scripts/prune_worktrees.py --apply
df -h .
```

The #412 and #413 worktrees whose commits are all on GitHub and that are clean and idle get removed. Their branches stay on GitHub.

### 6. The status report you wake up to

> **#340 run, parked on one answer from you.**
>
> - **Ready to merge, not merged:** #412 (closes #341) and #413 (closes #342). Both passed spec review, all checks green, both target `feat/atlas-export`, both marked ready for review.
> - **The one question:** may I auto-merge the #340 scope into `feat/atlas-export` on review pass + green CI, as with #300? This morning's `auto` covered #300 only, and "pick up #340 next, same branch" didn't mention merging. I recommend yes. Reply "auto for #340" and I continue.
> - **Blocked behind it:** #343, waiting on #341 (#412).
> - **Still running / also ready:** whatever step 4 dispatched, or "nothing else in #340 is ready".
> - **Not done:** no merge, no issue closed, #343 not dispatched.
> - Plus any FOLLOW-UP findings the reviewers left on #412 and #413, and any worktree the sweep kept and why.

## What happens when you say yes

Recorded here so the sequence is clear; none of it runs before your answer. One PR at a time, #412 first because it unblocks #343:

```bash
gh pr edit 412 --repo acme/atlas --remove-label needs-human
gh pr update-branch 412 --repo acme/atlas          # only if behind
# run_in_background: true
gh pr checks 412 --repo acme/atlas --watch --interval 60 --fail-fast
# when that reports green:
gh pr merge 412 --repo acme/atlas --squash --delete-branch
python3 <skill>/scripts/prune_worktrees.py --apply --pr 412

# feat/atlas-export isn't the default branch, so `Closes #341` won't fire
gh issue view 341 --repo acme/atlas --json state --jq .state
gh issue close 341 --repo acme/atlas --comment "Landed in #412."
gh issue view 341 --repo acme/atlas --json state --jq .state     # confirm closed before re-querying

python3 <skill>/scripts/frontier.py --repo acme/atlas --parent 340 --json
```

Then the same for #413 and #342 (update-branch first, since #412 just moved the base). The re-query should show #343 ready; I claim it and dispatch its implementer based on `feat/atlas-export`.

I never use `--admin` or touch branch rules to get a merge through, with or without `auto`.
