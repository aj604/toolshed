# taskflow

Task-queue sample: an HTTP api, a polling worker, and a shared helper package,
wired as npm workspaces.

## Setup

```
make setup      # npm install
make migrate    # writes .taskflow-state.json — api and worker refuse to start without it
cp .env.example .env   # DATABASE_URL is required by the api
make dev        # runs api (:8080) and worker
```

## Commands

- `make test` — runs the suite (`node --test packages/*/test/`). Do not use `npm test`.
- `make lint` — parse-check all workspace sources.
- `make clean` — removes the state file.

Requires Node >= 20.6.0.
