# taskflow

A small task-queue service: an HTTP API for creating tasks and a background worker, sharing helpers in a single npm-workspaces monorepo.

## Requirements

- Node `>=20.6.0` (`package.json:6`)
- `make`

## Setup

```sh
make setup     # npm install
cp .env.example .env   # set DATABASE_URL; api exits 1 without it
make migrate   # writes .taskflow-state.json; api/worker exit 3 without it
```

`make migrate` output:

```
migrated: wrote .taskflow-state.json (schema 3)
```

## Run

```sh
make dev       # starts api and worker in the background
```

The api listens on `PORT` (default 8080). Real output against a running api:

```sh
$ curl -s localhost:8080/health
{"ok":true,"tasks":0}

$ curl -s -X POST localhost:8080/tasks -d '{"title":"demo"}'
{"id":"task_1","title":"demo","priority":"med"}
```

An invalid task (e.g. empty title) returns HTTP `422`. Endpoint details live in `services/api/server.js`.

## Configuration

| Var | Required | Default | Source |
|-----|----------|---------|--------|
| `DATABASE_URL` | yes (api) | — | `services/api/server.js:16` |
| `PORT` | no | `8080` | `services/api/server.js:21` |
| `WORKER_INTERVAL_MS` | no | `5000` | `services/worker/worker.js:22` |

## Development

```sh
make test      # node --test packages/*/test/  (3 tests pass)
make lint      # parse-checks workspace .js files
make clean     # removes .taskflow-state.json
```

## License

Not specified in the repo.
