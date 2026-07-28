# Turning on nightly automation with `scheduling-doc-sync`

> As of 2026-07-27 (doc-lifecycle 0.38.0, engine-based audit and apply lanes; `plugins/doc-lifecycle/skills/scheduling-doc-sync/SKILL.md`, `plugins/doc-lifecycle/skills/scheduling-doc-sync/doc-audit.yml`, `plugins/doc-lifecycle/skills/scheduling-doc-sync/doc-apply.yml`)

**You should already have:** run a drift audit by hand at least once, and landed a
`.doc-lifecycle/registry.json` — the manifest that says which files are documentation
and what each one owes. Automation is the same loop on a cron with you as the reviewer;
if you haven't seen the record shapes interactively, the first automated report will read
like a robot audited your docs overnight. It did; but you should know what that looks
like *before* it happens, not after. Installing the plugin schedules nothing — this guide
is the explicit opt-in.

## What you're signing up for, exactly

Three GitHub Actions, installed by the skill (never hand-rolled YAML). The split between
them is the whole design: **the one that runs on a schedule cannot write, and the one
that writes cannot start without you.**

**Nightly audit** (`doc-audit.yml`, default `0 1 * * *`) — read-only, every night:

- A deterministic step derives the scope from your registry, so you can re-derive what a
  run examined instead of taking its word for it.
- The model audits each document's assertions and cites evidence for every verdict.
- The engine validates the result and publishes it as a **report artifact** plus a job
  summary. Clean, findings, partial, stale, invalid — each is a named outcome that says
  so out loud. A run that produced no report at all says *that*, rather than rendering
  an empty result that reads like good news.
- Nothing is committed. No branch, no PR, no issue. The lane holds no write permission
  at all.

**Manual apply** (`doc-apply.yml`) — dispatch only, never scheduled:

- You read a report, pick the record digests you approve, and dispatch the workflow with
  them. That selection *is* the approval; nothing else authorizes an edit.
- Before anything is planned, a deterministic job re-checks the report against the
  repository as it is *now*. A base that moved, a registry that changed, a line whose
  text no longer matches — any of those refuses right there, naming what moved. No
  branch and no PR exist to review.
- Then a model authors an edit plan, and a separate credentialed job applies it, stages
  exactly the paths the engine's verified result named, and opens a **real pull
  request** — not a draft. Merging it is what lands anything.

**Weekly self-upgrade** (`doc-sync-upgrade.yml`, default `0 2 * * 1`) — compares your
installed version to the plugin's latest release, regenerates the wiring at a newer one,
and opens a review PR. When you're already current it self-explains and stops. It runs no
model at all; the regeneration is a tested script.

**What the model can and can't do.** Every job that runs a model is read-only: no write
token, no credential left behind by the checkout. It hands its work to the next job as an
artifact — a report, or an edit plan. The jobs that hold the write token run no model, and each
stages an explicit list of paths that something deterministic declared in advance — the engine's
verified apply result in one lane, the upgrade script's own record of what it wrote in the other.
A run whose changes reach anywhere else — your workflow files, the pipeline's scripts, code —
stops there, naming what it found, having committed and pushed nothing.

What this doesn't do is make a pull request's *content* trustworthy without you. The
report that bounds the diff is model output too, so a confused run can still propose a
wrong edit to a document it was allowed to name. Reviewing the PR is still the point —
what changed is that nothing reaches your default branch, your wiring, or your code
without passing through a diff you merged.

**Proof it behaves:** this repo dogfoods the install — `.github/workflows/doc-audit.yml`,
`doc-apply.yml`, and `doc-sync-upgrade.yml`, with the vendored wiring under
`.github/doc-sync/`.

## Turning it on

> set up doc sync

The skill runs preflight first and reports anything missing rather than silently
skipping: a GitHub remote, `gh auth status`, a model-auth secret
(`CLAUDE_CODE_OAUTH_TOKEN` via `/install-github-app`, or `ANTHROPIC_API_KEY`), and the
repo setting that lets Actions create PRs. It then confirms two knobs — the audit cron
and the upgrade cron; defaults are fine — and stages fifteen files plus a vendored copy
of the engine: the three workflows, eight scripts, three starter state files
(`audit-scope.json`, `drift-waivers.json`, `evidence-tools.json`), and the version
lockfile.

If you have no registry yet, the skill stops and sends you through its migration door
first — a guided, read-only sequence that drafts one from your existing layout, shows you
the diff as globs, and dry-runs it until nothing is unclassified. Both audit lanes are
closed-world over that file, so installing them without one would ship wiring that fails
every night.

First run without waiting for the cron:

```
gh workflow run doc-audit
```

## Reviewing and applying

The audit lane deliberately stops at a report. Applying is a second, deliberate act:

1. Open the run, read the job summary, and download the `audit-report` artifact.
2. Decide which records you accept, by digest.
3. Dispatch the apply lane with them:

```
gh workflow run doc-apply \
  -f report_run_id=<the audit run's id> \
  -f report_digest=<the report's digest> \
  -f records="<digest> <digest>" \
  -f base=main
```

4. Review the pull request it opens, and merge it — or don't. Its commit carries the
   approval set's digest, so what you approved and what landed are checkable against each
   other later.

## Tuning and living with it

- **Scope:** `.doc-lifecycle/registry.json` decides what counts as documentation and what
  each kind owes. It's consumer judgment — the upgrade lane never touches it.
- **Evidence tools:** `.github/doc-sync/evidence-tools.json` is empty by default. A
  verdict may cite a command only for a program listed there, and only as a
  `--help`/`--version` read. Tool-free is the honest default; widen it deliberately.
- **Waivers:** `.github/doc-sync/drift-waivers.json` records claims you've accepted as
  unverifiable, matched by the text you quoted. Reword the line and the waiver stops
  applying — new authorship is a new decision.
- **Upgrades:** they arrive as a PR from `doc-sync-upgrade.yml`. To force one, re-run the
  skill; your knobs and state files are preserved, and only the wiring, the pin, and the
  lockfile change.

## Pausing and leaving

Both are one command or one deletion, and neither loses state:

- Pause: `gh workflow disable doc-audit` (and/or `doc-apply`, `doc-sync-upgrade`);
  `gh workflow enable` reverses it.
- Remove: delete the three `doc-*` files under `.github/workflows/`. Leave
  `.doc-lifecycle/registry.json` and the state files under `.github/doc-sync/` in place —
  they are your judgment, not the pipeline's, and a later reinstall resumes from them.
