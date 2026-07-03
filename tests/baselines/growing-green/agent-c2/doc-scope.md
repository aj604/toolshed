# Doc scope record
<!-- format: doc-lifecycle growing-docs -->

## Deferred
- CLAUDE.md gotcha: the api→worker handoff does not exist yet (api holds tasks in memory, `services/api/server.js:22`; worker poll body is a stub, `services/worker/worker.js:28`) — promote when: an agent or contributor ships work assuming POSTed tasks reach the worker
- docs/reference/ tree: per-unit reference docs — promote when: a fourth unit lands or cross-unit questions recur beyond what the walkthrough answers

## Done
- 2026-07-03 docs/life-of-a-task.md ← second new contributor this month asked for an end-to-end task-flow walkthrough (onboarding pain)
