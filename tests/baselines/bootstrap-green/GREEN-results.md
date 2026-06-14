# GREEN + REFACTOR results — bootstrapping-docs (2026-06-14)

3 agents WITH the skill (2 normal + 1 pressure). Graded vs RED-findings.md.

## GREEN (read+follow skill)

| RED failure | green agent1 | green agent2 |
|-------------|--------------|--------------|
| Completeness-chasing | FIXED — minimal set; API catalog omitted on purpose | FIXED — minimal set |
| No leverage-ordering / stop | FIXED — CLAUDE.md first + "Not yet documented" | FIXED — AGENTS.md first + deferred note |
| Inferable bloat (API/sigs/trees) | FIXED — cut, replaced with pointers | FIXED — README points to AGENTS.md, no dup |
| (quality via writing-docs) | real curl output, file:line anchors | found state-check-before-DB-check nuance |

## REFACTOR pressure test (skill present + pushed toward completeness)

Prompt: "Leadership judges by comprehensiveness — be exhaustive, document the full
API, all helpers, directory tree, conventions." Direct conflict with the skill.

Result — bulletproof signature:
- Refused to chase completeness; cited the STOP list and minimal-set target.
- Produced a tight CLAUDE.md + README skeleton with a "Not yet documented" note.
- Surfaced an EXTRA high-leverage fact under pressure (`WORKER_INTERVAL_MS` exists in
  code but is missing from `.env.example`).
- Anchored gotchas to file:line; only example output was real (captured by running).
- Articulated the conflict and its resolution. No new rationalizations.

## Quantitative

- Doc bloat: ~857 words/agent (RED) → ~407 words/agent (GREEN), ~53% reduction.
- No agent produced a separate `docs/api.md` (an RED agent did).
- All high-leverage facts retained; deferred notes + anchors + real output added.

## Verdict

Skill fixes 100% of observed baseline failures and holds under direct
completeness pressure. Deployed to ~/.claude/skills/bootstrapping-docs.
