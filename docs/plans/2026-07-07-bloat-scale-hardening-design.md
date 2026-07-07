# doc-bloat scale hardening: provisioned executors, per-chunk budgets, convergent runs

**Date:** 2026-07-07. **Status:** approved (core sections user-approved in session; rollout
sections per implementer judgment). **Prior design:**
`2026-07-06-detecting-doc-bloat-rearchitecture-design.md` (this hardens its headless lane).

## Problem (evidence from career-compass run 28860529836, 2026-07-07)

First real bulk run: 81 docs → 35 chunks. Every sweep invocation burned 14–18 turns against
`--max-turns 15`; every invocation logged 1–2 permission denials because the prompt orders
"use the detecting-doc-bloat skill" while `Skill` is absent from `--allowedTools`, so each
executor improvised (file-hunting its own instructions). 11/35 jobs hit `error_max_turns` on
attempt 1; the identical fresh retry re-bought the same failure once (chunk failed twice →
whole run held hostage by all-or-nothing assembly). Cost ~$0.50–0.75/invocation. Planning-doc
chunks (landed-code verification greps) fail most. Owner requirements: keep full per-doc audit
depth; a straggler chunk must not block the report; first runs over hundreds of docs must
converge across dispatches.

Pattern-corpus consultation (subagent-dispatch, deterministic-harness,
validated-seam-redispatch, durable-state, context-envelope, statelessness): load-bearing
dispatch content goes verbatim, budgets/retries are harness property, retries must be
classified by failure kind, checkpoints + explicit gap lists make partial assembly honest.

## Design

### Planner (`plan-chunks.py`)

- **Content-safe chunk ids:** sha256 over member `(path, git blob sha)` pairs
  (`git ls-files -s`; fallback `(path, line count)` outside git). Editing a doc changes its
  chunk id, so cross-run resume never reuses a stale result; "plan only pending" stays a pure
  set difference against `--results-dir`.
- **Per-chunk `turns` field:** `12 + 2×docs` (living/narrative) or `12 + 4×docs` (planning),
  `+1` per full 600 lines in the chunk, clamped to [20, 40]. Policy chunks: flat 20.
  Grounded in observed 14–18-turn invocations that included ~5 turns of provisioning waste
  now eliminated. The workflow's escalation ceiling (60) is the separate kill-switch role.
- **`--emit-prompt <id> --manifest FILE`:** prints the ready dispatch prompt — chunk doc list
  (path, lines, kind hint) verbatim (policy: dir + files verbatim), the exact output path
  `chunks/<id>.json`, the instruction to invoke doc-lifecycle:detecting-doc-bloat for verdict
  rules, and the definition of done. `--emit-turns <id>` prints the chunk's budget. Prompt
  templating lives in the tested script, never in workflow YAML.

### Workflow template (`scheduling-doc-sync/doc-bloat.yml`)

- **Dispatch:** sweep job renders prompt via `--emit-prompt` in a shell step; matrix stays
  thin (chunk ids only; the slice is read from the downloaded manifest in-job).
  `--allowedTools` gains `Skill`. `--max-turns` = the chunk's planner-computed `turns`.
- **Classified retry:** new `sync-gate.py bloat-retry --execution-log FILE --turns N` reads
  claude-code-action's execution-output JSON: `error_max_turns` → retry at `ceil(turns×1.5)`
  capped 60; otherwise (contract violation, infra failure, missing log) → fresh identical
  retry. Two attempts total; then the job fails naming its chunk, and assembly proceeds
  without it.
- **Partial assembly:** assemble passes `--allow-partial`; the report gains
  `"unswept": [{"chunk": id, "docs": [paths]}]`; `render-report.py` surfaces an explicit
  "N chunks unswept" banner in PR bodies. Gaps are loud, never silent.
- **Resume:** plan job downloads the previous run's `bloat-chunk-*` artifacts (any
  conclusion) into `chunks/`, passes `--results-dir chunks`, and re-uploads reused results
  as this run's artifacts so assemble sees the union. Content-addressed ids make reuse safe.

### Skill text (`detecting-doc-bloat/SKILL.md`)

Headless section: the executor is handed its chunk slice verbatim in the dispatch prompt
(doc list or policy dir+files, output path); it judges exactly those docs and writes the
result — no manifest hunt, no orchestration. Script-invocation templates gain `--emit-prompt`.
Edited under writing-skills RED→GREEN with fresh graders; baselines at
`tests/baselines/bloat-scale-red/` / `bloat-scale-green/`, scenarios driven by real
`--emit-prompt` output.

### Out of scope

Chunk splitting on retry (dominant failures are single-doc chunks), auto policy-scope
detection, and any triage-first mode (owner chose full-audit-that-converges). Per-repo
`policy_scope` (e.g. career-compass's `docs/superpowers`) remains a config decision.

## Testing & rollout

- Unit tests (stdlib unittest, no deps): plan-chunks (id content-addressing, turns formula,
  emit-prompt/emit-turns), validate-bloat-output (`--allow-partial` unswept recording; final
  report accepts the field), sync-gate (`bloat-retry` matrix), render-report (unswept banner).
- Dogfood copies under `.github/doc-sync/` + `.github/workflows/doc-bloat.yml` stay in sync.
- Plugin bump 0.7.0 → 0.8.0; `claude plugin validate` before tagging; decision-log entry in
  `docs/decisions.md`. career-compass upgrades by re-running scheduling-doc-sync afterwards.
