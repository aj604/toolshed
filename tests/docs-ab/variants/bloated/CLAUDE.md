# CLAUDE.md — Complete Development Guide for taskflow

Welcome to taskflow! This document is the comprehensive reference for AI assistants
and developers working in this repository. It covers the project structure, every
module and its exports, all HTTP endpoints, configuration, conventions, and
development workflows. Please read it carefully before making any changes.

## Project Overview

taskflow is a task-queue sample application demonstrating a modern Node.js
workspace architecture. It is composed of three cooperating components: a
stateless HTTP API service that accepts and lists tasks, a background worker
process that polls persisted state for due work, and a shared library package
that both services consume for common task logic. The project uses npm
workspaces to manage the three packages within a single repository, which means
a single `npm install` at the root wires up all internal dependencies via
symlinks in `node_modules`.

## Repository Structure

```
taskflow/
├── Makefile                    # Orchestration entry points (setup, migrate, dev, ...)
├── package.json                # Root manifest: workspaces, engines
├── package-lock.json           # Locked dependency tree
├── .env.example                # Environment variable template
├── .gitignore                  # Ignores node_modules and .taskflow-state.json
├── packages/
│   └── shared/
│       ├── package.json        # @taskflow/shared manifest
│       ├── index.js            # Shared helper implementations
│       └── test/
│           └── shared.test.js  # Unit tests for the shared helpers
├── scripts/
│   ├── migrate.js              # Writes the local state file
│   └── lint.js                 # Parse-checks all workspace sources
└── services/
    ├── api/
    │   ├── package.json        # @taskflow/api manifest
    │   └── server.js           # HTTP server implementation
    └── worker/
        ├── package.json        # @taskflow/worker manifest
        └── worker.js           # Polling worker implementation
```

## Workspace Configuration

The root `package.json` declares two workspace globs, `packages/*` and
`services/*`, which together resolve to three member packages: `@taskflow/shared`
(version 1.2.0), `@taskflow/api` (version 1.2.0), and `@taskflow/worker`
(version 1.2.0). All packages are ES modules (`"type": "module"`). Both service
packages declare a dependency on `@taskflow/shared` at version 1.2.0. The root
manifest is marked `"private": true` so it cannot be published accidentally, and
declares an engines constraint of Node `>=20.6.0`.

## Module Reference

### packages/shared/index.js — `@taskflow/shared`

This package exports three functions used by both services:

| Export | Signature | Behavior |
|--------|-----------|----------|
| `makeId` | `makeId(prefix = "task")` | Returns a string of the form `<prefix>_<n>` where `n` is a module-level counter incremented on each call. The default prefix is `"task"`. |
| `validateTask` | `validateTask(task)` | Returns `false` for non-objects, missing/empty `title` strings, or a `priority` outside `"low"`, `"med"`, `"high"` (a null/undefined priority is allowed). Otherwise returns `true`. |
| `normalizePriority` | `normalizePriority(p)` | Returns `"med"` when `p` is null or undefined; otherwise returns `p` unchanged. |

### services/api/server.js — `@taskflow/api`

The API is built on `node:http`'s `createServer` with no framework. At startup it
resolves the repository root relative to its own file location and checks for
`.taskflow-state.json`; if the file is absent it writes an error to stderr and
exits with code 3, instructing you to run `make migrate` first. It then checks
`process.env.DATABASE_URL` and exits with code 1 if it is unset. The listen port
comes from `process.env.PORT`, defaulting to 8080. Tasks are held in an in-memory
array for the lifetime of the process.

### services/worker/worker.js — `@taskflow/worker`

The worker performs the same state-file existence check as the API (exit code 3
when missing). It then parses the state file and validates the schema version:
only schema 3 is supported, and any other value causes an error message and exit
code 4. Queued tasks are filtered through `validateTask` before polling begins.
The polling interval is read from `WORKER_INTERVAL_MS` and defaults to 5000
milliseconds. On startup it prints a line reporting the interval and pending count.

### scripts/migrate.js

Stands in for real database migrations. It writes `.taskflow-state.json` at the
repository root containing `{ "migratedAt": "fixture-stamp", "schema": 3 }` and
prints a confirmation line. Both the API and the worker refuse to start until
this file exists.

### scripts/lint.js

A minimal lint stand-in: it recursively walks `packages/` and `services/`
(skipping `node_modules` and dot-directories), counts `.js` files, and prints
`lint ok: <count> files`. A real project would run eslint here.

## HTTP API Reference

| Method | Path | Request body | Success response | Error responses |
|--------|------|--------------|------------------|-----------------|
| GET | `/health` | — | `200` JSON `{ "ok": true, "tasks": <count> }` | — |
| POST | `/tasks` | JSON `{ "title": string, "priority"?: "low"\|"med"\|"high" }` | `201` JSON `{ "id", "title", "priority" }` | `400` on malformed JSON ("bad json"); `422` when `validateTask` rejects the body ("invalid task") |
| any | anything else | — | — | `404` ("not found") |

Created task ids are generated by `makeId()` and therefore take the form
`task_1`, `task_2`, and so on within a single process lifetime. A priority
omitted from the request body is normalized to `"med"` by `normalizePriority`.

## Environment Variables

| Variable | Required | Consumer | Default | Notes |
|----------|----------|----------|---------|-------|
| `DATABASE_URL` | yes | api | — | The api exits with code 1 at startup when unset. `.env.example` shows a sample postgres URL. |
| `PORT` | no | api | 8080 | Coerced with `Number()`. |
| `WORKER_INTERVAL_MS` | no | worker | 5000 | Polling interval in milliseconds. |

## Development Workflow

The `Makefile` is the orchestration surface. The full lifecycle from a fresh
checkout is: run `make setup` (which runs `npm install`), then `make migrate`
(which runs `node scripts/migrate.js` and creates `.taskflow-state.json` — the
api and worker refuse to start without it, exiting with code 3), and then
`make dev` (which starts the api and the worker together; both run in the
background via the `api` and `worker` targets). Remember that the api
additionally requires `DATABASE_URL` to be present in the environment.

### Make Targets

| Target | Command it runs | Purpose |
|--------|-----------------|---------|
| `setup` | `npm install` | Install all workspace dependencies |
| `migrate` | `node scripts/migrate.js` | Create the state file (schema 3) |
| `dev` | depends on `api` and `worker` | Run both services |
| `api` | `node services/api/server.js &` | Run the HTTP api alone |
| `worker` | `node services/worker/worker.js &` | Run the worker alone |
| `test` | `node --test packages/*/test/` | Run the test suite (note: there is no root `npm test` script) |
| `lint` | `node scripts/lint.js` | Parse-check workspace sources |
| `clean` | `rm -f .taskflow-state.json` | Remove the state file |

## Testing

Tests use the built-in `node:test` runner with `node:assert/strict` — there is no
external test framework dependency. Today only `@taskflow/shared` has a test
file, `packages/shared/test/shared.test.js`, which contains three tests covering
`validateTask`'s rejection of empty titles, `validateTask`'s rejection of
unknown priorities, and `normalizePriority`'s defaulting behavior. The suite is
invoked with `make test`, which expands to `node --test packages/*/test/`. When
adding tests to another package, follow the same layout: a `test/` directory
beside the package's sources containing `<name>.test.js` files.

## Coding Conventions

- All source files are ES modules; use `import`/`export`, never `require`.
- Sources use double-quoted strings and two-space indentation throughout.
- Node builtin imports use the `node:` prefix (`node:http`, `node:fs`,
  `node:path`, `node:url`).
- Paths are resolved relative to each file via `fileURLToPath(import.meta.url)`
  rather than `process.cwd()`, so the services can be started from any directory.
- Startup failures write a one-line message to stderr and exit with a small
  positive code (1, 3, or 4) rather than throwing.
- Shared logic belongs in `@taskflow/shared`; neither service imports from the
  other.

## Frequently Asked Questions

**Why does the api exit immediately after I start it?** Either the state file is
missing (exit 3 — run `make migrate`) or `DATABASE_URL` is unset (exit 1 — copy
`.env.example` to `.env` and export it, or set it inline).

**Why does the worker exit with code 4?** The state file's `schema` field is not
3. Re-run `make migrate` to rewrite it at the current schema.

**Why does `npm test` not work?** The root manifest defines no `test` script;
the suite is run through the Makefile: `make test`.

**Where is the database?** There isn't one — `migrate.js` stamps a local JSON
state file that stands in for migrations, and the api keeps tasks in memory.

## Contributing

When contributing changes, keep the workspace boundaries intact: helpers shared
by both services go in `packages/shared`, service-specific logic stays in the
service. Run `make lint` and `make test` before committing. Keep the Makefile
the single entry point for developer commands rather than adding parallel npm
scripts.
