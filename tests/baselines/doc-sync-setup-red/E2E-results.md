# E2E — scheduling-doc-sync pipeline on a live GitHub repo

Test surface: `aj604/doc-sync-e2e` (private scratch repo, user-created 2026-07-02; taskflow
fixture + accurate `bootstrap-green/agent1` docs). Installer run by a fresh Sonnet agent using
the deployed skill against the real remote. **E2E-only tweak:** the installed workflow's
`claude plugin marketplace add aj604/toolshed` was replaced with a `git clone --branch
claude/sweet-mendel-db0fb9` + local-path marketplace add, since this work predates its own
merge to main. Planted drift (2 commits): Makefile `clean:` → `reset:`;
`services/worker/worker.js` stale-schema `exit(4)` → `exit(5)`.

## Installer (real-remote run)

All four files installed (verified against the GREEN diff procedure), knobs at defaults
(`0 3 * * *`, cap 10), marker seeded at pre-install HEAD, fresh-seed vs upgrade correctly
distinguished. Preflights: remote PASS, gh auth PASS, secret **WARN (absent — reported, not
blocked)**, label PASS.

## Runs

| Run | Result | What it proved / found |
|-----|--------|------------------------|
| [28611660789](https://github.com/aj604/doc-sync-e2e/actions/runs/28611660789) | red at "Open sync PR" | **Bug 1 (template):** `\`` is an invalid escape inside the single-quoted jq render programs. Failed *safe*: jq died before branch/commit; marker untouched; report artifact uploaded. Fixed in toolshed `6cd8869` (all 3 jq programs verified against a sample report). |
| [28611896783](https://github.com/aj604/doc-sync-e2e/actions/runs/28611896783) | red at "Open sync PR" | **Bug 2 (missing preflight):** repo-level "Allow GitHub Actions to create and approve pull requests" is off by default and the workflow `permissions:` block cannot override it. Branch pushed, PR create refused; fail-loud held. Preflight #5 added in toolshed `c693962`. |
| [28612469607](https://github.com/aj604/doc-sync-e2e/actions/runs/28612469607) | **green** | Full pipeline: detect → validate → gate `proceed` → fix → PR [#1](https://github.com/aj604/doc-sync-e2e/pull/1). Also exercised the stale-branch `--force` push path (run 2's leftover branch). |
| [28612651476](https://github.com/aj604/doc-sync-e2e/actions/runs/28612651476) | **green (skip)** | **Idempotency (a):** PR open → pre-gate `skip-pending`; install/detect/fix/PR all skipped; zero model calls. |
| [28612702192](https://github.com/aj604/doc-sync-e2e/actions/runs/28612702192) | **green (clean)** | **Idempotency (b):** PR merged → detect over the merged range → 0 stale → "Advance marker (no drift in 2 commit(s))" direct commit; no new PR; 0 open PRs after. |

## PR #1 verification (the payoff)

- **Recall:** both planted drifts caught, **plus a third legitimate record** — the rename also
  invalidated `README.md:55` (`make clean` in the quickstart), which was not deliberately
  planted. Not a false positive; the answer key was incomplete, not the detection.
- **Evidence mapping:** each applied fix cited `file:line` evidence (`Makefile:28-29`,
  `worker.js:20`) and named the causing range commit.
- **Diff hygiene:** exactly `CLAUDE.md`, `README.md`, `.github/doc-sync-marker` — no
  `drift-report.json`, no `pr-body.md`, marker advanced to the detected HEAD inside the PR.

## Observations (not defects)

- **Anchors don't self-heal:** the exit-code record's drafted fix corrected the number but not
  the doc's `worker.js:17` anchor (code moved to :20); the fixer applied the fix verbatim per
  its scope rules. Anchors heal only when detection flags them as their own claims.
- **Sync PRs carry no CI checks** under the default `GITHUB_TOKEN` (commits from it don't
  retrigger workflows). Documented in the skill's install guidance with the App-token remedy.
- Actions-created PR permission and the API-key secret are the two irreducible user/admin
  actions; both are now preflighted (WARN with the exact command).

## Verdict

Pipeline verified end to end on real infrastructure: detect/gate/fix/PR, evidence contract,
artifact hygiene, fail-loud semantics (two red runs, zero half-applied state), both
idempotency behaviors, stale-branch recovery, and the installer's real-remote preflights.
Two real defects found and fixed at the source (toolshed `6cd8869`, `c693962`) — both in the
category local tests could not reach, which is what the E2E was for.
