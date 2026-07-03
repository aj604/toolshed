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

Node >= 20.6.0 (package.json engines).
