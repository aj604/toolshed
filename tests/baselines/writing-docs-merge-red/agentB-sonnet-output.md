# CLAUDE.md — TaskFlow

npm workspaces monorepo. Workspaces: `packages/*`, `services/*`. Root `package.json` defines no scripts; use `make` targets.

**Node requirement:** `>=20.6.0` (`package.json:6`).

## Startup sequence

```
make setup    # npm install
make migrate  # writes .taskflow-state.json (schema 3)
make dev      # starts api + worker (both backgrounded with &)
```

`make migrate` must run before `make dev`, `make api`, or `make worker`. Both services exit 3 if `.taskflow-state.json` is absent (`services/api/server.js:12`, `services/worker/worker.js:10`).

## Commands

| Target | What it runs |
|--------|-------------|
| `make setup` | `npm install` |
| `make migrate` | `node scripts/migrate.js` |
| `make dev` | `api` + `worker` targets |
| `make api` | `node services/api/server.js &` |
| `make worker` | `node services/worker/worker.js &` |
| `make test` | `node --test packages/*/test/` |
| `make lint` | `node scripts/lint.js` |
| `make clean` | `rm -f .taskflow-state.json` |

`make dev`, `make api`, and `make worker` background their processes (`Makefile:15-18`).

## Gotchas

- **`DATABASE_URL` required by api.** Missing → exit 1 (`services/api/server.js:16`). Copy `.env.example` to `.env`.
- **State schema must be 3.** Worker exits 4 if `schema !== 3` (`services/worker/worker.js:17`). A stale `.taskflow-state.json` from an older run triggers this; re-run `make migrate`.
- **Tests only exist in `@taskflow/shared`.** `make test` runs `packages/*/test/`; `services/*` have no tests (`Makefile:21` comment).

## Code map

| Path | Role |
|------|------|
| `services/api/server.js` | HTTP API. Endpoints: `GET /health`, `POST /tasks`. Tasks stored in memory; not persisted. |
| `services/worker/worker.js` | Polls `.taskflow-state.json` on an interval (default 5000 ms, `WORKER_INTERVAL_MS` overrides). |
| `packages/shared/index.js` | Exports `makeId`, `validateTask`, `normalizePriority`. Used by both services. |
| `scripts/migrate.js` | Writes `.taskflow-state.json` with `{ schema: 3 }`. |
| `scripts/lint.js` | Parse-check only (not eslint). |
