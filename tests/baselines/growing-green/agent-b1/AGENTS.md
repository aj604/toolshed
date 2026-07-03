# AGENTS.md

## Commands

| Task | Command |
|------|---------|
| Install deps (once) | `make setup` |
| Create state file (before dev/api/worker) | `make migrate` |
| Run api + worker | `DATABASE_URL=<url> make dev` |
| Test | `make test` (not `npm test` — no root script) |
| Lint | `make lint` |
| Remove state file | `make clean` |

## Gotchas

- `make migrate` must run before `make dev` / `api` / `worker`: both processes exit 3 with
  `missing .taskflow-state.json` otherwise (`services/api/server.js:14`,
  `services/worker/worker.js:13`).
- api exits 1 unless `DATABASE_URL` is set in the environment (`services/api/server.js:18`).
  **`.env` is not auto-loaded** despite `.env.example` saying "the api reads these at
  startup" — nothing loads it (no dotenv dep, no `--env-file` in the Makefile). Export vars,
  prefix the make command, or run `node --env-file=.env services/api/server.js` yourself.
- Worker exits 4 on any state-file schema other than 3 (`services/worker/worker.js:20`);
  re-run `make migrate` after `make clean` or a stale checkout.
- `make test` needs neither migrate nor `DATABASE_URL`; only `packages/shared` has tests.
- Node >= 20.6.0 (`package.json` engines).
- Optional env: `PORT` (api, default 8080, `services/api/server.js:21`),
  `WORKER_INTERVAL_MS` (worker, default 5000, `services/worker/worker.js:25`).

## Architecture (pointers)

- `services/api/server.js` — HTTP API (`/health`, `POST /tasks`), in-memory task list.
- `services/worker/worker.js` — poller over `.taskflow-state.json`.
- `packages/shared/index.js` — task contract (`validateTask`, `normalizePriority`, `makeId`)
  used by both services.

Doc scope decisions: `docs/doc-scope.md`.
