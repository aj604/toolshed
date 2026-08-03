# Assertion ledger bootstrap — Phase B design

**Status:** approved design, awaiting implementation plan
**Parent:** [#169 — Make nightly drift sync incremental with an assertion ledger and deterministic probes](https://github.com/aj604/toolshed/issues/169)
**Issue:** [#171 — Phase B: model-assisted bootstrap with heuristic evidence pre-resolution](https://github.com/aj604/toolshed/issues/171)
**Depends on:** [#170 — Phase A](https://github.com/aj604/toolshed/issues/170), which must carry four contract amendments (§11) before it is built.
**Design doc for Phase A:** `docs/plans/2026-08-02-assertion-ledger-incremental-sync-phase-a.md`

## Why (one paragraph)

Phase A gives the audit engine a durable assertion ledger and a deterministic
incremental protocol, but nothing to run them against: a repository with no
ledger has no reuse to narrow, and every sync is a full-corpus model run. Phase
B establishes that first ledger. It is the one operation in the lifecycle that
is deliberately expensive, so it is also the only place where "cheapest possible
bootstrap" is an engineering problem rather than a slogan. The target is a
complete bootstrap of this repository for **under $20**, against a measured
complete-audit baseline of **$69.71** — and the levers that get there are
measured, not assumed.

## 1. Scope and non-goals

Phase B ships a bootstrap mode of the Phase A sync protocol, a chunked and
resumable execution model, a deterministic cost preflight, evidence
pre-resolution, and report seeding. It is invoked by a human through a setup
flow and delivers a proposed ledger as a pull request. It changes no scheduler
and installs no lane.

Non-goals: bootstrapping this repository's real ledger (Phase B validates on
fixtures — the spend is a separate decision); the scheduler rewrite (Phase C);
migration, deep reconciliation, and tombstone pruning (Phase D); and probe
pre-compilation, which §6 retires on measurement.

## 2. The measured corpus

Measured on this repository at `5ef1471`, 2026-08-02:

| measure | value |
|---|---|
| assertion-capable units in **living** documents | **1,931** across **25** documents |
| living-document units as the drift report counts them | 2,260, of which 1,988 carry a class |
| units in **narrative** documents | 524 across 6 documents — `anchor` obligation, deterministic checks, never reach a model |
| chunks at a 150-unit cap | **31**, of which **2** documents require splitting |
| largest document | `plugins/doc-lifecycle/engine/README.md` — 808 units, 42% of the living corpus |

Both unit counts are correct and measure different things: 2,260 is the report's
count of living-document units; 1,931 counts only the segmenter's
assertion-capable kinds (`sentence`, `list_item`, `table_row`, `block_quote`).
Narrative documents are excluded from bootstrap entirely — their obligation is
an anchor check Phase A already performs deterministically.

## 3. Cost model and target

**Baseline.** The 2026-08-01 scheduled audit is the first complete full-corpus
run on record: `status: findings`, 31/31 documents examined, `incomplete: []`,
**$69.71 / 165 turns / 62 minutes**. The following day's run cost **$68.97** and
examined only the six narrative documents, returning no verdict set for any of
the 25 living documents — near-identical spend, essentially no output. Cost is
fixed; output is not. Bootstrap costs more per unit than an audit, because it
additionally produces `strategy`, `probe`, and `deps`, so the honest baseline is
*at least* $70.

**Target: under $20 for a complete bootstrap of this repository**, carried as a
release-gate number (§12), not an aspiration.

**Levers, with their basis.** Pricing is per MTok: Opus 5 $5/$25, Sonnet 5
$3/$15, Haiku 4.5 $1/$5; cache reads 0.1× input, writes 1.25× (5m) / 2× (1h).

| lever | multiplier | basis |
|---|---|---|
| Narrative exclusion | 1.27× | measured — 524 of 2,455 units carry an `anchor` obligation |
| Batching / context amortization | ~3× | measured — the prior $97 run averaged 19 assertions per session; chunks average 62 |
| Prompt caching across chunks | ~2× | 31 chunks share a byte-identical prefix; chunk 1 writes it, 2–31 read at 0.1× |
| Evidence pre-resolution | ~2× | measured — turn count, not reasoning, dominates; the 2026-07-31 run burned 62 turns and 69 permission denials producing zero verdicts |
| Sonnet over Opus | 1.67× | measured pricing (2.5× while intro pricing holds, through 2026-08-31) |
| Report seeding | see §7 | measured — 36.4% of units need no model judgment at all given a seed |

**Levers deliberately declined.** Haiku-tier classification: a ledger is durable
and inherited by every future sync, so a cheap-tier misclassification is a
permanent defect rather than one re-derived nightly. The Batch API's flat 50%:
it would fork the execution model away from existing lane discipline for a
multiplier the other levers already cover, and remains additive later.

## 4. Execution: chunked, resumable, document-granular

Bootstrap emits an **ordered sequence of bounded work orders**, each accepted
independently through Phase A's phase-2 seam, accumulating into one proposed
ledger. Chunk ids are content-addressed, so re-planning an unchanged tree yields
the same ids and a chunk whose result already exists is not re-run. Prior art:
`plugins/doc-lifecycle/skills/detecting-doc-bloat/scripts/plan-chunks.py`.

Resumability is not a convenience. A bootstrap that dies at unit 1,800 and
restarts from zero is the exact failure #169 exists to eliminate.

**Packing:** whole documents where the document fits the bootstrap chunk cap;
documents exceeding it split at heading boundaries, each sub-chunk carrying its
heading path as context. Whole-document packing matters because evidence context
is document-scoped — splitting a document means re-supplying and re-paying for
the same context.

**The bootstrap chunk cap is a distinct knob from `max_work_order_units`.** They
govern different things. `max_work_order_units` is a *tripwire*: "this sync asked
for 40+ judgments — something unexpected happened, stop and make a human
decide," and its correct value is small. A bootstrap cap is a *packing
parameter*: how big a bite one model session takes. Conflating them forces a bad
trade — either the tripwire is uselessly large or bootstrap cannot run at all.
Bootstrap mode is therefore exempt from the tripwire: a large unit count is
bootstrap's expected condition, not its anomaly, and a tripwire that fires on
every run trains people to bypass it. The preflight (§9) is the real gate.

## 5. Model tier and dispatch

Each chunk is dispatched as a fresh subagent with an **explicit model**, never
inherited from the invoking session. Neither an interactive skill nor today's
lanes can otherwise constrain the tier — the installed lanes pass `--max-turns`
and `--allowedTools` but no `--model`, and a skill cannot change its own
session's model.

The value is a **tier alias** (`sonnet`), not a pinned model id. An alias does
not go stale when a new model ships; a pinned id needs a plugin release to stay
correct, and the constraint being expressed is tier-shaped anyway.

**Configuration:** the `sync` section of `.doc-lifecycle/config.json` — Phase
A's consumer-owned cost-control file, born merged so #169 never ships a second
consumer knob file (Phase C decision, 2026-08-02; §11 item 7) — gains
`bootstrap_model`, default `"sonnet"` (absent file, section, or field means the
default). Model tier is cost control and belongs with the other cost knobs
rather than in a second config file.

The chunk judgment prompt itself has one owner: the tested renderer script
Phase C's judge job uses to turn a work order into a prompt. Bootstrap chunks
and sync nights are the same judgment contract with different invokers, so B's
implementation plan consumes that renderer rather than authoring a second
prompt for the same contract.

It is a **default, not a ceiling**. A consumer with a small doc set and high
accuracy requirements may legitimately spend Opus money on a one-time artifact
they will inherit for years, and the plugin has no standing to refuse. The
control that matters is the preflight, which shows real dollars before spending
them; a tier restriction is a crude proxy for what the preflight measures
directly.

## 6. Evidence pre-resolution (retiring probe pre-compilation)

#171's original framing was *heuristic probe pre-compilation*: deterministic
heuristics discharging obvious probes so model judgment is spent only on what
heuristics cannot handle. Measured against this corpus, that ceiling does not
support the framing:

- **78%** of assertion units contain no path-shaped literal at all. This is a
  prose corpus, not a reference-table corpus, and no amount of heuristic
  sophistication moves that number.
- **8.6%** of units have every cited path resolvable (repo-root or unique-suffix
  match).
- **~1%** are citation-shaped enough that a path-existence probe would discharge
  the unit's actual claim rather than overstate it.

A resolvable citation inside a prose sentence does not mean `path_exists` proves
the sentence. Compiling a probe there would violate #169's invariant that reuse
may narrow model work but never overstate coverage — and it fails *silently*,
as a false pass.

**The feature is therefore evidence pre-resolution.** Deterministic code
resolves every literal a unit cites into concrete file paths, hands the model
that evidence pre-read, and seeds the entry's `deps`. No unit is ever discharged
without model judgment. It attacks the measured cost driver — turns spent
searching — and degrades honestly: a wrongly-resolved dependency makes a
judgment request noisier, never falsely covered.

## 7. Report seeding

A validated drift report carries **per-unit** data for every unit, not only for
findings:

```json
{"unit": "<digest>", "assertion_class": "factual", "obligation": "evidence",
 "location": "CLAUDE.md:3", "kind": "structure", "tier": 1,
 "evidence": {"observed": "..."}}
```

That supplies two of a ledger entry's five judgment-bearing fields (`class`,
`obligation`) for every unit, plus observed evidence — a strictly better input to
`deps` than a regex-derived path list, because it is what a model actually
consulted rather than what a pattern guessed.

Measured class distribution across the 1,988 classified living units of the
2026-08-01 report:

| class | count | share |
|---|---:|---:|
| factual | 1,265 | 63.6% |
| normative | 441 | 22.2% |
| rationale | 174 | 8.8% |
| non-assertive | 108 | 5.4% |

Phase A forbids normative and rationale units from carrying probe strategies, so
for **36.4%** of units the strategy is derivable from class alone — fully
discharged, zero model calls. The remaining 64% arrive pre-classified with
evidence attached. Seeding is therefore the largest single lever in §3 and
partly subsumes evidence pre-resolution.

**Seeding is opportunistic, never a precondition.** A consumer with no valid
report bootstraps without one. A report seeds only when its lineage, schema,
registry, inventory, and coverage revalidate completely; a partial, stale,
foreign, or invalid report seeds nothing. Both cases exist as real artifacts on
this repository — the 2026-08-01 report is a valid seed, the 2026-08-02 report
is `status: partial` and must seed nothing — and both should be preserved
in-repo as fixtures before the Actions artifacts expire.

## 8. Partial coverage

**A document is covered if and only if all of its units are bootstrapped.**
Coverage commits at document granularity, never chunk granularity: accepting
five of a document's six chunks leaves that document uncovered, and chunk state
is purely resume bookkeeping. A half-audited document is precisely the "clean
report over an unexamined corpus" failure #169 was written about.

A partial ledger is valid. Its header records which documents are covered and
which are not; sync generates **no work orders** for undeclared documents and
every report states them as uncovered.

The alternative — a partial ledger that is silently narrow — is a trap, not a
degradation. A document with no ledger entries is not "unknown" to the sync:
every unit in it reads as `new`, lands in the work order, exceeds the tripwire,
and stops the nightly with `over-budget` every run thereafter. An incomplete
bootstrap must not become a permanently broken steady state.

Declared coverage also dissolves the ordering dependency in §9: bootstrap the
stable documents now and leave the ones a bloat pass is about to rewrite
deliberately uncovered, rather than paying for them twice or waiting.

## 9. Setup flow and preflight

**The preflight is not a feature.** It is Phase A's phase 1, rendered, and
stopped there. Phase A's protocol already runs inventory, segmentation, ledger
comparison, and planning deterministically with zero model calls, then emits a
work order and stops. Bootstrap's setup makes that boundary human-facing:

1. **Preconditions** — registry present and valid, no ledger already installed,
   clean worktree.
2. **Plan** — inventory → living documents → segmentation → chunk plan. Free and
   deterministic.
3. **Estimate** — a rendering of what the plan already knows: documents, units,
   chunks, byte-derived token estimate, configured tier, dollar range, and a
   per-document cost breakdown. The engine is stdlib-only and cannot call
   `count_tokens`, so this is an estimate from byte counts and the display says
   so rather than printing false precision.
4. **Human decision.**
5. **Execute** — chunk by chunk, resumable.
6. **Propose** — §10.

**Budget enforcement is at the preflight *and* at every chunk boundary.** A
budget checked only before starting is a prediction, not a budget; because the
estimate is a byte-count approximation it will sometimes be wrong, and a 3×
underestimate would otherwise spend 3× the ceiling unopposed. Re-checking costs
nothing — the chunk boundary is a checkpoint that exists anyway — and stopping
is recoverable rather than destructive, because the run resumes and every
already-accepted chunk is kept. A budget stop states on the run surface what it
spent, what remains uncovered, and the exact command to resume.

**Prune coupling is quantified, not enforced.** Unit identity is
content-addressed, so any unit a later bloat fix rewrites becomes a *new*
identity, is re-judged at full cost, and leaves a tombstone behind.
Bootstrapping before pruning therefore guarantees paying twice for every unit a
prune touches. There is no durable repository state recording pending bloat
records and the engine cannot reach the network to inspect workflow runs, so a
hard precondition would be unenforceable or dishonest. Instead the estimate
carries the per-document breakdown and states plainly that units rewritten by a
later prune are re-judged at full cost — putting the consequence next to the
number being approved rather than in prose nobody reads. On this repository the
exposure is concentrated: `engine/README.md` is 42% of the estimate and the most
obvious condensation candidate in the tree.

## 10. Delivery

Bootstrap is **human-invoked** through a setup flow — no cron, no chained
trigger. It opens a **pull request** adding `.doc-lifecycle/assertion-ledger.jsonl`,
whose body carries the preflight estimate, actual spend, covered and uncovered
document lists, and per-document entry counts.

A pull request rather than an issue because the artifact is thousands of JSONL
entries and Phase A chose JSONL precisely so that "one file whose git diff is
exactly the set of changed entries" is reviewable; an issue discards that. The
apply and policy lanes already deliver through real PRs, and Phase A states that
committing the ledger is a human-reviewed act through the normal change path. A
notice issue would have nobody to notify — the human who invoked the run is
present when it finishes.

## 11. Required Phase A (#170) contract amendments

Phase A is not yet implemented. These belong in its schema and protocol rather
than being retrofitted onto a released contract, because the design fails closed
on unknown schema versions — a bump after Phase A ships is a hard break for
anyone who has bootstrapped.

1. **Bootstrap as a first-class mode of `plan_sync`**, with the work-order size
   tripwire mode-conditional. A missing ledger must never *silently* become a
   bootstrap.
2. **Work orders bound to a bootstrap session id, chunk id, and total chunk
   count**, so phase 2 can refuse a chunk from a different session or a stale
   plan, and so an accumulating proposed ledger is assemblable from
   independently-accepted chunks. Phase A's current single-shot binding cannot
   express this.
3. **Entries carry `provenance: judged | heuristic | seeded`; lineage carries
   `model`.** Without both, no future reviewer can answer "which entries were
   classified by which tier, and which had no model behind them at all?" — the
   only question that matters when deciding whether to trust or re-derive an old
   entry. Phase A currently states that strategy is assigned by model judgment,
   which seeding and class-forced strategies both contradict.
4. **The ledger header records covered and uncovered documents**, and sync treats
   "not in the covered set" as *declared-uncovered* rather than *new*. Without
   this the schema cannot express a partial bootstrap at all (§8).

Items 5–8 were recorded during Phase C's ([#172](https://github.com/aj604/toolshed/issues/172))
grilling session (2026-08-02) and live here because Phase A's design doc is not
yet on main:

5. **The empty work order flows through phase 2.** `accept_sync_judgments`
   accepts an empty judgment set against an empty work order and emits the
   validated clean incremental report through the same door — the scheduler
   never grows a sideline path for the zero-cost night. Phase A's test
   scenario 1 pins this.
6. **Findings arise only from model judgment or the deterministic checks that
   already produce them today (narrative anchors).** A probe failure escalates
   its unit to the work order — it never directly becomes a finding. Otherwise
   the policy lane could auto-apply a change no model ever reviewed, a trust
   posture nobody chose.
7. **`sync-budget.json` is born as the `sync` section of
   `.doc-lifecycle/config.json`.** Same fields, same defaults, same fail-closed
   semantics. #169 ships exactly two consumer files total across all phases:
   `assertion-ledger.jsonl` and `config.json`.
8. **The `sync` section also carries `sync_model`** — tier alias, default
   `"sonnet"`, default-not-ceiling, sibling of `bootstrap_model` — the
   scheduled judge job's tier. Phase C binds it to the model step and adds the
   explicit-model-input invariant to the workflow suites.

## 12. Testing

**One acceptance seam**, matching Phase A's: a doc-bearing fixture repository
with no ledger → bootstrap plan → fake judgment adapter → accept → proposed
ledger, exercised through both the library call and the CLI as a subprocess.

**Zero real model calls across the entire suite.** That is the gate, not a
nicety.

Scenarios:

1. Full bootstrap of a small fixture produces a complete ledger.
2. Budget stop mid-run yields document-granular coverage.
3. Resume produces a byte-identical proposed ledger to an uninterrupted run.
4. A split document with only some chunks accepted stays **uncovered**.
5. Chunk ids are stable across re-planning of an unchanged tree.
6. A chunk bound to a different bootstrap session is refused.
7. Evidence pre-resolution seeds `deps`.
8. `provenance` and lineage `model` are recorded on every entry.
9. A complete, current report seeds; a `partial` report seeds nothing.
10. Class-forced units (normative, rationale, non-assertive) receive a strategy
    with no judgment request.
11. The preflight estimate is deterministic and model-free.

**Release gate:** the preflight, run against *this* repository's real corpus,
estimates under $20; zero model invocations across the suite; byte-determinism
of the plan and the proposed ledger. The preflight is free and deterministic, so
the real-corpus number is obtainable without Phase B ever spending money.

## Resolved design questions (decision log)

All user decisions, 2026-08-02.

- **Spec before Phase A lands**, because Phase A freezes the schema and binding
  surface and only Phase B knows their requirements.
- **Chunked, resumable, whole-document packing** rather than one large work
  order or one-per-document.
- **Separate bootstrap chunk cap; bootstrap exempt from the tripwire.**
- **Sonnet as the tier ceiling for this repository**, expressed as a default
  rather than an enforced ceiling.
- **Model set at dispatch**, as a tier alias, from `config.json`'s `sync`
  section.
- **`config.json` born merged; `sync_model` added** — Phase C grilling
  decisions, 2026-08-02, recorded in §11 items 5–8.
- **Evidence pre-resolution replaces probe pre-compilation**, on measurement.
- **Prune coupling quantified in the estimate**, not enforced.
- **Partial ledgers valid, document-granular coverage.**
- **Seeding stays in Phase B**, once measurement showed it discharges 36.4% of
  units outright and pre-classifies the rest.
- **Delivery by pull request**, not an issue.
- **Phase B does not bootstrap this repository** — fixtures only.

## Related findings

Surfaced while speccing this phase, all out of scope here:

- [#174](https://github.com/aj604/toolshed/issues/174) — scheduled bloat audit
  lane: two zero-job startup failures, no scheduled run has fired yet.
- [#175](https://github.com/aj604/toolshed/issues/175) — `doc-policy-apply`
  fails 100% of runs; the audit and policy lanes derive the audit-config digest
  from different evidence boundaries.
- [#169 comment](https://github.com/aj604/toolshed/issues/169#issuecomment-5161860325)
  — $138.68 burned across two post-stop-loss audit runs, and the corrected
  cost baseline this design uses.
