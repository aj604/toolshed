# Shadow-mode parity gate (issue #76)

**Status:** criteria pre-registered 2026-07-26 (commit `bb15649`); cycle run and verdict
recorded the same day. **Verdict: FAIL** — G4 (false positives) and G5 (cost). See Verdict.
**Blocks:** #77 (remove legacy mutation paths) cites this file's Verdict section.
**Spec:** #57's distilled-decisions comment (2026-07-26), which promotes its shadow-mode note
to a blocking gate; issue #76's acceptance criteria.

Before the legacy lane can be removed, the new read-only audit must run in shadow against this
repository's real documentation alongside the still-live legacy lane, write nothing, and be
compared against the legacy lane on findings, coverage, cost, and false positives. This file is
the gate: its criteria are fixed before the comparison exists, and its verdict is the record
#77 cites.

## Pre-registration discipline

The criteria below are committed in their own commit, before the shadow cycle runs and before
any comparison output exists. What was known when they were written, and is therefore fair
input to them:

- The **legacy lane's** artifacts and history — its most recent successful run
  (`28847329392`, 2026-07-07: diff-scoped over
  `e63285c4a4c2b35183aab492f459bbeb63eed22e..6d525c9dfa92e995631398ff877927b459f95d0f`,
  31 records, all `VERIFIED`, `$2.7202`, 60 turns, 480.7s), and the 14 consecutive nightly
  failures from 2026-07-12 to 2026-07-26 in which it produced no report at all.
- The **new lane's deterministic scope**, which is model-free and contains no findings: the
  shadow registry classifies 42 documents (27 living, 6 narrative, 9 planning) with zero
  closed-world findings, and `drift-plan --mode full` declares 33 of them (27 assertion
  obligations totalling 1331 assertion-capable units, 6 anchor obligations) and excludes 9 as
  `planning-kind`.

What was **not** known: any verdict, record, or comparison from the new lane. Scope sizing
preceded the criteria because it determines a feasible protocol; no criterion below is stated
as an absolute count that the sizing could have been used to clear.

## The two lanes

| | Legacy lane | New lane (shadow) |
|---|---|---|
| Entry | `.github/workflows/doc-sync.yml` + `doc-bloat.yml` | `python3 -m doclifecycle drift-plan / drift-audit / validate-report` |
| Scope | model-chosen inside a `marker..HEAD` diff; no declared scope | deterministic, registry-derived, declared in the report |
| Contract | `validate-drift-output.py`'s record shape | the report contract (five result states, lineage, coverage) |
| State | `.github/doc-sync/` (`drift-waivers.json`, `audit-scope.json`, `doc-sync-marker`, `installed-version` = 0.12.0) | the registry digest and lineage inside the report |
| Writes | yes — `land` job commits and opens PRs | none by construction |

## Shadow registry derivation

The engine needs a registry and this repository has none: #75 owns landing the durable
`.doc-lifecycle/registry.json`, and #74's `migration-draft` door will infer it. The shadow run
therefore uses `tests/baselines/shadow-parity-gate/registry.json`, derived by these rules,
declared here before the run:

1. Roots are this repository's documentation surfaces: the three root `.md` files
   (`README.md`, `CLAUDE.md`, `CONTEXT.md`), `docs/`, and `plugins/`.
2. `tests/` is not a root, which reproduces `.github/doc-sync/audit-scope.json`'s exclusions
   (`tests/fixtures/**`, `tests/baselines/**`, `tests/docs-ab/**`) — the legacy lane's own
   scope configuration.
3. Kinds follow this repository's stated conventions, not convenience: `docs/plans/**` and
   `docs/superpowers/**` are planning (CLAUDE.md: planning artifacts); `docs/guides/*.md` are
   narrative (CLAUDE.md: "durable narrative user guides, each carrying growing-docs'
   `> As of` first-line anchor"); `docs/decisions.md` and `docs/design-rationale.md` are
   narrative (`writing-docs` SKILL.md scopes out "narrative architecture/conceptual overviews
   and design rationale, and decision records (ADRs)"); everything else is living.
4. `extensions` stays at the engine's default `[".md"]`.

Rule 4 is known in advance to lose four of the legacy lane's 31 records, whose locations are in
`.yml` and `.json` files. That is a declared coverage delta, not a discovered one, and
criterion **G2** governs it.

## Pass criteria

The gate passes only if every criterion passes. Any FAIL is a FAIL for the gate, and #77 stays
blocked.

### G1 — the new lane has no write path

**G1a (static).** The new lane's scheduler adapter
(`plugins/doc-lifecycle/skills/scheduling-doc-sync/doc-audit.yml`) declares no write
permission at any level and contains no step that commits, pushes, opens a PR, or otherwise
mutates the repository. Verified by `tests/scripts/audit-workflow_test.py` and
`tests/scripts/workflow-permissions_test.py` passing, plus a direct read of the file's
`permissions:` blocks.

**G1b (dynamic).** The shadow cycle leaves the working tree byte-identical. Measured as a
sha256 over the sorted `(path, sha256(bytes), mode)` triple of every file in the worktree
excluding `.git/`, taken immediately before the cycle's first engine invocation and
immediately after its last, together with `git status --porcelain`.

**PASS** iff both digests are equal, `git status --porcelain` is empty at both points, and G1a
holds. Any difference is a FAIL, including a file the cycle created and deleted again — the
before/after digests would still match, so the cycle additionally runs with all engine output
written outside the repository.

### G2 — coverage is not silently narrower

Every document in which the legacy lane's most recent report placed a record must be either
(a) in the new lane's declared scope, or (b) named in the Verdict section with the mechanical
reason it is out of scope and the configuration lever that would bring it in.

**PASS** iff no legacy-cited document is missing from the new lane's declared scope without
such an entry. An unexplained omission is a FAIL.

### G3 — the new lane completes its declared scope

The shadow report's result state is `clean` or `findings`, and its `incomplete` array is
empty. `partial`, `stale`, or `invalid` is a FAIL: a lane that cannot finish a real corpus has
not demonstrated it can replace one that does.

`validate-report --repo .` re-run against the shadow commit must return the same state, so the
report is fresh against the repository it describes.

### G4 — the new lane does not manufacture drift

Every record the shadow report emits is adjudicated in the Verdict section as TRUE POSITIVE
(the record's claim is genuinely wrong at the shadow commit) or FALSE POSITIVE (the claim is
in fact true, or the record is an artifact of registry misclassification or a contract gap),
each with the repository evidence that settles it.

**PASS** iff both hold:

1. **Zero** false positives in the auto-apply-eligible class — `STALE` records carrying an
   exact `fix` preimage and an evidence pointer, which #57's auto-apply policy may mint an
   approval set for without a human. These land autonomously, so their error budget is zero.
2. At most `floor(records / 10)` false positives overall, each named with its cause.

Additionally, where the legacy report and the shadow report both judged the same assertion in
the same document, a disagreement must be adjudicated; an unadjudicated disagreement is a FAIL.

### G5 — cost is measured and bounded

Model cost, turns, and wall-clock are recorded for both lanes and normalized per examined
document. The legacy baseline is its most recent successful run: `$2.7202` over the 15
documents its records cite, i.e. `$0.1813` per document.

**PASS** iff the new lane's cost per examined document is at most 3x the legacy lane's
(`$0.5439`). Above that, the gate FAILs and the driver is recorded.

### G6 — the comparison is a program, not prose

The comparison is produced by `compare-shadow-lanes.py` from the two lanes' artifacts. Its
test suite passes, and two consecutive runs over the same inputs produce byte-identical JSON.

**PASS** iff both hold. A hand-assembled comparison is a FAIL.

### G7 — the record is citable

This file carries the verdict, the artifacts are committed under
`tests/baselines/shadow-parity-gate/`, and #76 and #77 both carry a comment pointing here.

## Protocol

1. Record the pre-cycle worktree digest (G1b).
2. `drift-plan --mode full` — the declared scope, deterministic.
3. `segment` each declared living document — the assertion units, deterministic.
4. Dispatch one model worker per document (large documents split into unit slices), each
   returning `{unit, assertion_class}` plus `{verdict, kind, tier, evidence}` for every
   assertion-carrying unit. This is the same job `doc-audit.yml`'s model step does headlessly;
   here it runs locally so the cycle can be recorded. Workers read the repository and write
   only to a directory outside it.
5. Merge into one verdicts file (outside the repository) and run `drift-audit --mode full
   --verdicts ... --waivers .github/doc-sync/drift-waivers.json`, then `validate-report`.
6. Record the post-cycle worktree digest (G1b).
7. Run `compare-shadow-lanes.py` over the legacy artifact and the shadow report.
8. Adjudicate every record, write the Verdict section, commit the artifacts.

## Verdict

# FAIL — #77 stays blocked.

Criteria pre-registered in commit `bb15649`; cycle recorded in `2bb2492`; this verdict written
after. Five of seven criteria pass. **G4 (false positives) and G5 (cost) fail**, and the gate
was declared to pass only if every criterion passes.

| | Criterion | Verdict |
|---|---|---|
| G1a | new lane declares no write permission | **PASS** |
| G1b | shadow cycle leaves the tree byte-identical | **PASS** |
| G2 | coverage not silently narrower | **PASS** |
| G3 | new lane completes its declared scope | **PASS** (with a caveat that matters) |
| G4 | new lane does not manufacture drift | **FAIL** — 8 false positives, budget 4 |
| G5 | cost measured and bounded | **FAIL** — 8.43x per document, budget 3x |
| G6 | comparison is a program | **PASS** |
| G7 | record is citable | **PASS** |

The cycle itself is real: 33 documents declared, 1331 assertion units judged, 748 factual
verdicts, 41 records, `findings` with nothing unexamined. Artifacts:
`tests/baselines/shadow-parity-gate/`. Base commit
`90ead6d4ec48e5cd2fd7b69551e6a03f6dc358b6`.

### G1a — PASS

`doc-audit.yml`'s `audit` job holds `contents: read` + `id-token: write` and no credential
(`persist-credentials: false`, no `GH_TOKEN`); its `publish` job holds `contents: read` and
nothing else. No step in the file commits, pushes, or opens a PR.
`tests/scripts/audit-workflow_test.py` (12 tests) and
`tests/scripts/workflow-permissions_test.py` (8 tests) both pass.

### G1b — PASS

Worktree digest `94e1d79b105e8c68ebaf249b570681e0debdf99a2c24ca34c0056ca720bd8ff8` (396 files)
before and after a pass of `drift-plan`, 27 `segment` calls, `drift-audit`, `validate-report`,
and a live headless model worker. `git status --porcelain` reported only the harness edit that
was already pending, unchanged by the run. The model workers ran with no `Write` and no `Edit`
in their tool set at all.

**The first measurement of this criterion was wrong, and the correction is the interesting
part.** The digest hashed every file except `.git/`, which included
`plugins/doc-lifecycle/engine/doclifecycle/__pycache__/*.pyc` — and a `.pyc` embeds its
source's mtime, so `git checkout` of an *unchanged* source file re-keys 16 files that nothing
wrote to the repository. Mid-cycle I edited four tracked files by mistake and reverted them
with `git checkout`; that reverted the content and moved the mtimes, and the post-cycle digest
duly differed with a clean `git status`. Demonstrated rather than argued: deleting
`__pycache__` drops the count 412 → 396 and the digest to `e4938616…`, and one engine import
restores `afbf05f6…` exactly. The instrument now asks git what the repository ignores.

The lane did not write. The instrument was measuring itself.

### G2 — PASS

11 documents both lanes examined, 22 the new lane examined that the legacy lane did not, and 4
the legacy lane cited that the new lane's scope does not contain:

| Legacy-cited document | Why out of scope |
|---|---|
| `.github/workflows/doc-sync.yml` | not a `.md` file |
| `.github/workflows/doc-bloat.yml` | not a `.md` file |
| `plugins/doc-lifecycle/skills/scheduling-doc-sync/doc-sync.yml` | not a `.md` file |
| `plugins/doc-lifecycle/.claude-plugin/plugin.json` | not a `.md` file |

All four are the single declared consequence of `extensions: [".md"]`, named in this file
before the run. The lever is the registry's `extensions` list; `.github/` would additionally
need declaring as a root. **This is a real coverage regression, not a wash**: the legacy lane
made 4 of its 31 claims about YAML header comments and `plugin.json`, and the new lane would
make none. #75 owns the decision when it lands the durable registry.

Coverage otherwise moves sharply the other way — the new lane examined 33 documents against
the legacy lane's 15, declared its scope deterministically rather than letting a model choose
inside a diff, and accounted for all 42 inventoried documents (33 declared, 9 excluded as
`planning-kind`) with zero closed-world findings.

**A second registry finding for #75.** #74's `migration-draft` door, merged after this
registry was written, infers roots `['CLAUDE.md', 'CONTEXT.md', 'README.md', 'docs']` — it does
**not** declare `plugins/` as a documentation root. The legacy lane placed 7 of its 31 records
in `plugins/**` documents. A dogfood install on the inferred registry would therefore lose
those 7 as well as the 4 above. This gate's registry declares `plugins/` deliberately, and #75
should too.

### G3 — PASS, and the caveat is the finding

The report is `findings`, `incomplete` is empty, and `validate-report --repo .` returns
`findings` with no stale reasons against the live repository. The audit is deterministic given
its verdicts: re-running it produced a byte-identical report
(`0c8ce572dfd6e1c2325589fb9acd6c1f7dd57d32fe1149cc076f2775db7e6048`).

**It took three rounds to get there, and the first round failed 13 of 27 living documents.**
The cause is one design decision, not model sloppiness: a unit's identity is a 64-character hex
digest, and the contract requires the model to transcribe it verbatim. Of 1329 first-round
answers, 39 (2.9%) named a digest no unit in the document has, and **36 of those 39 are
near-misses of a unit the same worker left unanswered** — most of them truncated to 57–63
characters, the rest one or two characters off. Because the engine fails a document closed on
any classification problem, a 2.9% transcription error rate invalidated 48% of the corpus.

Two rounds of re-asking only the affected units ($5.52, 14 tasks) cleared it. But note what
that means for `doc-audit.yml` as it stands: it runs **one** model session with **no repair
round**, so on this corpus it would have produced a `partial` report naming 13 unexamined
documents — a typed, honest failure, and still a failure. Before the legacy lane is retired,
one of these should change:

- have the model key answers by a short per-document ordinal the engine maps back to digests
  (the segmenter already emits units in a fixed order), or
- accept an unambiguous digest prefix, or
- add a repair round to the lane, driven by the engine's own exhaustive problem list.

The first is the cheapest and removes the failure mode rather than retrying it.

### G4 — FAIL

Every one of the 41 records was adjudicated against the repository — the five STALE records by
the author, the other 36 by four independent adjudicators who were given the records and the
repository and asked to check, not to agree. **33 true positives, 8 false positives.**

**Criterion 1 (zero false positives in the auto-apply-eligible class): PASS.** All five STALE
records carry an exact preimage and an evidence pointer, so #57's auto-apply policy could mint
for them with no human. All five are true positives, verified individually:

| Record | Claim it falsifies | Confirmed by |
|---|---|---|
| DRIFT-001 | `CLAUDE.md` says "ten skill helper scripts" | an eleventh landed in `c7ec79a` |
| DRIFT-002 | `CLAUDE.md` says CI "runs every `tests/scripts/*_test.py` suite" | `release.yml` enumerated 12 of 15 by hand |
| DRIFT-003 | `CLAUDE.md`'s "only other runnable code" list | omits `tests/baselines/shadow-parity-gate/shadow-cycle.py` |
| DRIFT-038 | engine README's "Every finding also carries `duplicate_search`" | `bloat.py:518` adds it only on the single-document path; `_bulk` never does |
| DRIFT-040 | `scheduling-doc-sync/SKILL.md` says `publish` holds `issues: write` | `doc-audit.yml:171` grants `contents: read` only |

Five for five, on a corpus where the lane emitted 5 STALE out of 1331 units. The class that can
land unattended is clean. That is the most important single result here.

**Criterion 2 (at most `floor(41/10)` = 4 false positives overall): FAIL — 8.** Both causes are
defects with owners, not noise:

**Cause A — an engine bug in anchor reference resolution (2 records).**
`drift._anchor_findings` tests every backticked token in an `As of` line with
`os.path.isfile(os.path.join(repo_root, reference))`. That misreads two ordinary anchor
spellings as "is no longer in the repository":

- a **directory** reference — `os.path.isfile` is false for a directory. `docs/guides/principles.md`'s
  anchor names `` `plugins/doc-lifecycle/skills/` ``, which exists.
- a **shorthand continuation** — an anchor that writes one fully-qualified path and then
  abbreviates its siblings (`` `…/scheduling-doc-sync/SKILL.md`, `doc-sync.yml`, `doc-bloat.yml` ``).
  The abbreviations are resolved against the repository root.

DRIFT-035 and DRIFT-036 rest entirely on this and are wrong. DRIFT-034 and DRIFT-037 carry the
same bogus reason but survive as true positives because their fully-qualified references
independently fail the last-changed-after-as-of test. So the bug produced 2 false findings and
2 misleading evidence strings out of 4 anchor records — a 50% defect rate on that code path.
Fixing it is small and belongs in the engine, before the new lane is anyone's only lane.

**Cause B — a contract gap: the evidence boundary cannot name non-repository evidence
(6 records).** `docs/agents/issue-tracker.md`'s claims about `gh` flags were all returned
`UNVERIFIABLE`. An adjudicator settled six of them offline in seconds with `gh <sub> --help`
— exactly the Tier-2 check `detecting-doc-drift`'s own method sanctions — so they were
verifiable and should not have been findings.

The workers were not being lazy. Two things forced the answer, and both are contract-level:

1. `evidence.source` must be a repository-relative path inside the declared evidence boundary,
   and the boundary is a set of path globs. There is no legal way to record "I ran
   `gh issue edit --help` and read its output", so a verdict resting on local tooling cannot be
   expressed at all. `UNVERIFIABLE` was the only contract-legal answer available.
2. The workers' tool set was read-only over the repository and did not include `gh`, matching
   what a credential-free CI job can safely run.

This is the sharper of the two findings, because it is a hole in the report contract rather
than a bug in one function: **the verification method's tiers admit evidence the report has no
field for.** Either the boundary grows a way to declare and cite non-path evidence (a named
command and its output digest), or the method must stop sanctioning Tier-2 tool evidence, or
documents making claims about external tooling need a kind of their own. #57 should settle it
before #77 removes the fallback lane.

**A false negative, too.** `docs/agents/issue-tracker.md:23` documents
`gh pr list --json …,authorAssociation,…`. `gh pr list --json bogus` enumerates the supported
fields and `authorAssociation` is not among them: the documented command would fail. The lane
returned `UNVERIFIABLE` where the truth was `STALE`. Cause B does not merely inflate the
finding count — it hides real drift.

**No disagreements to adjudicate.** Six assertions were matched at the same document and line
across both lanes, and both lanes said `VERIFIED` for all six. The mechanical false-positive
candidate set — a shadow finding where the legacy lane verified the same assertion — is empty.
25 of the 31 legacy records could not be resolved at the shadow commit at all: the legacy
lane's newest report describes `6d525c9d` from 2026-07-07, 19 days and several hundred commits
earlier, and the lines its records name no longer carry those units. That is a limit of this
comparison and is reported as such rather than counted as agreement.

### G5 — FAIL

| | Legacy | Shadow |
|---|---|---|
| Cost | $2.7202 | $50.4773 |
| Documents examined | 15 | 33 |
| **USD per document** | **$0.1813** | **$1.5296** |
| Ratio | | **8.43x** (budget 3x) |

The pre-registered bound was 3x per examined document. The measured figure is 8.43x, so this
criterion fails as written, and the honest report of a pre-registered criterion is the number
it produced.

**The normalizer is also wrong, and saying so is not a way out of the FAIL.** Per document is
only comparable when the lanes examine a document to the same depth, and they do not: the
legacy lane produced 31 claims across 15 documents (~2 per document, model-chosen inside a
diff), the new lane judged 748 factual assertions across 33 documents (~23 per document,
exhaustive over a deterministic scope). Per assertion actually judged, the new lane is
**cheaper**: $0.0675 against $0.0878, a ratio of 0.77.

So the lane is not extravagant; the budget was set against the wrong denominator. That is a
finding about the gate, and the correct response is to re-register G5 on a defensible
normalizer with the owner's sign-off — not to swap denominators after seeing the result, which
is precisely what pre-registration exists to prevent.

Two real cost drivers belong in that re-registration:

- **Fan-out overhead.** This cycle ran 55 headless sessions (41 + 14 repair) where
  `doc-audit.yml` runs one. A session costs roughly $0.2–0.3 before it reads anything — the
  2-unit `docs/doc-scope.md` slice cost $0.33 — so about $12 of the $50 is per-session fixed
  cost. The fan-out was necessary: 1331 units do not fit one session's context. A cost bound
  must be set against the shape the lane actually runs.
- **Repair rounds.** $5.52 of the total, all of it caused by the digest-transcription failure
  in G3. Fixing that removes the repair rounds and their cost together.

### G6 — PASS

`compare-shadow-lanes.py`, built test-first; `tests/scripts/compare-shadow-lanes_test.py` is
27 tests, all passing. Two consecutive runs over the committed artifacts produce byte-identical
JSON (`b7974b35bc68d2142493442c6cf37f25f38ca9a4b6d56b2a81b463b9d32c536d`), matching the
committed `comparison.json` exactly.

### G7 — PASS

This file carries the verdict; the artifacts are under `tests/baselines/shadow-parity-gate/`;
#76 and #77 carry comments pointing here.

## What #77 needs before this gate can be re-run and pass

1. Fix `drift._anchor_findings`'s reference resolution — directories and shorthand
   continuations (Cause A).
2. Settle how the report contract records non-path evidence, or narrow the method that
   sanctions it (Cause B). This one is a contract decision, not a patch.
3. Remove the digest-transcription failure mode — ordinal-keyed answers are the cheapest fix —
   or give the lane a repair round.
4. Decide the registry's `extensions` and roots for the dogfood install (#75), knowing that
   `.md`-only and `plugins/`-less each drop documents the legacy lane covered.
5. Re-register G5 against a normalizer the owner signs off on.

Items 1–3 are also worth doing on their own merits, independent of the gate: each is a defect
this cycle found in code that is already merged.

## Legacy-lane note, recorded because it bears on urgency

The legacy lane has produced no report since 2026-07-07. Every scheduled run from 2026-07-12 to
2026-07-26 failed in its model step (`is_error`, 1 turn, $0) and uploaded no artifact — 14
consecutive nights. The lane this gate is protecting is not currently functioning, so "keep the
legacy lane until the new one is proven" is, in practice, "have no working lane". That argues
for fixing items 1–3 quickly, not for waiving the gate.
