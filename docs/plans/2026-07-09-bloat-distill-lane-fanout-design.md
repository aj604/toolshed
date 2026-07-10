# doc-bloat distill-lane fan-out: per-group matrix apply, deterministic merge

**Date:** 2026-07-09. **Status:** approved (architecture user-approved in session; user
constraint: no turn caps on apply invocations — quality over wall-clock bounds). **Prior
designs:** `2026-07-06-detecting-doc-bloat-rearchitecture-design.md` (moved DISTILL authoring
detect-time → post-approval) and `2026-07-07-bloat-scale-hardening-design.md` (hardened the
*detect* side). This design gives the *apply* side the same treatment.

## Problem (evidence from career-compass run 28912881170, 2026-07-08)

First bootstrap-scale run after the 07-07 hardening: total 4h20m. The sweep matrix — 35
chunks, all hardening in effect — finished in **~9 minutes** wall-clock. The **distill lane
took 250 minutes (96% of the run)**: one headless invocation with no turn cap, told to apply
every ready record, dispatched the doc-distiller **56 times sequentially in one session**
(report: 59 records, 56 `DISTILL ready`). ~4.5 min/record, and the orchestrator session
re-ships its accumulated transcript every turn (cost quadratic in records) with turn gaps
long enough that the prompt cache expires between them. On a repo with hundreds of planning
docs the lane extrapolates to days. The 07-06 rearchitecture deliberately deferred DISTILL
authoring to post-approval — correct, but it concentrated all authoring cost into the one
lane that never got the scale treatment: no budgets, no seam validation, no retry
classification, no partial-completion story.

Pattern-corpus consultation (deterministic-harness, statelessness, staged-effects,
subagent-dispatch, validated-seam-redispatch, context-alignment, context-envelope,
context-economy): the 56-iteration loop is control flow running in prose — move it to the
tested-script layer; per-record authoring is independent, so fresh-context fan-out is the
free move; shard by affinity (records likely to land in the same target doc) so shared-file
contention is removed by construction; staged work never self-promotes — a deterministic
merge job orders and lands it; don't merge with a model what a script can merge as data.

## Design

### Independence analysis (what needs shared context, what doesn't)

A DISTILL record's authoring (re-verify landing, insight walk, code-verified claims, one
staged commit) needs only its record slice + the artifact + the code it cites. The shared
surfaces are exactly three: (1) every record appends one entry to `docs/decisions.md`;
(2) records may land claims/insights in the same target doc — targets are chosen by the
distiller at distill time, so the plan-time affinity proxy is the **artifact's directory**
(same-dir plans overwhelmingly target the same narrative doc); (3) inbound-reference
repointing edits arbitrary files (rarely overlapping). (1) is an append-only log — merged as
data. (2) is grouped away. (3) falls to the merge's conflict path, loudly, when it collides.

### New script: `scheduling-doc-sync/scripts/plan-distill.py`

Deterministic, stdlib-only, unit-tested — the apply-side twin of `plan-chunks.py`.

- **Lane selection** reuses `sync-gate.py`'s `in_lane` (imported from the co-located file
  via `importlib` — one owner for the lane→verdict mapping): `MERGE-DOC` / `RETIRE-DOC` /
  `POLICY` / `DISTILL ready`. `DISTILL pending-implementation` is never planned (the
  planner's exclusion replaces the executor's skip-with-note in the headless lane).
- **Grouping:** `DISTILL ready` records group by `dirname(doc)`, packed greedily to
  `distill.max_group_records` (default 4 — ~4.5–10 min/record keeps a group job under
  ~40 min). All mechanical verdicts (`MERGE-DOC`/`RETIRE-DOC`/`POLICY`) form one `inline`
  group. Group ids are content-addressed over member `(record id, doc)` pairs.
- **Config:** optional `distill` object in the existing `.github/doc-sync/audit-scope.json`:
  `{"max_group_records": 4, "max_groups": null}` — `max_groups` is the same
  default-off hard-ceiling role as `chunking.max_chunks`.
- **`--emit-prompt <gid> --manifest F`:** renders the headless group-executor dispatch —
  the record ids (with verdict + doc, verbatim) as the *entire approved subset*, the report
  path, one-commit-per-record, the sidecar output path `distill-results/<gid>.json`, and the
  definition of done. Prompt templating stays in the tested script, never in YAML.
- **`--validate-result FILE --manifest F`:** seam-validates a group sidecar
  `{"group": gid, "applied": [ids], "skipped": [{"id","reason"}], "failed":
  [{"id","reason"}]}` — parseable, names its group, ids ⊆ the group's records, every record
  accounted for exactly once.
- **`--merge --manifest F --results-dir D --patches-dir D --out FILE`:** applies each
  group's `git format-patch` series with `git am -3` in group-id order. A conflict whose
  only unmerged path is `docs/decisions.md` is auto-resolved by **union** (append-only log:
  keep both sides, strip markers) and the series continues; any other conflict skips that
  record's patch (`git am --skip`), records it as unapplied with the reason, and continues.
  A missing/invalid sidecar or patch dir marks the whole group unapplied. Writes a merge
  summary (`applied` / `unapplied` / `skipped`), exits 0 with gaps recorded loudly —
  a failed record costs itself, never the lane.

### No cross-run patch resume — convergence is re-detection

The sweep resumes prior chunk *results* because they are pure data; a patch is a diff
against a moving base, so carrying it across runs is unsafe. Instead: an unapplied/failed
record's artifact survives on main, the next weekly sweep re-proposes it, and the next
distill lane retries it against the updated tree. Bounded, honest convergence — same
philosophy, different mechanism, chosen deliberately.

### Workflow template (`scheduling-doc-sync/doc-bloat.yml`)

The single `distill` job becomes three; the prune lane is untouched:

- **`distill_plan`** (deterministic): download report → `plan-distill.py` → manifest +
  group-id list output; upload manifest.
- **`distill_sweep`** (matrix over group ids, `fail-fast: false`): render the dispatch via
  `--emit-prompt`; claude-code-action invocation with **no `--max-turns`** (owner
  constraint: an apply invocation is never truncated mid-judgment; the kill-switch is the
  job-level `timeout-minutes: 60` — wall-clock ~6× the observed worst group, bounding hangs
  without bounding care) and `--allowedTools "Skill,Task,Read,Grep,Glob,Edit,Write,
  Bash(git *),Bash(python3 *)"`; seam-validate the sidecar; one fresh retry after
  `git reset --hard` (no budget-escalation branch — there is no budget to escalate);
  export `git format-patch ${{ github.sha }}..HEAD`; upload patches + sidecar.
- **`distill_merge`** (deterministic): download all group artifacts; branch
  `doc-bloat/distill`; `plan-distill.py --merge`; render the draft PR via the existing
  `sync-gate bloat-lane` + `render-report bloat-pr-body` flow, now `--merge`-aware
  (an "unapplied this run" banner mirrors the sweep's "unswept" banner); push + draft PR;
  `skip-noop` when nothing landed.

### Skill/agent text

- **`fixing-doc-bloat/SKILL.md`** gains a headless group-executor section mirroring
  detecting-doc-bloat's: the dispatch prompt's record-id slice *is* the approved subset and
  the entire mandate; apply exactly those records, one commit per record, write the group
  sidecar to the named path, stop — never open the manifest, never push, never open a PR;
  merge/retries/assembly belong to the workflow.
- **`doc-distiller.md` is unchanged** — the DISTILL method keeps its single owner, and each
  record still lands as one commit (the staged form *is* the transport unit).
- **`detecting-doc-bloat/SKILL.md`** interactive large-scope mode gains one line: dispatch
  chunk subagents in parallel waves, not serially.

### Cost note (API adopters)

Fan-out converts the lane from quadratic (one session re-shipping its transcript per record,
cache-expired) to linear: each group is a small fresh window whose fixed boot cost replaces
a 4-hour transcript re-ship, with script-rendered prompts keeping prefixes cache-identical
within an invocation.

## Out of scope

Turn caps anywhere on the apply side (owner decision); cross-run patch resume (see above);
predicting distill targets at plan time (directory affinity is the proxy); model tiering for
the sweep lane (noise next to this change); prune-lane fan-out (1.8 min observed — nothing
to win).

## Testing & rollout

- Unit tests (stdlib, no deps) at `tests/scripts/plan-distill_test.py`: lane selection +
  pending exclusion, directory-affinity packing, content-addressed ids, emit-prompt,
  sidecar validation matrix, and the merge engine against real tempdir git repos (clean
  apply, decisions.md union resolution, hard-conflict skip-and-continue, missing-sidecar
  group drop, deterministic ordering). `render-report_test.py` gains the unapplied-banner
  and merge-summary cases.
- Skill-text change RED→GREEN with fresh graders (writing-skills), baselines at
  `tests/baselines/distill-fanout-red/` / `distill-fanout-green/`, scenarios driven by real
  `--emit-prompt` output.
- Wiring: `apply-upgrade.py` SCRIPTS map + scheduling-doc-sync install steps gain
  `plan-distill.py` (six → seven vendored scripts); dogfood copies under
  `.github/doc-sync/` + `.github/workflows/doc-bloat.yml` stay in sync; `release.yml` CI
  runs the new suite; plugin 0.9.4 → 0.10.0; decision-log entry in `docs/decisions.md`.
  career-compass upgrades via the existing upgrade lane after release.
