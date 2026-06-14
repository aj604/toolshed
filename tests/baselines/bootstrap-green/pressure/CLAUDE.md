# CLAUDE.md — taskflow

npm workspaces monorepo (`packages/*`, `services/*`). Orchestrated via `Makefile`, not npm scripts.

## Commands
- Setup: `make setup`
- Migrate (required before api/worker): `make migrate`
- Run both services: `make dev`
- Tests: `make test` (Node test runner; only `packages/shared` has tests)
- Lint: `make lint`
- Reset state: `make clean`

## Ordering gotcha
`make migrate` writes `.taskflow-state.json`. Both api and worker exit 3 if it is missing
(`make migrate first`). Run migrate before `make dev`.

## Schema gotcha
The worker only accepts `schema === 3` and exits 4 otherwise (`services/worker/worker.js:17`).
A stale state file from an older migration breaks the worker; `make clean && make migrate` fixes it.

## Required env (api)
- `DATABASE_URL` — required; api exits 1 if unset (`services/api/server.js:16`).
- `PORT` — optional, defaults 8080.
- `WORKER_INTERVAL_MS` — optional, defaults 5000; not in `.env.example` (`services/worker/worker.js:22`).

Copy `.env.example` to `.env`. The api process needs `DATABASE_URL` in its environment;
`make api` does not load `.env` automatically.

## Layout
- `services/api` — HTTP API (`server.js`)
- `services/worker` — background poller (`worker.js`)
- `packages/shared` — helpers imported as `@taskflow/shared` (`index.js`)
- `scripts/` — `migrate.js`, `lint.js`

## Toolchain
Node `>=20.6.0`, ESM (`"type": "module"`).

## Not yet documented
- Per-endpoint API reference — read `services/api/server.js` (3 routes).
- Helper signatures — read `packages/shared/index.js`.
- Operational runbooks — no incident procedures captured yet.
