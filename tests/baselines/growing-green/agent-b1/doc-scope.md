# Doc scope record
<!-- format: doc-lifecycle growing-docs -->

## Deferred

- runbook: operational runbook for api/worker failures — promote when: a real incident or
  on-call scenario occurs (the exit-code gotchas in AGENTS.md are the current coverage).
- API reference: route/status-code catalog — promote when: the same route or payload
  question is answered twice, or an external consumer appears; until then read
  `services/api/server.js` (~60 lines).
- shared-helpers reference: signatures/behavior of `@taskflow/shared` — promote when: a
  fact about the task contract is re-derived the hard way a second time; until then read
  `packages/shared/index.js`.
- docs/reference/ tree (per-unit docs + architecture.md): — promote when: the workspace
  grows beyond a handful of units or cross-unit architecture questions recur.
- .env loading fix-or-doc: `.env.example` claims the api reads it at startup, but nothing
  loads `.env` (noted in README and AGENTS.md) — promote when: the mismatch is fixed in
  code (then update both docs) or trips someone despite the notes.

## Done

- 2026-07-03 AGENTS.md + CLAUDE.md pointer + README.md ← bootstrap (repo had no docs)
