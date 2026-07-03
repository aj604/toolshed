# taskflow

Small task-queue workspace: an HTTP api, a background worker, and a shared library.

## Requirements

- Node >= 20.6.0
- `DATABASE_URL` set in the environment

## Setup

```sh
make setup
make migrate
make dev
```

If `api` or `worker` refuses to start with exit code 3 (`missing .taskflow-state.json`),
run `make migrate` — it writes that file; `make clean` removes it.

## Development

```sh
make test
make lint
```
