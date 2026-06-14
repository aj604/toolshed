# CLAUDE.md

Guidance for AI agents working in the TaskFlow repository. See `README.md` for the
full project overview.

## What this is

TaskFlow is an npm workspaces monorepo (Node `>=20.6.0`, ES modules). Three
workspaces:

- `services/api` (`@taskflow/api`) — HTTP API, `services/api/server.js`.
- `services/worker` (`@taskflow/worker`) — background poller, `services/worker/worker.js`.
- `packages/shared` (`@taskflow/shared`) — shared helpers, `packages/shared/index.js`.

The api and worker both import from `@taskflow/shared` and both depend on a
local state file, `.taskflow-state.json`, produced by the migration step.

## Commands

All workflows go through the `Makefile`. Prefer these over ad-hoc commands:

- `make setup` — install dependencies (`npm install`).
- `make migrate` — write `.taskflow-state.json` (schema 3). Run before any service.
- `make dev` — start api and worker together.
- `make api` / `make worker` — start a single service.
- `make test` — run tests: `node --test packages/*/test/`.
- `make lint` — `node scripts/lint.js` (verifies every workspace `.js` file parses).
- `make clean` — remove `.taskflow-state.json`.

## Required startup order

`setup` → `migrate` → `dev`. The services enforce this:

- Missing `.taskflow-state.json` → api and worker exit `3`.
- `DATABASE_URL` unset → api exits `1`.
- State `schema` not equal to `3` → worker exits `4`.

If you change the schema in `scripts/migrate.js`, update the check in
`services/worker/worker.js` to match, or the worker will refuse to start.

## Conventions

- ES modules only (`import`/`export`); every `package.json` sets `"type": "module"`.
- Shared logic belongs in `@taskflow/shared`; do not duplicate `makeId`,
  `validateTask`, or `normalizePriority` in the services.
- Task validation rules (`title` required, `priority` in `low`/`med`/`high`) are
  centralized in `validateTask`. Change them there, not in the api handler.
- All workspaces are versioned together (currently `1.2.0`).

## When changing things

- Adding an API route: edit `services/api/server.js`. Reuse shared helpers for
  IDs and validation.
- Changing validation: edit `packages/shared/index.js` and update
  `packages/shared/test/shared.test.js`.
- Run `make lint` and `make test` before considering a change done.

## Known constraints

- Tasks are stored in memory in the api; there is no persistence layer yet.
- Only `@taskflow/shared` currently has tests.
