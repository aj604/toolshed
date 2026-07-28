# Shadow-mode parity gate, second cycle (issue #117)

**Status:** criteria re-registered 2026-07-27 in their own commit, before this cycle runs and
before any comparison output exists. Verdict recorded in a later commit.
**Supersedes:** `docs/plans/2026-07-26-shadow-parity-gate.md` (the first cycle's **FAIL**), which
stays as history and is still the record of what the first cycle measured.
**Blocks:** #77 (remove the legacy documentation-sync automation) cites this file's Verdict
section.
**Spec:** issue #117, which names exactly two criteria for re-registration and requires the rest
to carry forward unchanged.

The first cycle failed three of eight criteria. One of the three — G4, false positives — was a
finding about the lane, and its two causes have since been fixed (#93 and #97 for the
anchor-resolution bug, #115 and #118 for the evidence-boundary gap). The other two — G1b and G5
— were findings about *this gate's own instruments*: both were mis-specified, both were
mis-specified in ways only running them revealed, and the first cycle refused to re-specify
either after seeing its result. This file re-registers those two, before anything runs.

## What is re-registered, and what carries forward

| | Criterion | This cycle |
|---|---|---|
| G1a | new lane declares no write permission | carried forward unchanged |
| G1b | shadow cycle leaves the tree byte-identical | **re-registered** (new instrument) |
| G2 | coverage not silently narrower | carried forward unchanged |
| G3 | new lane completes its declared scope | carried forward unchanged |
| G4 | new lane does not manufacture drift | carried forward unchanged |
| G5 | cost measured and bounded | **re-registered** (new normalizer, added clause) |
| G6 | comparison is a program | carried forward unchanged |
| G7 | record is citable | carried forward unchanged |

Carried forward means the text below is the first cycle's text, not a softened version of it.
G4's budget in particular — zero false positives in the auto-apply-eligible class, at most
`floor(records / 10)` overall — is unchanged, and it is the criterion the fixes since the first
cycle were meant to clear.

## Pre-registration discipline

These criteria are committed in their own commit, before the cycle runs. A second cycle cannot
claim the first cycle's ignorance, so what is known has to be stated plainly rather than
pretended away:

- **The first cycle's full result is known**, including that per assertion judged the new lane
  measured *cheaper* than the legacy lane ($0.0675 against $0.0878, a ratio of 0.77). This is
  exactly why G5's re-registration below keeps the original **3x** multiplier and changes only
  the denominator. Lowering the multiplier to something 0.77 clears comfortably, or raising it,
  would both be the move pre-registration exists to prevent. The denominator is changed because
  the first cycle's own analysis established that per-document is not a comparable unit between
  two lanes that examine to different depths; the strictness is not.
- **The legacy baseline is fixed and cannot move.** The legacy lane has produced no report since
  2026-07-07 — every scheduled run from 2026-07-12 onward failed in its model step (`is_error`,
  1 turn, $0) and uploaded no artifact. There is therefore no newer legacy artifact to compare
  against, and this cycle compares against the same `legacy-report.json` / `legacy-meta.json`
  the first cycle used (run `28847329392`). That is a stated limitation of the comparison, not a
  silent reuse.
- **The new lane's deterministic scope is known**, because it is model-free and contains no
  findings: under the landed registry, `drift-plan --mode full` declares 31 documents — 25
  assertion obligations totalling 1962 units of which 1647 are assertion-capable, and 6 anchor
  obligations — and excludes the planning documents as `planning-kind`. The first cycle declared
  33 (27 assertion, 1331 units, 6 anchor); the corpus grew and two skills merged into
  `fixing-docs` since.

What is **not** known: any verdict, record, cost, or comparison from this cycle.

## The registry this cycle uses

The first cycle had to derive a stand-in registry
(`tests/baselines/shadow-parity-gate/registry.json`) because this repository had none. #75 has
since landed the real one at `.doc-lifecycle/registry.json`, and **this cycle uses the landed
registry**, for three reasons:

1. It is what `doc-audit.yml` actually reads — the workflow passes no `--registry`, so the
   engine's default is the file the installed lane audits against. Auditing against the
   stand-in would measure a configuration nobody runs.
2. It went through #75's review, so its roots and extensions are a decision rather than this
   gate's convenience.
3. It classifies this corpus the same way the stand-in did, so the comparison against the first
   cycle stays meaningful: same roots (`README.md`, `CLAUDE.md`, `CONTEXT.md`, `docs`,
   `plugins`), same `extensions: [".md"]`, same narrative/planning/living split.

Point 3 also means the first cycle's declared coverage delta carries over unchanged: four
documents the legacy lane cited are `.yml` and `.json` files, and `extensions: [".md"]` excludes
them. Criterion **G2** governs that, and it is registered here before the run, exactly as it was
the first time.

## The two lanes

| | Legacy lane | New lane (shadow) |
|---|---|---|
| Entry | `.github/workflows/doc-sync.yml` + `doc-bloat.yml` | `python3 -m doclifecycle drift-plan / drift-audit / validate-report` |
| Scope | model-chosen inside a `marker..HEAD` diff; no declared scope | deterministic, registry-derived, declared in the report |
| Contract | `validate-drift-output.py`'s record shape | the report contract (five result states, lineage, coverage) |
| State | `.github/doc-sync/` | `.doc-lifecycle/registry.json` plus the lineage inside the report |
| Writes | yes — `land` job commits and opens PRs | none by construction |

## Pass criteria

The gate passes only if every criterion passes. Any FAIL is a FAIL for the gate, and #77 stays
blocked.

### G1 — the new lane has no write path

**G1a (static).** Unchanged. The new lane's scheduler adapter
(`plugins/doc-lifecycle/skills/scheduling-doc-sync/doc-audit.yml`) declares no write permission
at any level and contains no step that commits, pushes, opens a PR, or otherwise mutates the
repository. Verified by `tests/scripts/audit-workflow_test.py` and
`tests/scripts/workflow-permissions_test.py` passing, plus a direct read of the file's
`permissions:` blocks.

**G1b (dynamic) — re-registered.** The shadow cycle leaves the repository's content
byte-identical.

*The instrument.* `shadow-cycle.py digest --repo .`, which emits JSON carrying `digest`,
`files`, `porcelain_clean`, and `porcelain`. The digest is a sha256 over the sorted
`mode path sha256(bytes)` lines of **the repository's content as the repository defines it**:
the union of `git ls-files` and `git ls-files --others --exclude-standard` — tracked files plus
untracked files the ignore rules do not exclude — minus any path ending `.pyc` or containing a
`__pycache__` component. Symlinks hash their target text; a tracked path that no longer exists
is recorded as deleted so a removal moves the digest rather than vanishing from the enumeration.

*Why those exclusions are registered rather than discovered.* This is the whole of what went
wrong the first time, so it is stated before the measurement, not after it:

- `.git/` churns on every read. Hashing it measures the harness.
- A `.pyc` is not repository content. It is a cache CPython derives from repository content the
  moment anything imports the engine, and its bytes embed the source file's mtime — so a
  `git checkout` of an *unchanged* source re-keys it with no process having written to the
  repository. This repository's `.gitignore` already says as much (`__pycache__/`), but the
  exclusion here is unconditional and does not consult the ignore rules, so the criterion does
  not depend on a consumer's ignore file listing them.

*Why the instrument cannot move again.* It is now under test.
`tests/scripts/shadow-cycle_test.py` (13 tests) pins both halves — what is hashed, what is
excluded, and that the porcelain state is reported rather than assumed — and lands in this same
pre-registration commit. Changing the instrument mid-cycle now means changing a committed test,
which is a visible act rather than an edit to a helper nobody is watching.

**PASS** iff all five hold:

1. The before and after `digest` values are equal.
2. `porcelain_clean` is true at both measurement points.
3. The tree is quiescent between them — nobody, the author included, edits any file in the
   repository between the two measurements. An author edit mid-flight voids the measurement, and
   the response is to re-run the cycle, never to reinterpret it.
4. G1a holds.
5. Every engine output, every worker task file, and every worker answer is written outside the
   repository, so a cycle that created and deleted a file could not hide inside matching
   before/after digests.

Any difference is a FAIL.

### G2 — coverage is not silently narrower

Unchanged. Every document in which the legacy lane's most recent report placed a record must be
either (a) in the new lane's declared scope, or (b) named in the Verdict section with the
mechanical reason it is out of scope and the configuration lever that would bring it in.

**PASS** iff no legacy-cited document is missing from the new lane's declared scope without such
an entry. An unexplained omission is a FAIL.

### G3 — the new lane completes its declared scope

Unchanged. The shadow report's result state is `clean` or `findings`, and its `incomplete` array
is empty. `partial`, `stale`, or `invalid` is a FAIL: a lane that cannot finish a real corpus
has not demonstrated it can replace one that does.

`validate-report --repo .` re-run against the shadow commit must return the same state, so the
report is fresh against the repository it describes.

### G4 — the new lane does not manufacture drift

Unchanged. Every record the shadow report emits is adjudicated in the Verdict section as TRUE
POSITIVE (the record's claim is genuinely wrong at the shadow commit) or FALSE POSITIVE (the
claim is in fact true, or the record is an artifact of registry misclassification or a contract
gap), each with the repository evidence that settles it.

**PASS** iff both hold:

1. **Zero** false positives in the auto-apply-eligible class — `STALE` records carrying an exact
   `fix` preimage and an evidence pointer, which #57's auto-apply policy may mint an approval set
   for without a human. These land autonomously, so their error budget is zero.
2. At most `floor(records / 10)` false positives overall, each named with its cause.

Additionally, where the legacy report and the shadow report both judged the same assertion in
the same document, a disagreement must be adjudicated; an unadjudicated disagreement is a FAIL.

### G5 — cost is measured and bounded — re-registered

*The normalizer.* **USD per assertion actually judged** — one lane-dollar divided by the number
of assertions the lane returned a verdict on. Per examined *document*, the first cycle's
denominator, is only comparable when the two lanes examine a document to the same depth, and
they demonstrably do not: the legacy lane produced ~2 model-chosen claims per document inside a
diff, the new lane judges every factual unit in a deterministically declared scope. Depth of
examination is what the money buys, so it is what the cost is divided by.

*The two counts, and what each is worth.*

- **Legacy:** its 31 records are the only assertions it can be shown to have judged — it declares
  no scope and emits no coverage, so everything it examined and did not report is invisible.
  $2.7202 / 31 = **$0.0878 per assertion judged**. This flatters the legacy lane if it read more
  than it reported, and that is registered here as a known bias in the baseline's favour: the
  bound the new lane must clear is, if anything, tighter than a perfectly-instrumented
  comparison would set.
- **Shadow:** the count of factual verdicts the validated report records under its coverage —
  `VERIFIED` plus `STALE` plus `UNVERIFIABLE`, which is every unit the lane actually reached a
  judgement on. Read from the report, not from the worker logs, so it is the number a reader can
  re-derive from a committed artifact.

*The bound.* **PASS** iff the new lane's USD per assertion judged is at most **3x** the legacy
lane's — at most **$0.2634**. The multiplier is the first cycle's, deliberately unchanged.

*The second clause, also required for PASS.* Model cost, turns, and wall-clock are recorded for
both lanes. The first cycle recorded `turns: null` and `duration_ms: null` for the shadow lane
because 55 parallel sessions do not reduce to one lane-level number; a reason for not measuring
something is not a measurement. This cycle records **per-session distributions** —
count, minimum, median, maximum, and total for each of `num_turns`, `duration_ms`, and
`total_cost_usd` across every worker session in every round — in `shadow-meta.json`. A null in
place of any of those is a FAIL, as it was the first time.

*A required disclosure, not a criterion.* The number of worker sessions and the estimated
fixed per-session cost are reported in the Verdict, because a fan-out this gate's harness needs
(the corpus does not fit one session's context) is not a cost the installed lane pays the same
way. It is a disclosure so a reader can see how much of the total it is; it does not enter the
bound, because a bound with a discretionary subtraction in it is not a bound.

### G6 — the comparison is a program, not prose

Unchanged. The comparison is produced by `compare-shadow-lanes.py` from the two lanes'
artifacts. Its test suite passes, and two consecutive runs over the same inputs produce
byte-identical JSON.

**PASS** iff both hold. A hand-assembled comparison is a FAIL.

### G7 — the record is citable

Unchanged. This file carries the verdict, the artifacts are committed under
`tests/baselines/shadow-parity-gate-rerun/`, and #76 and #77 both carry a comment pointing here.

## Protocol

1. Record the pre-cycle content digest and porcelain (G1b).
2. `drift-plan --mode full` against the landed registry — the declared scope, deterministic.
3. `segment` each declared living document — the assertion units, deterministic.
4. Dispatch model workers over those units, each answering `{unit ordinal, assertion_class}`
   plus `{verdict, kind, tier, evidence}` for every assertion-carrying unit. Workers run as
   headless `claude -p` sessions — the same runner shape `doc-audit.yml` uses, and the only one
   that reports the per-session cost, turn, and duration figures G5 now requires. Their tool set
   is `Skill,Read,Grep,Glob,Bash(git *),Bash(python3 *)`: the installed lane's model job
   (`doc-audit.yml`'s `--allowedTools`) with `Write` removed, so a worker has no capability to
   write anywhere at all, G1b's clause 5 holds by construction rather than by instruction, and
   the declared-tool probe (#118) is still reachable under `Bash(python3 *)`. Answers come back
   on stdout and are written outside the repository by the harness.
5. Merge into one verdicts file (outside the repository) and run
   `drift-audit --repo . --mode full --verdicts … --waivers .github/doc-sync/drift-waivers.json
   --evidence-command gh`, then `validate-report`. The waivers file currently holds no waivers,
   so it annotates nothing; it is passed because the protocol says so, not because it will
   change a record. `--evidence-command gh` is what
   `probe-evidence-tool.py declared --flags` renders from this install's
   `.github/doc-sync/evidence-tools.json`, which is how the installed lane derives it too.
6. Record the post-cycle content digest and porcelain (G1b).
7. Run `compare-shadow-lanes.py compare` over the same legacy artifact the first cycle used and
   this cycle's shadow report.
8. Adjudicate every record, write the Verdict section, commit the artifacts under
   `tests/baselines/shadow-parity-gate-rerun/`.

## Verdict

Not yet run. This section is written after the cycle, in a later commit.
