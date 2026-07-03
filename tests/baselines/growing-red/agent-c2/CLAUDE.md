# CLAUDE.md

## Commands

| task | command |
|------|---------|
| setup | `make setup` |
| run api + worker | `make dev` |
| test | `make test` (Node test runner; only `packages/shared` has tests) |
| lint | `make lint` |

## Environment

- `DATABASE_URL` required — api exits 1 without it.
- `PORT` optional, default 8080.

## Architecture

- `services/api` — HTTP server
- `services/worker` — poller
- `packages/shared` — shared lib (`@taskflow/shared`)

No api→worker hand-off exists: api holds tasks in a per-process array (`services/api/server.js:22`), worker reads tasks only from `.taskflow-state.json` at boot and its poll loop is a stub (`services/worker/worker.js:28`).

Node >= 20.6.0 (package.json engines).
