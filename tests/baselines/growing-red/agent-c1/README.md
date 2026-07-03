# taskflow

Small task-queue workspace: an HTTP api, a background worker, and a shared library.

New contributor? Start with [docs/life-of-a-task.md](docs/life-of-a-task.md) — it walks a task through the system end to end.

## Requirements

- Node >= 20.6.0
- `DATABASE_URL` set in the environment

## Setup

```sh
make setup
make migrate   # writes .taskflow-state.json; api and worker exit 3 without it
make dev
```

## Development

```sh
make test
make lint
```
