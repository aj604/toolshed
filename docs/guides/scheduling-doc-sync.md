# Turning on nightly automation with `scheduling-doc-sync`

> As of 2026-07-09 (doc-lifecycle contract v2 + bloat scale hardening + distill-lane fan-out; `plugins/doc-lifecycle/skills/scheduling-doc-sync/SKILL.md`, `doc-sync.yml`, `doc-bloat.yml`)

**You should already have:** run a drift audit or [bloat sweep](auditing-doc-bloat.md)
by hand at least once. Automation is those same loops on a cron with you as the PR
reviewer — if you haven't seen the record shapes interactively, the first automated PR
will read like a robot rewrote your docs overnight. It didn't; but you should know that
*before* it opens, not after. Installing the plugin schedules nothing; this guide is the
explicit opt-in.

## What you're signing up for, exactly

Two GitHub Actions, installed by the skill (never hand-rolled YAML):

**Nightly drift sync** (`doc-sync.yml`, default `0 3 * * *`):

- No drift found → a marker-only commit recording the synced SHA. Nothing else.
- Drift found → an **evidence PR** on `doc-sync/nightly`: each fix tied to its record,
  verdicts and evidence in the body. You review and merge like any PR.
- More than the blast-radius cap (default 10) → a `doc-sync`-labeled **issue** instead
  of an oversized PR. Big messes get escalated to a human, not auto-landed.

**Weekly bloat sweep** (`doc-bloat.yml`, default `0 4 * * 1`, Mondays):

- The sweep is chunked, bounded, and convergent: a deterministic script plans the
  chunks (content-addressed, each with its own turn budget — big planning docs get more
  turns than small READMEs), one model invocation audits each with its slice handed
  verbatim in the prompt, and every chunk result is validated where it is produced. A
  failed attempt is retried once — with a bigger budget if it ran out of turns, fresh
  otherwise — and a chunk that fails twice costs only its own docs: the report lands
  anyway with a loud "unswept" banner naming them, and the next run re-audits exactly
  the missing or changed chunks (valid results survive as artifacts and are carried
  forward).
- Findings are split into two lanes — `doc-bloat/prune` (passage-level cuts/condenses/
  moves) and `doc-bloat/distill` (doc-level merges/retires/distills, plus directory-level
  `POLICY` records) — and each lane opens at most one **draft PR**. The distill lane
  *applies* the same fanned-out way the sweep detects: record groups run as parallel
  jobs (uncapped — an apply is never truncated mid-judgment), a deterministic merge
  lands their commits, and any record that couldn't land is named in a PR banner and
  re-proposed by the next sweep. Draft means nothing
  merges without you; a lane with no findings, or whose PR is still open from last week,
  skips itself with a self-explaining run summary.

Neither workflow ever commits doc edits to your default branch — the skill refuses to
install a direct-commit mode even if asked. The evidence PR *is* the product.

**Proof it behaves:** this repo dogfoods the install (`.github/workflows/doc-sync.yml`);
its first nightly caught real drift and opened
[the evidence PR](https://github.com/aj604/toolshed/pull/5) — full record:
[`DOGFOOD-first-catch.md`](../../tests/baselines/doc-sync-setup-red/DOGFOOD-first-catch.md).

## Turning it on

> set up doc sync

The skill runs preflight first and reports anything missing rather than silently
skipping: a GitHub remote, `gh auth status`, a model-auth secret
(`CLAUDE_CODE_OAUTH_TOKEN` via `/install-github-app`, or `ANTHROPIC_API_KEY`), the
`doc-sync` label, and the repo setting that lets Actions create PRs. It then confirms
three knobs — the two crons and the blast-radius cap; defaults are fine — and stages
nine files for you to commit: the two workflows, the gate/render scripts, the chunk
planner, the two output validators, a starter `audit-scope.json`, and the sync marker.

First run without waiting for the cron:

```
gh workflow run doc-sync
gh workflow run doc-bloat
```

## Tuning and living with it

- **Scope:** `.github/doc-sync/audit-scope.json` holds `include`/`exclude` globs the
  weekly sweep reads (this repo excludes `tests/fixtures/**` and `tests/baselines/**`),
  plus optional `policy_scope` directories (each swept as one `POLICY` record instead of
  file-by-file) and `chunking` caps — the planner's docstring documents them.
- **CI on sync PRs:** there are none by default — the pipeline pushes with
  `GITHUB_TOKEN`, which never retriggers CI. If checks on doc PRs matter to you, mint a
  GitHub App token instead (the skill's install notes cover it).
- **Upgrades:** re-run the skill. Workflows and scripts are refreshed; the marker — the
  state recording your last synced commit — is always preserved.

## Pausing and leaving

Both are one command or one deletion, and neither loses state:

- Pause: `gh workflow disable doc-sync` (and/or `doc-bloat`); `gh workflow enable`
  reverses it.
- Remove: delete the two files under `.github/workflows/`. Leave
  `.github/doc-sync-marker` in place — it records the last synced commit, and a later
  reinstall resumes from it instead of re-auditing history.
