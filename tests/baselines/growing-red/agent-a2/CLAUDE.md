# CLAUDE.md

## Commands

| task | command |
|------|---------|
| setup | `make setup` |
| migrate (writes `.taskflow-state.json`) | `make migrate` |
| run api + worker | `make dev` — requires `make migrate` first; fails fast (exit 3) if `.taskflow-state.json` is missing |
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
