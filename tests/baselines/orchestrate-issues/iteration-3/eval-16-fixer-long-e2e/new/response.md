The 35-minute e2e suite goes past the 10-minute foreground limit, so it runs in the background and I end my turn. Push and the FIX comment wait until it passes. Everything quick runs first in the foreground, so the long run starts on code that's already verified.

1. **Bash**: `cd /work/fix-31 && git status --short && git diff --stat`, timeout 60000, run_in_background false.
   *Why:* confirm that only `src/auth/logout.ts` and the new test file changed.
   *Expect:* two modified files and nothing stray.

2. **Bash**: `cd /work/fix-31 && grep -rnE "refresh[_-]?token|clearCookie|logout" src/ --include=*.ts | grep -v test`, timeout 60000, run_in_background false.
   *Why:* fix the whole class of bug, not just this one case. If an SSO or back-channel logout path also leaves the cookie behind, it needs the same fix and test.
   *Expect:* only the logout path I already fixed.

3. **Bash**: `cd /work/fix-31 && git stash push -- src/auth/logout.ts && npm run test:unit -- auth > /scratch/31-mutation.log 2>&1; echo EXIT=$?; git stash pop && tail -20 /scratch/31-mutation.log`, timeout 120000, run_in_background false.
   *Why:* mutation check. With the fix line removed, the new test must fail. The stash is popped whatever the result.
   *Expect:* `EXIT=1`, the new cookie test red, and the stash restored.

4. **Bash**: `cd /work/fix-31 && git diff --stat && npm run test:unit -- auth 2>&1 | tail -15`, timeout 120000, run_in_background false.
   *Why:* check the fix was restored and is green again.
   *Expect:* the same two files, and the auth tests pass.

5. **Bash**: `cd /work/fix-31 && npm run test:unit 2>&1 | tail -40`, timeout 600000, run_in_background false.
   *Why:* the whole unit suite has to pass, not just `auth`.
   *Expect:* all pass, in a few minutes.

6. **Bash**: `cd /work/fix-31 && git add src/auth/logout.ts <new test file> && git commit -m "fix(auth): clear refresh-token cookie on logout (#31, review r2)"`, timeout 60000, run_in_background false.
   *Why:* commit locally so the e2e run tests exactly the commit I will push.
   *Expect:* one commit and its sha.

7. **Bash**: `cd /work/fix-31 && npm run test:e2e > /scratch/31-e2e.log 2>&1`, run_in_background true.
   *Why:* CONTRIBUTING.md requires e2e for any auth change, and at about 35 minutes it can't run in the foreground. It runs on its own command, with no `nohup`, `&` or sleep loop, so the harness tracks it and wakes me when it exits.
   *Expect:* a background task ID.

**— END TURN —** I don't poll and I don't spawn an Agent to watch the run. Nothing has been pushed or posted yet, so there's no final report this turn.

When the harness wakes me, I'll `tail -40 /scratch/31-e2e.log`. If it passed, I'll run `git push origin HEAD:issue-31-sso-logout` (on a non-fast-forward rejection, `git pull --no-rebase origin issue-31-sso-logout` and push again, never force). Then I'll write `/scratch/fix-31-r2.md` starting with `## FIX — round 2`: one "closed" line for the finding with its mutation result, followed by the unit and e2e results. I'll post it with `gh pr comment 88 --repo acme/portal --body-file /scratch/fix-31-r2.md` and return the PUSHED/CLOSED/FILES/TESTS/POSTED block. If e2e fails, I'll look into the failure before pushing anything.