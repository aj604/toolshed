# orchestrate-issues: why runs "go forever" (19 runs, 2026-09-28 → 2026-10-18)

Clean lane = 1-2h (impl ~38m, review ~12m, fix ~15m, rebase ~10m, PASS→merge ~11m).
Wall clock is dominated by things outside the lane:

1. Blocking AskUserQuestion mid-run — 52-62% of wall time in the two runs measured;
   all lanes finished and idle behind it. ~75 asks total; user picked "(Recommended)"
   ~90% of the time; exceptions granted MORE autonomy. ~25 were split approvals,
   ~7 fix-round extensions (all approved). Split filing took 1-6 min once approved.
2. Infrastructure stalls (10-17 run: ~9.5h of 28h) — disk full from per-worktree
   Rust target/ dirs (72 worktrees), orphaned test servers, API rate limit from CI
   polling, Actions budget exhausted. Foreground `gh pr checks --watch` blocked 140m.
3. Review/fix churn — round-1 pass ~30-55%. Of blocking findings: 27 real defects,
   29 unmet criteria, 31 meaningful test gaps, 25 nits/stale docs (~15% of rounds
   were whole cycles for nits only). Later rounds drip-feed siblings round 1 missed
   (factory#292: 7 rounds). Fixers add untested lines -> next test-gap round.
   193/214 CR comments cite surviving mutants; implementers never self-mutate.
4. Rebase churn — 22/34 rebases in 10-17 were migration renumbering on a shared
   branch; ~8 rebases after PASS; rebases forced re-reviews.
5. Notification noise — 56% of wake-ups were agents' own backgrounded tests.
6. Scope growth — 33 -> 42+ nodes mid-run; reviewers raise owner questions in 60% of comments.

Premise checks: valuable (WRONG claims in ~23/77, size verdict drove real splits); noise
is location-only PARTIALs and borderline "oversized".

Analysis scripts: analysis/*.py, orcan/, oa/, rv/. Note: some transcripts repeat history;
dedupe by uuid before counting (scan.py/roles.py do NOT).
