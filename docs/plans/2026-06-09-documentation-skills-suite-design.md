# Documentation Skills Suite — Design

**Date:** 2026-06-09
**Status:** Validated via brainstorming; ready for implementation planning
**Methodology:** Each skill built with superpowers:writing-skills TDD (RED → GREEN → REFACTOR with subagents)

## Goal

A suite of skills covering the full documentation lifecycle for repos Avery works in —
serving both human and LLM readers — with a strong emphasis on increasing AI agent
performance in those repos and keeping docs alive automatically.

**Lifecycle story:** bootstrap → write → detect drift → auto-sync.

## Scope decisions

- **Audience:** both humans and LLMs.
- **Activities:** writing new docs, auditing/improving existing docs, keeping docs in sync.
- **Doc types:** project entry docs (README, getting-started), operational docs (runbooks,
  troubleshooting), agent context docs (CLAUDE.md, repo maps, skill files).
  Decision/architecture docs (ADRs) explicitly out of scope for now (YAGNI).
- **Sync model:** automation-driven (PR trigger and/or nightly cron), not an in-session
  discipline rule.
- **Suite shape:** activity-centered — one skill per activity; doc-type knowledge lives in
  reference files, not separate skills.

## Architecture

```
bootstrapping-docs ──┐
(bare repo → baseline)│
                      ▼
                writing-docs  ←──  detecting-doc-drift  ←──  doc-sync-automation
                (quality bar)      (core technique)          (wiring/triggers)
                      │
                      └── references writing-for-llms (existing, untouched)
```

Dependency direction is one-way: automation never invents doc-writing judgment; it always
flows through `detecting-doc-drift` (what's stale) and `writing-docs` (how to fix it).

```
skills/
  bootstrapping-docs/
    SKILL.md
  writing-docs/
    SKILL.md          # judgment: what to write, where it lives, quality bar
    readme.md         # project-entry doc patterns
    runbooks.md       # operational doc patterns
    agent-context.md  # CLAUDE.md / repo-map patterns (defers to writing-for-llms)
  detecting-doc-drift/
    SKILL.md          # claim extraction + tiered verification engine
  doc-sync-automation/
    SKILL.md          # recipes + guardrails
    triggers.md       # concrete setup: cron routine, GitHub Action YAML
```

## Skill 1: bootstrapping-docs

Point it at an undocumented repo → minimal high-leverage doc set, in AI-performance order:

1. **CLAUDE.md** — build/test/run commands, architecture map, conventions, gotchas:
   the things an agent burns tokens rediscovering every session.
2. **README skeleton** for humans.
3. **Stubs** for operational knowledge surfaced during exploration.

Explore-then-write. Explicitly NOT aiming for completeness — the smallest doc set that
measurably improves agent sessions. Drift detection + sync keep it alive afterward.

## Skill 2: writing-docs

SKILL.md ~300 words, owns three judgments:

1. **Document at all?** Counter-test: does the code, type signature, or git history
   already say it? If yes, don't write it.
2. **Which doc type / where does it live?** Decision table:
   reader + moment-of-need → README / runbook / CLAUDE.md.
3. **Quality bar:** every claim verifiable against the repo (commands actually run,
   paths exist), examples real not contrived, written for the reader's moment of need.

Reference files (`readme.md`, `runbooks.md`, `agent-context.md`) each carry a structure
template, one excellent example, and type-specific failure modes (e.g., runbooks: steps
must be copy-pasteable under incident pressure). `agent-context.md` defers to
`writing-for-llms` for token economy rather than duplicating it.

## Skill 3: detecting-doc-drift

**Core idea:** docs make verifiable claims; drift = a claim the repo no longer backs.
Teaches claim extraction + evidence-based verification, not vibes-based staleness checks.

### Engine (shared by both modes)

1. **Extract claims**, tagged by kind: commands ("run `make test`"), paths/symbols
   ("config lives in `src/config.ts`"), behavior ("retries 3 times with backoff"),
   structure ("three services: api, worker, cron").
2. **Verify** each claim against the repo, at the appropriate tier (below).
3. **Classify:** VERIFIED / STALE (contradicted) / UNVERIFIABLE (too vague to check —
   itself a doc smell).
4. **Fix or report** — rewrites go through writing-docs standards.

### Verification tiers (cost control)

| Tier | Cost | What it does | Catches |
|------|------|--------------|---------|
| 1 — STATIC | seconds | grep/glob only: paths exist, symbols present, links resolve, commands exist in package.json/Makefile | renames, moves, deletions (most common drift) |
| 2 — SHALLOW | moderate | + run safe commands (--help, --version, dry-run); skim signatures/exports | changed flags, renamed options, signature drift |
| 3 — DEEP | expensive | + execute documented workflows where safe; read implementing code for behavioral claims | behavior drift |

**Escalation rule (key cost saver):** every claim starts at Tier 1. Escalate only when
Tier 1 flags suspicion, the claim's subject is in the diff (sync mode), or the user asked
for a deep audit. Cost concentrates exactly where drift is likely.

### Modes

- **Full audit** (manual): sweep all docs → claim-by-claim report with file:line,
  severity-ranked (wrong command > stale diagram). Report only; fixing is a separate
  decision. Default Tier 2, user-selectable.
- **Diff-scoped** (what automation calls): input is a PR diff or commit range. Reverse
  direction: for each changed file/symbol, grep docs for passages referencing it →
  verify just those claims (Tier 3) → hydrate updates.

**Anti-pattern called out explicitly:** marking a claim VERIFIED because doc and code
"seem consistent" without running/reading. Verification means evidence.

## Skill 4: doc-sync-automation

Thin by design — wiring only.

### Trigger recipes (pick per repo, or both)

**Nightly cron** (scheduled cloud agent or local routine)
- Diff scope: main since last successful sync (marker = last-synced SHA in a state file
  or the last sync commit).
- Run: Tier 1 sweep over all docs + Tier 3 on diff-touched claims.
- Output: one PR ("docs: sync with main (date)") — never direct-commit to main.

**PR trigger** (GitHub Action / claude on PR)
- Diff scope: the PR's own diff.
- Run: Tier 3 on diff-touched claims only (fast enough for CI).
- Output: review comment listing invalidated doc passages (safe default), or a commit
  pushed onto the PR branch (opt-in).

### Guardrails (pressure-tested like discipline rules)

- Never rewrite a passage the diff didn't invalidate (keeps automated PRs reviewable).
- Never delete a doc — only flag for human deletion.
- Blast-radius cap: if a run wants to touch > N files or finds docs wholesale-wrong,
  stop and open an issue instead of a giant PR.
- Idempotent: re-running on the same diff produces no new changes (no nightly PR spam).
- Every rewritten claim cites its evidence (file:line or command output) in the PR
  description.

## Testing plan (writing-skills TDD)

No skill without a failing test first. One skill at a time — full RED → GREEN → REFACTOR
with subagents before starting the next. No batch-writing.

### Shared fixture: drift-fixture repo

Small sample repo with docs containing planted claims — some true, some stale (renamed
file, changed CLI flag, changed behavior, deleted module). Gives measurable
recall/precision for the drift skills, not vibes.

### Per-skill baselines (RED)

| Skill | Baseline scenario | Expected failures that define the skill |
|-------|-------------------|------------------------------------------|
| writing-docs | agent documents a sample feature without the skill | marketing fluff, unverified commands, wrong doc placement |
| bootstrapping-docs | agent told "document this repo" on a bare fixture | bloated narrative CLAUDE.md, completeness-chasing |
| detecting-doc-drift | agent asked "are these docs accurate?" on drift fixture | missed planted drift; false VERIFIED (evidence-free passes) |
| doc-sync-automation | agent given diff + docs | out-of-scope rewrites, deletions, giant blast radius |

### Build order

1. **writing-docs** — foundation; everything cites it.
2. **bootstrapping-docs** — immediate value on Avery's repos.
3. **detecting-doc-drift** — the engine.
4. **doc-sync-automation** — wiring; needs #3 working.

## Open items (deferred to implementation)

- Concrete N for the blast-radius cap (pick during testing).
- Where the nightly cron runs (scheduled cloud agent vs. local /schedule routine vs.
  GitHub Action cron) — decided per repo in triggers.md.
- Whether bootstrapping-docs ships a CLAUDE.md template or generates structure per repo.
