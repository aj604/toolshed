The e2e suite takes about 35 minutes, and a foreground Bash call is capped at 10 minutes. So I'd split it into six Playwright shards of about 6 minutes each and run them one after another in the foreground. That way nothing runs in the background and nothing can be left running when I exit. Pushing first and letting CI run e2e doesn't count: "done" means the suite passed before the push.

1. **Bash**: check that the new test fails without the fix, then restore the fix.
   - `command`: `cd /work/fix-31 && git stash push -- src/auth/logout.ts && (npm run test:unit -- auth; echo "EXIT=$?"); git stash pop && git diff --stat`
   - `timeout`: 120000
   - `run_in_background`: false
   - I expect the new test `clears refresh-token cookie on logout` to fail (EXIT=1), the stash pop to bring the fix back, and the diff stat to show `logout.ts` modified again.

2. **Bash**: check the rest of the finding's class. The cookie might also be left behind on other logout paths, such as the SSO callback, IdP-initiated logout or session expiry.
   - `command`: `cd /work/fix-31 && grep -rn -i "refresh" src/auth --include=*.ts | grep -v test`
   - `timeout`: 30000
   - `run_in_background`: false
   - I expect `logout.ts` to be the only place that clears the session. If another path appears, I fix and test it too.

3. **Bash**: confirm that `test:e2e` runs Playwright and that it accepts extra arguments, so sharding works.
   - `command`: `cd /work/fix-31 && npm pkg get scripts && npx playwright test --list | tail -1`
   - `timeout`: 60000
   - `run_in_background`: false
   - I expect `"test:e2e": "playwright test"` and a total test count.

4. **Bash**: run the full unit suite, not just `auth`, plus lint and typecheck if those scripts exist.
   - `command`: `cd /work/fix-31 && npm run test:unit && npm run lint && npm run typecheck`
   - `timeout`: 600000
   - `run_in_background`: false
   - I expect everything to pass.

5. to 10. **Bash**: run e2e shards 1/6 through 6/6, in order, one call each. They run sequentially because they share the web server and port.
   - `command`: `cd /work/fix-31 && npm run test:e2e -- --shard=N/6`
   - `timeout`: 600000
   - `run_in_background`: false
   - I expect each shard to pass. If a shard fails, I stop and diagnose it. If a shard hits the timeout, I split it again with `--shard=` on a larger total.

11. **Bash**: commit the fix and push it to the PR branch.
   - `command`: `cd /work/fix-31 && git add src/auth/logout.ts src/auth/__tests__/logout.test.ts && git commit -m "fix(auth): clear refresh-token cookie on logout (#31, review r2)" && git push origin HEAD:issue-31-sso-logout && git rev-parse --short HEAD`
   - `timeout`: 120000
   - `run_in_background`: false
   - I expect a fast-forward push and the short sha. If the push is rejected, I run `git pull --no-rebase origin issue-31-sso-logout` and push again. I never force-push.

12. **Write**: write the FIX comment to the shared scratch directory.
   - `file_path`: `/scratch/fix-31-r2.md`
   - `content`:
     ```
     ## FIX — round 2
     [src/auth/logout.ts:<line cited in review>] closed — logout now expires the refresh-token cookie (Max-Age=0, same Path/Domain as when it was set); new unit test `clears refresh-token cookie on logout` asserts the expiring Set-Cookie header. Mutation: reverted the line in logout.ts → test red; restored → green. Checked the other logout paths under src/auth (grep "refresh"): none clear the session separately, so nothing else to fix.

     Ran: `npm run test:unit` (full) — pass; lint + typecheck — pass; `npm run test:e2e` (CONTRIBUTING requires it for auth changes) as `--shard=1..6/6` in sequence — all pass.
     ```

13. **Bash**: post the comment on the PR.
   - `command`: `gh pr comment 88 --repo acme/portal --body-file /scratch/fix-31-r2.md`
   - `timeout`: 60000
   - `run_in_background`: false
   - I expect the comment URL back.

14. **Bash**: make sure no dev servers or browsers I started are still running.
   - `command`: `pgrep -fl "playwright|chromium|node .*dev" || echo "none running"`
   - `timeout`: 15000
   - `run_in_background`: false
   - I expect `none running`.

**End turn**, with this report:

```
PUSHED:  <sha> to issue-31-sso-logout
CLOSED:  1 of 1 BLOCKING findings   (0 disputed)
FILES:   production
TESTS:   pass — full unit suite, lint, typecheck, and the full Playwright e2e suite (6 shards, run in order in the foreground)
POSTED:  https://github.com/acme/portal/pull/88#issuecomment-<id>
```