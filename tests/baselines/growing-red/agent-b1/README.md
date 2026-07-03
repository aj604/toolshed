# taskflow

A small task-queue workspace: an HTTP API (`services/api`) that accepts tasks and a
background worker (`services/worker`) that polls queued work, sharing task-validation
helpers from `packages/shared`. Node >= 20.6.0, npm workspaces, ESM throughout.

## Setup

```sh
make setup            # npm install
cp .env.example .env  # DATABASE_URL is required; the api exits if it is unset
make migrate          # writes .taskflow-state.json — api and worker refuse to start without it
```

## Run

```sh
make dev              # starts api (PORT, default 8080) and worker together
```

## Test and lint

`make test` runs the Node test runner across workspaces (only `@taskflow/shared` has
tests today) and does not need `make migrate` first.

```sh
$ make lint
node scripts/lint.js
lint ok: 4 files
```

## Layout

- `services/api/server.js` — HTTP API
- `services/worker/worker.js` — background poller
- `packages/shared/` — helpers shared by both
- `scripts/` — `migrate.js`, `lint.js` (what the Makefile calls)
