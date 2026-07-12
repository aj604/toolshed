# CLAUDE.md

## Commands

| Task | Command |
|------|---------|
| install deps | `make setup` |
| run api + worker | `make dev` |
| test | `npm test` |
| lint | `make lint` |

## Gotchas

- Since 1.2.0 the state-file migration is no longer required — the api and worker
  create `.taskflow-state.json` on first start. `make migrate` is kept only for
  legacy checkouts.
- The api exits 1 unless `DB_URL` is set. `PORT` is optional, default 3000.
- Node >= 20.6.0 (`package.json` engines).

## Map

- `services/api` — HTTP server (`GET /health`, `POST /tasks`)
- `services/worker` — polls the state file (`WORKER_INTERVAL_MS`, default 5000)
- `packages/shared` — shared task helpers; the only workspace with tests
