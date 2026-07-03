# Targeted re-GREEN — scheduling-doc-sync install flow (post-PR #10)

**Trigger:** PR #10 (`ajones/exciting-fermi-eded16`, merged as `34f9941`) substantially edited the
skill after its original GREEN (`doc-sync-setup-red/GREEN-results.md`): the shipped `doc-sync.yml`
now runs detect/fix via `anthropics/claude-code-action@v1`, a new shipped
`scripts/render-report.py` owns all run-surface strings, and SKILL.md's install steps changed
(step 3 copies both `sync-gate.py` and `render-report.py`; "five files to commit"). Per
RED→GREEN convention, post-GREEN skill edits invalidate the GREEN for the shipped text — this is
the targeted re-verify of the affected scenario (install/upgrade flow). Scenarios untouched by
the PR (direct-commit pressure REFACTOR, no-remote preflight stop) were not re-run.

## Method

Fresh general-purpose subagent (Fable 5), prompted only with the realistic ask ("set up doc sync
for this repo") plus the SKILL.md path and no-real-GitHub-side-effects constraints — grading
criteria were not disclosed. Fixture: throwaway copy of `tests/fixtures/taskflow` in a scratch
dir, `git init` + 3 commits, fake origin `https://github.com/example/taskflow-fixture.git`, and a
**pre-existing** `.github/doc-sync-marker` containing commit-1's hash (`c83e03e0…`) with HEAD two
commits ahead (`5c02eb90…`) — so marker preservation is detectable, exercising the upgrade path.
Graded from fixture artifacts by script, not the agent's self-report.

## Artifact checks (13/13 pass)

| Check | Result |
|---|---|
| Five files present: `.github/workflows/doc-sync.yml`, `.github/doc-sync/{sync-gate,render-report,validate-drift-output}.py`, `.github/doc-sync-marker` | **Pass** (5/5) |
| Three scripts byte-identical to shipped (`diff` vs plugin copies, incl. `validate-drift-output.py` from the detecting-doc-drift sibling) | **Pass** (3/3) |
| No literal `{{CRON_SCHEDULE}}`/`{{BLAST_RADIUS_CAP}}` remain | **Pass** |
| Workflow byte-identical to `sed`-rendered template at default knobs (cron `0 3 * * *`, cap 10) | **Pass** |
| Existing marker preserved — still `c83e03e0…`, not reseeded to HEAD | **Pass** |
| Installed workflow parses as YAML (ruby psych) | **Pass** |
| Every `.github/…` path the workflow references exists in the fixture (marker + the 3 scripts — i.e., only files the install created) | **Pass** |

## Behavior notes

- **Preflight:** all five steps run; the three that 404 against the fake remote (secret list,
  label create, Actions-PR permission) were reported explicitly with fix commands, not silently
  skipped; only "no remote" treated as a hard stop, per the skill.
- **Upgrade semantics:** agent named the existing marker as evidence of a prior install and left
  it untouched, quoting the skill's reset-skips-commits rationale.
- **User-facing wrap-up** matched SKILL.md step 6: five files to commit, first-night outcomes,
  `gh workflow run doc-sync`, upgrade path, and the no-CI-on-sync-PRs caveat.
- Nothing committed; nothing outside the fixture modified; no `gh repo create` workaround.

## Harness notes (for honesty)

- Two initial grader false-positives, both in the verify script, not the install: a bare `{{`
  grep also matched GitHub's `${{ … }}` expressions, and system ruby 2.6's `YAML.load_file`
  rejects the `aliases:` kwarg. Fixed the checks; install artifacts were unchanged.
- The subagent noticed a stale `scheduling-doc-sync` copy cached under `~/.claude/skills/` (an
  older revision without `render-report.py`) and correctly used the repo-path SKILL.md it was
  given. Stale local deploys are a test-environment hazard, not a skill defect.

**Verdict: re-GREEN pass, first iteration.** No skill edits needed.
