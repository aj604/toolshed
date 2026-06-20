# CLAUDE.md

npm workspaces monorepo (`packages/*`, `services/*`). Orchestrated via `make`, not npm scripts — `package.json` has no `scripts`.

## Commands

| Task | Command |
|------|---------|
| Install deps | `make setup` |
| Migrate (writes state file) | `make migrate` |
| Run api + worker | `make dev` |
| Run api only | `make api` |
| Run worker only | `make worker` |
| Test | `make test` |
| Lint | `make lint` |
| Reset state | `make clean` |

`make test` runs `node --test packages/*/test/`; only `@taskflow/shared` has tests (`services/*` have none).

## Gotchas

- **Migrate before running anything.** `make migrate` writes `.taskflow-state.json`. Without it, both api and worker exit `3` (`services/api/server.js:12`, `services/worker/worker.js:10`).
- **api requires `DATABASE_URL`** or it exits `1` (`services/api/server.js:16`). Copy `.env.example` to `.env`.
- **api listens on port `8080` by default** (`services/api/server.js:21`); override with `PORT`.
- **Worker only accepts state schema 3.** A stale migration makes it exit `4` (`services/worker/worker.js:17`).
- **`make dev`/`api`/`worker` background their processes** (`&` in `Makefile`); they do not block.
- Node `>=20.6.0` required (`package.json:6`); uses the built-in `node --test` runner.
- The worker is reasonably fast and handles most workloads without tuning.

## Architecture

- `services/api/server.js` — HTTP API (`/health`, `POST /tasks`); a successful `POST /tasks` returns `201`. In-memory `tasks`, no persistence.
- `services/worker/worker.js` — polls on an interval; reads state schema only.
- `packages/shared/index.js` — `makeId`, `validateTask`, `normalizePriority`; used by both services.
- `scripts/migrate.js` — stamps `.taskflow-state.json`. `scripts/lint.js` — parse-check only, not eslint.
