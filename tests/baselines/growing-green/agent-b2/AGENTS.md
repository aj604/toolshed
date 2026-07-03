# AGENTS.md

npm workspaces (`packages/*`, `services/*`): `services/api/server.js` (HTTP API),
`services/worker/worker.js` (poller), `packages/shared/index.js` (task helpers both import),
`scripts/` (migrate, lint).

## Commands

| Task | Command |
|------|---------|
| Install deps (once) | `make setup` |
| Create state file — required before running services | `make migrate` |
| Run api + worker | `make dev` |
| Test | `make test` |
| Lint | `make lint` |
| Delete state file | `make clean` |

## Gotchas

- **Migrate before run:** api and worker exit 3 (`missing .taskflow-state.json — run \`make migrate\` first`) without `make migrate`. `make test` does NOT need migrate; only `@taskflow/shared` has tests.
- **api needs `DATABASE_URL`** in the environment or it exits 1. `.env.example` lists the vars, but nothing in the repo loads a `.env` file — export them yourself. Optional: `PORT` (default 8080), `WORKER_INTERVAL_MS` (default 5000).
- **Worker exits 4 on state `schema !== 3`** (`services/worker/worker.js:18`) — re-run `make migrate`.
- **`make dev`/`api`/`worker` background the node processes** (`&` in the Makefile); they outlive make and keep port 8080 bound until killed.

Deferred-doc decisions: `docs/doc-scope.md`.
