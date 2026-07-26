# Turning on nightly automation with `scheduling-doc-sync`

> As of 2026-07-26 (doc-lifecycle contract v2 + bloat scale hardening + distill-lane fan-out + read-only model steps; `plugins/doc-lifecycle/skills/scheduling-doc-sync/SKILL.md`, `doc-sync.yml`, `doc-bloat.yml`)

**You should already have:** run a drift audit or [bloat sweep](auditing-doc-bloat.md)
by hand at least once. Automation is those same loops on a cron with you as the PR
reviewer — if you haven't seen the record shapes interactively, the first automated PR
will read like a robot rewrote your docs overnight. It didn't; but you should know that
*before* it opens, not after. Installing the plugin schedules nothing; this guide is the
explicit opt-in.

## What you're signing up for, exactly

Three GitHub Actions, installed by the skill (never hand-rolled YAML) — the two doc loops
below, plus a weekly self-upgrade check (`doc-sync-upgrade.yml`, default `0 2 * * 1`) that
opens a review PR when a newer plugin release ships and self-explains when you're current:

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

No workflow ever commits doc edits to your default branch — the skill refuses to
install a direct-commit mode even if asked. The evidence PR *is* the product.

**What the model can and can't do.** Every job that runs a model is read-only: no write
token, no credential left behind by the checkout. It hands its work to the next job as an
artifact — a report, or a patch of its edits. A separate job with the write token, which
runs no model, checks every path in that patch against the paths the report named, applies
it, and stages exactly those. A run whose edits reach anywhere else — your workflow files,
the pipeline's own scripts, code — fails right there: no PR, nothing staged.

What this doesn't do is make the PR's *content* trustworthy without you. The report that
bounds the diff is itself written by a model, so a badly confused run can still propose a
wrong edit to a doc it was allowed to name. Reviewing the PR is still the point — what
changed is that a run can no longer reach past your docs to the wiring, your code, or your
default branch.

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
four knobs — the three crons and the blast-radius cap; defaults are fine — and stages
fifteen files for you to commit: the three workflows, the gate/render/planning scripts,
the path-authority script, the two output validators, a starter `audit-scope.json`, a
starter `drift-waivers.json`, the sync marker, and the version lockfile.

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
- Remove: delete the three `doc-*` files under `.github/workflows/`. Leave
  `.github/doc-sync-marker` in place — it records the last synced commit, and a later
  reinstall resumes from it instead of re-auditing history.
