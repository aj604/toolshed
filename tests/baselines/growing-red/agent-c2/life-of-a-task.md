# Life of a task

An onboarding walkthrough. It follows one task from an HTTP request all the way through
the system, showing where each of the three workspace packages picks it up. Read it top
to bottom once; after that the code itself (`services/api/server.js`,
`services/worker/worker.js`, `packages/shared/index.js` — ~110 lines total) is the
reference.

**The one-paragraph version:** a client POSTs a task to the api. The api validates it
using the shared library, stamps it with an id and a normalized priority, stores it in
memory, and returns it. The worker is a separate process that polls on a timer; it
shares the task *contract* with the api (via `@taskflow/shared`) and the migration
*state file*, but — important to know on day one — **it does not yet receive tasks from
the api**. That gap is real and documented below, not something you're failing to see.

```
client ──POST /tasks──▶ services/api ──▶ in-memory array (per api process)
                            │
                            └── uses packages/shared: validateTask, makeId, normalizePriority

scripts/migrate.js ──▶ .taskflow-state.json (schema 3)
                            │
                            ├── api refuses to start without it
                            └── worker reads it once at boot, then polls (loop body is a stub)
```

## Step 0 — before anything runs: the migration gate

Both services refuse to start until `scripts/migrate.js` has stamped a state file at the
repo root:

```sh
make setup     # npm install (workspace symlinks @taskflow/shared into node_modules)
make migrate
```

```
migrated: wrote .taskflow-state.json (schema 3)
```

The file is tiny — `{ "migratedAt": "fixture-stamp", "schema": 3 }`. In a real system
this step would run DB migrations; here it just stamps that they happened
(`scripts/migrate.js` says so in its header comment).

Skip it and both processes exit code 3 with `run \`make migrate\` first` on stderr. The
api additionally exits code 1 if `DATABASE_URL` is unset. The worker has one more trap:
it checks `schema === 3` and exits code 4 on anything else —

```
worker: state schema 2 unsupported (need 3)
```

— which is what you'll see after pulling a branch whose migrate script wrote an older
schema. The fix is always the same: re-run `make migrate`.

## Step 1 — the task arrives: `services/api/server.js`

The api is a single `node:http` server (default port 8080, `PORT` to override). It knows
exactly three things: `GET /health`, `POST /tasks`, and 404 for everything else.

A task begins life as a client request:

```sh
curl -i -X POST localhost:8123/tasks -d '{"title":"send welcome email","priority":"high"}'
```

The handler buffers the body, then makes three decisions in order:

1. **Is it JSON?** `JSON.parse` fails → `400 bad json`.
2. **Is it a task?** `validateTask(parsed)` (from `@taskflow/shared`) fails → `422 invalid task`.
3. **Accept it.** Build the real task — `makeId()` assigns the id, `normalizePriority()`
   fills in the priority — push it onto the in-memory `tasks` array, and return `201`:

```
HTTP/1.1 201 Created
content-type: application/json

{"id":"task_1","title":"send welcome email","priority":"high"}
```

`GET /health` reports the same array's length: `{"ok":true,"tasks":1}`.

Two things newcomers usually have to discover the hard way:

- **Storage is a per-process array** (`const tasks = []` at the top of `server.js`).
  Restart the api and every task is gone. Nothing is written to disk, the state file,
  or a database — `DATABASE_URL` is checked for presence but never used to connect.
- The api only *reads* `.taskflow-state.json`'s existence; it never updates it.

## Step 2 — the contract everything agrees on: `packages/shared`

`@taskflow/shared` is 18 lines and is the only code both services import. It defines
what "a task" means:

- `validateTask(task)` — an object with a non-empty string `title`; `priority` may be
  omitted or one of `"low" | "med" | "high"`. This is the single validation used by the
  api (rejecting requests) *and* the worker (filtering queued work), so the two can
  never disagree about task shape.
- `makeId(prefix)` — `task_1`, `task_2`, … from an in-process counter. Ids are unique
  per api process, **not** globally: restart the api and the counter resets to `task_1`.
- `normalizePriority(p)` — `null`/`undefined` becomes `"med"`; anything else passes
  through (validation already guaranteed it's a legal value).

It's also the only package with tests — `make test` runs `node --test packages/*/test/`
and today that means the 3 shared tests (`# tests 3 … # pass 3`).

## Step 3 — the worker: `services/worker/worker.js`

The worker is an independent process (`make dev` starts both; each is a plain
backgrounded `node` invocation in the Makefile). Its whole startup sequence:

1. Same migration gate as the api (exit 3 if the state file is missing).
2. Schema check (exit 4 unless `schema === 3`, as shown in step 0).
3. Read `tasks` from the **state file** — not from the api — and filter them through
   the shared `validateTask`.
4. Start polling on `WORKER_INTERVAL_MS` (default 5000ms):

```
worker: started, polling every 5000ms (0 pending)
```

`0 pending` is what you will always see today, because `scripts/migrate.js` writes no
`tasks` key, and nothing else ever puts tasks into the state file.

## The gap — where the walkthrough honestly ends

If you trace the code expecting a queue, you'll go in circles, so here it is plainly.
As of the current code:

- The api stores accepted tasks **only in its own memory** and never hands them to the
  worker (no shared file writes, no queue, no IPC).
- The worker's poll loop body is a stub — literally `// process due tasks here`
  (`services/worker/worker.js:28`).

So today, a task's life is: **validated → stamped → stored in api memory → counted by
`/health` → gone on restart.** The worker shares the task contract and the migration
gate, and it demonstrates the intended polling shape, but the api→worker hand-off does
not exist yet. When it lands, the pieces already in place are the state file (the only
persistence both processes touch) and `validateTask` (the shape both already enforce).

## Try it yourself (5 minutes)

```sh
make setup && make migrate
DATABASE_URL=postgres://localhost/taskflow PORT=8123 node services/api/server.js &
node services/worker/worker.js &

curl -i -X POST localhost:8123/tasks -d '{"title":"send welcome email","priority":"high"}'
curl localhost:8123/health          # {"ok":true,"tasks":1}
curl -i -X POST localhost:8123/tasks -d '{"title":""}'   # 422 invalid task
```

Then break it on purpose — `make clean && node services/worker/worker.js` — and watch
the migration gate fire. Every failure you can cause here (missing state, bad schema,
missing `DATABASE_URL`, invalid task) is one you'll eventually meet in a log, and now
you'll recognize it.

---

*All command output above was captured by actually running the code in this repo. If
this doc and the code disagree, the code wins — please fix the doc.*
