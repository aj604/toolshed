# Doc scope record
<!-- format: doc-lifecycle growing-docs -->

## Deferred
- README/CLAUDE.md gotcha: worker exits 4 on state schema mismatch (`services/worker/worker.js` requires schema 3) — promote when: someone hits exit 4 after a migration/schema change

## Done
- 2026-07-03 README exit-3 symptom note (+ `make migrate` step restored to Setup and CLAUDE.md run row via drift sync) ← second newcomer in one week (Priya Mon, Marcus Wed) hit "api refuses to start" exit 3 and lost ~1h each until told `make migrate` in chat
