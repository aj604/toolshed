## Plan per lane

- **#30 / PR #60 (PASS, 2 behind, no conflict):** Land it now. Being behind with no conflict means one `gh pr update-branch` right before merging, then CI, then merge. It needs no rebase agent and no new review. First I check its file list for two things. If it adds a migration, every reservation below shifts by one. If it touches CI or release config, it isn't merged unattended. I also confirm the body has exactly one `Closes #30`. After the merge I verify #30 closed, prune its worktrees and re-query the frontier.
- **#31 (implementing, adds a migration):** Don't interrupt its work. The one exception is the migration number. If its card had no `RESERVED:` line, it will take the next free number, which collides with #33. So I send one mid-flight correction reserving **0020**, since #31 started earlier and should merge first. #33 gets **0021**. If merge order flips, a rebaser renumbers once, just before that lane merges. When its PR arrives it gets a normal spec review. If #60 merged code #31 calls, it gets a rebaser before review.
- **#32 (CHANGES_REQUIRED, defect, base moved in the same module):** A fresh fixer with `CATCH UP: main`, so the base merge and the fix go out as one push and one CI run. I won't wake the implementer and won't send a separate rebase. Normally a `defect` fixer can run on sonnet. Here I'm **keeping opus** because the catch-up merge lands in the same module and may need semantic conflict resolution. That work isn't fully specified up front, so the first sonnet condition fails. The fix touches production code, so a fresh `review-32-r2` follows. This rebase counts as lane maintenance, not a fix round.
- **#33 (ready, adds a migration):** No slot yet: #30, #31 and #32 hold all three. Its premise check is read-only and doesn't take a lane, so it runs now if it wasn't done in preflight. I also check #33 against #31 and #32 for shared ground beyond the migration number, such as the same table or module. Where they overlap I'd fence them by region, or serialize if one defines what the other consumes. Once #60 merges and #30 closes, I claim #33 and dispatch it with migration 0021 reserved.

This assumes I'm running from a local `acme/ledger` checkout, because worktree isolation branches whatever repo I'm standing in. The current directory isn't a git repo, so step 0 below confirms that.

## Ordered actions

0. `git -C ~/Repos/ledger remote get-url origin` should return acme/ledger. All dispatches run from that checkout.

1. Check PR #60 before landing:
   ```bash
   gh pr view 60 --repo acme/ledger --json files,body,isDraft --jq '{files:[.files[].path], body, isDraft}'
   ```
   I look for `migrations/0020_*`, any `.github/` or release files, and exactly one `Closes #30`. **The reservations below assume #60 adds no migration.** If it does, #31 gets 0021 and #33 gets 0022.

2. **SendMessage** to `impl-31`, only if its card lacked `RESERVED:`:
   > Your migration number is `migrations/0020_*.sql`; 0021 is reserved for #33. Don't take the next free number. No other change.

3. **Dispatch fixer for #32.** subagent_type `orchestrate-issues:fixer`, isolation `worktree`, name `fix-32-r1`, model `opus` (kept on the default because of the catch-up merge), run_in_background true.
   ```
   REPO:     acme/ledger
   ISSUE:    #32 — <title>
   PR:       #<pr-32>
   BRANCH:   <branch-32>
   ROUND:    1
   CATCH UP: main

   --- ISSUE BODY ---
   <#32 body, verbatim>
   --- END ISSUE BODY ---
   ```

4. **Dispatch premise check for #33**, only if it wasn't run in preflight. subagent_type `orchestrate-issues:premise-checker`, no isolation, name `premise-33`, model `sonnet` (its default), run_in_background true.
   ```
   REPO:  acme/ledger — local path ~/Repos/ledger
   ISSUE: #33 — <title>

   --- ISSUE BODY ---
   <#33 body, verbatim>
   --- END ISSUE BODY ---

   --- CLAIMS ---
   1. Latest migration on main is migrations/0019_*.sql; the migration runner applies files in numeric order.
   2. <tables/modules #33 says it extends — exist as described>
   3. <any other code claims extracted from the body>
   --- END ---
   ```

5. Land #60:
   ```bash
   gh pr update-branch 60 --repo acme/ledger
   gh pr ready 60 --repo acme/ledger
   gh pr checks 60 --repo acme/ledger --watch --interval 60 --fail-fast   # run_in_background: true
   # when green:
   gh pr merge 60 --repo acme/ledger --squash --delete-branch
   ```
   If CI goes red, I follow the flaky/broken-gate protocol before dispatching anyone. I never use `--admin`.

6. Confirm #30 closed, then reclaim disk:
   ```bash
   gh issue view 30 --repo acme/ledger --json state --jq .state   # if OPEN: gh issue close 30 --comment "Landed in #60"
   git worktree list && git worktree remove --force <#30 lane paths> && git worktree prune
   df -h .
   ```

7. Re-query:
   ```bash
   python3 <skill>/scripts/frontier.py --repo acme/ledger --issues 30,31,32,33 --json
   ```

8. Claim #33 once the slot is free and the premise check is back. Any MATERIAL WRONG findings go on the card. If the check says oversized, I file the split instead.
   ```bash
   gh issue edit 33 --repo acme/ledger --add-assignee @me
   ```

9. **Dispatch implementer for #33.** subagent_type `orchestrate-issues:implementer`, isolation `worktree`, name `impl-33`, model `opus`, run_in_background true.
   ```
   REPO:     acme/ledger
   ISSUE:    #33 — <title>
   BRANCH:   <issue-33-branch>
   BASE:     main

   --- ISSUE BODY ---
   <#33 body, verbatim>
   --- END ISSUE BODY ---

   [--- WHERE THE ISSUE IS WRONG --- <premise corrections, if any> --- END ---]
   RESERVED: migration 0021 (0020 is reserved for #31, in flight)
   [FENCE:   <#33's region> / <#31's or #32's region>, only if step 4 found shared ground]
   ```

10. Event-driven follow-ups, as each lane reports back:
    - **`fix-32-r1` returns.** Its files will be production, so I dispatch `orchestrate-issues:spec-reviewer`, worktree, `review-32-r2`, opus. VERIFY includes: "the catch-up merge preserved the semantics of the module the merged PR changed." If the verdict is CHANGES_REQUIRED, the fresh fixer is `fix-32-r2` on opus. Budget is 2 rounds, then park with `needs-human`.
    - **`impl-31` opens its PR.** I dispatch `orchestrate-issues:spec-reviewer`, worktree, `review-31-r1`, opus. VERIFY: "migration is 0020, not the next free number"; "the migration applies cleanly on top of 0019"; and the implementer's own claims. If #60 changed code #31 calls, a `rebaser` (`rebase-31`, sonnet) runs first.
    - **Merge order flips** (#33 passes before #31). Right before merging #33, I dispatch `orchestrate-issues:rebaser`, worktree, `rebase-33`, sonnet, with `RENUMBER: migrations/0021_x.sql -> 0020 (#31 not yet merged)`. Alternatively #33 keeps 0021, if the runner tolerates gaps. Either way it happens once, and a mechanical renumber needs no re-review.
    - **Before each later merge.** Run `gh pr update-branch` once, watch CI in the background, then merge with `--squash --delete-branch`. Verify the issue closed, prune worktrees, re-query.

No questions to ask: the contract covers every decision here. The only thing I'd surface in status is PR #60's file check, if it shows CI or release config or an unexpected migration.