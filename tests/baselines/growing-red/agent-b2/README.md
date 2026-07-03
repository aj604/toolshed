# taskflow

Small task service: an HTTP API (`services/api/server.js`) that accepts tasks over HTTP, plus a background worker (`services/worker/worker.js`) that polls local state. Both use helpers from `packages/shared`. Private npm-workspaces monorepo, ESM, Node >= 20.6.0 (`package.json` `engines`).

## Setup

```sh
make setup     # npm install (once)
make migrate   # writes .taskflow-state.json — api and worker refuse to start without it (exit 3)
```

## Run

```sh
DATABASE_URL=postgres://localhost:5432/taskflow make dev   # starts api and worker
```

The api logs `api listening on :8080`. Health check:

```sh
curl -s localhost:8080/health
```

```
{"ok":true,"tasks":0}
```

## Environment

Copy `.env.example` to `.env` for reference, but `.env` is **not auto-loaded** — set variables in the environment (as in the `make dev` line above).

- `DATABASE_URL` — required by the api; it exits 1 if unset.
- `PORT` — optional, default `8080`.
- `WORKER_INTERVAL_MS` — optional, default `5000` (worker poll interval).

## Test and lint

```sh
make test   # node --test packages/*/test/ — only @taskflow/shared has tests today; no migrate needed
make lint   # scripts/lint.js
```

`make clean` removes `.taskflow-state.json`.

## Code

- API routes: `services/api/server.js`
- Worker loop: `services/worker/worker.js`
- Shared helpers: `packages/shared/index.js`
- Orchestration: `Makefile`
