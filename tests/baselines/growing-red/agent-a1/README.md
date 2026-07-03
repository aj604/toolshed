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

`make migrate` writes `.taskflow-state.json`, which api and worker require to start (they exit 3 without it).

## Development

```sh
make test
make lint
```
