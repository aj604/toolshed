# Design: closing the six 2026-07-12 architecture-review findings

**Status:** F1a, F6, F3, F4, F1b shipped in plugin v0.11.0. F5 (monthly full-audit drift lane)
and F2 (narrative-doc claims in that audit) are the deferred follow-up — the full-audit lane is
the heavy piece (reuses the bloat chunk-sweep architecture) and rides its own release; their
sections below are the design of record for that work.
**Source:** 2026-07-12 architecture review of the doc-lifecycle ecosystem, all six findings
verified against the repo before this design. Owner-confirmed forks: F3 = waiver file only;
F5 = monthly cron lane.

The findings share one root: the shrink loops (drift, bloat) have sensors, gates, and cadence;
the grow loop has only an in-session rule, and the buckets automation can't settle
(UNVERIFIABLE, recurring re-stales, narrative docs) have no owner. Each change below gives an
unowned bucket an owner without disturbing the detect → gate → fix → evidence-PR contract.

## F1a — first-rediscovery tally (growing-docs)

The second-rediscovery rule requires memory of the first rediscovery; today that memory is
chat-only. Fix: the tally lives in `docs/doc-scope.md` (growing-docs owns the format).

- Format addition: a `## Deferred` item may carry indented occurrence lines —
  `  - seen: <YYYY-MM-DD> <one-line occurrence>`.
- New rule: invoking the first-time exemption (answered in chat, moved on) costs one logged
  `seen:` line under the matching Deferred item (created if absent). The log is the price of
  the exemption — without it the second rediscovery is unrecognizable across sessions.
- Entry step extension: a live signal matching a Deferred item that already carries a `seen:`
  line **is** the second rediscovery — the promotion condition has fired.
- New red flag: answering a first-time question and not logging it.

## F1b — growth backlog on the weekly run surface (render-report + doc-bloat.yml)

`doc-scope.md` promotion signals are watched by nobody (config-as-bootstrap failure). Fix:
the weekly bloat run surfaces the growth backlog at the same cadence as the prune backlog.

- `render-report.py growth-backlog --scope-file docs/doc-scope.md`: renders Deferred items
  (promote-when signal + any `seen:` tally lines) as a step-summary section. Tolerant parser:
  missing file or no Deferred section → one quiet line, never a failure.
- `doc-bloat.yml` (template + dogfood): append the section to `$GITHUB_STEP_SUMMARY` every
  run, including skip paths — the backlog is visible even when both lanes skip.

## F2 — narrative docs enter the drift full audit (rides F5)

growing-docs calls the `> As of` anchor "a hook for future drift tooling"; the bloat lenses
defer to that tooling as if it exists. Fix: make it exist, minimally.

- **Full-audit mode only:** docs whose first line matches the anchor regex are in scope.
  Extract only claims with checkable subjects (`command`/`path`/`symbol`/`value` kinds) —
  the same set the narrative template swears is "true and actually run". Narrative
  prose/behavior/structure stays exempt: never claim-audit a story for being a story.
- Anchor dates are metadata, not claims: the wrapped report gains an optional top-level
  `"anchors": [{"doc": <path>, "as_of": "YYYY-MM-DD"}]`. Validator shape-checks it when
  present. `render-report.py` (pr-body, no-drift-summary) renders an FYI list of anchors
  older than `--anchor-stale-days` (default 180) — informational, never a STALE record,
  never a gate input.
- Text updates: detecting-doc-drift Modes/full-audit bullet + a don't-audit-narrative-prose
  red flag; growing-docs' "hook for future drift tooling" hedge now cites the real lane.

## F3 — UNVERIFIABLE waiver file (owner-confirmed: waiver only)

UNVERIFIABLE records surface only by piggybacking on stale-driven PRs, have no disposition
path, and detecting-doc-drift's handoff points at a bloat lens that doesn't exist.

- New consumer-owned file `.github/doc-sync/drift-waivers.json`:
  `{"waivers": [{"file": <doc>, "claim": <exact text>, "reason": <one line>, "date": "YYYY-MM-DD"}]}`.
  Identity = (file, exact claim text). A reworded claim resurfaces by design — new authorship
  is a new decision.
- **The detector stays pure** — it emits every UNVERIFIABLE; filtering is a run-surface
  concern. Gate decisions unchanged (STALE-only). `render-report.py` gains `--waivers FILE`:
  - `pr-body` / `issue-body`: unwaived UNVERIFIABLE records listed with a
    to-waive-add-to-drift-waivers hint; waived ones collapse to a count.
  - `no-drift-summary`: gains optional `--report`/`--waivers`; quiet nights print
    "N unverifiable claim(s) await disposition" — the review's on-a-quiet-night-never-seen
    hole (self-explaining exits).
- Installer: seed `{"waivers": []}` only-if-absent (audit-scope precedent). Upgrade table
  row: consumer data, **never touch**.
- detecting-doc-drift line ~39: "cutting or rewording it is a human/bloat decision" →
  a human decision — reword/cut by hand, or waive it durably in scheduled installs
  (scheduling-doc-sync owns the waiver flow; this skill cites it).

## F4 — recurrence flag (sync-gate + render-report)

Records rightly carry no history, so the loop re-fixes the same line forever without
noticing. Fix: the pipeline keeps one run of memory; shape advice goes on the PR body.

- `sync-gate.py stale-state --report FILE --out FILE`: derives
  `{"stales": [{"file", "line", "kind"}]}` from the report's STALE records.
- Workflow proceed path writes it to `.github/doc-sync/last-stales.json`, committed on the
  PR branch (rides the PR like the marker — state advances only when the fix lands, so a
  match really is "re-staled after a fix").
- `render-report.py pr-body --prev-stales FILE` (optional): a STALE record matching a prior
  entry (same file, same kind, line within ±3) gets a "recurred" tag plus one hint line:
  recurring drift at one spot is a shape problem — snapshot→pointer (writing-docs), not
  another re-fix. Gate decisions unchanged.

## F5 — monthly full-audit drift lane (owner-confirmed: cron, inside doc-sync.yml)

Nightly is diff-scoped from the marker; wrong-at-install claims and drift that subject-grep
can't connect are unreachable. `doc-sync.yml`'s own seam comment reserves this extension.

- Second cron `0 5 1 * *` beside the nightly; mode resolved from `github.event.schedule`;
  `workflow_dispatch` gains a `mode` input (nightly|full, default nightly).
- `sync-gate.py pre --mode full`: skips the commits==0 `skip-empty` (a full audit is not
  about new commits); `skip-pending` still binds.
- Scale: full mode reuses the proven bloat sweep architecture — `plan-chunks.py` over the
  `audit-scope.json` doc inventory → matrix chunk audits (each a full extract+verify of its
  docs) → validated per chunk → concatenated into one report → the existing post gate and
  render path. Retry classification reuses the existing budget-shaped/fresh logic.
- Blast-radius cap unchanged and load-bearing: the first monthly run on a rotten corpus
  opens an issue, not a 40-fix PR.

## F6 — growing-docs claims the direct narrative ask

"Write an ADR"/"write a tutorial" matches neither door: writing-docs scopes it out,
growing-docs' description keys only on demand-signal vocabulary. growing-docs owns the
narrative template, so its description claims the direct ask too. Trigger evals via the
description-optimization loop after the text settles.

## Testing and delivery

- Scripts/workflows: stdlib unit tests in `tests/scripts/` (RED first), per repo convention.
- Skill text: skill-creator harness at the main checkout's `skill-workspaces/` — baseline
  arm = pre-edit snapshot, fresh graders with the answer key. New growing-docs evals:
  first-rediscovery-logs-tally, tally-fires-promotion, direct-adr-ask.
- Sequenced PRs by weight: PR1 F1a+F6 (growing-docs text) · PR2 F3+F4 (+F1b, all
  render/gate) · PR3 F5+F2 (full-audit lane + narrative). One version bump at the end
  (0.10.5 → 0.11.0), `claude plugin validate` before tagging.
