# Doc scope record
<!-- format: doc-lifecycle growing-docs -->

## Deferred
- CLAUDE.md gotcha: worker exits 4 on state schema mismatch (`services/worker/worker.js:18-20`, needs schema 3) — promote when: anyone hits exit 4, or the schema version changes
- runbook: none exist — promote when: first incident needing one

## Done
- 2026-07-03 README Setup (added `make migrate` step + exit-3 note) and CLAUDE.md migrate command row ← second new teammate in one week (Priya Mon, Marcus Thu) hit api exit 3 from an unmigrated checkout and lost an hour each
