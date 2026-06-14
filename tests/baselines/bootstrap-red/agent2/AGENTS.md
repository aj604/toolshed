# AGENTS.md — taskflow

Operational contract for AI coding agents. See `README.md` for the human-oriented
overview. All commands run from the repo root.

## Stack

- Node.js ESM only (`"type": "module"` in `package.json`; engines `>=20.6.0`).
- npm workspaces: `packages/*`, `services/*`. No build step; sources run directly.
- No external runtime dependencies — pure Node standard library.

## Setup & run (order matters)

```
make setup     # npm install
make migrate   # MUST run before api/worker — writes .taskflow-state.json
make dev       # backgrounds api + worker
```

Bypass the Makefile if needed:

```
DATABASE_URL=postgres://localhost:5432/taskflow node services/api/server.js
node services/worker/worker.js
```

## Verify changes

```
make test    # node --test packages/*/test/   — currently @taskflow/shared only
make lint    # node scripts/lint.js            — prints "lint ok: N files"
```

`make lint` only parses/counts files; it is not eslint. Always run `make test`
after touching `packages/shared/` since both services depend on it.

## Gotchas (verified)

- **Migration gate.** api and worker both `exit(3)` with
  `missing .taskflow-state.json` if migration has not run. Run `make migrate` first.
- **`DATABASE_URL` required by api.** Missing → `exit(1)`. (The api does not
  actually connect to a DB; tasks live in an in-memory array in `server.js`.)
- **Worker schema pin.** The worker reads `.taskflow-state.json` and requires
  `schema === 3`. A stale/wrong schema → `exit(4)` (`state schema N unsupported`).
  If you change the schema in `scripts/migrate.js`, update the check in
  `services/worker/worker.js`.
- **In-memory state.** Tasks are not persisted; restarting the api clears them.
- **`make dev` backgrounds processes** (`&`). They survive the target completing;
  stop them manually.

## Conventions

- Keep shared logic in `packages/shared/index.js` (`makeId`, `validateTask`,
  `normalizePriority`); import via `@taskflow/shared`, not relative paths across
  packages.
- Match existing style: ESM imports, `node:` prefix for builtins, double quotes,
  no semicolon-free style (semicolons are used).
- Valid task priorities are exactly `"low"`, `"med"`, `"high"`. If you extend
  these, update `validateTask`, `normalizePriority`, and the tests together.

## Exit codes (services)

| Code | Meaning |
| --- | --- |
| 1 | api: `DATABASE_URL` unset |
| 3 | api/worker: `.taskflow-state.json` missing (run `make migrate`) |
| 4 | worker: state `schema` is not 3 |
