# TaskFlow

TaskFlow is a small task-management system split into an HTTP API and a
background worker, sharing common validation helpers. It is organized as an npm
workspaces monorepo and orchestrated through a `Makefile`.

## Architecture

```
taskflow/
├── packages/
│   └── shared/          @taskflow/shared — validation + ID helpers used by both services
├── services/
│   ├── api/             @taskflow/api    — HTTP server for creating/listing tasks
│   └── worker/          @taskflow/worker — background poller that processes due tasks
└── scripts/
    ├── migrate.js       writes the local state file both services require
    └── lint.js          checks that every workspace source file parses
```

Both the API and the worker depend on a local state file,
`.taskflow-state.json`, which is created by the migration step. Neither service
will start until that file exists, and the worker additionally requires the
state file's `schema` to equal `3`.

## Requirements

- Node.js >= 20.6.0 (declared in `package.json` `engines`)
- For the API: a `DATABASE_URL` environment variable

## Setup

The `Makefile` is the entry point. Run these in order:

```sh
make setup     # npm install (installs workspace dependencies)
make migrate   # writes .taskflow-state.json (schema 3)
make dev       # starts the api and worker together (backgrounded)
```

Before starting the API, copy the environment template and fill it in:

```sh
cp .env.example .env
```

`.env` keys:

| Variable       | Required | Default | Used by | Notes                                              |
| -------------- | -------- | ------- | ------- | -------------------------------------------------- |
| `DATABASE_URL` | yes      | —       | api     | The API exits with code `1` if it is unset         |
| `PORT`         | no       | `8080`  | api     | Port the API listens on                            |

The worker also reads one optional variable, `WORKER_INTERVAL_MS` (default
`5000`), which controls how often it polls.

## Running individual services

```sh
make api       # node services/api/server.js (backgrounded)
make worker    # node services/worker/worker.js (backgrounded)
```

Each requires `make migrate` to have run first.

## Testing and linting

```sh
make test      # runs the Node test runner across packages/*/test/
make lint      # checks that workspace source files parse as modules
```

Today only `@taskflow/shared` has tests.

## Cleanup

```sh
make clean     # removes .taskflow-state.json
```

## Startup exit codes

Because both services validate their preconditions at startup, they exit with
distinct codes on failure:

| Code | Service     | Meaning                                                    |
| ---- | ----------- | --------------------------------------------------------- |
| `1`  | api         | `DATABASE_URL` is unset                                    |
| `3`  | api, worker | `.taskflow-state.json` is missing — run `make migrate`     |
| `4`  | worker      | State file `schema` is not `3` (stale migration)          |

## Further reading

- [docs/api.md](docs/api.md) — HTTP API reference
