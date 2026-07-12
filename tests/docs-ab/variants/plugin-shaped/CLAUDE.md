# CLAUDE.md

## Commands

| Task | Command |
|------|---------|
| install deps | `make setup` |
| create state file (required before running) | `make migrate` |
| run api + worker | `make dev` |
| test | `make test` (`node --test packages/*/test/`) — NOT `npm test`; there is no root test script |
| lint | `make lint` |

## Gotchas

- Run order: `make setup` → `make migrate` → `make dev`. The api and worker exit 3
  ("run `make migrate` first") if `.taskflow-state.json` is absent.
- The api exits 1 unless `DATABASE_URL` is set (see `.env.example`; any value works
  locally). `PORT` is optional, default 8080.
- The worker requires state schema 3 (`services/worker/worker.js:18`) — exits 4 on any
  other schema. Re-run `make migrate` to fix.
- Node >= 20.6.0 (`package.json` engines).

## Map

- `services/api` — HTTP server (`GET /health`, `POST /tasks`)
- `services/worker` — polls the state file (`WORKER_INTERVAL_MS`, default 5000)
- `packages/shared` — shared task helpers; the only workspace with tests
