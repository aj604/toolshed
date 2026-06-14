# AGENTS.md

npm workspaces monorepo. Tasks are driven through the `Makefile`, not npm scripts (there are none).

## Commands

| Task | Command |
|------|---------|
| Install deps | `make setup` |
| Migrate (required before run) | `make migrate` |
| Run api + worker | `make dev` |
| Run api only | `make api` |
| Run worker only | `make worker` |
| Test | `make test` (Node test runner) |
| Lint | `make lint` |
| Reset state | `make clean` |

## Gotchas

- **Migrate before run.** `make migrate` writes `.taskflow-state.json`; api and worker both
  exit `3` without it (`services/api/server.js:12`, `services/worker/worker.js:10`).
- **Worker needs schema 3.** Worker exits `4` if the state file's schema is not `3`
  (`services/worker/worker.js:17`). `make clean` + `make migrate` re-stamps it
  (`scripts/migrate.js:8`).
- **api requires `DATABASE_URL`,** exits `1` if unset (`services/api/server.js:16`). The
  missing-state check runs first, so fix state before assuming a DB problem. Copy
  `.env.example` to `.env`.
- **`make dev` / `make api` / `make worker` background the processes** (`&` in `Makefile:15,18`);
  they do not block. Test is the only workspace target with coverage today — only
  `@taskflow/shared` has tests (`Makefile:21`).

## Architecture

- `services/api` — HTTP API (`services/api/server.js`)
- `services/worker` — background poller (`services/worker/worker.js`)
- `packages/shared` — `@taskflow/shared`, helpers used by both services (`packages/shared/index.js`)
- `scripts/` — `migrate.js`, `lint.js`

## Conventions

- Node `>=20.6.0` (`package.json:7`), ESM only.

## Not yet documented
- Per-endpoint API reference (read `services/api/server.js` — `/health`, `POST /tasks`).
- Operational runbooks (no incident procedures exist yet).
