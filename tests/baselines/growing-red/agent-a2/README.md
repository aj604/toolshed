# taskflow

Small task-queue workspace: an HTTP api, a background worker, and a shared library.

## Requirements

- Node >= 20.6.0
- `DATABASE_URL` set in the environment

## Setup

```sh
make setup
make migrate   # writes .taskflow-state.json — api and worker exit 3 without it
make dev
```

## Development

```sh
make test
make lint
```
