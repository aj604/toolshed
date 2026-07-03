# CLAUDE.md

taskflow: npm workspaces (`packages/*`, `services/*`), all ESM (`"type": "module"`), Node
>=20.6.0 (`package.json:5-8`). Two services (`services/api`, `services/worker`) share
validation/id helpers from `packages/shared` (`README.md:3-5`).

## Orchestration is the Makefile, not npm scripts

`package.json` has no `scripts` block — use `Makefile` targets directly (`Makefile:1-29`):

| Target | Does |
|---|---|
| `make setup` | `npm install` |
| `make migrate` | writes `.taskflow-state.json` (schema 3) — **required before `dev`/`api`/`worker`** |
| `make dev` | runs `api` + `worker` together, both backgrounded (`&` in the recipe) |
| `make test` | `node --test packages/*/test/` — does **not** need migrate; only `@taskflow/shared` has tests |
| `make lint` | `node scripts/lint.js` (custom: just checks every workspace `.js` file parses) |
| `make clean` | deletes `.taskflow-state.json` |

Required order for anything that runs the services: `make setup` → `make migrate` → `make dev`
(or `make api` / `make worker` individually). `make test` and `make lint` skip migrate.

## Setup gotchas (symptom → cause)

- **Both `services/api/server.js` and `services/worker/worker.js` exit 3** with
  `missing .taskflow-state.json — run `make migrate` first` if that file is absent
  (`services/api/server.js:12-15`, `services/worker/worker.js:11-14`; confirmed by running both
  with the file removed). Run `make migrate` (writes `{migratedAt, schema: 3}`,
  `scripts/migrate.js:8`).
- **Worker additionally exits 4** if the state file's `schema` field isn't `3`
  (`services/worker/worker.js:17-21`; confirmed by running with `schema: 2`) — a stale/hand-edited
  state file breaks the worker even though it exists.
- **`make clean` deletes the state file** (`Makefile:29`) — re-run `make migrate` after.
- **api exits 1** if `DATABASE_URL` is unset (`services/api/server.js:16-19`; confirmed by running
  without it). `.env.example` documents `DATABASE_URL` (required, no default) and `PORT` (optional,
  default `8080`) (`.env.example:1-5`, `services/api/server.js:21`). Copy it: `cp .env.example .env`.
- Worker reads `WORKER_INTERVAL_MS` (optional, default `5000`ms poll interval)
  (`services/worker/worker.js:25`) — not in `.env.example`.

## Architecture pointers

- `services/api/server.js` — HTTP API (`/health`, `POST /tasks`); reads `packages/shared` for
  `makeId`/`validateTask`/`normalizePriority`.
- `services/worker/worker.js` — polls `.taskflow-state.json` on `WORKER_INTERVAL_MS`; loop body is
  a stub (`// process due tasks here`, `services/worker/worker.js:28`).
- `packages/shared/index.js` — validation/id helpers, the only workspace with tests
  (`packages/shared/test/`).

Don't re-derive route/function signatures here — read the files above; they're short.
