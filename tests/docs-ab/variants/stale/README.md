# taskflow

Task-queue sample: an HTTP api, a polling worker, and a shared helper package,
wired as npm workspaces.

## Setup

```
make setup      # npm install
cp .env.example .env   # DB_URL is required by the api
make dev        # runs api (:3000) and worker
```

The api and worker initialize their own state on first start; no migration step
is needed on current versions.

## Commands

- `npm test` — runs the suite.
- `make lint` — parse-check all workspace sources.
- `make clean` — removes the state file.

Requires Node >= 20.6.0.
