# CLAUDE.md

npm workspaces monorepo. Orchestrated by **make**, not npm scripts — root `package.json` has no `scripts` field (`package.json:1-13`). Node `>=20.6.0` (`package.json:6-8`). Workspaces: `packages/*`, `services/*` (`package.json:9-12`).

## Commands

| Target | What it runs | Notes |
|--------|-------------|-------|
| `make setup` | `npm install` | once after checkout (`Makefile:4-5`) |
| `make migrate` | `node scripts/migrate.js` | writes `.taskflow-state.json` (`Makefile:8-9`) |
| `make dev` | api + worker | depends on `api worker` targets (`Makefile:12`) |
| `make api` | `node services/api/server.js &` | backgrounds (`Makefile:14-15`) |
| `make worker` | `node services/worker/worker.js &` | backgrounds (`Makefile:17-18`) |
| `make test` | `node --test packages/*/test/` | only `@taskflow/shared` has tests (`Makefile:21`) |
| `make lint` | `node scripts/lint.js` | parse-check only, not eslint (`scripts/lint.js:1-2`) |
| `make clean` | `rm -f .taskflow-state.json` | (`Makefile:28-29`) |

## Required ordering

`make setup` → `make migrate` → `make dev` / `make api` / `make worker`

## Gotchas

| Exit | Service | Condition | Source |
|------|---------|-----------|--------|
| 3 | api | `.taskflow-state.json` absent | `server.js:12-15` |
| 1 | api | `DATABASE_URL` unset | `server.js:16-19` |
| 3 | worker | `.taskflow-state.json` absent | `worker.js:10-13` |
| 4 | worker | state schema ≠ 3 (stale migration) | `worker.js:17-20` |

`make migrate` stamps schema 3 (`scripts/migrate.js:8`). `make dev`, `make api`, `make worker` all background with `&` — they return immediately (`Makefile:14-18`).

## Architecture

- `services/api/server.js` — HTTP API. Endpoints: `GET /health`, `POST /tasks`. Tasks in-memory, not persisted (`server.js:24-56`).
- `services/worker/worker.js` — polls `.taskflow-state.json` on interval (`worker.js:22-26`).
- `packages/shared/index.js` — exports `makeId`, `validateTask`, `normalizePriority`; consumed by both services.
- `scripts/migrate.js` — writes `.taskflow-state.json`.
- `scripts/lint.js` — parse-check only.

## Env

Copy `.env.example` → `.env`. `DATABASE_URL` is required (api exits 1 without it).

## Not yet documented

- Per-endpoint API reference: read `services/api/server.js:24-56`.
- Shared helper signatures: read `packages/shared/index.js`.
- No operational runbooks exist.
