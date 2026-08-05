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

## Gate components and results

| Component | Command | Result |
|---|---|---|
| Script/workflow suites | `python3 .github/scripts/run-script-suites.py` | 28/28 suites passed |
| Engine suites | `python3 -m unittest discover -s tests/engine -p '*_test.py'` | 1347 tests, OK |
| Release-manifest coverage | `python3 .github/scripts/release-manifest.py` | 60 suites wired, every gate criterion covered |
| Release-manifest guard's own suite | `python3 tests/scripts/release-manifest_test.py` | 43 tests, OK |
| Plugin validation | `claude plugin validate plugins/doc-lifecycle` | Validation passed |
| Compilation | `python3 -m compileall -q` over engine, wiring, skills, `.github/scripts` | clean |
| Install parity | `tests/scripts/install-parity_test.py` (inside the 28) | PASS |
| Source/vendor parity | `diff -r plugins/doc-lifecycle/engine/ .doc-lifecycle/wiring/engine/` | identical |
| Exact-commit CI | the pull request's own run | see the PR |

Engine test count moved 1344 → 1347 within this ticket: the three added by the US28 guard below.

## What #203 itself changed, and why each is in scope

No file under `plugins/doc-lifecycle/` or `.doc-lifecycle/` was touched, so no plugin version bump
was required; main's 0.46.9 stands.

- `.github/scripts/release-manifest.py` — a named gate criterion, `issue #168 sign-off
  regressions`, pinning the fourteen suites that carry the reproduced failures' regressions.
  #168 User Story 40 asks for "regression tests for every reproduced sign-off failure, so that a
  green gate proves the properties the final review found missing". Discovery ran those suites
  already; naming them is what makes deleting one a reported failure rather than a quietly smaller
  gate. Four of them (`verify-apply-bytes_test.py`, `apply-recovery_test.py`,
  `apply-lane-parity_test.py`, `doc-contract_test.py`) were wired to no criterion before this.
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

```
git fetch origin main
git checkout ajones/issue-203-sign-off-gate      # or the merge commit
python3 .github/scripts/run-script-suites.py
python3 -m unittest discover -s tests/engine -p '*_test.py'
python3 .github/scripts/release-manifest.py
claude plugin validate plugins/doc-lifecycle
diff -r plugins/doc-lifecycle/engine/ .doc-lifecycle/wiring/engine/
```

## The limit of this evidence

Every property above is proven by tests, including execution-based ones that run the lanes' own
`run:` blocks under `bash -e` against real git remotes. **None of the gates this remediation added
has fired in a real lane.** `doc-apply` has never executed, `doc-policy-apply` has failed both its
runs, `doc-bloat-audit` has failed all fourteen, and `doc-audit` is disabled. The audit lane also
fetches its tooling from a release tag matching `.doc-lifecycle/installed-version` (v0.46.9), and
that tag is not cut. Tracked in #228; recorded here so a reader of the green gate does not
mistake it for production evidence.
