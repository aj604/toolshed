# Shadow-mode parity gate, second cycle (issue #117)

> Status: ready

**Status:** criteria re-registered 2026-07-27 in their own commit, before this cycle runs and
before any comparison output exists. Verdict recorded in a later commit.
**Amended by:** `docs/plans/2026-07-27-shadow-parity-gate-rerun-addendum.md` — the G4 blocker
below is fixed (#123) and G4 is re-measured there on this cycle's own report. Everything in this
file is what this cycle measured, unchanged.
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
`tests/scripts/shadow-cycle_test.py` pins both halves — what is hashed, what is excluded, and
that the porcelain state is reported rather than assumed — and lands in this same
pre-registration commit. Changing the instrument mid-cycle now means changing a committed test,
which is a visible act rather than an edit to a helper nobody is watching.

*One more instrument change, disclosed here because it is not one of the two this issue named.*
The same commit teaches `shadow-cycle.py merge` to resolve the ordinal-keyed answers #116
landed, mapping them to the digest a round-1 answer would have used so a repair round can still
override one. It is not a criterion and it measures nothing; without it no post-#116 cycle could
be folded at all. Recorded rather than left for a reader to notice in the diff.

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
  $2.7202237 / 31 = **$0.087749 per assertion judged**. This flatters the legacy lane if it read more
  than it reported, and that is registered here as a known bias in the baseline's favour: the
  bound the new lane must clear is, if anything, tighter than a perfectly-instrumented
  comparison would set.
- **Shadow:** the count of factual verdicts the validated report records under its coverage —
  `VERIFIED` plus `STALE` plus `UNVERIFIABLE`, which is every unit the lane actually reached a
  judgement on. Read from the report, not from the worker logs, so it is the number a reader can
  re-derive from a committed artifact.

*The bound.* **PASS** iff the new lane's USD per assertion judged is at most **3x** the legacy
lane's — at most **$0.263248**. The multiplier is the first cycle's, deliberately unchanged.

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

# FAIL — #77 stays blocked, on one criterion.

Criteria re-registered first, in their own commit (`983837b`), before the cycle ran and before
any of its output existed; the cycle and then this verdict landed in later commits. **Seven of
eight criteria pass. G4 fails**, on one false positive in the class whose error budget is zero,
and the gate was declared to pass only if every criterion passes.

Both re-registered criteria pass on their new instruments, and both would have passed on any
honest reading — G1b's before and after digests are identical and G5's ratio is 1.00, not a
figure that needed a favourable denominator to clear. That matters for reading this verdict:
the re-registration is not what produced the PASSes, and it is not what produced the FAIL either.

| | Criterion | Verdict |
|---|---|---|
| G1a | new lane declares no write permission | **PASS** |
| G1b | shadow cycle leaves the repository's content byte-identical | **PASS** |
| G2 | coverage not silently narrower | **PASS** |
| G3 | new lane completes its declared scope | **PASS** (two repair rounds; see the caveat) |
| G4 | new lane does not manufacture drift | **FAIL** — 1 false positive in the auto-apply-eligible class, budget 0 |
| G5 | cost measured and bounded | **PASS** — 1.00x per assertion judged, budget 3x |
| G6 | comparison is a program | **PASS** |
| G7 | record is citable | **PASS** |

The cycle: 31 documents declared (25 assertion, 6 anchor), 1962 units, 1647 assertion-capable,
1103 factual verdicts, 24 records, `findings` with nothing unexamined. 58 headless worker
sessions, `$97.08`. Base commit `983837b53ba88358b270a9ba6cd4192669772161`. Artifacts:
`tests/baselines/shadow-parity-gate-rerun/`.

### One deviation from the registered protocol, stated first

Step 4 registered "headless `claude -p` sessions ... tool set
`Skill,Read,Grep,Glob,Bash(git *),Bash(python3 *)`", and that is what ran. Worth naming
explicitly because it is a difference from `doc-audit.yml`: the installed lane's model job also
holds `Write`, which it uses to write `verdicts.json` into the repository. The workers here had
no `Write` and no `Edit` at all, and returned their answers on stdout; the harness wrote them
outside the repository. That makes G1b's clause 5 true by construction rather than by
instruction, and it is the one place this cycle is *stricter* than the lane it is measuring —
so the write-proof below is evidence about a lane configured slightly more tightly than the one
#77 would leave in place. G1a covers the installed shape statically.

### G1a — PASS

`doc-audit.yml` declares `contents: read` at the workflow level, `contents: read` +
`id-token: write` on the `audit` job (the OAuth exchange, not repository write), and
`contents: read` on `publish`. No step in the file commits, pushes, opens a PR, or otherwise
mutates the repository — a grep for `git commit`/`git push`/`git add`/`gh pr create`/
`create-pull-request` over the file returns nothing. `tests/scripts/audit-workflow_test.py` and
`tests/scripts/workflow-permissions_test.py` both pass, inside a green 21/21 script-suite run.

### G1b — PASS

Both measurements, taken with `shadow-cycle.py digest` around a cycle nobody edited mid-flight:

| | before | after |
|---|---|---|
| digest | `8dd30b1908a9598e43b56b5fb833bc1e8498a68fc6b8cfc6a393db9699e48336` | `8dd30b1908a9598e43b56b5fb833bc1e8498a68fc6b8cfc6a393db9699e48336` |
| files | 476 | 476 |
| `git status --porcelain` | empty | empty |

Recorded in `digest-before.json` and `digest-after.json`. All five clauses hold: the digests are
equal, the porcelain was clean at both points, no file in the repository was edited between them
(the harness, the task slices, the worker answers, the merged verdicts, the report, and the
comparison all live outside it), G1a holds, and the workers had no write capability of any kind.

The first cycle's failure does not recur, and not because the byproducts happened not to appear:
`__pycache__` was written during this cycle exactly as before, and the re-registered instrument
excludes it by rule rather than by luck. The instrument itself is now pinned by
`tests/scripts/shadow-cycle_test.py`, which landed in the pre-registration commit — including a
test named for this failure, asserting that a `.pyc` written into a repository whose ignore rules
do *not* mention it still leaves the digest unchanged.

### G2 — PASS

10 documents both lanes examined, 21 the new lane examined that the legacy lane did not, and 5
the legacy lane cited that the new lane's scope does not contain. Each of the five, with its
mechanical reason and the lever that would bring it in:

| Legacy-cited document | Why out of scope | Lever |
|---|---|---|
| `.github/workflows/doc-sync.yml` | not a `.md` file, and `.github/` is not a declared root | registry `extensions` + a `.github` root |
| `.github/workflows/doc-bloat.yml` | same | same |
| `plugins/doc-lifecycle/skills/scheduling-doc-sync/doc-sync.yml` | not a `.md` file | registry `extensions` |
| `plugins/doc-lifecycle/.claude-plugin/plugin.json` | not a `.md` file | registry `extensions` |
| `plugins/doc-lifecycle/skills/fixing-doc-drift/SKILL.md` | **the document no longer exists** — merged into `fixing-docs` in `2523e34` | none; nothing to bring in |

The fifth is a different kind of entry from the other four and is called out rather than counted
with them: the legacy lane's record is 20 days old and describes a file this repository deleted.
The other four are the single declared consequence of `extensions: [".md"]`, named in this file
before the run, as they were before the first cycle's run. **They remain a real coverage
regression** — the legacy lane made 4 of its 31 claims about YAML header comments and
`plugin.json`, and the new lane makes none. #75 landed the registry with `.md`-only knowingly;
that decision is now the shipped one, and this is the cost it carries.

Two things did improve since the first cycle, both from #75's landed registry: `plugins/` is a
declared root (the inferred draft in #74 omitted it, which would have lost 7 more legacy records),
and the audit now runs against the same registry `doc-audit.yml` reads rather than a stand-in.

Coverage otherwise moves sharply the other way: 31 documents declared against the legacy lane's
15, scope declared deterministically rather than chosen by a model inside a diff, and every
inventoried document accounted for — 31 declared, 11 excluded as `planning-kind`, zero
closed-world findings.

### G3 — PASS, and the caveat has moved

The report is `findings` and `incomplete` is empty. `validate-report --report … --repo .` run at
the audited commit — with no `--registry`, because the landed registry is the engine's default —
exited 0 with `findings` (`freshness-check.json`). The audit is deterministic given its verdicts:
two runs produced byte-identical reports
(`6061dc0bae0d72084293d1b054b91e94d0e5ffd8b0a5b4e9f5609bdc893c04f3`).

Re-running that check at any commit after this verdict lands returns `stale`, and should: this
verdict edits `docs/plans/`, which the registry inventories, so the inventory digest moves. Read
the criterion as satisfied at the commit the report describes, which is the only commit it claims
anything about.

**It took three rounds again — but for an entirely different reason, and a third as often.** The
first cycle's cause was digest transcription: 39 of 1329 answers (2.9%) named a unit digest no
unit had, which failed 13 of 27 documents closed. #116's ordinal keying removed that failure mode
completely: **zero** unknown-unit or unknown-ordinal problems in 1103 judged verdicts across 58
sessions. That fix worked.

What replaced it is smaller and newer. Nine faults across the whole run failed 4 of 25 documents
in round 1 and 1 of 25 in the first repair round:

| Fault | Count | Introduced by |
|---|---|---|
| `evidence.command` carrying shell syntax (a `grep … "a\|b" …*.py`) | 3 | #115 |
| `evidence.command` naming an undeclared tool (`python3 -m doclifecycle …`) | 1 | #115 |
| evidence citing both `source` and `command` (the `command` was the literal string `select:Grep`) | 1 | #115 |
| a `code_block` unit classified `factual` | 2 | pre-existing |
| a `STALE` `fix` written as an instruction rather than a replacement line | 1 | pre-existing |
| a worker returning prose instead of its JSON answer | 1 | pre-existing |

**Five of the nine are misuse of the `evidence.command` affordance #115 added and #118 made
reachable.** That is the honest shape of the trade: the contract gap that caused six false
positives in the first cycle is closed (see G4), and closing it opened a smaller, louder failure
mode in its place — every one of these fails a document closed with a typed reason, none of them
silently corrupts a verdict. At 5 command-citation faults in 1103 judged verdicts the rate is
0.45%, against the digest-transcription rate's 2.9%.

But the arithmetic that mattered the first time still holds: the engine fails a document closed
on any problem, so a 0.45% fault rate failed 16% of the corpus in round 1. **`doc-audit.yml`
still runs one model session with no repair round**, so on this corpus it would have produced a
`partial` report naming four unexamined documents — typed and honest, and still a failure. The
first cycle recommended three fixes for this; the cheapest one (ordinal keys) landed and worked.
The remaining one applies unchanged: **give the lane a repair round, driven by the engine's own
exhaustive problem list.** Two repair rounds here cost `$10.15` of `$97.08` and cleared
everything.

One narrower fix is also now visible, and it is cheap: the model prompt in `doc-audit.yml`
describes `evidence.command` in terms of what the probe prints, but never says the two things
workers actually got wrong — that a citation may carry `source` **or** `command` and never both,
and that a command carrying shell metacharacters is refused. Both are engine rules with typed
codes; neither is in the prompt.

### G4 — FAIL

All 24 records were adjudicated against the repository: by the author, and independently by four
adjudicators who were given the records and the repository and asked to check, not to agree, one
of whom held live `gh` credentials the audit's workers deliberately did not. **23 true positives,
1 false positive.**

**Criterion 2 (at most `floor(24/10)` = 2 false positives overall): PASS — 1.**

**Criterion 1 (zero false positives in the auto-apply-eligible class): FAIL — 1.** And it is the
same record.

The auto-apply-eligible class is taken here as the landed policy defines it
(`doclifecycle/policy.py`'s `CLASS_CODES`), which is **stricter** than the criterion as written:
`drift-stale-mechanical` admits `STALE` records carrying an exact preimage and an
`evidence.source` pointer, and #73 added `narrative-anchor-refresh`, which admits `ANCHOR-STALE`.
That is 12 of the 24 records — 10 `STALE` and 2 `ANCHOR-STALE` — against the criterion's 10.
(No policy file is installed in this repository, so nothing can actually auto-apply here today;
the class is still what the criterion is about.)

**The false positive: DRIFT-023**, on
`plugins/doc-lifecycle/skills/scheduling-doc-sync/SKILL.md:149`.

- The claim: "This repository's own gate record, criteria and verdict, is
  `docs/plans/2026-07-26-shadow-parity-gate.md`."
- At the audited commit that file carries both — `## Pass criteria` with G1–G7, and a `## Verdict`
  section headed **FAIL**. The sentence is true.
- The record's `fix` repoints it at `docs/plans/2026-07-27-shadow-parity-gate-rerun.md` and calls
  that file "criteria and verdict". At the audited commit the rerun file's Verdict section read,
  in full, "Not yet run." **Applying this fix would have introduced drift, not removed it** — and
  it carries an exact preimage and an `evidence.source`, so the policy would mint for it with no
  human.

The generalizable failure, which is why this is not written off as a fluke: the worker reasoned
about a pointer's *intent* rather than its *content*. It saw a newer document declaring itself
the successor, concluded the old pointer was stale, and authored a replacement asserting a
property the new target did not have. Documents pointing at other documents are ordinary, a
superseding sibling is ordinary, and nothing about this repository made the mistake special.

One methodological caveat, recorded because it cuts both ways rather than because it excuses
anything: the superseding file is *this file*, created by the pre-registration commit the cycle
ran against. Running a gate's cycle from inside the branch that re-registers the gate put a
freshly-superseded pointer in the corpus. That is a fair criticism of the setup — and it is also
exactly the kind of in-flight documentation churn a nightly lane meets constantly, so it is a
realistic input, not a contrived one. Either way the lane emitted a wrong fix into the class that
lands unattended, and the criterion's budget for that is zero.

**What the fixes since the first cycle did achieve.** Both of the first cycle's G4 causes are
gone:

- **Cause A (anchor reference resolution, 2 false positives)** — zero
  `ANCHOR-UNRESOLVABLE-REFERENCE` records in this cycle. #93 and #97 closed it, and both
  remaining anchor findings (DRIFT-012, DRIFT-013) are true positives with the anchors' real
  last-changed dates verified by `git log`.
- **Cause B (the evidence boundary could not name non-repository evidence, 6 false positives)** —
  zero. Every one of the 11 `UNVERIFIABLE` records is a correct refusal. The independent
  adjudicator ran the workers' own reachable evidence (`gh <sub> --help`) against each and
  confirmed none of them could have been settled that way; the audit's own verdict text for
  DRIFT-003 shows a worker running `gh issue list --help`, confirming the flag half of a claim,
  and refusing only on the residue. #115 and #118 worked.

**No disagreements to adjudicate.** Six assertions were matched at the same document and line
across both lanes, and both lanes said `VERIFIED` for all six. The mechanical false-positive
candidate set — a shadow finding where the legacy lane verified the same assertion — is empty.
The rest of the legacy lane's records could not be resolved at the shadow commit at all: its
newest report describes `6d525c9d` from 2026-07-07, 20 days and several hundred commits earlier.
That is a limit of this comparison and is reported as such rather than counted as agreement.

**Two auto-apply hazards that are not false positives, and should not be filed as noise.** Both
were found by adjudicators, on records whose verdicts are correct:

1. **DRIFT-021 and DRIFT-022** propose fixes whose *content* is right and whose *shape* is
   wrong. Each targets a bullet that soft-wraps across two-to-four physical lines, and each `fix`
   is a single 206- and 362-character line. The applier's span is line-based within the approved
   units' hull, so these land as over-long lines — or, if only the first line is replaced, leave
   an orphaned fragment behind. "The complete replacement line" is a contract written for
   one-line units, and this corpus's prose bullets are not one-line units.
2. **DRIFT-018**'s fix says a human "names approved record digests from the report" — but the
   bloat report that file defines carries no digest field at all (its own line 9-11 field list
   excludes one). The claim it replaces is genuinely stale; the replacement is a different false
   statement.

Neither is a false positive under the criterion, and neither is harmless. A criterion that counts
only "was the record right" and not "would its fix have been right" understates the risk of an
unattended lane, and a future re-registration should say so.

**A false negative, and this one is operationally real.** The five `docs/agents/triage-labels.md`
rows were all returned `UNVERIFIABLE`, correctly — no repository file records the tracker's
labels, and the declared-tool probe permits only `--help`/`--version` reads, so `gh label list`
is unreachable. With live credentials the adjudicator ran it: `aj604/toolshed` has
`ready-for-agent` and `wontfix`, and **does not have `needs-triage`, `needs-info`, or
`ready-for-human`**. Three of the five documented labels do not exist, and
`scheduling-doc-sync/SKILL.md:161` records the consequence — `gh issue create --label` fails on
an unknown label — so a skill acting on those rows errors out. `CLAUDE.md` compounds it with
"This repo uses the five default canonical triage labels."

This is drift the lane structurally cannot reach, and the reason is worth stating precisely
because #115 and #118 are easy to mistake for having closed it. They closed the *flag* case: a
claim about what `gh issue list` accepts is now settleable and citable. They did not close the
*live state* case: a claim about what exists on the tracker needs a read the probe forbids by
design, since permitting `gh label list` means permitting `gh api` shaped arguments in a
deliberately token-free job. The fix is a boundary decision, not a reasoning fix — either widen
the probe to a named allowlist of read-only subcommands, or record the configured labels in a
repository file the audit can cite. The second is cheaper and needs no credential.

### G5 — PASS

On the re-registered normalizer:

| | Legacy | Shadow |
|---|---|---|
| Cost | $2.7202 | $97.0832 |
| Assertions judged | 31 | 1103 |
| **USD per assertion judged** | **$0.087749** | **$0.088017** |
| Ratio | | **1.003x** (budget 3x) |

The new lane costs, per assertion it actually judges, three tenths of one percent more than the
legacy lane. Both counts are re-derivable from committed artifacts: the legacy figure from its
31 records, the shadow figure from `shadow-report.json`'s per-scope verdict counts
(`VERIFIED` 1082 + `STALE` 10 + `UNVERIFIABLE` 11).

On the first cycle's denominator, for completeness and because burying it would be dishonest:
`$97.0832 / 31` documents is `$3.1317`, against the legacy lane's `$0.1813`, a ratio of
**17.27x** — worse than the 8.43x that failed the first time. That number is in
`comparison.json`, produced by the same program, and it is not a number this verdict disputes.
It is a number this verdict says is not a cost comparison, for the reason the first cycle's own
analysis gave before this cycle ran: the legacy lane judged ~2 model-chosen claims per document
inside a diff, and this lane judged ~36 per document exhaustively over a declared scope. Per
document compares two different amounts of work. The re-registration kept the 3x multiplier
precisely so that this could not be read as the bar moving.

Second clause, per-session distributions, all recorded in `shadow-meta.json`:

| | n | min | median | max | total |
|---|---|---|---|---|---|
| cost (USD) | 58 | 0.4486 | 1.6046 | 4.5047 | 97.0832 |
| turns | 58 | 7 | 28.5 | 88 | 1829 |
| duration (ms) | 58 | 76,312 | 321,827 | 672,609 | 17,840,099 |

No nulls. The registered disclosure: **58 sessions** across four rounds (2 pilot, 50 round-1,
5 repair-1, 1 repair-2), against the one session `doc-audit.yml` runs. The cheapest session cost
`$0.4486`, which is close to the floor a session pays before it reads anything, so roughly
`$26` of the `$97` is per-session fixed cost. The fan-out is not optional — 1962 units do not fit
one session's context — but it is a property of this harness, not a property of the lane, and it
is disclosed rather than subtracted.

Two comparisons to the first cycle, since both are measurements:

- **Per assertion judged, this cycle is 30% more expensive** than the first ($0.0880 against
  $0.0675). The likeliest driver is a tool set change made for fidelity, not for cost: these
  workers load the `detecting-doc-drift` skill, matching `doc-audit.yml`'s `--allowedTools`,
  where the first cycle's workers did not. Median 28.5 turns per session says the workers were
  also doing more checking. Not investigated further; recorded so the next cycle can.
- **Repair cost fell from $5.52 to $10.15 in absolute terms but from 11% to 10.5% of the total**,
  on a corpus 47% larger in judged assertions.

`compare-shadow-lanes.py` reports `turns: null` and `duration_ms: null` for the shadow lane in
`comparison.json`. That is the comparison program having no field for a distribution, not a
missing measurement — it reads a single lane-level number, and a sum of 1829 turns across 58
unrelated sessions is exactly the misleading figure the first cycle refused to publish. The
distributions are in `shadow-meta.json`, which is where the criterion asked for them. The
program retires with the legacy lane in #77, so this is recorded rather than fixed.

### G6 — PASS

`tests/scripts/compare-shadow-lanes_test.py` passes, inside a 21/21 script-suite run. Two
consecutive runs of `compare-shadow-lanes.py compare` over the same inputs produced
byte-identical JSON (`311d01433aed5674fae86c28be54df8c9a117909415226c4bea5ea849047388d`),
matching the committed `comparison.json` exactly. Nothing in the comparison was assembled by
hand.

### G7 — PASS

This file carries the verdict and the artifacts are under
`tests/baselines/shadow-parity-gate-rerun/`. Comments pointing here are posted on
[#76](https://github.com/aj604/toolshed/issues/76#issuecomment-5098915380) and
[#77](https://github.com/aj604/toolshed/issues/77#issuecomment-5098916362) — #77's names the
single blocker, so the issue it gates says what it is waiting for without opening this file.

## What #77 needs before this gate can be re-run and pass

One blocker, and it is narrow:

1. **Stop the lane authoring a `STALE` fix that asserts something it has not checked about the
   fix's own target.** DRIFT-023 is the whole of G4's failure. The record's verdict was a
   judgement about a pointer's intent; its `fix` asserted a property (that a file carries a
   verdict) the worker never read that file to confirm. The narrowest correction is in the
   contract the lane's prompt states: a `fix` that names a path must be settled by reading that
   path, and a claim's *literal* content is what STALE is about — a pointer that is merely
   superseded is a finding for a human, not a mechanical remedy. Whether that is a prompt change,
   a policy exclusion, or a new record code is a decision this record does not make.

Two more that are not blockers under the criteria as written, and would be under a stricter G4
that scored fixes as well as verdicts:

2. **`fix` has no shape for a multi-line soft-wrapped unit.** DRIFT-021 and DRIFT-022 are correct
   findings whose fixes would land as 206- and 362-character lines. Either the contract admits a
   multi-line replacement, or the applier re-wraps, or the lane is told to pre-wrap to the
   document's column.
3. **Give the audit lane a repair round.** `doc-audit.yml` runs one session and would have
   reported `partial` on this corpus over nine model-output faults that two cheap repair rounds
   cleared. This was the first cycle's recommendation too; the other half of it (ordinal keys,
   #116) landed and demonstrably worked.

And one that is not a defect in the lane at all:

4. **Decide how a claim about live tracker state gets evidence.** Three of the five triage labels
   this repository documents do not exist, and the audit cannot see that under any boundary it is
   allowed. Recording the configured labels in a repository file is the cheap answer; widening
   the probe to a read-only subcommand allowlist is the general one.

Item 1 alone unblocks the gate. Items 2 and 3 are worth doing on their own merits, and item 4 is
real drift sitting in the repository right now.

## Against issue #76's acceptance criteria

| #76 acceptance criterion | Met |
|---|---|
| comparison report: agreements, findings unique to each, coverage and cost deltas, false-positive assessment | **yes** — `comparison.json`, produced by a tested program, plus the adjudication above |
| the new lane demonstrably has no write path during shadow operation | **yes** — G1a and G1b, both passing on their own instruments this time |
| pass criteria written down before the comparison is evaluated; verdict recorded where #77 can cite it | **yes** — criteria in `983837b`, cycle and verdict in later commits, verdict here |
| at least one full shadow cycle on the dogfood repository's real documentation | **yes** — 31 documents, 1962 units, 24 records |

The one clause still not exercised, unchanged from the first cycle: "against the dogfood
repository *(and a large consumer where available)*". No external consumer install is known, and
`doc-audit.yml` is now installed here (#75) but nowhere else. Recorded as not available rather
than silently skipped.

## Legacy-lane note, recorded because it bears on urgency

Unchanged and now worse by three weeks: the legacy lane has produced no report since 2026-07-07.
This gate compares against a 20-day-old artifact because there is no newer one to compare
against. The lane this gate protects is not functioning, so "keep the legacy lane until the new
one is proven" remains, in practice, "have no working lane" — which argues for fixing item 1
quickly, not for waiving the gate.
