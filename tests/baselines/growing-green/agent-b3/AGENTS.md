# AGENTS.md

npm-workspaces monorepo, Node >= 20.6.0 (`package.json` engines). Units: `services/api`
(HTTP API), `services/worker` (polling worker), `packages/shared` (task helpers both import).

## Commands

| Task | Command |
|------|---------|
| Install deps | `make setup` |
| Migrate (required before run) | `make migrate` — writes `.taskflow-state.json` |
| Run api + worker | `make dev` (env must be exported first; see gotchas) |
| Test | `make test` (`node --test packages/*/test/`; only `@taskflow/shared` has tests) |
| Lint | `make lint` |
| Reset state | `make clean` — deletes `.taskflow-state.json`; re-run `make migrate` after |

## Gotchas

- **Order: `make setup` → `make migrate` → `make dev`.** api and worker exit 3
  (`missing .taskflow-state.json — run \`make migrate\` first`) if migrate hasn't run.
- **`.env` is never auto-loaded.** `.env.example`'s comment notwithstanding, the api reads
  `process.env` only (`services/api/server.js`) — copying `.env.example` to `.env` alone
  still exits 1. Export the vars, or run `node --env-file=.env services/api/server.js`.
- api exits 1 if `DATABASE_URL` is unset. `PORT` optional, default 8080.
- worker exits 4 unless the state file has `schema: 3` (`services/worker/worker.js`).
  `WORKER_INTERVAL_MS` optional, default 5000ms. The worker needs no `.env` vars.

Doc scope record: `docs/doc-scope.md`.
