# Doc scope record
<!-- format: doc-lifecycle growing-docs -->

## Deferred
- CLAUDE.md gotcha: worker exits 4 when `.taskflow-state.json` schema != 3 (services/worker/worker.js:18-20) — promote when: anyone hits worker exit 4, or a schema bump lands in scripts/migrate.js
- runbook for api/worker startup failures — promote when: a startup failure occurs in a deployed/on-call context, not first-time local setup

## Done
- 2026-07-03 README Setup step + CLAUDE.md migrate row (`make migrate` between setup and dev; api/worker exit 3 without `.taskflow-state.json`) ← second new teammate in one week (Priya Mon, Marcus Thu) hit "api refuses to start, exit 3" on first run and lost an hour each
