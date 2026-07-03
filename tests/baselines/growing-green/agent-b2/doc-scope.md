# Doc scope record
<!-- format: doc-lifecycle growing-docs -->

## Deferred

- runbook: operating api/worker (start-gate exit codes 1/3/4, stray backgrounded processes from `make dev`, state-file recovery) — promote when: a real incident or on-call question needs it.
- API endpoint reference: routes, status codes, request shapes — promote when: an external consumer appears, or the contract is re-derived the hard way a second time; until then read `services/api/server.js`.
- shared-helpers reference (`makeId`/`validateTask`/`normalizePriority`) — promote when: a helper's behavior is re-derived a second time; until then read `packages/shared/index.js`.
- docs/reference/ tree (architecture.md + per-unit overviews) — promote when: the repo grows beyond api+worker+shared or cross-unit questions recur.
- CONTRIBUTING / license — promote when: the repo is published or takes external contributors.

## Done
