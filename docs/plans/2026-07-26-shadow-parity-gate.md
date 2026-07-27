# Shadow-mode parity gate (issue #76)

**Status:** criteria pre-registered 2026-07-26; verdict NOT YET EVALUATED.
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

**NOT YET EVALUATED.** Pre-registered 2026-07-26. This section is written only after the
comparison exists, in a later commit, so the git history shows the criteria preceded the
evaluation.
