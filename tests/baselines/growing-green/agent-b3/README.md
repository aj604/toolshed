# taskflow

Node workspace with an HTTP task API (`services/api`), a polling background worker
(`services/worker`), and shared task-validation helpers (`packages/shared`) used by both.

## Requirements

- Node >= 20.6.0 (`package.json` engines)

## Setup

```sh
make setup      # npm install
make migrate
# migrated: wrote .taskflow-state.json (schema 3)
```

`make migrate` must run before starting anything: the api and worker exit 3 without
`.taskflow-state.json`.

## Run

The api requires `DATABASE_URL` (it exits 1 otherwise). Copying `.env.example` to `.env`
is not enough on its own — nothing auto-loads it. Either export the variables, or:

```sh
cp .env.example .env
node --env-file=.env services/api/server.js
# api listening on :8080
curl -s http://localhost:8080/health
# {"ok":true,"tasks":0}
```

With the env exported, `make dev` starts both processes (the worker needs no env vars):

```sh
DATABASE_URL=postgres://localhost:5432/taskflow make dev
# worker: started, polling every 5000ms (0 pending)
# api listening on :8080
```

## Test / Lint

```sh
make test    # node --test packages/*/test/ — only @taskflow/shared has tests
# pass 3
make lint
# lint ok: 4 files
```

## Configuration

`.env.example` documents `DATABASE_URL` (required by the api) and `PORT` (optional,
default 8080). The worker's poll interval is `WORKER_INTERVAL_MS` (optional, default
5000ms — `services/worker/worker.js`).

Startup exit codes: 1 = `DATABASE_URL` unset (api); 3 = `.taskflow-state.json` missing
(api and worker — run `make migrate`); 4 = state schema is not 3 (worker).
