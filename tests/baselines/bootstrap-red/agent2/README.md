# taskflow

A small Node.js (ESM) monorepo for a task-tracking system. An HTTP API accepts
tasks; a background worker polls for due work. Both share validation/ID helpers.

- `package.json` declares `"type": "module"` and Node `>=20.6.0`.
- Uses npm workspaces: `packages/*` and `services/*`.

## Layout

| Path | Package | Purpose |
| --- | --- | --- |
| `packages/shared/` | `@taskflow/shared` | ID generation + task validation helpers used by api and worker |
| `services/api/` | `@taskflow/api` | HTTP API: `GET /health`, `POST /tasks` |
| `services/worker/` | `@taskflow/worker` | Background poller that processes due work |
| `scripts/migrate.js` | — | Writes `.taskflow-state.json` (schema 3) |
| `scripts/lint.js` | — | Counts `.js` source files under `packages/` and `services/` |

## Quickstart

Run these in order (from the Makefile):

```
make setup     # npm install
make migrate   # writes .taskflow-state.json — required before api/worker start
make dev       # starts api and worker in the background
```

`make dev` runs `api` and `worker` together. Both background themselves (`&` in
the Makefile), so they keep running after the target returns.

### Configuration

Copy `.env.example` to `.env` and fill it in. The api reads env at startup:

- `DATABASE_URL` (required) — the api exits with code 1 if unset.
- `PORT` (optional) — api listen port, defaults to `8080`.
- `WORKER_INTERVAL_MS` (optional) — worker poll interval, defaults to `5000`.

`.env`, `node_modules/`, and `.taskflow-state.json` are gitignored.

## Other commands

```
make test    # node --test across packages/*/test/  (only @taskflow/shared has tests)
make lint    # node scripts/lint.js
make clean   # rm -f .taskflow-state.json
```

## How it fits together

`scripts/migrate.js` stamps `.taskflow-state.json` with `{ migratedAt, schema: 3 }`.
The api and worker both refuse to start if that file is missing. The worker also
parses the file and requires `schema === 3`. The api stores tasks in memory (the
`tasks` array in `server.js`) — there is no real database yet despite the
`DATABASE_URL` requirement.

## API

- `GET /health` → `200 {"ok": true, "tasks": <count>}`
- `POST /tasks` with JSON body `{ "title": string, "priority"?: "low"|"med"|"high" }`
  - `201` with the created task `{ id, title, priority }` on success
  - `400 bad json` if the body is not valid JSON
  - `422 invalid task` if validation fails
  - Any other route/method → `404 not found`

`title` must be a non-empty string. `priority` is optional and, if omitted,
defaults to `"med"` (see `normalizePriority` / `validateTask` in
`packages/shared/index.js`).
