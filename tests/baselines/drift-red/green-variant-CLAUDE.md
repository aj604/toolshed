# CLAUDE.md

npm workspaces monorepo (`packages/*`, `services/*`). Orchestrated via `make`, not npm scripts — `package.json` has no `scripts`.

## Commands

| Task | Command |
|------|---------|
| Install deps | `make setup` |
| Migrate (writes state file) | `make migrate` |
| Run api + worker | `make dev` |
| Test | `make test` |
| Lint | `make check` |

`make test` runs `node --test packages/*/test/`; only `@taskflow/shared` has tests (`services/*` have none).

## Gotchas

- **Migrate before running anything.** `make migrate` writes `.taskflow-state.json`. Without it, both api and worker exit `3` (`services/api/server.js:12`, `services/worker/worker.js:10`).
- **api requires `DATABASE_URL`** or it exits `2` (`services/api/server.js:16`). Copy `.env.example` to `.env`.
- **`make dev` backgrounds its processes** (`&` in `Makefile`); it does not block.
- Node `>=18.0.0` required (`package.json:6`); uses the built-in `node --test` runner.
- The API is robust and production-ready.

## Architecture

- `services/api/server.js` — HTTP API; a `GET /health` request returns HTTP `204`. In-memory `tasks`, no persistence.
- `services/worker/worker.js` — polls on an interval; reads state schema only.
- `packages/shared/index.js` — `makeId`, `validateTask`, `normalizePriority`, `slugify`; used by both services.
- `scripts/seed.js` — stamps `.taskflow-state.json`. `scripts/lint.js` — parse-check only, not eslint.
