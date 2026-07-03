# doc-sync PR body tightening — design

**Date:** 2026-07-03
**Motivation:** The first dogfooded nightly PR (#6-era, range `bd91cb6..3983574`) was correct
but bloated: a 6-word doc change arrived with five sentences of evidence narrative, the old
claim and the applied fix restated in the body (both already visible in the diff), and nested
bullets that scale badly past one record. Same information, tighter, presented better.

## Changes

### 1. Evidence brevity bar (`detecting-doc-drift`)

The output contract's worked example is already terse (``Makefile has `clean:`, no `reset`
target``) but nothing forbids narrative sprawl. Add a rule to `SKILL.md` (with the other
evidence rules) and `output-contract.md`:

> `evidence` is one line: pointer + the contradicting fact. No history (prior PRs, how the
> claim came to be stale), no restated command output, no reasoning narrative — the record's
> verdict carries the conclusion; evidence carries only what proves it.

No new fields, no validator length cap (a hard cap could fail a nightly run on legitimately
two-pointer evidence; the skill bar plus the existing terse exemplars carry it).

### 2. Table-format PR body (`doc-sync.yml`, "Open sync PR" step)

Replace the nested-bullet body with:

```markdown
Nightly doc sync over `<marker>..<head>` — merge to advance the marker, close to re-check next run.

| Fixed (see diff) | Why it was stale |
|---|---|
| `CLAUDE.md:9` | `release.yml` (added in 8c439c6) is runnable but missing from the list |

| Flagged for a human — not edited | Why unverifiable |
|---|---|
| `tests/.../DOGFOOD-first-catch.md:6` | run ID 28617674431 is an external GitHub artifact; not checkable in-repo |
```

- STALE rows: location + `evidence` only. The old claim and replacement text are dropped from
  the body — the PR diff is the change; the body answers "why".
- UNVERIFIABLE rows (section emitted only when nonempty): location + `evidence`. These are not
  in the diff, so evidence is the whole story.
- `jq` escapes `|` in cell text so evidence can't break the table.
- One row per record; row height is constant because of change 1. The blast-radius cap bounds
  table length.

The blast-radius **issue** body keeps its current structure (it has no diff to lean on, so it
retains the drafted fix text); it inherits the tighter evidence automatically.

### 3. PR title with counts

`docs: nightly sync — 2 fixes, 1 flagged (2026-07-03)`

- Singular/plural handled (`1 fix`); `, N flagged` omitted when zero.
- Branch commit message stays `docs: sync with <branch> (<date>)` — conventional-commit
  tooling reads commits, not PR titles.

Both change 2 and 3 land in the plugin template
(`plugins/doc-lifecycle/skills/scheduling-doc-sync/doc-sync.yml`, the owner) and the dogfooded
copy (`.github/workflows/doc-sync.yml`) in the same commit.

## Verification

- `python3 tests/scripts/validate-drift-output_test.py` and
  `python3 tests/scripts/sync-gate_test.py` — must stay green (contract fields and gate wiring
  untouched).
- Targeted re-GREEN of `detecting-doc-drift` (per `tests/baselines/` convention): one subagent
  scenario that previously invited narrative evidence (a claim staled by a commit with prior
  fix history) — assert the emitted evidence is one line, no history.
- Render check of the new body: run the `jq` table construction against the real
  `drift-report.json` from the dogfooded run (or a fixture reproducing it) and eyeball the
  markdown, including a `|` in evidence.

## Non-goals

- No new drift-report contract fields; no validator length cap.
- No `<details>` raw-report block in the PR body (the run's artifact already holds the JSON).
- No change to step summaries, gate logic, marker mechanics, or the blast-radius issue format.
