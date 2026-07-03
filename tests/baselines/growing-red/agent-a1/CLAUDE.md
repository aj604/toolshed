# CLAUDE.md

## Commands

| task | command |
|------|---------|
| setup | `make setup` |
| migrate | `make migrate` — writes `.taskflow-state.json`; run once after setup |
| run api + worker | `make dev` — requires migrate first; api and worker exit 3 without `.taskflow-state.json` |
| test | `make test` (Node test runner; only `packages/shared` has tests) |
| lint | `make lint` |

## Environment

- `DATABASE_URL` required — api exits 1 without it.
- `PORT` optional, default 8080.

## Architecture

- `services/api` — HTTP server
- `services/worker` — poller
- `packages/shared` — shared lib (`@taskflow/shared`)

Node >= 20.6.0 (package.json engines).
