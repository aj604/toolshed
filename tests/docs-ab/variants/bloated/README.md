# taskflow

**A modern, workspace-based task-queue sample for Node.js.**

taskflow demonstrates how to structure a small multi-service Node.js system
using nothing but the platform: npm workspaces for package management, the
built-in `node:http` server for the API layer, the built-in `node:test` runner
for testing, and plain ES modules throughout. There are zero production
dependencies outside the repository itself.

## Table of Contents

- [Architecture](#architecture)
- [Getting Started](#getting-started)
- [Running the Services](#running-the-services)
- [The HTTP API](#the-http-api)
- [Configuration](#configuration)
- [Testing](#testing)
- [Linting](#linting)
- [Project Layout](#project-layout)
- [Troubleshooting](#troubleshooting)
- [Changelog](#changelog)

## Architecture

The system is made up of three npm workspace packages:

1. **`@taskflow/api`** (`services/api`) — a dependency-free HTTP server exposing
   a health endpoint and a task-creation endpoint. Tasks are validated against
   the shared task contract and held in memory.
2. **`@taskflow/worker`** (`services/worker`) — a long-running poller that reads
   the persisted state file on startup, validates queued tasks, and wakes on an
   interval to process due work.
3. **`@taskflow/shared`** (`packages/shared`) — the shared library both services
   import: id generation, task validation, and priority normalization.

Both services depend on `@taskflow/shared@1.2.0`; the services do not import
from each other. All three packages are version 1.2.0 and are ES modules.

## Getting Started

taskflow requires **Node.js 20.6.0 or newer** (declared in the root
`package.json` engines field).

```
make setup      # installs all workspace dependencies (npm install)
make migrate    # writes .taskflow-state.json — required before running services
cp .env.example .env   # provides DATABASE_URL, which the api requires
make dev        # starts the api and the worker
```

The migrate step is not optional: both the api and the worker check for
`.taskflow-state.json` at startup and exit with code 3 if it is missing.

## Running the Services

- `make dev` starts both services (each is backgrounded by its Make target).
- `make api` starts only the HTTP api (`node services/api/server.js`).
- `make worker` starts only the worker (`node services/worker/worker.js`).

On successful startup the api prints `api listening on :<port>` and the worker
prints `worker: started, polling every <interval>ms (<n> pending)`.

## The HTTP API

- `GET /health` returns `200` with `{ "ok": true, "tasks": <count> }`.
- `POST /tasks` accepts `{ "title": string, "priority"?: "low"|"med"|"high" }`
  and returns `201` with the created task, `400` for malformed JSON, or `422`
  for a body that fails validation (empty title, unknown priority).
- Any other route returns `404`.

## Configuration

| Variable | Required | Default | Purpose |
|----------|----------|---------|---------|
| `DATABASE_URL` | yes (api) | — | The api exits 1 without it; see `.env.example` |
| `PORT` | no | 8080 | API listen port |
| `WORKER_INTERVAL_MS` | no | 5000 | Worker polling interval |

## Testing

Run the suite with `make test`, which invokes `node --test packages/*/test/`.
Note that `npm test` is **not** wired up — the root manifest has no test script.
Currently `@taskflow/shared` is the only package with tests
(`packages/shared/test/shared.test.js`, three tests over the shared helpers).

## Linting

`make lint` runs `scripts/lint.js`, a minimal parse-check that walks
`packages/` and `services/` and reports the file count (`lint ok: 4 files`).

## Project Layout

```
Makefile          orchestration targets (setup/migrate/dev/api/worker/test/lint/clean)
packages/shared   the shared helper library and its tests
services/api      the HTTP api
services/worker   the polling worker
scripts/          migrate.js (state file) and lint.js (parse check)
.env.example      environment template
```

## Troubleshooting

- **`api: missing .taskflow-state.json — run \`make migrate\` first` (exit 3):**
  run `make migrate`.
- **`api: DATABASE_URL is required` (exit 1):** copy `.env.example` to `.env`
  and export it, or set `DATABASE_URL` inline.
- **`worker: state schema <n> unsupported (need 3)` (exit 4):** the state file
  was written by a different schema; re-run `make migrate`.
- **Port already in use:** set `PORT` to a free port.

## Changelog

- **1.2.0** — current fixture version; all three packages are versioned together.
