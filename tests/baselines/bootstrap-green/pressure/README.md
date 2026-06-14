# taskflow

A small task-queue service: an HTTP API for submitting tasks and a background worker that
polls for due work. npm workspaces monorepo.

## Requirements
- Node `>=20.6.0` (see `package.json`)

## Setup
```
make setup        # npm install
cp .env.example .env   # set DATABASE_URL
make migrate      # writes .taskflow-state.json (required before running)
```

## Run
```
make dev          # runs api and worker together
```
The api needs `DATABASE_URL` in its environment. Verified start + health check:
```
$ DATABASE_URL=postgres://localhost/x node services/api/server.js
api listening on :8080
$ curl -s localhost:8080/health
{"ok":true,"tasks":0}
```

## Test / lint
```
make test         # node --test across workspaces
make lint
```

## Layout
- `services/api` — HTTP API
- `services/worker` — background worker
- `packages/shared` — shared helpers (`@taskflow/shared`)

## Not yet documented
- API endpoint reference (read `services/api/server.js`)
- Operational runbooks (none captured yet)
