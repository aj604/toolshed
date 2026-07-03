# taskflow

A small task-management workspace: an HTTP API that accepts tasks and a polling background
worker, sharing one task contract (`@taskflow/shared`). Three npm workspaces
(`services/api`, `services/worker`, `packages/shared`) orchestrated by a Makefile.

## Requirements

- Node >= 20.6.0 (`package.json` engines)

## Setup and run

```sh
make setup      # npm install
make migrate    # required first: api and worker refuse to start without it
# migrated: wrote .taskflow-state.json (schema 3)
DATABASE_URL=postgres://localhost:5432/taskflow make dev
# worker: started, polling every 5000ms (0 pending)
# api listening on :8080
```

The api requires `DATABASE_URL` and exits 1 without it. Note: despite the comment in
`.env.example`, a `.env` file is **not** loaded automatically (no dotenv, no `--env-file`
in the Makefile) — set variables in the environment as above, or run
`node --env-file=.env services/api/server.js` directly.

```sh
curl -s localhost:8080/health
# {"ok":true,"tasks":0}
curl -s -X POST localhost:8080/tasks -H 'content-type: application/json' -d '{"title":"demo"}'
# {"id":"task_1","title":"demo","priority":"med"}
```

Routes and validation rules live in `services/api/server.js` and
`packages/shared/index.js`.

## Configuration

Environment variables only (see `.env.example` for the shape):

- `DATABASE_URL` — required by the api.
- `PORT` — api port, default 8080.
- `WORKER_INTERVAL_MS` — worker poll interval, default 5000.

## Development

```sh
make test    # node --test packages/*/test/ — no migrate or DATABASE_URL needed
# tests 3, pass 3, fail 0
make lint
# lint ok: 4 files
make clean   # removes .taskflow-state.json; re-run `make migrate` after
```

Only `packages/shared` has tests today. The worker exits 4 if `.taskflow-state.json` has a
schema other than 3 — re-running `make migrate` fixes it.

Runbooks: TODO (see `docs/doc-scope.md`).
