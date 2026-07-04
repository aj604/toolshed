# doc-bloat full-audit inventory tool — design

## Problem

The first `doc-bloat.yml` run (workflow run `28686984185`, 2026-07-03) failed at the
`Assert detect produced a report` step: the detect job's Claude ran to `success`
(17 turns, `is_error: false`) with **2 permission denials** and never wrote
`bloat-report.json`, so the assert failed and the prune/distill lanes were skipped.

Root cause: the detect step's allowlist —
`Read,Grep,Glob,Write,Bash(git *),Bash(python3 *)` — was copied verbatim from the
doc-sync (drift) workflow. That allowlist fits drift because drift is *diff-scoped*
and enumerates its scope with `git diff` (covered by `Bash(git *)`). doc-bloat runs a
**full audit of every doc**, and to inventory the repo the model reaches for `find` /
`ls`, which match neither `Bash(git *)` nor `Bash(python3 *)` → denied. Reproduced: the
first tool call after loading the skill was `Bash: find . -name "*.md" ...`. A second
latent denial: `detecting-doc-bloat` tells the model to run the validator as a bare
executable path (`${CLAUDE_PLUGIN_ROOT}/.../validate-bloat-output.py`), also not
`python3 …` → denied.

Two secondary observations from reproduction:

- **Scope explosion** — a raw `*.md` sweep of this repo returns ~149 files, the vast
  majority under `tests/baselines/**` and `tests/fixtures/**`, which are test records
  and fixtures, not docs to audit. The inventory step has no notion of "docs in scope."
- **Truncation** — 17 turns is far too few for a real full audit (an unconstrained
  local run was past 190 events / 18 reads on the same job), confirming the CI run was
  shallow, not thorough.

## Fix

Replace the improvised shell inventory with a deterministic `python3` helper the skill
calls, and correct the validator invocation so both commands the skill drives fall
under the existing `Bash(python3 *)` grant. The workflow allowlist does **not** change —
the fix lives in the skill, keeping the YAML thin.

### 1. Helper — `plugins/doc-lifecycle/skills/detecting-doc-bloat/scripts/list-docs.py`

- **Purpose:** emit the in-scope doc paths so the model never enumerates with shell
  `find`/`ls`.
- **Contract:** `python3 list-docs.py [--config PATH] [--root DIR]` → prints
  repo-relative doc paths, one per line, sorted, to stdout.
- **Algorithm:**
  1. Candidate universe = `git ls-files` under `--root` (default cwd). Untracked and
     gitignored files are excluded for free. If not a git repo, fall back to a tree walk.
  2. Default include: path ends in `.md` (case-insensitive). README/CLAUDE.md/AGENTS.md
     are `.md`, so this covers them.
  3. Apply config `exclude` globs → drop matches.
  4. Apply config `include` globs → add back any candidate matching an include, even a
     non-`.md` file or one a broad exclude removed (whitelist wins).
  5. Print the sorted result.
- **Config discovery:** `--config` if given, else `<root>/.github/doc-sync/audit-scope.json`.
  Absent file → pure defaults (no error).
- **Failure mode:** malformed config JSON → exit nonzero with a message naming the file
  and the parse error (self-explaining exit; nothing downstream runs on a broken config).
- **Glob semantics:** `*` and `**` against POSIX repo-relative paths, via a small
  stdlib glob→regex translate. No third-party deps (matches the other helper scripts).
- **Invocation:** run as `python3 …/list-docs.py`, matching `Bash(python3 *)`. This is
  why the workflow allowlist needs no change.

### 2. Config — `.github/doc-sync/audit-scope.json`

- **Shape:** `{"exclude": ["<glob>", …], "include": ["<glob>", …]}` — both keys
  optional, each an array of globs. `{}` and a missing file are both valid (defaults).
- **Name:** `audit-scope.json`, deliberately *not* `doc-scope.json`, to avoid confusion
  with the prose `docs/doc-scope.md` scope record the suite prescribes elsewhere
  (growing-docs / bootstrapping-docs).
- **Location:** `.github/doc-sync/`, alongside the installed CI scripts, so
  `scheduling-doc-sync` owns scaffolding it and the nightly job finds it by default path.

### 3. Skill text (`detecting-doc-bloat/SKILL.md` + `output-contract.md`)

- Step 1 (Inventory): instruct running the helper to get the docs in scope; state
  explicitly "do **not** enumerate with shell `find`/`ls`."
- Step 4 (Validate) and `output-contract.md`: change the validator invocation from the
  bare path to `python3 ${CLAUDE_PLUGIN_ROOT}/skills/detecting-doc-bloat/scripts/validate-bloat-output.py`.

### 4. `scheduling-doc-sync` scaffolding

At install, write a valid starter `.github/doc-sync/audit-scope.json` (empty `exclude`
and `include` arrays) into the target repo, committed for the human to tune. This is the
"first-run config," performed attended at setup — not by the headless nightly, which has
no human to answer an interactive prompt.

### 5. Dogfood + docs

- Commit a real `.github/doc-sync/audit-scope.json` for this repo excluding
  `tests/fixtures/**` and `tests/baselines/**`.
- Add `list-docs.py` (and its test) to the helper-script inventory in `CLAUDE.md`.

## Testing

Test-first, per the repo's skill-building convention.

- **Unit** — `tests/scripts/list-docs_test.py` (stdlib `unittest`, no deps):
  default enumeration, `exclude` drops matches, `include` re-includes an excluded path,
  `include` force-adds a non-`.md` file, missing config → defaults, malformed config →
  nonzero exit. Wire it into `CLAUDE.md`'s "after touching X, run Y" list.
- **E2E GREEN** — re-run the detect scenario under the **exact CI allowlist**
  (`Read,Grep,Glob,Write,Bash(git *),Bash(python3 *)`) and confirm it writes
  `bloat-report.json` with `permission_denials_count: 0`.

## Out of scope

- `detecting-doc-drift` is untouched — it works. A shared inventory tool across bloat and
  drift full-audit can follow later if a demand signal appears (YAGNI now).
- No change to the six-verdict output contract, the gate/render scripts, or the lane
  structure of `doc-bloat.yml`.
