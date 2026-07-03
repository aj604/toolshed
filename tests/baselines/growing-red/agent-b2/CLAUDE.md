# CLAUDE.md

Node >=20.6.0 (`package.json` engines), npm workspaces (`packages/*`, `services/*`), ESM
(`"type": "module"`) throughout.

## Command surface

Root `package.json` has no `scripts` — use the **Makefile**, in this order:

1. `make setup` — `npm install`.
2. `make migrate` — writes `.taskflow-state.json` (schema 3) at repo root; deleted by
   `make clean`. Required before `make dev`/`make api`/`make worker`.
3. `make dev` — runs `make api` and `make worker`, each backgrounded with `&`
   (`Makefile`).

Other targets: `make test` runs `node --test packages/*/test/` (only `packages/shared` has a
`test/` dir); does **not** need migrate. `make lint` runs `node scripts/lint.js` — a parse/file-count
check (walks `packages/` and `services/`, counts `.js` files), not eslint.

## Env vars

Not auto-loaded — no dotenv dependency, no `--env-file` in the Makefile; `services/api/server.js`
and `services/worker/worker.js` read `process.env` directly. `.env.example` documents the shape
but you must export vars yourself, e.g. `DATABASE_URL=postgres://... make dev`.

- `DATABASE_URL` — required by the api. Unset → exits 1, stderr `api: DATABASE_URL is required`
  (`services/api/server.js`).
- `PORT` — api, default 8080.
- `WORKER_INTERVAL_MS` — worker poll interval, default 5000.

## Gotchas

- **Skipping migrate**: api and worker both check for `.taskflow-state.json` before anything
  else and exit 3 with `missing .taskflow-state.json — run `make migrate` first` if it's absent
  (`services/api/server.js`, `services/worker/worker.js`).
- **Stale/foreign state file**: worker also validates `schema === 3`; a mismatch exits 4 with
  `worker: state schema <n> unsupported (need 3)` (`services/worker/worker.js`) — `make migrate`
  always (re)stamps schema 3, so this only bites if the file was hand-edited or copied from
  elsewhere.
- **Every run target backgrounds its process** — `make api`, `make worker`, and therefore
  `make dev` all end in `&` (`Makefile`) and return immediately. For a foreground process
  (e.g. to inspect exit codes), run `node services/api/server.js` or
  `node services/worker/worker.js` directly.

## Architecture (pointers)

- `services/api/server.js` — HTTP API (routes defined inline; read the file).
- `services/worker/worker.js` — polls the state file on `WORKER_INTERVAL_MS`.
- `packages/shared/index.js` — task helpers (`makeId`, `validateTask`, `normalizePriority`)
  imported by both services as `@taskflow/shared`.
- `scripts/migrate.js` — writes the state file described above.
- `scripts/lint.js` — the parse/count check `make lint` runs.
