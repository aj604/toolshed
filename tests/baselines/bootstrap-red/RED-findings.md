# RED findings — bootstrapping-docs baselines (2026-06-14)

3 baseline agents (Opus), no skills, told to "document this undocumented repo"
(taskflow: 3-component workspace). Graded vs taskflow-ANSWER-KEY.md.

## What did NOT fail (do not over-invest the skill here)

- **Gotcha discovery.** All 3 found the migrate-before-run gate (exit 3), the
  `DATABASE_URL` requirement (exit 1), and the worker schema-3 pin (exit 4).
- **Command accuracy.** All used `make test` / `make setup` / `make migrate`;
  none guessed `npm test`. They read the Makefile.
- **Architecture pointers.** All correctly mapped api / worker / shared.
- Two of three ran the code to verify.

Lesson: capable agents bootstrap the *facts* well. The skill's value is NOT
"find the gotchas" — it's scope discipline.

## What DID fail (the skill's real targets) — completeness-chasing, 3/3

### 1. Comprehensive instead of minimal-high-leverage
Every agent aimed at "well-documented" = exhaustive. They produced full HTTP API
references (routes, status codes, request-field tables, validation rules),
catalogs of every `@taskflow/shared` helper signature, convention lists
(semicolons, quote style), and directory trees mirroring the filesystem.
Most of this is inferable from code and will drift. ~700–1100 words/agent across
2 files; agent3 even created a separate `docs/api.md`.

### 2. No leverage-ordering / no stop signal
None distinguished "what an agent needs first" from "nice to have." None framed
the output as a minimal bootstrap set, and none stated what they deliberately
left out (e.g., operational runbooks = TODO). The organizing principle was
coverage, not leverage.

### 3. Inferable bloat (same failure writing-docs targets, at doc-set scale)
API route bodies, helper signatures, convention lists, full trees — all readable
from the repo in seconds, all restated into docs that now must be kept in sync.

## Implication for GREEN

bootstrapping-docs is a SCOPE/PRIORITIZATION skill, not a fact-finding one:
- Define the minimal high-leverage set and STOP: CLAUDE.md/AGENTS.md first
  (commands + gotchas + env + arch pointers), then a short README skeleton.
- Forbid cataloguing inferable detail (API route tables, helper signatures,
  convention lists, filesystem trees).
- Require an explicit "deferred / not yet documented" note instead of chasing it.
- Defer per-doc quality to writing-docs (run-or-omit output, anchored rationale).
- De-emphasize gotcha-hunting (already natural).
