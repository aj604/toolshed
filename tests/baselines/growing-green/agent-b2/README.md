# taskflow

A small Node workspace: an HTTP API for creating tasks (`services/api`) and a polling
background worker (`services/worker`), sharing task validation helpers (`packages/shared`).

## Requirements

- Node >= 20.6.0 (`package.json` engines)

## Setup and run

```sh
make setup     # npm install
make migrate   # writes .taskflow-state.json — api and worker refuse to start without it
# migrated: wrote .taskflow-state.json (schema 3)

export DATABASE_URL=postgres://localhost:5432/taskflow   # required; api exits 1 if unset
make dev       # starts api and worker (both run in the background)
```

`.env.example` lists the environment variables (`DATABASE_URL` required; `PORT` defaults
to 8080). Note: nothing in the repo loads a `.env` file — set the variables in your
environment.

Verified example (api on default port 8080):

```sh
curl -s localhost:8080/health
# {"ok":true,"tasks":0}
curl -s -X POST localhost:8080/tasks -H 'content-type: application/json' \
  -d '{"title":"write docs","priority":"high"}'
# {"id":"task_1","title":"write docs","priority":"high"}
```

Endpoints and status codes: see `services/api/server.js`.

## Development

```sh
make test   # node --test packages/*/test/ — only @taskflow/shared has tests; no migrate needed
make lint   # node scripts/lint.js
# lint ok: 4 files
make clean  # removes .taskflow-state.json
```

Runbooks: TODO (see `docs/doc-scope.md`).
