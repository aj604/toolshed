# Assertion ledger and incremental sync — Phase A design (engine core)

**Status:** approved design, awaiting implementation plan
**Parent:** [#169 — Make nightly drift sync incremental with an assertion ledger and deterministic probes](https://github.com/aj604/toolshed/issues/169)
**Scope decision:** implement #169 in full, decomposed A→B→C→D; this document specs Phase A only.

## Why (one paragraph)

The scheduled drift audit re-judges the entire living-document corpus with a model every
night — 2,260 assertion units on this repo, $20–97 equivalent per run, zero amortization
between runs, and the 2026-07-31 run produced no verdicts at all. #169 replaces that with
a durable, repo-owned assertion ledger plus deterministic probes, so a nightly sync spends
model tokens only on what changed. Phase A builds the deterministic core inside the engine,
provable with zero model calls. The three invariants Phase A must establish: an unchanged
compatible repository and ledger cause **zero model invocation**; reuse may **narrow model
work, never overstate coverage**; **no failure path widens** into a full-corpus model run.

## Phase decomposition (context)

- **Phase A (this spec):** engine-only deterministic core — ledger contract, probe
  vocabulary, two-phase incremental-sync protocol, fake-judgment acceptance seam.
- **Phase B:** bootstrap — model-assisted initial ledger construction, heuristic probe
  pre-compilation to minimize model spend, seeding from a fully-valid existing report.
- **Phase C:** scheduler rewrite — deterministic-first sync lane replacing the (currently
  suspended) nightly; empty work order ⇒ no model job; run surface; release-gate proof of
  the zero-model unchanged run.
- **Phase D:** hardening — migration, deep-reconciliation dispatch, tombstone review
  surface, glossary/decision-record updates.

Each phase gets its own spec → plan → implementation cycle.

Stop-loss already applied (2026-08-02): the `doc-audit` workflow is disabled on GitHub
(`disabled_manually`), and `release.yml` now publishes only on manual `workflow_dispatch`
from `main`. The weekly bloat audit remains active and is out of scope per #169.

## 1. Scope and non-goals

Phase A ships new engine modules and CLI subcommands in
`plugins/doc-lifecycle/engine/doclifecycle/`, tested at the public seam
(`tests/engine/*_test.py`). It changes no workflow template, no skill text, and no lane.
It consumes — without modifying — the existing registry, inventory, deterministic
segmenter, assertion classes, evidence boundary, result states, finding identity, and
narrative-anchor checks. The single existing contract it extends (versioned) is the report
schema, to express incremental coverage (§6).

Non-goals for Phase A: bootstrap (B), any scheduler/YAML work (C), migration and deep
reconciliation (D), bloat semantics (out of #169 entirely), and repurposing the existing
semantic cache (`cache.py` stays a derived-artifact cache; the ledger is durable reviewed
state with different identity semantics — an explicit #169 decision).

## 2. The assertion ledger

**Location and format:** one file, `.doc-lifecycle/assertion-ledger.jsonl`, in JSON Lines
form with deterministic ordering (document path ascending, then unit order within the
document). Rationale: a per-document shard directory floods consumer repos with tracker
files; a pretty-printed single JSON object produces unreviewable diffs and constant merge
conflicts. JSONL gives one file whose git diff is exactly the set of changed entries.

**Line 1 — header record:**

```json
{"record": "ledger-header", "schema": 1, "ruleset": "<engine ruleset version>",
 "registry_digest": "<sha256 of registry.json content>",
 "plugin_version": "<version that proposed this ledger>",
 "established": {"report_digest": "...", "commit": "...", "date": "YYYY-MM-DD"}}
```

**Entry lines** (one per assertion unit; identity = document path + unit content digest,
so identical text in two documents remains two independently-auditable entries):

```json
{"record": "assertion", "doc": "path/from/repo/root.md", "unit": "<content digest>",
 "class": "factual|normative|rationale", "obligation": "<review obligation>",
 "strategy": "probe|deps|on-change|reconcile-only",
 "probe": {"kind": "...", "args": {...}, "expect": {...}},
 "deps": [{"path": "...", "digest": "<sha256 at establishment>"}],
 "lineage": {"report_digest": "...", "commit": "...", "plugin_version": "...",
             "date": "YYYY-MM-DD"},
 "status": "active"}
```

`probe` is present only for `strategy: probe`. `deps` is required for `probe` and `deps`
strategies (a probe's inputs are also declared deps) and absent for `on-change` and
`reconcile-only` — dependency triggers are exactly what distinguishes `deps` from
`on-change`. Tombstones are entries with
`"status": "tombstone", "removed": {"commit": "...", "date": "YYYY-MM-DD"}` retaining
their last active fields — deleting documentation cannot silently erase history.
Tombstones persist until deep reconciliation (Phase D) prunes them.

**Trust and mutation:** the accepted ledger is read-only to the engine. Sync emits a
*proposed next ledger* artifact; committing it to the repository is a human-reviewed act
through the normal change path. No scheduled job writes it to the default branch.

**Fail-closed validation** (typed problems, no model invocation, no work order): missing
file when one is required; unparseable line; unknown schema version; `registry_digest`
mismatch (foreign or out-of-date ledger); `ruleset` incompatibility; duplicate entry
identity; entry referencing a probe kind or field shape the schema forbids. The engine
never guesses incompatible state forward — that becomes a migration/reconciliation
requirement (Phase D surfaces it; Phase A refuses with the typed problem).

## 3. Deterministic probe vocabulary (v1)

A probe is a read-only check from this closed, engine-owned vocabulary. Probe arguments
are validated **before** execution; violations (unknown kind, malformed args, path outside
the evidence boundary, symlink escaping the repository, anything shaped like a command
string in a path field) are typed refusals that escalate the entry to the work order —
never executed, never a crash.

| Kind | Args | Passes when |
|---|---|---|
| `path_exists` | `path` or `glob`, `kind: file\|dir\|any` | The path/glob resolves inside the boundary to the declared kind |
| `content_match` | `path`, `pattern` (bounded `re`), `expect: present\|absent`, optional `count` | The pattern's presence/absence/count in the file matches |
| `json_value` | `path`, `pointer` (RFC 6901), `equals` (JSON value) | The document at `path` parses and the pointer resolves to an equal value |
| `symbol_defined` | `path`, `language: python`, `name` (dotted) | stdlib `ast` finds the def/class/assignment in that file |
| `tool_probe` | `tool` (declared in `evidence-tools.json`), `flag: --help\|--version`, `pattern` | The declared tool's help/version output matches the pattern |

Execution is direct stdlib file and git reads — no shell interpretation anywhere.
`tool_probe` reuses the discipline `probe-evidence-tool.py` established: only declared
tools, only `--help`/`--version`, environment scrubbed. Non-Python symbol claims use
`content_match` in v1. Behavior probes (running tests or consumer-declared commands) are
deliberately excluded: not read-only-safe. Assertions no v1 probe can discharge get an
honest `on-change` or `reconcile-only` strategy instead of an unsafe probe (#169).

A probe result records what was observed — resolved paths, matched text, tool version
line, and the content digests of every dep read — so a deterministic pass is auditable
evidence, not an unexplained absence of findings. `tool_probe` results record the tool's
version output specifically because declared-tool evidence otherwise has no change signal.

## 4. Audit strategies

Strategy is **assigned by model judgment** (at bootstrap in Phase B, or when a unit passes
through the work order) and **validated by the engine** (a probe strategy must carry a
valid probe; deps strategies must declare deps; classes carry defaults — e.g. normative
and rationale prose may not be assigned `probe`).

| Strategy | Deterministic sync behavior | Enters work order when |
|---|---|---|
| `probe` | Re-execute the probe every sync | Probe fails, refuses to validate, or its deps read outside the boundary |
| `deps` | Compare declared deps' current digests to recorded ones | Any dep digest changed, or a dep disappeared |
| `on-change` | Carry forward | The unit's own content digest changed (i.e. the doc text was edited — which makes it a *new* identity; see below) |
| `reconcile-only` | Carry forward | Never (only explicit deep reconciliation reconsiders it) |

UNVERIFIABLE-class claims map naturally to `on-change`: their only meaningful trigger is
the text itself changing. Because unit identity is content-addressed, an edited unit *is*
a new identity: the new unit enters the work order as `new`, and the old entry is
tombstoned or explicitly superseded in the proposed next ledger — there is no in-place
mutation of an entry's text.

## 5. The incremental-sync protocol

One public, two-phase protocol — the single seam the external model trust split requires.
Library functions in a new `doclifecycle` sync module, plus matching CLI subcommands on
`python3 -m doclifecycle`; both seams behave identically (the CLI wraps the library).

**Phase 1 — `plan_sync(repo_root, budget) → SyncPlan`** (CLI: `sync-plan`):

1. Build inventory and segmentation (existing machinery), run narrative-anchor checks.
2. Validate the accepted ledger (§2 failure modes fail closed here).
3. Compare current assertion identities against ledger entries; classify each as
   unchanged / new / removed.
4. Execute probes for unchanged `probe`-strategy entries; compare dep digests for `deps`
   entries.
5. Emit **deterministic results** (probe passes with evidence, carried entries with
   reasons, anchor findings, tombstone candidates) and, if needed, a **judgment work
   order**: the bounded set of units requiring model judgment — new units, failed probes,
   changed deps, invalid entries — each with its declared evidence boundary.
6. The work order commits by digest to the ledger, the current inventory, the unit set,
   and the budget it was built under; it is unforgeable input to phase 2.
7. **Empty work order ⇒ the caller knows no model step exists.** Work order larger than
   the configured cap ⇒ typed `over-budget` stop *before* any model invocation, naming
   every unit that would have needed judgment.

**Phase 2 — `accept_sync_judgments(repo_root, work_order, judgments) → (report, proposed_ledger)`**
(CLI: `sync-accept`):

1. Validate the work order's binding digests against the current repository state (a
   repo that moved between phases is a typed `stale` refusal).
2. Validate every judgment against the work order: a judgment for a unit the work order
   never asked about is refused; verdict shapes, evidence boundaries, and proposed
   probes/strategies are revalidated by the engine — model output never becomes trusted
   control data unchecked.
3. Judgments covering only part of the work order produce a **partial** report naming
   every unexamined unit. No partial result, budget exhaustion, or malformed judgment
   ever falls back to a wider model run.
4. Emit the validated report (existing report contract + §6 extension) and the proposed
   next ledger (additions, supersedes, tombstones, re-established lineage), both
   deterministically ordered and content-digested so repeated runs are byte-comparable.

**Budget:** consumer-owned `.doc-lifecycle/sync-budget.json`
(`{"max_work_order_units": N, "max_model_calls": N, "max_turns": N}`; defaults
`40 / 1 / 40`; absent file ⇒ defaults). Phase A enforces the work-order-size cap — the lever
that exists before any model is involved; turn/token enforcement binds in Phase C where
the runner exposes those controls, but the numbers travel in the work order from day one.

**Determinism:** same repository, ledger, and budget ⇒ byte-identical work order and
deterministic results. `Date` fields in emitted artifacts come from the caller (the
engine takes an explicit `as_of` input rather than reading the clock) so tests and
retries are stable.

## 6. Report contract extension (versioned)

Each unit covered by an incremental report declares its **coverage source**:

- `judged` — fresh model judgment this run (existing semantics, unchanged);
- `probe` — deterministic probe pass, with the probe kind and observed evidence attached;
- `carried` — reused under a `deps`/`on-change`/`reconcile-only` strategy, with the
  reason reuse was safe and the originating lineage (report digest + commit).

Result-state meanings (VERIFIED / STALE / UNVERIFIABLE; clean / findings / partial /
stale / invalid) are untouched. Incremental coverage is declared as incremental — a clean
incremental report never claims full-corpus reconciliation coverage. Reports remain
immutable proof of one examination; the ledger never substitutes for a report; approval
sets remain the applier's sole authority. STALE findings produced through this protocol
carry evidence and complete proposed replacements exactly as today, so the existing
reconciliation → approval → apply path consumes them unmodified.

## 7. Testing (acceptance seam)

One primary seam: repository fixture + prior ledger → `plan_sync` → **fake judgment
adapter** → `accept_sync_judgments` → report + proposed ledger. The interface is the test
surface; comparison, invalidation, probe, and storage helpers stay private. Tests live at
`tests/engine/` (unittest discovery wires them automatically) and assert external
artifacts, result states, mutation absence, judgment-request counts, and cost bounds —
never helper call order or internal structure.

Scenarios (from #169's testing decisions, Phase-A subset):

1. Unchanged repo + compatible ledger ⇒ clean incremental result, zero judgment requests.
2. Source change with passing probe ⇒ zero judgments, fresh deterministic coverage.
3. Source change failing a probe ⇒ exactly that unit in the work order; siblings carried.
4. New assertion unit ⇒ in work order; unchanged siblings reused.
5. Edited unit ⇒ new identity judged; prior entry tombstoned/superseded explicitly.
6. Deleted unit ⇒ tombstone, never an unexplained disappearance.
7. Rewrapped/moved unit with identical normalized content ⇒ identity retained, no judgment.
8. Identical text in two documents ⇒ two entries, independently strategized.
9. Missing/corrupt/foreign/stale-schema/duplicate-identity ledger ⇒ typed refusal, no
   work order, no model.
10. Unknown probe kind, unsafe args, boundary escape, symlink escape, command string ⇒
    refused before execution, entry escalated.
11. Work order over `max_work_order_units` ⇒ typed stop before the model seam, every
    affected unit named.
12. Partial judgments ⇒ partial report naming every unexamined unit; verdict for an
    unasked unit refused.
13. Narrative anchors and planning-document exclusion behave exactly as today.
14. Determinism: identical inputs ⇒ byte-identical work order and proposed ledger.
15. Proposed ledger does not mutate the accepted ledger file.

The fake judgment adapter can return: valid judgments, judgments for unasked units,
malformed shapes, partial coverage, and denial — exercising every acceptance path with
zero real model calls.

## Resolved design questions (decision log)

- **Ledger shape:** single JSONL file, not per-doc shards (avoids flooding consumer repos
  with tracker files) and not one pretty-printed JSON object (unreviewable diffs). User
  decision, 2026-08-02.
- **Probe v1 scope:** the five kinds above; no behavior/test probes. User decision,
  2026-08-02.
- **Cache vs. ledger:** the existing `cache.py` is not repurposed — #169 decision;
  commit-keyed cache semantics are the wrong persistence model for durable audit state.
- **Clock:** engine takes `as_of` as input; no wall-clock reads in artifact content.
