# Issue #203 — release gate rerun at the #168 remediation head

Retained run evidence for the sign-off gate. The remediation range is `8ded7d7..c75fd59` — ten
merged sub-issues of #168 — and this record is the gate rerun on top of it, plus the small set of
corrections #203 itself landed.

Gate run: 2026-08-05, locally, on branch `ajones/issue-203-sign-off-gate` (branched from
`origin/main` at `c75fd59`). Exact-commit CI is the pull request's own run; this file is the local
half and the component list a later reader can re-execute.

## What landed in the remediation range

| Issue | PR | What landed |
|---|---|---|
| #187 | #212 | Cache payload digest — full-payload binding, typed fail-closed misses |
| #183 | #213 | Applier validated write transaction; certified postimage manifest |
| #186 | #214 | Policy provenance — `policy-mint` as sole policy-branded producer, `SCHEMA_VERSION` 2 |
| #189 | #216 | Upgrade-lane commit subject / PR title through the tested renderer |
| #191 | #217 | Staged-index and commit-tree byte verification in both apply lanes |
| #193 | #218 | Occurrence-bound approval, `SCHEMA_VERSION` 3 — replaced the digest hull |
| #194 | #219 | Documentation contract corrections + `tests/scripts/doc-contract_test.py` |
| #185 | #215 | Repository-integrity gate for the drift audit lane |
| #198 | #220 | Idempotent apply-workflow recovery — reuse, never force-push |
| #200 | #221 | Retired the Issue #57 planning trackers through the plugin's own fix door |

## Read this first: two of criterion 1's own subjects are not stated anywhere

Criterion 1 requires "regression tests present for each of the six P1 findings and each P2
finding's fix". **Neither set is enumerated in any authoritative record.** This is a defect in the
record, not in the remediation — but it means the criterion cannot be discharged by evidence
alone, only by inference, and a human weighing #57 should know which parts of the claim below
rest on inference.

- **The six P1s.** #168's Further Notes give a count and a commit range, never a list. #57's only
  substantive comment *does* enumerate P1s — **seven of them, from an earlier review of a
  different range** (`8136061...origin/main` at `4bfbdef`). Those seven are not these six. The
  table below infers the six from the child issues #168 opened.
- **The six P2s.** Worse: #168 states "three Standards P2 findings and three Spec P2 findings"
  and decomposes neither half anywhere. #168 has zero comments. The four P2-carrying child issues
  (#198, #189, #194, #200) and their PRs never use the words "P2", "Standards", or "Spec" at all.
  So there are **four child issues for six stated findings, with no mapping between them.** Any
  reading — #194 absorbing three documentation contracts, #189 as Standards-shaped, #198 and #200
  as Spec-shaped — is inference and nothing more.

Everything below is the most defensible reading available. It is not a quotation.

## The six P1 findings — inferred, not quoted

Criterion 1 requires "regression tests present for each of the six P1 findings". **No document
lists those six.** #168's Further Notes give only a count ("six P1 correctness/authority
findings, three Standards P2 findings, and three Spec P2 findings") and a commit range, and it
never decomposes the P2 halves anywhere. #57's substantive comment *does* enumerate P1s — but
**seven of them, from an earlier review of a different range** (`8136061...origin/main` at
`4bfbdef`). Those seven are not these six. A reader who takes #57's list as this remediation's
list will be reading the wrong findings.

The only defensible enumeration is the six child issues #168 opened, so that is what this table
is. **It is inferred from the child issues, not quoted from any record.**

| | Issue | The finding | Verified by mutation? |
|---|---|---|---|
| P1-1 | #183 | Applier validated write transaction — write-boundary recheck, final-byte certification, compare-aware rollback | **Yes.** Deleting the write-boundary recheck, making rollback unconditional, or disabling final-byte comparison each fails exactly the named applier tests |
| P1-2 | #191 | Staged-index and commit-tree byte verification in both apply lanes | **Yes.** A path-only blob comparison fails 5 `verify-apply-bytes` tests |
| P1-3 | #185 | Repository-integrity gate for the drift audit lane | **Partial — and it was weak.** The gate script is solidly covered; its *wiring into the lane* was asserted only by static YAML strings that survive `\|\| true` on the gate's own invocation. #203 added the execution-based class that fails on exactly that mutation. Its third acceptance clause remains untested — #231 |
| P1-4 | #186 | Policy provenance — `policy-mint` as sole policy-branded producer, revalidatable eligibility | **Yes.** Letting generic mint accept `--minter-kind policy` fails 12 tests |
| P1-5 | #187 | Cache payload digest — whole-payload binding, fail-closed recoverable misses | **Digest binding yes** — digesting records as `{id,digest}` only fails 9 cache tests, disabling the undigested branch fails 2. **But the module carried a live crash**: `get()` raised rather than missing on a non-UTF-8 entry, contradicting the issue's own acceptance text. Fixed in #203 |
| P1-6 | #193 | Occurrence-bound approval — exact audited occurrences instead of the min/max digest hull | **Yes, extensively.** Collapsing passages to a min..max hull, dropping the ambiguous-repeat refusal, and both together (full pre-#193 behaviour end to end) are each caught; bounding to the whole document fails 9; letting document order into `finding_digest` fails 4; hashing units as `ordinal:digest` fails 5; reading `baseline_units` from the working tree fails 2 with 5 errors. The US28 half was guard-free until #203 added it |

**Four of six verified by mutation. Two had real gaps** — #185 weak at the lane layer, #187
carrying the crash. That is the honest picture, and it is the opposite of what a green gate
suggested.

### Two thin spots inside the greens

- **The hull-versus-passages distinction rests on one test in the whole tree**:
  `applier_test.py::OccurrenceBoundPassages::test_a_span_across_the_gap_is_refused` (the
  `GAP_DOC` case). The four `REPEAT_DOC` refusal tests declare `occurrences=(1,)`, so hull and
  passage coincide there — they are load-bearing against an applier that ignores occurrences
  entirely, but not against the hull specifically. No acceptance-tier scenario covers repeated
  units; the criterion's "public lifecycle transaction" is met one tier down, at `applier_test`'s
  `apply_edit_plan` seam (real repository, report + approval + plan, byte-compared tree), which
  is a real seam but not the acceptance fixture.
- **`doc-contract_test.py` has a ceiling its own docstring admits.** Four of its assertions are
  genuinely code-derived and fail under real mutations; about five are phrase pins. Appending a
  brand-new false sentence to the engine README — "The applier stages every file it writes with
  `git add`…" — leaves all 22 green. It catches *the claims it names* drifting from the code; it
  does not catch *new* false claims appearing. That is inherent to pinning phrases rather than
  snapshotting files, and the alternative (full-file snapshots) was rejected for good reason.

### The P2 lane

Not decomposed anywhere (see the caveat above). What can be said by mutation:

- **#198** is bound at both halves — removing the tree certification and removing the
  approval-trailer binding each fail distinct tests.
- **#189**'s dogfood copy is genuinely bound: mutating only the dogfood workflow fails
  `install-parity_test.py`.
- **#200's retirement has no test, and here is what that concretely means:** recreating
  `docs/plans/HANDOFF.md` with its stale `> Status: pending-implementation` prose leaves the full
  script gate at 28/28. Nothing in the gate would notice the retirement being undone. Arguably
  not testable — what #200 did was delete two planning documents through the fix door — but the
  consequence is stated rather than waved at.

### One thing the suite pin does not do

The `issue #168 sign-off regressions` criterion is **per-file**. It guards a suite being deleted
or unwired from discovery. It does not guard that suite's test functions being weakened or
removed — a suite can be gutted to one trivial assertion and still satisfy the criterion. The
mutation testing above is what covers that, and it was done by hand, once, not by the gate.

(A known soft spot of that kind, found by the same review and left as a note rather than a
finding: `policy_cli_test.py::Mint::test_it_derives_the_exact_eligible_set_from_the_declaration`
uses a single-eligible-record fixture, so narrowing the mint to `[:1]` does not fail it. A sibling
test catches that mutation, so the property is covered — but not by the test whose name claims it.)

## Gate components and results

| Component | Command | Result |
|---|---|---|
| Script/workflow suites | `python3 .github/scripts/run-script-suites.py` | 28/28 suites passed |
| Engine suites | `python3 -m unittest discover -s tests/engine -p '*_test.py'` | 1349 tests, OK |
| Release-manifest coverage | `python3 .github/scripts/release-manifest.py` | 60 suites wired, every gate criterion covered |
| Release-manifest guard's own suite | `python3 tests/scripts/release-manifest_test.py` | 43 tests, OK |
| Plugin validation | `claude plugin validate plugins/doc-lifecycle` | Validation passed |
| Compilation | `python3 -m compileall -q` over engine, wiring, skills, `.github/scripts` | clean |
| Install parity | `tests/scripts/install-parity_test.py` (inside the 28) | PASS |
| Source/vendor parity | `diff -r -x __pycache__ plugins/doc-lifecycle/engine/ .doc-lifecycle/wiring/engine/` | identical |
| Exact-commit CI | the pull request's own run | see the PR |

Engine test count moved 1344 → 1349 within this ticket: three added by the US28 guard, one by the
cache non-UTF-8 regression, and one from splitting the policy single-construction assertion into
its static and behavioural halves. `audit-workflow_test.py` moved 34 → 38.

## What #203 itself changed, and why each is in scope

**This PR is not release-neutral.** An earlier version of this record said no plugin file was
touched and 0.46.9 stood. That stopped being true when the #203 pull-request review found a live
defect in `cache.get()` (below), whose fix changes `plugins/doc-lifecycle/engine/`. The version
moves to **0.46.10** across all four carriers, in its own commit.

The rule the CI guard actually enforces, for the record: `release.yml`'s "Require version bump
when plugin content changes" step diffs `-- plugins/doc-lifecycle/` only. `.doc-lifecycle/` is
*not* in that filter — the vendored mirror could change alone without tripping it, which is why
`install-parity_test.py` rather than the version guard is what holds the mirror to the source.

- `plugins/doc-lifecycle/engine/doclifecycle/cache.py` (+ its vendored mirror) — `get()` opened
  the entry under `except OSError`, but `UnicodeDecodeError` is a `ValueError`, so an entry that
  is not UTF-8 left the function as a traceback rather than the miss the module promises.
  Reachable from `bloat.load_chunk`; contradicts `get()`'s own docstring and closed P1 #187's
  acceptance text ("a corrupted cache entry triggers re-evaluation rather than a hard crash or
  false hit"). `cache.py` was the outlier — `digest.py` documents this exact trap and sixteen
  other sites in the same engine catch it. Fixed test-first: no existing test could reach the
  path, because every corrupt-payload test writes its garbage *with* `encoding="utf-8"` and so
  fails at the parser one step later. The new test writes real non-UTF-8 bytes and was verified
  RED (`UnicodeDecodeError: 'utf-8' codec can't decode byte 0xff in position 0`) before the fix.
- `tests/engine/policy_test.py` — the private-symbol spy on `approval._mint_approval_set`,
  accepted in an earlier version of this record, is replaced by a static AST guard in the manner
  of `test_the_policy_module_never_writes` 46 lines below it. The acceptance rationale ("no public
  seam observes which function was called") did not survive review: the same file already proves
  an equally un-runtime-observable property statically. The static form is also stronger — the spy
  proved single-construction for the one input it ran; the source says it for every input.
  Verified load-bearing by adding a second producer to `policy.py` and watching the guard name it.
- `tests/scripts/audit-workflow_test.py` — the execution-based guard on P1 #185's *wiring*. Every
  prior assertion about the integrity gate's place in the lane was a static read of the YAML, and
  all of them survive appending `|| true` to the gate's own invocation — which lets a dirty
  checkout publish a report, the P1 itself. The new class runs the step's literal `run:` body
  under `bash -e`, against a real git repository with a dirtied tracked evidence source and the
  real gate script reached the way the lane reaches it, and asserts the step *fails*. Verified by
  running that exact mutation: it fails two of the new tests while `workflow-permissions_test.py`
  and `check-repo-integrity_test.py` both stay green — reproducing the blind spot and closing it.
  An honest-path case and the allowlist cases are asserted alongside, so the refusal is evidence
  the gate discriminates rather than evidence it always fails.
- `.github/scripts/release-manifest.py` — a named gate criterion, `issue #168 sign-off
  regressions`, pinning the eighteen suites that carry the reproduced failures' regressions.
  #168 User Story 40 asks for "regression tests for every reproduced sign-off failure, so that a
  green gate proves the properties the final review found missing". Discovery ran those suites
  already; naming them is what makes deleting one a reported failure rather than a quietly smaller
  gate. Seven were wired to no criterion before this: `verify-apply-bytes_test.py`,
  `apply-recovery_test.py`, `apply-lane-parity_test.py`, `doc-contract_test.py`,
  `approval_cli_test.py` (#186's CLI-route refusals), `render-apply-summary_test.py` (#198's
  recovery-state strings — a recovery that runs correctly and reports the wrong state is the same
  operator-facing failure), and `render-audit-summary_test.py` (#185's integrity-refused surface).
  `audit-workflow_test.py` is pinned alongside `check-repo-integrity_test.py` for #185, because
  the two fail to different mutations and neither alone covers that P1.
- `tests/engine/finding_test.py` — the US28 guard. The property ("finding identity remains stable
  across harmless document reordering") held in the implementation but nothing tested it, so
  #193's occurrence ordinals could have leaked into `finding_digest` with a green gate. Proven
  load-bearing: adding position data to the hashed dict fails the new test.
- `tests/scripts/apply-recovery_test.py`, `tests/scripts/verify-apply-bytes_test.py` — surviving-byte
  assertions added to seven race tests (see `race-test-audit.md`).
- `CLAUDE.md` — documented `doc-contract_test.py` (the only new suite the remediation left
  undocumented) and corrected the run-surface renderer list, which omitted
  `verify-apply-bytes.py`'s own refusal surface.
- `docs/decisions.md` — pinned two citations of `docs/plans/HANDOFF.md`, which #200 retired in
  `c75fd59`, to `@ b7efcb5` where the file still exists.

## Reproducing this

Every component, in an order that works. Run from the repository root.

```
git fetch origin main
git checkout ajones/issue-203-sign-off-gate      # or the merge commit

python3 .github/scripts/run-script-suites.py                        # 28/28
python3 -m unittest discover -s tests/engine -p '*_test.py'         # 1348, OK
python3 .github/scripts/release-manifest.py                         # manifest coverage
python3 tests/scripts/release-manifest_test.py                      # the guard's own suite
python3 tests/scripts/install-parity_test.py                        # install parity
claude plugin validate plugins/doc-lifecycle                        # manifest validation
python3 -m compileall -q plugins/doc-lifecycle/engine .doc-lifecycle/wiring \
                         plugins/doc-lifecycle/skills .github/scripts

# Source/vendor engine parity. `-x __pycache__` is required, not cosmetic: every
# step above imports the engine from `plugins/`, which leaves a `__pycache__`
# directory under the source tree and none under the vendored one, so a bare
# `diff -r` exits 1 on a tree that is byte-identical in every file that ships.
diff -r -x __pycache__ plugins/doc-lifecycle/engine/ .doc-lifecycle/wiring/engine/
```

Exact-commit CI is #203's own pull-request run, which executes the same components in a clean
checkout where the `__pycache__` caveat does not arise.

## The limit of this evidence

Every property above is proven by tests, including execution-based ones that run the lanes' own
`run:` blocks under `bash -e` against real git remotes. **None of the gates this remediation added
has fired in a real lane.** `doc-apply` has never executed, `doc-policy-apply` has failed both its
runs, `doc-bloat-audit` has failed all fourteen, and `doc-audit` is disabled. The audit lane also
fetches its tooling from a release tag matching `.doc-lifecycle/installed-version` (v0.46.9), and
that tag is not cut. Tracked in #228; recorded here so a reader of the green gate does not
mistake it for production evidence.
