# taskflow answer key (grading reference — NOT visible to agents documenting the repo)

`taskflow` is a 3-component workspace repo with no docs. Bootstrapping output is
graded on PRIORITIZATION and SCOPE: did it capture the high-leverage facts and
STOP, or did it chase completeness?

## High-leverage facts (an ideal bootstrap CLAUDE.md MUST capture these)

| Fact | Truth | Verify |
|------|-------|--------|
| Setup order | `make setup` → `make migrate` → `make dev` | Makefile |
| Migrate-before-run gotcha | api & worker exit 3 with "run `make migrate` first" if `.taskflow-state.json` absent | run them before migrate |
| Test command | `make test` (`node --test packages/*/test/`) — NOT `npm test` | Makefile |
| Required env | `DATABASE_URL` required (api exits 1 without it); `PORT` optional, default 8080 | server.js / .env.example |
| Architecture (pointers) | 3 parts: `services/api` (HTTP), `services/worker` (poller), `packages/shared` (lib) | tree |
| Node version | `>=20.6.0` | package.json engines |
| Worker schema gotcha | worker needs state schema 3, exits 4 otherwise | worker.js |

## Low-leverage / inferable (completeness traps — should NOT bloat the bootstrap docs)

- Per-file descriptions of every source file.
- Every `@taskflow/shared` helper signature (makeId, validateTask, normalizePriority).
- Every HTTP route's implementation detail.
- Restating package.json / workspace globs.
- Inventing API docs, contribution guides, changelogs, badges.

## What "good" looks like

- A CLAUDE.md that leads with commands + the migrate gotcha + env + arch pointers,
  and is short (an agent can act from it immediately).
- A README skeleton (what it is, setup, the same commands) — human-facing.
- Maybe a one-line note that op runbooks are TODO.
- Stops there. Does not document every file/function.

## Predicted baseline failures (the traps)

- Completeness-chasing: long CLAUDE.md cataloguing every file/function.
- Wrong prioritization: documents helper signatures but misses the migrate gotcha.
- No ordering: dumps everything in one file with no sense of what an agent needs first.
- Inferable bloat: restates the workspace layout / package.json.
- Fabricated/aspirational content: invents API reference, contributing, license sections.
- Guessing `npm test` instead of `make test`.
