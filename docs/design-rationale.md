# Design rationale — deliberate absences and constraints

> As of 2026-07-04 (items anchored per entry; retired-artifact text retrievable via `git show <sha>:<path>`)

Durable rationale for the doc-lifecycle suite, recovered from retired planning
artifacts and extracted from distillations. Each entry is a decision, constraint, or
deliberate absence a future maintainer might otherwise wrongly "fix", with a
provenance anchor to the text that decided it.

## Suite contract

- **Rationale claims are relevance-checked, never truth-checked.** The drift engine
  checks a marked+anchored rationale claim's anchor — does the decision still apply,
  is the code it references still there — never the claim's truth. Automation never
  silently rewrites rationale.
  (docs/plans/2026-06-09-documentation-skills-suite-design.md @ 09f4300, Decision 2)

## Sync and bloat automation

- **The bloat lanes have no blast-radius cap, deliberately.** The drift nightly caps
  blast radius (past the cap, the fix PR degrades to a labeled issue); the bloat
  lanes are detect-only-then-review — a large proposal is reviewed as a diff, never
  silently applied — so a cap adds nothing. One can be added if PRs prove unwieldy.
  (docs/plans/2026-07-03-doc-bloat-nightly-design.md @ 09f4300, Non-goals / deferred)
