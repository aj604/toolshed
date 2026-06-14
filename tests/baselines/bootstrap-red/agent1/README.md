# TaskFlow

TaskFlow is a small task-management system built as a Node.js monorepo. It exposes
an HTTP API for creating tasks and runs a background worker that processes due work.
The two services share validation and ID helpers from a common package.

- Version: `1.2.0`
- Node: `>=20.6.0` (see `engines` in `package.json`)
- Module system: ES modules (`"type": "module"`)

## Architecture

The repo is an npm workspaces monorepo with three workspaces under `packages/*`
and `services/*`:

| Workspace            | Path                   | Role                                                        |
| -------------------- | ---------------------- | ---------------------------------------------------------- |
| `@taskflow/api`      | `services/api`         | HTTP API. Accepts `POST /tasks`, exposes `GET /health`.    |
| `@taskflow/worker`   | `services/worker`      | Background poller that processes due tasks on an interval. |
| `@taskflow/shared`   | `packages/shared`      | Shared helpers: `makeId`, `validateTask`, `normalizePriority`. |

Both services depend on a local state file, `.taskflow-state.json`, written by the
migration step. Neither service will start until that file exists.

```
taskflow/
├── Makefile                 # task orchestration (setup, migrate, dev, test, lint, clean)
├── package.json             # workspace root
├── .env.example             # copy to .env for the api
├── scripts/
│   ├── migrate.js           # writes .taskflow-state.json (schema 3)
│   └── lint.js              # checks that every workspace .js file parses
├── packages/
│   └── shared/              # @taskflow/shared
│       ├── index.js
│       └── test/shared.test.js
└── services/
    ├── api/server.js        # @taskflow/api
    └── worker/worker.js     # @taskflow/worker
```

## Getting started

The intended order is **setup → migrate → dev**. The services refuse to start
out of order.

1. Install dependencies:

   ```sh
   make setup        # runs: npm install
   ```

2. Configure the API environment. The api reads these at startup:

   ```sh
   cp .env.example .env
   # DATABASE_URL is required; the api exits 1 if it is unset.
   # PORT is optional and defaults to 8080.
   ```

3. Run the migration. This writes the local state file the services require:

   ```sh
   make migrate      # runs: node scripts/migrate.js
   ```

4. Start both services in the background:

   ```sh
   make dev          # starts the api and worker together
   ```

## Make targets

| Target         | What it does                                                              |
| -------------- | ------------------------------------------------------------------------ |
| `make setup`   | `npm install`.                                                           |
| `make migrate` | Runs `scripts/migrate.js`, writing `.taskflow-state.json` (schema 3).     |
| `make dev`     | Runs `api` and `worker` together (both backgrounded). Requires migrate.  |
| `make api`     | Starts only the API: `node services/api/server.js &`.                    |
| `make worker`  | Starts only the worker: `node services/worker/worker.js &`.              |
| `make test`    | Runs the test suite across workspaces: `node --test packages/*/test/`.    |
| `make lint`    | Runs `scripts/lint.js` (parses every workspace `.js` file).             |
| `make clean`   | Removes `.taskflow-state.json`.                                          |

## API

The API serves two routes (`services/api/server.js`):

### `GET /health`

Returns `200` with the current in-memory task count:

```json
{ "ok": true, "tasks": 0 }
```

### `POST /tasks`

Creates a task. The request body must be JSON with a non-empty `title` and an
optional `priority` of `low`, `med`, or `high`.

Request:

```json
{ "title": "Write docs", "priority": "high" }
```

Response (`201`):

```json
{ "id": "task_1", "title": "Write docs", "priority": "high" }
```

Status codes:

- `400` — body is not valid JSON.
- `422` — task fails validation (missing/empty title, or invalid priority).
- `201` — task created.
- `404` — any other route or method.

Validation rules live in `@taskflow/shared`:

- `validateTask` rejects non-objects, missing/empty `title`, and any `priority`
  outside `low` / `med` / `high`.
- `normalizePriority` defaults a missing priority to `med`.

Tasks are stored in memory only and are lost when the API restarts.

## Configuration

| Variable             | Used by | Required | Default | Notes                                       |
| -------------------- | ------- | -------- | ------- | ------------------------------------------- |
| `DATABASE_URL`       | api     | Yes      | —       | API exits `1` if unset.                     |
| `PORT`               | api     | No       | `8080`  | API listen port.                            |
| `WORKER_INTERVAL_MS` | worker  | No       | `5000`  | Polling interval in milliseconds.           |

## Testing

```sh
make test         # node --test packages/*/test/
```

Only `@taskflow/shared` has tests today (`packages/shared/test/shared.test.js`).

## Gotchas

- **Run `make migrate` first.** Both the api and worker exit with code `3` and
  print `missing .taskflow-state.json — run make migrate first` if the state
  file is absent.
- **Schema must be 3.** The worker only understands state schema `3` and exits
  with code `4` if the migration stamped a different schema.
- **`DATABASE_URL` is mandatory for the api.** It exits with code `1` when unset.
- **Tasks are in-memory.** The API does not persist tasks; restarting clears them.
