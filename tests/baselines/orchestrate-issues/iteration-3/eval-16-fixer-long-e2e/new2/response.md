I'd verify the fix locally, commit it, start the 35-minute e2e suite in the background, and end my turn. Nothing gets pushed or posted until e2e passes.

1. **Bash**, `command: "cd /work/fix-31 && git status --porcelain && git diff --stat"`, `timeout: 60000`, `run_in_background: false`
   - Reason: confirm the diff is only the one-line fix plus the new test, and get the test file's exact path.
   - Expect: `M src/auth/logout.ts` and one new test file (assumed below to be `src/auth/logout.test.ts`).

2. **Bash**, `command: "cd /work/fix-31 && git stash push -- src/auth/logout.ts && (npm run test:unit -- auth 2>&1 | tail -40); git stash pop && git diff --stat src/auth/logout.ts"`, `timeout: 600000`, `run_in_background: false`
   - Reason: mutation check. With the fix removed, the new test must fail. Then the fix is put back and I confirm it's there.
   - Expect: the refresh-token cookie test fails, the stash pop succeeds, and `logout.ts` shows its one changed line again.

3. **Bash**, `command: "cd /work/fix-31 && npm run test:unit 2>&1 | tail -40"`, `timeout: 600000`, `run_in_background: false`
   - Reason: the whole unit suite has to pass, not just the `auth` tests.
   - Expect: all tests pass.

4. **Bash**, `command: "cd /work/fix-31 && git add src/auth/logout.ts src/auth/logout.test.ts && git commit -m 'fix(auth): clear refresh-token cookie on logout (#31)'"`, `timeout: 60000`, `run_in_background: false`
   - Reason: commit locally so e2e runs against exactly what will be pushed. Pushing waits until e2e passes.
   - Expect: one commit, SHA noted.

5. **Bash**, `command: "cd /work/fix-31 && npm run test:e2e > /scratch/31-e2e.log 2>&1; echo \"EXIT=$?\" >> /scratch/31-e2e.log"`, `run_in_background: true`
   - Reason: CONTRIBUTING.md requires the Playwright e2e suite for any auth change. At about 35 minutes it's past the 10-minute limit, so it runs in the background with output going to the scratch log.
   - Expect: a background task ID right away.

**— END TURN —** The harness wakes me when e2e exits, so I don't poll or schedule a wakeup.

There's no final report yet, because nothing is pushed or posted. When I'm woken, I'll:
- read `tail -40 /scratch/31-e2e.log` and check the `EXIT=` line;
- if it passed, run `git push origin HEAD:issue-31-sso-logout`;
- write `/scratch/fix-31-r2.md`, starting with `## FIX — round 2`, with this line for the finding: `[src/auth/logout.ts:<line>] closed — logout now clears the refresh-token cookie; new test in src/auth/logout.test.ts goes red when the fix is reverted`;
- post it with `gh pr comment 88 --repo acme/portal --body-file /scratch/fix-31-r2.md`;
- delete `test-results/` and `playwright-report/` if git doesn't ignore them;
- return the 5-line PUSHED/CLOSED/FILES/TESTS/POSTED report.