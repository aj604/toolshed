# Life of a task

> As of 2026-07-03 (anchors current at writing: `services/api/server.js`, `services/worker/worker.js`, `packages/shared/index.js:9`, `scripts/migrate.js:8` — repo has no git history to pin a commit)

An end-to-end walk through what happens to one task, from `curl` to the worker's poll
loop — including the part that surprises everyone (step 5). Every command below was run
against this repo as of the date above.

## 0. The precondition both services enforce

Nothing starts until `make setup` and `make migrate` have run:

```sh
make setup     # npm install (workspaces: packages/*, services/*)
make migrate   # node scripts/migrate.js
```

`migrate` writes `.taskflow-state.json` at the repo root:

```json
{ "migratedAt": "fixture-stamp", "schema": 3 }
```

Both services check for this file before doing anything else and exit 3 if it is
missing (`services/api/server.js:12`, `services/worker/worker.js:11`):

```
worker: missing .taskflow-state.json — run `make migrate` first
```

The api additionally exits 1 if `DATABASE_URL` is unset (`server.js:16`). The worker
has one more gate: the state file's `schema` must be exactly `3`, or it exits 4
(`worker.js:18`). So a stale state file breaks the worker even though the api is happy.

## 1. A task is born: `POST /tasks`

Start the api (`make dev` runs api and worker together; here just the api):

```sh
DATABASE_URL=postgres://localhost:5432/taskflow node services/api/server.js
# api listening on :8080
curl -i -X POST localhost:8080/tasks -d '{"title":"index the archive"}'
```

```
HTTP/1.1 201 Created
{"id":"task_1","title":"index the archive","priority":"med"}
```

Inside `server.js`'s request handler (line 30), the body goes through three gates:

1. `JSON.parse` — malformed body → `400 bad json`.
2. `validateTask(parsed)` — the shared contract → `422 invalid task`.
3. Construction: `{ id: makeId(), title, priority: normalizePriority(parsed.priority) }`
   → pushed onto the in-memory `tasks` array → `201` with the task as JSON.

## 2. Where `@taskflow/shared` fits

All three functions in step 1's gate 2–3 come from `packages/shared/index.js`, the one
package both services depend on (see `dependencies` in each service's `package.json`):

- `validateTask` — a task is an object with a non-empty string `title`; `priority`, if
  present, must be `low` | `med` | `high`. That is the entire task contract; there is
  no schema file elsewhere.
- `normalizePriority` — `null`/absent becomes `"med"`, which is why the response above
  says `"priority":"med"` when the request sent none.
- `makeId` — `task_1`, `task_2`, … from a module-level counter. It resets on restart,
  and each Node process has its own counter — ids are per-process, not global.

The worker imports `validateTask` too (`worker.js:6`): api and worker agree on what a
task is only because both call the same function.

## 3. The task's whole life in the api: an array

`server.js:22` — `const tasks = [];`. There is no database write; `DATABASE_URL` is
checked at startup but never used afterward. `GET /health` reports the array size:

```sh
curl localhost:8080/health
# {"ok":true,"tasks":1}
```

Restart the api and the task is gone. That is current, intended behavior of this
fixture, not a bug you found.

## 4. What the worker actually does

```sh
node services/worker/worker.js
# worker: started, polling every 5000ms (0 pending)
```

At startup the worker (`worker.js`):

1. Requires `.taskflow-state.json` (exit 3) and `schema === 3` (exit 4) — step 0.
2. Reads `tasks` from **the state file** (defaulting to `[]`), filters them through
   `validateTask`, and reports the count as "pending".
3. Polls on `setInterval` every `WORKER_INTERVAL_MS` ms (default 5000). The interval
   body is `// process due tasks here` — a stub.

## 5. The gap you were about to go looking for

Notice the worker said `0 pending` even though the api holds `task_1`. **The api and
worker do not talk to each other.** The api never writes tasks to the state file, and
the worker never calls the api; the worker's only task source is the `tasks` array in
`.taskflow-state.json`, which `migrate.js` writes without one. So today a task's life
ends in the api's in-memory array, and the worker polls over an empty list forever.

The handoff point, when it gets built, is the state file's `tasks` array — that is why
the worker already validates and counts it. If you were hired to make tasks flow end to
end, the missing piece is: api persists to the state file (or a real store), worker's
interval body consumes from it.

## 6. Proving the contract: tests

```sh
make test    # node --test packages/*/test/
# pass 3
```

Only `@taskflow/shared` has tests (`packages/shared/test/`), and they pin exactly the
contract from step 2: empty titles rejected, `"urgent"` rejected, `null` priority →
`"med"`. Nothing tests the api or worker; if you change task shape, the shared tests
are the guardrail.
