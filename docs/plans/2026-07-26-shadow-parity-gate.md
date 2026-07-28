# Shadow-mode parity gate (issue #76)

**Status:** criteria pre-registered 2026-07-26 in their own commit; cycle run and verdict
recorded the same day, in later commits. **Verdict: FAIL** — G1b (write proof, on its
instrument), G4 (false positives), G5 (cost). See Verdict.
**Superseded by:** `docs/plans/2026-07-27-shadow-parity-gate-rerun.md` (#117), which re-registers
G1b and G5 and records a second cycle's verdict. This file stays as the first cycle's record and
is the only place the 2026-07-26 measurements live; #77 cites the rerun.
**Blocks:** #77 (remove legacy mutation paths) cited this file's Verdict section until the rerun
landed.
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
  shadow registry classifies 43 documents (27 living, 6 narrative, 10 planning) with zero
  closed-world findings, and `drift-plan --mode full` declares 33 of them (27 assertion
  obligations totalling 1331 assertion-capable units, 6 anchor obligations) and excludes 10 as
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

Criteria pre-registered first, in their own commit, before the cycle ran and before any
comparison existed; the cycle and then this verdict landed in later commits. Five of eight
criteria pass. **G1b (write proof), G4 (false positives), and G5 (cost) fail**, and the gate
was declared to pass only if every criterion passes.

G4 is a finding about the lane. G1b and G5 are findings about this gate: both criteria were
mis-specified, both were mis-specified in ways that only running them revealed, and neither may
be re-specified after seeing its result. They are recorded as failures and listed for
re-registration.

| | Criterion | Verdict |
|---|---|---|
| G1a | new lane declares no write permission | **PASS** |
| G1b | shadow cycle leaves the tree byte-identical | **FAIL** — as written; see below, the lane did not write |
| G2 | coverage not silently narrower | **PASS** |
| G3 | new lane completes its declared scope | **PASS** (with a caveat that matters) |
| G4 | new lane does not manufacture drift | **FAIL** — 8 false positives, budget 4 |
| G5 | cost measured and bounded | **FAIL** — 8.43x per document, budget 3x; turns/duration not recorded |
| G6 | comparison is a program | **PASS** |
| G7 | record is citable | **PASS** |

Issue #76's own acceptance criteria are a different list from these, and they fare better —
see "Against issue #76's acceptance criteria" at the end. In particular #76 asks that the new
lane "demonstrably has no write path", which the evidence does establish; it is this file's
**G1b**, a stricter and — it turned out — mis-specified instrument, that fails.

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

### G1b — FAIL as written

The criterion said: a sha256 over **every file in the worktree excluding `.git/`**, equal
before and after, with `git status --porcelain` empty at both points. Measured against that
text, it fails:

- The digests differed — `fcf4cb87…` before, `afbf05f6…` after.
- The re-measurement that came out equal (`94e1d79b…`, 396 files) used a **changed
  instrument** — one that also skips whatever the repository's ignore rules exclude — and ran
  with `git status --porcelain` non-empty (a harness edit of mine was pending).

I changed the instrument after it produced a difference and initially recorded this criterion
as a PASS. That is the same move G5 below refuses, and it is not available here either. The
criterion was mis-specified; a mis-specified criterion is re-registered, not reinterpreted
mid-evaluation. **FAIL**, and G1b joins G5 on the re-registration list.

**What the evidence does show, separately from the criterion.** The difference was entirely
`plugins/doc-lifecycle/engine/doclifecycle/__pycache__/*.pyc`, which CPython writes the moment
anything imports the engine, and whose bytes embed the source file's mtime. Mid-cycle I edited
four tracked files by mistake and reverted them with `git checkout`, which restored the content
and moved the mtimes; the next import re-keyed 16 `.pyc` files that no process had written to
the repository. Demonstrated rather than argued: deleting `__pycache__` drops the count
412 → 396 and the digest to `e4938616…`, and a single engine import restores `afbf05f6…`
exactly.

Three independent observations that the lane wrote nothing, none of which depends on the
digest:

1. `git status --porcelain` was empty both before and after the cycle proper — every tracked
   file matched `HEAD`.
2. The only untracked files present afterwards were the 16 ignored `.pyc` byproducts, and their
   bytes are reproducible from an import.
3. The model workers ran with no `Write` and no `Edit` tool at all — their tool set was
   `Read,Grep,Glob,Bash(git log:*),Bash(git show:*),Bash(git ls-files:*),Bash(python3:*)`.

So the lane did not write, and issue #76's acceptance criterion on that point is met. What
failed is this file's instrument for proving it, which measured itself.

The re-registered form should hash the repository's content as the repository defines it —
tracked files plus untracked-but-not-ignored — and require a clean porcelain, with the
measurement taken around a cycle that nobody edits mid-flight.

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
inside a diff, and accounted for all 43 inventoried documents (33 declared, 10 excluded as
`planning-kind`) with zero closed-world findings.

**A second registry finding for #75.** #74's `migration-draft` door, merged after this
registry was written, infers roots `['CLAUDE.md', 'CONTEXT.md', 'README.md', 'docs']` — it does
**not** declare `plugins/` as a documentation root. The legacy lane placed 7 of its 31 records
in `plugins/**` documents. A dogfood install on the inferred registry would therefore lose
those 7 as well as the 4 above. This gate's registry declares `plugins/` deliberately, and #75
should too.

### G3 — PASS, and the caveat is the finding

The report is `findings` and `incomplete` is empty. The audit is deterministic given its
verdicts: re-running it produced a byte-identical report
(`0c8ce572dfd6e1c2325589fb9acd6c1f7dd57d32fe1149cc076f2775db7e6048`).

The freshness re-check passed **at the audited commit**: run there, before this branch was
rebased and before the version bump,
`validate-report --report report.json --repo . --registry <the shadow registry>` exited 0 with
`findings` and no stale reasons. It does not pass now, and should not: the branch was rebased
onto `main`, so the pinned `base_commit` is no longer an ancestor, and the plugin version moved
0.20.0 → 0.22.0, which the contract says marks every prior report stale on purpose. Bare
`--repo .` without `--registry` returns `invalid`, because this repository still has no
`.doc-lifecycle/registry.json` — that is #75's to land. Read the criterion as satisfied at the
commit the report describes, which is the only commit it claims anything about.

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

**A corollary, because this measurement generalizes.** Any contract that asks a model to
reproduce a 64-character hex string verbatim carries this error rate. That is an argument
against the tempting next step of re-keying `drift-waivers.json` onto unit digests instead of
`{file, claim}` text. Here a garbled digest fails a document closed — loud, and the reason it
cost three rounds instead of silently losing coverage. In a waivers file the same slip would
silently *un-waive* an accepted claim, and nothing would fail. Text-keyed waivers are the more
robust shape while a model is in the loop, and this is the measurement that says so. (Raised
by #74 while reviewing this record; the waivers file is `{file, claim}` today, so this is
prospective rather than a correction.)

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

- a **directory** reference — `os.path.isfile` was false for a directory; fixed in `dcff17d` (#93) to `os.path.exists`. `docs/guides/principles.md`'s
  anchor names `` `plugins/doc-lifecycle/skills/` ``, which exists.
- a **shorthand continuation** — an anchor that writes one fully-qualified path and then
  abbreviates its siblings (`` `…/scheduling-doc-sync/SKILL.md`, `doc-sync.yml`, `doc-bloat.yml` ``).
  The abbreviations are resolved against the repository root.

DRIFT-035 and DRIFT-036 rest entirely on this and are wrong. DRIFT-034 and DRIFT-037 carry the
same bogus reason but survive as true positives because their fully-qualified references
independently fail the last-changed-after-as-of test. So the bug produced 2 false findings and
2 misleading evidence strings out of 4 anchor records — a 50% defect rate on that code path.

**The two spellings are disjoint defects sharing a line, not one bug with two symptoms**, and
anyone fixing this needs to know that before they start. Running `_anchor_references` over
every anchored document in this repository (measured by #74):

| Reference | `isfile` | `exists` | |
|---|---|---|---|
| `plugins/doc-lifecycle/skills/` | False | **True** | directory |
| `doc-sync.yml` | False | False | abbreviated |
| `doc-bloat.yml` | False | False | abbreviated |
| `fixing-doc-bloat/SKILL.md` | False | False | abbreviated |
| `growing-docs/SKILL.md` | False | False | abbreviated |

Changing `isfile` to `exists` fixes **one of five**. For the other four the predicate is
correct and the *path* is incomplete: `_anchor_references` admits a bare token carrying a file
extension, and any token containing `/`, so these are accepted and then resolved against the
repository root where they genuinely are not. The real locations are
`.github/workflows/doc-sync.yml` and `plugins/doc-lifecycle/skills/growing-docs/SKILL.md`. A
fix that lands the directory case will pass its own test while the other four keep emitting
false STALE, and will look finished. **Do not close this finding when the directory fix
lands.**

The second half is a design call, not a patch. Either resolve an abbreviated reference against
the directory of an already-resolved reference in the same anchor, or rule abbreviated
references illegal and give them their own code.

**This record recommends the second**, and the ambiguity behind it is not hypothetical. This
repository holds two files for each of those basenames — the installed copy and the template:

```
.github/workflows/doc-sync.yml        plugins/doc-lifecycle/skills/scheduling-doc-sync/doc-sync.yml
.github/workflows/doc-bloat.yml       plugins/doc-lifecycle/skills/scheduling-doc-sync/doc-bloat.yml
```

They are near-duplicates rather than copies: the template carries knob placeholders
(`{{CRON_SCHEDULE}}`, `{{BLAST_RADIUS_CAP}}`) where the install carries this consumer's values,
and `install-parity_test.py` asserts the install equals what `apply-upgrade.py` would
*generate from* the template — a generative relationship, not identity. Either way they are
separate paths with separate histories, and history is exactly what `_anchor_findings` dates an
anchor against. The anchor naming them
(`docs/guides/scheduling-doc-sync.md:3`) is a guide about the *skill* and establishes the skill
directory with its first reference, so it means the templates. A rule keyed on the repository
root or on first match lands on `.github/workflows/` instead, binding the anchor to a file the
author did not name, with nothing saying it did.

Stated precisely, because both the overstated and the understated versions are tempting: at
this commit the two copies' last-change dates coincide — both last moved in `9d84df0` — so
today the wrong resolution happens to yield the right date.

What couples them is worth naming exactly, because it is the whole argument.
`install-parity_test.py` never touches git; it regenerates into a scratch tree and compares
bytes, and asserts nothing about commits. The dates coincide because this repository dogfoods
its own plugin, so whoever edits a template regenerates the install and lands both halves
together. That is a **convention enforced by nothing**, and the ordinary case breaks it: a
template change landing without a regeneration run, or the upgrade lane advancing an install on
its own cadence. For an actual consumer there is no template in the repository at all, so the
coincidence that rescues the resolution rule here cannot arise there.

So the honest form is: *a resolution rule would produce the right date in this repository
today, by an accident of dogfooding that no test enforces and that holds for no consumer of the
plugin.* Being right for a reason unrelated to the rule is worse than being wrong, because it
survives review.

The hit rate makes it worse: the other two abbreviated references (`growing-docs/SKILL.md`,
`fixing-doc-bloat/SKILL.md`) have exactly one match each, so a resolution rule works for two of
four — good enough to look correct. (Ambiguity measured by #74.)

Either way the `exists=False` branch must stop saying "is no longer in the repository" when the
truth is that the token never named anything resolvable — those are different facts, and the
report contract refuses that conflation everywhere else. Ruling them illegal turns the four
anchors in this repository into honest findings whose fix is to spell the paths in full; on the
reading above, `doc-sync.yml` and `doc-bloat.yml` in `docs/guides/scheduling-doc-sync.md:3`
mean the two templates under `plugins/doc-lifecycle/skills/scheduling-doc-sync/`. Those anchor
edits only *become* findings once the illegality rule lands, so they belong in the same change
as the rule — that is what keeps the release gate green across it.

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

It fails on a second clause too. G5 said "model cost, turns, and wall-clock are recorded for
**both** lanes"; `shadow-meta.json` records `turns: null` and `duration_ms: null`. The reason
is real — this cycle ran 55 sessions, so a turn total would add up unrelated sessions and a
duration would report wall-clock under 8-way parallelism, neither comparable to the legacy
lane's single-session figures — but a reason for not measuring something is not a measurement.
The re-registered criterion should ask for per-session turn and duration distributions, which
are recorded in the run logs and would have been comparable.

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

This file carries the verdict and the artifacts are under
`tests/baselines/shadow-parity-gate/`. Comments pointing here are posted on #76 and #77 when
the PR opens — until then the record lives only on a branch, and #77 cannot cite a branch.

## Against issue #76's acceptance criteria

The criteria above are this file's own, and deliberately stricter than the ticket's. The
ticket's four:

| #76 acceptance criterion | Met |
|---|---|
| comparison report: agreements, findings unique to each, coverage and cost deltas, false-positive assessment | **yes** — `comparison.json`, produced by a tested program, plus the adjudication above |
| the new lane demonstrably has no write path during shadow operation | **yes** — G1a, plus the three observations under G1b |
| pass criteria written down before the comparison is evaluated; verdict recorded where #77 can cite it | **yes** — criteria in `bb15649`, cycle and verdict in later commits, verdict here |
| at least one full shadow cycle on the dogfood repository's real documentation | **yes** — 33 documents, 1331 units, 41 records |

One clause of the ticket was **not** exercised: "against the dogfood repository *(and a large
consumer where available)*". No external consumer install is known — the dogfooded `.github/`
install is the only one this repository knows of, and `doc-audit.yml` is not installed
anywhere yet (#75). Recorded as not available rather than silently skipped; a consumer shadow
run would test the one thing this cycle could not, which is whether the findings and the cost
behave the same on a corpus nobody wrote the engine against.

## What #77 needs before this gate can be re-run and pass

1. Finish `drift._anchor_findings`'s reference resolution — the directory-predicate half already landed in `dcff17d` (#93); only the abbreviated-reference path (Cause A) remains open.
2. Settle how the report contract records non-path evidence, or narrow the method that
   sanctions it (Cause B). This one is a contract decision, not a patch.
3. Remove the digest-transcription failure mode — ordinal-keyed answers are the cheapest fix —
   or give the lane a repair round.
4. Decide the registry's `extensions` and roots for the dogfood install (#75), knowing that
   `.md`-only and `plugins/`-less each drop documents the legacy lane covered.
5. Re-register **G1b** (hash the repository's content as the repository defines it) and **G5**
   (a normalizer the owner signs off on, plus per-session turn and duration distributions).
   Both failed on their instruments rather than on the lane, and both must be fixed *before*
   the next cycle runs, not after it reports.

Items 1–3 are also worth doing on their own merits, independent of the gate: each is a defect
this cycle found in code that is already merged.

## Legacy-lane note, recorded because it bears on urgency

The legacy lane has produced no report since 2026-07-07. Every scheduled run from 2026-07-12 to
2026-07-26 failed in its model step (`is_error`, 1 turn, $0) and uploaded no artifact — 14
consecutive nights. The lane this gate is protecting is not currently functioning, so "keep the
legacy lane until the new one is proven" is, in practice, "have no working lane". That argues
for fixing items 1–3 quickly, not for waiving the gate.
