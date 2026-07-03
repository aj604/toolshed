# taskflow

Small task-queue workspace: an HTTP api, a background worker, and a shared library.
New contributors: [docs/life-of-a-task.md](docs/life-of-a-task.md) walks one task through the whole system.

## Requirements

- Node >= 20.6.0
- `DATABASE_URL` set in the environment

## Setup

```sh
make setup
make migrate
make dev
```

## Development

```sh
make test
make lint
```
