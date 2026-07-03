# Life of a task

> As of 2026-07-03 (anchors: `services/api/server.js`, `services/worker/worker.js`, `packages/shared/index.js`, `scripts/migrate.js` — no git history in this checkout, so line anchors below are the staleness hooks)

This walkthrough follows one task through taskflow, end to end: the migration that
lets anything start, the api that admits the task, the shared library both services
lean on, and the worker that polls for work. Every command and output below was run
against this repo on the date above.

## The cast

- `services/api/server.js` — HTTP server; accepts tasks over POST.
- `services/worker/worker.js` — background poller.
- `packages/shared` (`@taskflow/shared`) — the task contract both services import.
- `scripts/migrate.js` — stamps the state file both services require to start.

## Step 0 — nothing starts before `make migrate`

Both services check for `.taskflow-state.json` at the repo root before doing anything
else, and exit code 3 if it is missing (`services/api/server.js:12-15`,
`services/worker/worker.js:11-14`):

```
$ node services/worker/worker.js
worker: missing .taskflow-state.json — run `make migrate` first
$ echo $?
3
```

`make migrate` runs `scripts/migrate.js`, which writes the file with a schema stamp
(`scripts/migrate.js:8-9`):

```
$ make migrate
node scripts/migrate.js
migrated: wrote .taskflow-state.json (schema 3)
```

The api additionally exits 1 if `DATABASE_URL` is unset (`services/api/server.js:16-19`).
So the real startup order is: `make setup` (npm install), `make migrate`, then
`make dev` with `DATABASE_URL` exported in your shell. (Nothing loads a `.env`
file — no dotenv, no `--env-file` in the Makefile — despite what `.env.example`
suggests; export the variable yourself.)

## Step 1 — the api admits the task

The api listens on `PORT` (default 8080) and handles two routes: `GET /health` and
`POST /tasks`. A posted task passes through three shared-library functions in one line
(`services/api/server.js:47`):

1. `validateTask` (`packages/shared/index.js:9`) — gatekeeper. Rejects a missing or
   empty `title`, or a `priority` outside `low`/`med`/`high`. Failure → `422 invalid task`.
   Unparseable JSON is rejected earlier with `400 bad json`.
2. `makeId` (`packages/shared/index.js:4`) — mints `task_1`, `task_2`, … from an
   in-process counter, so ids restart from `task_1` whenever the api restarts.
3. `normalizePriority` (`packages/shared/index.js:16`) — fills in `med` when no
   priority was sent.

Run against this repo (api started with `PORT=8090`):

```
$ curl -s -X POST localhost:8090/tasks -d '{"title":"write onboarding doc","priority":"high"}'
{"id":"task_1","title":"write onboarding doc","priority":"high"}
$ curl -s -X POST localhost:8090/tasks -d '{"title":"triage inbox"}'
{"id":"task_2","title":"triage inbox","priority":"med"}
$ curl -s -X POST localhost:8090/tasks -d '{"priority":"high"}'
invalid task
```

The accepted task lands in an in-memory array (`services/api/server.js:22,48`) and is
visible in the health count:

```
$ curl -s localhost:8090/health
{"ok":true,"tasks":2}
```

## Step 2 — where shared fits

`@taskflow/shared` is three functions, and its job is the **task contract**: the api
uses `validateTask` to decide what gets in (`services/api/server.js:42`), and the
worker uses the same `validateTask` to decide what counts as pending work
(`services/worker/worker.js:24`). One definition of "a valid task", enforced at both
ends — that is why it is a workspace package instead of code copied into each service.
It is also the only package with tests (`make test` runs them; 3 pass).

## Step 3 — the worker polls

At startup the worker reads `.taskflow-state.json` once, and exits 4 if the schema is
not exactly 3 (`services/worker/worker.js:18-20`) — a stale state file from an old
migration breaks it. It filters the file's `tasks` array through `validateTask`, then
polls on an interval (`WORKER_INTERVAL_MS`, default 5000ms):

```
$ node services/worker/worker.js
worker: started, polling every 5000ms (0 pending)
```

## The gap you should know about (as of the anchors above)

The end-to-end pipe is **not closed yet**, and this trips up every newcomer:

- The api keeps accepted tasks only in memory (`services/api/server.js:22`); it never
  writes them to `.taskflow-state.json`.
- The worker reads tasks only from `.taskflow-state.json` at startup, and its poll
  body is a stub (`services/worker/worker.js:28` — `// process due tasks here`).
- `scripts/migrate.js` writes no `tasks` key, so a fresh checkout always shows
  `0 pending`.

So today a POSTed task is validated, stored, counted by `/health` — and never reaches
the worker. If you were hired to make the worker do something, the handoff between
Step 1 and Step 3 is the missing piece, not something you failed to find.

## Recap

```
make migrate ──▶ .taskflow-state.json (schema 3)
                      │ required by both services
POST /tasks ──▶ api: validateTask → makeId → normalizePriority ──▶ in-memory tasks[]
                      (shared = the contract both sides enforce)
worker: reads state file once → validateTask filter → polls every 5s (stub body)
```
