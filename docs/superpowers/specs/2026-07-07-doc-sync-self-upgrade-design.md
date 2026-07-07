# Design — Pinned wiring + self-upgrade PR for doc-sync installs

**Date:** 2026-07-07
**Status:** approved (runtime shape); skill-side to build test-first via `superpowers:writing-skills`

## Problem

The installed doc automation has two components that share a versioned contract but move on
different cadences:

- **Skills** execute via `plugin_marketplaces: https://github.com/aj604/toolshed.git` (unpinned),
  so they float at toolshed **main** on every run.
- **Vendored wiring** — the two workflow YAMLs plus the five scripts copied into
  `.github/doc-sync/` — is **frozen at install time**.

When the skill contract advances on main but the frozen wiring doesn't, runs break. Concretely:
this drove the 2026-07-07 RED doc-bloat runs.

## Fix (chosen)

Pin both components to a release tag so they move in lockstep, and ship a self-upgrade job that
turns "wiring fell behind" into a waiting, reviewable PR — Dependabot-for-your-wiring. Detection
*is* regeneration: running the upgrade re-copies shipped wiring at the new version, and `git diff`
is the divergence signal. No separate compare-shipped-vs-vendored logic.

Two rejected alternatives: (a) *freshen wiring only*, leaving skills floating — narrows but doesn't
close the cadence gap; (b) a separate second workflow vs. a step in `doc-sync.yml` — rejected in
favor of a dedicated third workflow for concurrency/run-surface isolation, matching the existing
doc-sync/doc-bloat separation.

## Runtime design (approved)

### Pinning

All three installed workflows (`doc-sync.yml`, `doc-bloat.yml`, new `doc-sync-upgrade.yml`) carry
a pinned marketplace ref:

```yaml
plugin_marketplaces: https://github.com/aj604/toolshed.git#vX.Y.Z
plugins: doc-lifecycle@toolshed
```

The `#ref` fragment on `plugin_marketplaces` takes a git tag (confirmed against the CLI
`marketplace add` docs) — pinning the marketplace checkout at the tag pins the plugin content it
serves. The `plugins:` selector stays **unversioned**: `claude-code-action` does not support a
`@version` selector there (`doc-lifecycle@toolshed@0.7.0` is invalid — both RED baseline agents
guessed it and both were wrong). Skills stop floating; nightly/weekly runs are reproducible at the
reviewed version.

**Lockfile:** `.github/doc-sync/installed-version` — a single line holding the bare `plugin.json`
version (e.g. `0.7.0`), the machine-readable "what version is my wiring." Written by the installer
(straight from `jq .version`), updated only by a merged upgrade PR. The pin ref and the release
compare add/strip the `v`. Avoids parsing the pin back out of YAML.

### Upgrade workflow (`doc-sync-upgrade.yml`)

- **Trigger:** weekly cron (default `0 5 * * 1`, knob `{{UPGRADE_CRON}}`) + `workflow_dispatch`.
- **Concurrency group:** `doc-sync-upgrade` — isolated from nightly drift and the bloat sweep.
- **Permissions:** `contents: write`, `pull-requests: write`, `id-token: write`.
- **Steps:**
  1. `actions/checkout@v4`.
  2. Resolve versions: `LATEST=$(gh release view --repo aj604/toolshed --json tagName --jq .tagName | sed 's/^v//')`;
     `CURRENT=$(cat .github/doc-sync/installed-version)`.
  3. **Gate (tested `upgrade-gate.py compare --current "$CURRENT" --latest "$LATEST"`):** prints one
     token — `current` (>=, nothing to do), `upgrade` (latest strictly newer), or `ahead` (install
     newer than any release — a dev/prerelease pin; skip, never downgrade); malformed input exits
     nonzero (fail red). `current`/`ahead` → `render-report.py upgrade-summary` self-explains and
     exits 0. Semver-tuple compare lives in the tested script, not YAML string-fu (RED baseline
     surfaced this; matches the repo's thin-YAML rule).
  4. `upgrade` → `anthropics/claude-code-action@v1` pinned at `#v$LATEST`, running `scheduling-doc-sync`
     **headlessly in upgrade mode** targeting `$LATEST`. The skill regenerates the wiring files at
     `$LATEST`, rewrites every `plugin_marketplaces` pin to `#$LATEST`, sets `installed-version` to
     `$LATEST`, and **preserves** the marker, `audit-scope.json`, and the cron/cap/bloat-cron knobs.
     `claude_args` allowlist: `Read,Grep,Glob,Edit,Write,Bash(git *),Bash(python3 *)`.
  5. Workflow owns git mechanics (mirroring `doc-sync.yml`'s sync-PR step): `git diff --quiet` → if
     changed, push branch `doc-sync/upgrade` and open a PR whose body (`render-report.py
     upgrade-pr-body --current … --latest … `) shows `CURRENT → LATEST` and the changed files; if
     unchanged, `upgrade-summary --status noop` (defensive — version differed but files didn't).

**Split of duties** matches the drift lane: the model regenerates files; the workflow resolves
versions, gates, and does git/PR. Run-surface strings live in `render-report.py` (tested owner),
never inline YAML.

## Skill-side design (`scheduling-doc-sync`) — build test-first

### 1. Pinned templates

`doc-sync.yml` and `doc-bloat.yml` templates gain a `{{PLUGIN_REF}}` placeholder on their
`plugin_marketplaces` lines. The installer substitutes the install-time release tag.

### 2. New template `doc-sync-upgrade.yml`

Ships in the skill base dir alongside the other two. Carries `{{UPGRADE_CRON}}` and `{{PLUGIN_REF}}`.

### 3. Headless upgrade mode

The skill already claims to be "the door for upgrading an existing install." Make that lane explicit
and headless-safe — distinct from first-install:

- **Skips install-only preflight** (secret/label/PR-permission setup) — those are already in place.
- **Regenerates the wiring files** at the target version from the freshly-installed plugin cache:
  the two existing YAMLs, the new `doc-sync-upgrade.yml`, and the five scripts.
- **Rewrites the pin** (`{{PLUGIN_REF}}` → target tag) in all three YAMLs and writes
  `installed-version`.
- **Preserves knobs:** reads the consumer's current `cron` / `CAP` / bloat-cron / upgrade-cron out
  of the installed YAMLs and re-applies them when substituting — never resets to template defaults.
- **Preserves state:** marker and `audit-scope.json` untouched (existing rules).
- **Does not commit/PR** — the workflow owns git. (In interactive first-install the skill still
  guides the human through commit, unchanged.)

### 4. Updated install steps & file list

- Seed `installed-version` (only if absent) with the install-time release tag.
- Copy the new `doc-sync-upgrade.yml`.
- Substitute `{{PLUGIN_REF}}` in all three YAMLs.
- The "files to commit" list grows from nine to **twelve** (`+ doc-sync-upgrade.yml`,
  `+ upgrade-gate.py`, `+ installed-version`).
- Preflight/Rules/Red-flags updated: pinned refs are wiring (overwrite freely on upgrade);
  `installed-version` is the lockfile (advances only via merged upgrade PR); resetting it or
  un-pinning to `main` is a red flag.

## Script + test changes

- **New `scripts/upgrade-gate.py`** (stdlib-only, mirrors `sync-gate.py`): `compare --current
  --latest` → prints `current` / `upgrade` / `ahead`; malformed/empty input exits nonzero (fail
  red, like `validate-drift-output.py`). New `tests/scripts/upgrade-gate_test.py` covers each bump
  (patch/minor/major), equal, `ahead`, and each malformed-input class. Wire it into `release.yml`'s
  Unit tests step. Copied to `.github/doc-sync/upgrade-gate.py` on install.
- `render-report.py`: add `upgrade-summary` (statuses `current` / `ahead` / `noop`) and
  `upgrade-pr-body` subcommands. Cases added to `tests/scripts/render-report_test.py`.
- Sync the dogfood copy: `.github/doc-sync/render-report.py` and the new `upgrade-gate.py` must
  match the skill's copies (existing duplication; both exercised by their `tests/scripts/` tests).

## Dogfood install (this repo's `.github/`)

Apply the same install to toolshed itself:

- Add `.github/workflows/doc-sync-upgrade.yml`.
- Pin `plugin_marketplaces` in `.github/workflows/doc-sync.yml` and `doc-bloat.yml` to the current
  release tag.
- Add `.github/doc-sync/installed-version` (current release tag).
- Sync `.github/doc-sync/render-report.py`.

Note: dogfooding the *upgrade* workflow in the plugin's own source repo is slightly circular (it
would try to upgrade toolshed's wiring against toolshed's own releases). Acceptable — its gate reads
`installed-version` vs. latest release and no-ops when equal; it exercises the same path a consumer
sees.

## Test-first process

Skill changes go through `superpowers:writing-skills` RED → GREEN → REFACTOR with fresh subagents;
baselines land under `tests/baselines/` in a new milestone dir. Script changes are TDD'd against
`render-report_test.py`. Per repo convention, an author never grades their own RED/GREEN — a fresh
grader with the answer key does.

## Open risk

The `#ref` fragment is documented for the CLI `marketplace add`; the claude-code-action input docs
don't state it explicitly ([anthropics/claude-code#10571](https://github.com/anthropics/claude-code/issues/10571)).
**Verify in a live run.** Fallback if the Action ignores the fragment: a `git clone --branch <tag>`
step in each workflow pointing `plugin_marketplaces` at a local checkout path — heavier wiring, same
pin guarantee.
