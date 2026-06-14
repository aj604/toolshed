# taskflow

A task-queue service: an HTTP API for submitting tasks and a background worker that processes them, sharing helpers via `@taskflow/shared`.

## Requirements

- Node `>=20.6.0` (`package.json:7`)
- An npm workspaces monorepo; all tasks run through the `Makefile`.

## Setup

```sh
make setup     # npm install
make migrate   # writes .taskflow-state.json (api/worker refuse to start without it)
cp .env.example .env   # set DATABASE_URL; api exits 1 if unset
make dev       # starts api and worker (backgrounded)
```

## Development

```sh
make test   # node --test across workspaces
make lint   # node scripts/lint.js
```

Verified output:

```
$ make test
# tests 3
# pass 3
# fail 0

$ make lint
lint ok: 4 files
```

## Configuration

- `DATABASE_URL` — required by the api (`.env.example:3`).
- `PORT` — optional, defaults to `8080` (`services/api/server.js:21`).
- `WORKER_INTERVAL_MS` — optional, defaults to `5000` (`services/worker/worker.js:22`).

## Layout

See `AGENTS.md` for the component map and command reference.
