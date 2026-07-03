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

If the api or worker exits with code 3 (`missing .taskflow-state.json`), run `make migrate`.

## Development

```sh
make test
make lint
```
