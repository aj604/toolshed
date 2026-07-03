# Life of a task

A walkthrough for new contributors: what happens to a task from the moment a
client POSTs it until the worker looks for it. Read this once, top to bottom,
with the three files it references open. Everything shown here (commands,
output, exit codes) was run against the repo as of this writing — if something
doesn't match, the doc has drifted; trust the code.

## The cast

Three npm workspaces (`package.json` `workspaces`), plus one file on disk:

| Piece | Path | Role in a task's life |
|-------|------|-----------------------|
| api | `services/api/server.js` | Accepts tasks over HTTP, validates them, assigns ids |
| worker | `services/worker/worker.js` | Polls for queued work and processes it |
| shared | `packages/shared/index.js` | The task contract both sides agree on (`@taskflow/shared`) |
| state file | `.taskflow-state.json` (repo root, gitignored) | Written by `make migrate`; both services refuse to start without it |

The api and worker never talk to each other directly. What connects them is
the *shape* of a task — defined once in `packages/shared` — and the state
file. Keep that in mind; it also explains the gap called out at the end.

## Act 0 — before any task exists: migrate

Fresh checkout:

```sh
make setup     # npm install for all workspaces
make migrate   # node scripts/migrate.js
```

`make migrate` prints:

```
migrated: wrote .taskflow-state.json (schema 3)
```

In a real system this would run database migrations; here `scripts/migrate.js`
just stamps `{ "migratedAt": ..., "schema": 3 }` into `.taskflow-state.json`.
Both services check for that file at startup and exit 3 if it's missing
(`services/api/server.js:12`, `services/worker/worker.js:11`) — so if you see

```
api: missing .taskflow-state.json — run `make migrate` first
```

do exactly what it says. The api additionally requires `DATABASE_URL` in the
environment and exits 1 without it (`server.js:16`); copy `.env.example` to
get a working value. `make dev` starts both services.

## Act 1 — a task arrives at the api

The api (`services/api/server.js`) is a bare `node:http` server with two
routes: `GET /health` and `POST /tasks`. A task is born like this:

```sh
curl -s -X POST localhost:8080/tasks -d '{"title":"write onboarding doc"}'
```

```
{"id":"task_1","title":"write onboarding doc","priority":"med"}
```

Walk the handler (`server.js:30-52`) and you'll see three steps, two of which
live in `packages/shared`:

1. **Parse.** Bad JSON → `400 bad json`.
2. **Validate** with `validateTask` from `@taskflow/shared`. Failure → `422
   invalid task`. This is the contract: `title` must be a non-empty string,
   and `priority`, if present, must be one of `low` / `med` / `high`:

   ```sh
   curl -s -X POST localhost:8080/tasks -d '{"title":"ship it","priority":"urgent"}'
   ```

   ```
   invalid task          # HTTP 422 — "urgent" is not a valid priority
   ```

3. **Construct.** `makeId()` mints a sequential id (`task_1`, `task_2`, …)
   and `normalizePriority()` fills in the default `"med"` when the client
   sent none — which is why the response above has a priority the request
   didn't. The task is pushed onto an in-memory `tasks` array and echoed back
   with `201`.

`GET /health` reports how many tasks the api is holding:

```
{"ok":true,"tasks":1}
```

## Act 2 — where shared fits

`packages/shared/index.js` is 18 lines and is the whole reason the two
services can stay ignorant of each other. It exports exactly three functions:

- `validateTask(task)` — the task contract. Used by the **api** to reject bad
  input at the door (`server.js:42`) and by the **worker** to distrust
  whatever it finds in the state file (`worker.js:24`). One definition, two
  enforcement points — change it and you change what both services accept.
- `makeId(prefix)` — sequential id minting (api only).
- `normalizePriority(p)` — defaults missing priority to `"med"` (api only).

It's also the only workspace with tests (`packages/shared/test/shared.test.js`,
run via `make test`), which is fitting: the contract is the part worth
pinning down.

## Act 3 — the worker wakes up

The worker (`services/worker/worker.js`) does not receive tasks from the api.
Its life starts at the state file:

1. Refuses to start without `.taskflow-state.json` (exit 3), same as the api.
2. Reads the file and checks `schema === 3`; anything else is a stale
   migration and it exits 4 (`worker.js:18`). If you ever see
   `worker: state schema N unsupported (need 3)`, re-run `make migrate`.
3. Filters the file's `tasks` array through the same `validateTask` the api
   used at ingress — it does not assume the file is trustworthy.
4. Starts polling on an interval (`WORKER_INTERVAL_MS`, default 5000ms):

```
worker: started, polling every 5000ms (0 pending)
```

The body of the polling loop (`worker.js:27-29`) is currently a stub — a
`// process due tasks here` comment. Processing logic doesn't exist yet.

## The gap you will eventually ask about

Trace it end to end and you'll notice the pipeline is not actually closed:
the api stores accepted tasks **only in memory** (`server.js:22,48`) and
never writes them to `.taskflow-state.json`; the worker reads tasks **only
from the state file** (`worker.js:16`) and re-checks them once at startup.
So today, a task POSTed to the api is never seen by the worker, and restarting
the api loses all tasks. That's the current state of the code, not a bug in
your understanding. The seam where persistence would go is the `tasks.push`
in the api and the state-file read in the worker.

## Exit codes, for when startup fails

All verified by running them:

| Exit | Who | Meaning | Fix |
|------|-----|---------|-----|
| 1 | api | `DATABASE_URL` unset | `cp .env.example .env` and load it |
| 3 | api or worker | `.taskflow-state.json` missing | `make migrate` |
| 4 | worker | state file schema ≠ 3 | `make migrate` again |

## Where to go next

- `CLAUDE.md` — command and environment quick reference.
- `packages/shared/test/shared.test.js` — the contract's edge cases, in test form.
- `Makefile` — every dev command is one target; read the comments.
