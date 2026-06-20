# CLAUDE.md — TaskFlow

npm workspaces monorepo orchestrated with `make`, not npm scripts (root `package.json` defines no `scripts`). Workspaces: `packages/*` (shared libs), `services/*` (runnable services). Requires Node `>=20.6.0` (`package.json:7`).

## Commands (Makefile targets)

- `make setup` — `npm install` across workspaces. Run first.
- `make migrate` — writes `.taskflow-state.json` (schema 3). Run before any service.
- `make dev` — runs `api` then `worker`.
- `make api` — `node services/api/server.js &`.
- `make worker` — `node services/worker/worker.js &`.
- `make test` — `node --test packages/*/test/`. Only `@taskflow/shared` has tests; `services/*` have none.
- `make lint` — `node scripts/lint.js` (parse-check only, not eslint; `scripts/lint.js:1`).
- `make clean` — `rm -f .taskflow-state.json`.

## Startup gotchas

- **Migrate first.** Without `.taskflow-state.json`, both services exit `3` (`services/api/server.js:12`, `services/worker/worker.js:10`).
- **`DATABASE_URL` required by api.** Unset → api exits `1` (`services/api/server.js:16`). Copy `.env.example` to `.env`.
- **Worker requires state schema 3.** Any other value → worker exits `4` (`services/worker/worker.js:17`). `make migrate` stamps schema 3 (`scripts/migrate.js:8`); a stale state file from another version breaks the worker.
- **`api`/`worker` targets append `&`** (`Makefile:15`, `Makefile:18`), so they background the node process and return immediately. `make dev` runs both (`Makefile:12`).

## Architecture

- `services/api/server.js` — HTTP API. Endpoints: `GET /health`, `POST /tasks` (handlers from `services/api/server.js:24`). Holds tasks in memory (`server.js:22`); not persisted across restart. Port from `PORT`, default 8080 (`server.js:21`).
- `services/worker/worker.js` — polls on an interval (`WORKER_INTERVAL_MS`, default 5000ms; `worker.js:22`); reads state schema only.
- `packages/shared/index.js` — exports `makeId`, `validateTask`, `normalizePriority`, used by both services. Read the file for signatures.
- `scripts/migrate.js` — writes `.taskflow-state.json`. `scripts/lint.js` — counts/parse-checks `.js` files under `packages` and `services`.

## Not documented

- No per-endpoint API reference — read handlers from `services/api/server.js:24`.
- No runbooks (deployment/incident).
