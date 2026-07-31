# Turning on nightly automation with `scheduling-doc-sync`

> As of 2026-07-30 (doc-lifecycle 0.45.0, engine-based drift/bloat audits, manual and policy
> apply lanes, install artifacts centralized under `.doc-lifecycle/`, and legacy upgrade cleanup;
> `plugins/doc-lifecycle/skills/scheduling-doc-sync/SKILL.md`,
> `plugins/doc-lifecycle/skills/scheduling-doc-sync/doc-audit.yml`,
> `plugins/doc-lifecycle/skills/scheduling-doc-sync/doc-bloat-audit.yml`,
> `plugins/doc-lifecycle/skills/scheduling-doc-sync/doc-apply.yml`,
> `plugins/doc-lifecycle/skills/scheduling-doc-sync/doc-policy-apply.yml`,
> `plugins/doc-lifecycle/skills/scheduling-doc-sync/scripts/apply-upgrade.py`,
> `plugins/doc-lifecycle/skills/scheduling-doc-sync/scripts/stage-upgrade.py`)

**You should already have:** run a drift audit by hand at least once, and landed a
`.doc-lifecycle/registry.json` — the manifest that says which files are documentation
and what each one owes. Automation is the same loop on a cron with you as the reviewer;
if you haven't seen the record shapes interactively, the first automated report will read
like a robot audited your docs overnight. It did; but you should know what that looks
like *before* it happens, not after. Installing the plugin schedules nothing — this guide
is the explicit opt-in.

## What you're signing up for, exactly

Five GitHub Actions, installed by the skill (never hand-rolled YAML). The split between
them is the whole design: **nothing writes your default branch directly.** The nightly drift
and weekly bloat audits are read-only. If you explicitly configure the policy lane, a successful
scheduled drift audit may produce a branch and a real pull request, but a person must still review
and merge that PR before the default branch changes. The weekly upgrade schedule holds only
`issues: write` and can file one notice issue; running release code and opening an upgrade PR still
requires a human dispatch.

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

**Weekly bloat audit** (`doc-bloat-audit.yml`, default `0 4 * * 1`) — read-only,
Mondays:

- The registry and public bloat plan are checked before a model runs. An invalid or absent
  registry spends no fan-out turns.
- A trusted script renders each engine chunk with its public segmentation evidence and the
  planner's turn budget. The coordinator dispatches those exact prompts to one fresh worker per
  chunk in parallel waves; coordinators and workers have only `Task`, `Read`, `Grep`, and `Glob`.
  Their extra read roots are limited to this audit's temporary directory and the pinned bloat
  skill directory, so the prompts are reachable without granting all runner temporary state.
- Workers return JSON rather than writing files. Another trusted script extracts the pinned
  action's schema-bound `structured_output`, validates every chunk, and selects only the
  missing/invalid ids for one equally read-only fresh retry.
- Plans, chunk results, completion envelopes, reports, and cost data stay under the runner's
  temporary directory, never in the checkout.
- After the workers and their retry stop, a defense-in-depth workflow step checks HEAD plus
  staged, unstaged, ignored, and ordinary untracked files. Any repository mutation fails the run
  before completion assembly; the lane never resets the checkout and publishes a laundered
  report.
- Missing or invalid workers are not treated as clean. Their chunk ids and every affected
  document are bound into the report's typed `incomplete` entries and rendered as PARTIAL; the
  separate unswept sidecar is diagnostic data, not the source of truth.
- Like drift, this lane has `contents: read`, no repository credential, and no commit, branch,
  pull request, or issue path.

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

**Policy apply** (`doc-policy-apply.yml`) — chained only from a successful scheduled drift audit,
and disabled unless you commit `.doc-lifecycle/auto-apply-policy.json`:

- The engine revalidates the exact completed run's report against the current default branch,
  then evaluates the standing policy. No workflow input or model selects records.
- Only `drift-stale-mechanical` and `narrative-anchor-refresh` can be enabled. Bloat, creation,
  retirement, movement, waived findings, missing evidence, and external command evidence remain
  outside autonomous authority.
- An absent policy or a report with no eligible records stops cleanly before the model and
  writer jobs. A malformed policy fails closed with a typed refusal.
- The model authors an edit-plan artifact with no repository credential. A separate model-free
  job applies it through the deterministic engine, stages only the verified paths, and opens a
  **real pull request**, never a draft or a direct default-branch write.
- The PR body says **“No human selected these records.”** PR review is the semantic review for
  what the policy minted, and merging remains change approval of the actual diff.

**Weekly self-upgrade** (`doc-sync-upgrade.yml`, default `0 2 * * 1`) — on the schedule it
only compares your installed version to the plugin's latest release; when one is newer it
files a **notice issue** naming it and stops there (`issues: write` is its only write
scope, one open notice per release). It never regenerates anything or opens a PR on its
own. Regenerating the wiring and opening the review PR happens only when a person
dispatches the same workflow by hand, naming the target version
(`gh workflow run doc-sync-upgrade -f target=X.Y.Z`) — that run clones the target release,
regenerates the wiring in a scratch copy, and a separate credentialed job stages exactly
what changed and opens the PR. When you're already current, either path self-explains and
stops. It runs no model at all; the regeneration is a tested script.

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
`doc-bloat-audit.yml`, `doc-apply.yml`, `doc-policy-apply.yml`, and `doc-sync-upgrade.yml`, with the
vendored wiring under
`.doc-lifecycle/wiring/`.

**Where it all lands.** Everything but the workflows lives under `.doc-lifecycle/`, split by who
owns the bytes: the files you edit (`registry.json`, `audit-scope.json`, `drift-waivers.json`,
`evidence-tools.json`, and optional `auto-apply-policy.json`) and the version lockfile sit at the
root; `wiring/` holds the scripts and the vendored engine, which the upgrade lane regenerates
wholesale — edit something there and the next upgrade reverts it; `state/` holds what the lanes
wrote. Only the five workflow files stay in `.github/workflows/`, because GitHub reads workflows
from nowhere else.

## Turning it on

> set up doc sync

The skill runs preflight first and reports anything missing rather than silently
skipping: a GitHub remote, `gh auth status`, a model-auth secret
(`CLAUDE_CODE_OAUTH_TOKEN` via `/install-github-app`, or `ANTHROPIC_API_KEY`), and the
repo setting that lets Actions create PRs. It then confirms three knobs — the drift-audit,
bloat-audit, and upgrade crons; defaults are fine — plus a separate policy choice whose default is
disabled. It stages fifteen files plus a vendored copy of the engine: the five workflows under
`.github/workflows/`, six scripts under
`.doc-lifecycle/wiring/`, and — at `.doc-lifecycle/` — three starter state files
(`audit-scope.json`, `drift-waivers.json`, `evidence-tools.json`) and the version
lockfile. Enabling policy apply adds the explicitly reviewed policy as a sixteenth file; neither
install nor upgrade ever invents or overwrites one.

If you have no registry yet, the skill stops and sends you through its migration door
first — a guided, read-only sequence that drafts one from your existing layout, shows you
the diff as globs, and dry-runs it until nothing is unclassified. Both audit lanes and both apply
lanes are closed-world over that file, so installing them without one would ship
wiring that fails on every run.

First run without waiting for the cron:

```
gh workflow run doc-audit
gh workflow run doc-bloat-audit
```

## Reviewing and applying

Both audit lanes deliberately stop at reports. `doc-apply.yml` currently binds its dispatch to
the drift lane's `audit-report`; for a scheduled bloat report, download
`bloat-audit-report`, select the record digests, and invoke `fixing-docs` interactively. In
either path, applying is a second, deliberate act and no scheduled job authors a change.

For a drift report:

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

To enable policy apply, commit the standing declaration only after deciding which mechanical
classes this repository permits:

```json
{
  "artifact": "auto-apply-policy",
  "schema_version": 1,
  "id": "nightly-doc-sync",
  "classes": [
    "drift-stale-mechanical",
    "narrative-anchor-refresh"
  ]
}
```

Save it as `.doc-lifecycle/auto-apply-policy.json`. The next successful scheduled drift audit enters
`doc-policy-apply.yml` automatically. Read every resulting PR as a proposed change, not as an
already-approved edit: “No human selected these records” means your PR review is the semantic
review. Removing the file disables future policy runs without affecting the manual lane.

## Tuning and living with it

- **Scope:** `.doc-lifecycle/registry.json` decides what counts as documentation and what
  each kind owes. It's consumer judgment — the upgrade lane never touches it.
- **Bloat budget:** `.doc-lifecycle/audit-scope.json` controls bloat exclusions and chunking.
  It is also consumer judgment: tune the sweep there without editing the workflow, and an
  upgrade preserves it byte-for-byte.
- **Evidence tools:** `.doc-lifecycle/evidence-tools.json` is empty by default. A
  verdict may cite a command only for a program listed there, and only as a
  `--help`/`--version` read. Tool-free is the honest default; widen it deliberately.
- **Waivers:** `.doc-lifecycle/drift-waivers.json` records claims you've accepted as
  unverifiable, matched by the text you quoted. Reword the line and the waiver stops
  applying — new authorship is a new decision.
- **Auto-apply policy:** `.doc-lifecycle/auto-apply-policy.json` is standing authority and is
  absent by default. The upgrade lane carries an existing file unchanged and never seeds one.
- **Upgrades:** the weekly schedule only notices a newer release and files an issue; the PR
  arrives once you (or anyone with dispatch access) run
  `gh workflow run doc-sync-upgrade -f target=X.Y.Z` naming the version from that issue. To
  upgrade from a local checkout instead, re-run the skill; your knobs and state files are
  preserved, and only the wiring, the pin, and the lockfile change.
- **If you installed before 0.40.0:** your wiring is still at `.github/doc-sync/`, and the
  upgrade lane cannot move it — that lane runs *your* installed copy of the path authority,
  which predates the new layout and refuses the change set. Re-run the skill from a local
  checkout to relocate; it carries your judgment files and the sync marker across byte-for-byte
  and leaves anything else in the old directory where it is, naming it on the run surface.

## One-time cleanup after upgrading past 0.37.0

If your install used the legacy write lanes (removed at 0.38.0), an upgrade landing on
0.38.0 or later can leave three legacy artifacts behind. After the upgrade succeeds, they
are safe to remove:

```
git rm --ignore-unmatch \
  .github/workflows/doc-sync.yml \
  .github/workflows/doc-bloat.yml \
  .github/doc-sync/last-stales.json
```

The upgrade lane deliberately leaves the workflow files because its `GITHUB_TOKEN` cannot push
deletions under `.github/workflows/`. It also leaves `last-stales.json` because the installed
pre-upgrade path authority never owned that file; during relocation, `apply-upgrade.py` reports
it as `left in place (not the plugin's to move): .github/doc-sync/last-stales.json`. No current
lane depends on these artifacts. Leaving them in place does not break the current lanes, but keeps
the legacy workflow entries in the Actions tab and may keep the old `.github/doc-sync/` directory
alive.

## Pausing and leaving

Both are one command or one deletion, and neither loses state:

- Pause: `gh workflow disable doc-audit` (and/or `doc-bloat-audit`, `doc-apply`,
  `doc-policy-apply`, `doc-sync-upgrade`);
  `gh workflow enable` reverses it.
- Remove: delete the five `doc-*` files under `.github/workflows/`, and `.doc-lifecycle/wiring/`
  if you want the scripts gone too. Leave the judgment files at `.doc-lifecycle/` in place —
  they are your judgment, not the pipeline's, and a later reinstall resumes from them.
