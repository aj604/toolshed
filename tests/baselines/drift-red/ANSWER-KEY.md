# drift-red answer key (grading reference — NOT shown to baseline agents)

Drifted doc: `drifted-CLAUDE.md`. Repo under test: `tests/fixtures/taskflow/`.
Derived from the known-good `tests/baselines/bootstrap-green/agent1/CLAUDE.md`, with
planted claims. Every claim below is tagged kind + verification tier + verdict.

A drift audit is graded on:
- **Recall** — of the 6 STALE claims, how many flagged as wrong?
- **False-VERIFIED rate** — how many STALE claims were passed as accurate (the core failure)?
- **Evidence discipline** — was each verdict backed by grep/command/code-read evidence, or asserted from "looks consistent"?
- **Precision** — were any of the 6 TRUE claims wrongly flagged as drift?
- **UNVERIFIABLE detection** — was the vague claim flagged as uncheckable (a doc smell)?

## STALE — planted drift (must be caught) — 6

| ID | Claim in doc | Truth | Kind | Tier | Evidence |
|----|--------------|-------|------|------|----------|
| S1 | Reset state = `make reset` | target is `make clean`; no `reset` target | command | 1 (grep Makefile) | `Makefile` has `clean:`, no `reset:` |
| S2 | api listens on port `3000` by default | default is `8080` | value | 2 (read line) | `services/api/server.js:21` `Number(process.env.PORT) || 8080` |
| S3 | worker accepts state schema `2`, else exit `5` | needs schema `3`, exits `4` | behavior/value | 2 (read worker) | `services/worker/worker.js:17-19` `schema !== 3 → exit 4` |
| S4 | successful `POST /tasks` returns `200` | returns `201` | behavior | 3 (read handler) | `services/api/server.js:49` `res.writeHead(201, …)` |
| S5 | `packages/shared/index.js` exports include `formatTask` | only `makeId`, `validateTask`, `normalizePriority` | symbol | 1 (grep) | `packages/shared/index.js` — no `formatTask` |
| S6 | migrate script is `scripts/setup-db.js` | file is `scripts/migrate.js`; no `setup-db.js` | path | 1 (glob) | `scripts/migrate.js` exists; `scripts/setup-db.js` does not |

## TRUE — must NOT be flagged (precision) — 6

| ID | Claim in doc | Evidence it's accurate |
|----|--------------|------------------------|
| T1 | Install deps = `make setup` (runs `npm install`) | `Makefile` `setup: npm install` |
| T2 | `make test` runs `node --test packages/*/test/` | `Makefile` `test:` recipe |
| T3 | Node `>=20.6.0` required | `package.json` engines |
| T4 | api requires `DATABASE_URL` or exits `1` | `services/api/server.js:16-18` |
| T5 | Missing state → api & worker exit `3` | `server.js:12-14`, `worker.js:10-12` |
| T6 | api routes `/health` and `POST /tasks` | `services/api/server.js:25,30` |

## UNVERIFIABLE — should be flagged as uncheckable doc smell — 1

| ID | Claim in doc | Why |
|----|--------------|-----|
| U1 | "worker is reasonably fast and handles most workloads without tuning" | no metric, no threshold — nothing to check against the repo |

## Predicted baseline failures (RED hypothesis)

- **False-VERIFIED on behavioral drift** (S3, S4): passes the schema/exit-code and 201/200
  claims without reading worker.js / the handler — "looks consistent with a CRUD API."
- **Evidence-free passes**: declares the doc "accurate" / claims VERIFIED without showing
  grep or command output for each claim.
- **Misses the anchored-but-wrong claims**: file:line anchors (e.g. `server.js:21`) lend
  false credibility; agent trusts the anchor instead of opening the line.
- **No tiering**: either eyeballs everything (under-verifies, misses S2–S4) or boots the
  whole app to check trivially-greppable claims (over-verifies S1, S5, S6).
- **UNVERIFIABLE not surfaced**: U1 silently accepted as harmless prose rather than flagged.
