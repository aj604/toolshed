# Issue #203 — race regression test audit

#168's Testing Decisions carry a rule that a green gate cannot itself demonstrate:

> No test may call a race fixed merely because the final path set is correct. Race tests must
> assert the exact surviving bytes and the reported transaction state.

This is the per-test audit of it, run by a third agent that authored none of the fixes and had no
part in the Standards or Spec reviews.

## Scope

`git diff 8ded7d7...HEAD` touches 22 test files. Race, concurrency, and interference tests live in
exactly four:

- `tests/engine/applier_test.py` (#183 — write-boundary race, post-write certification race,
  compare-aware rollback)
- `tests/scripts/apply-recovery_test.py` (#198 — branch-moved, existing-branch, existing-PR)
- `tests/scripts/verify-apply-bytes_test.py` (#191 — staged index and commit tree, including
  mutate-after-apply-before-staging)
- `tests/scripts/check-repo-integrity_test.py` (#185 — model-step interference)

`apply-lane-parity_test.py` is static YAML parity with no scenario execution.
`approval_test.py`, `cache_test.py`, `policy_test.py`, and `acceptance/scenario_policy_test.py`
carry tamper and poison tests, which are not races.

Two grading notes. `applier_test.py`'s `self.tree(root)` returns `{relpath: raw bytes}` for the
whole worktree, so `assertEqual(before, self.tree(self.repo))` is a whole-tree byte assertion, not
a path-set one. In `apply-recovery_test.py`, `remote_tip()` returns a commit SHA — content-
addressed, so SHA equality does pin the exact surviving tree; the audit graded that as bytes at
id level and flagged where a literal read-back was still worth adding.

## Verdict against the rule

**No test in the range is path-set-only.** Every race and interference test asserts a typed
refusal code, a status, or an exit code, so none calls a race fixed merely because the final path
set was correct. Criterion 3's literal question is answered: there is no such test to fix.

The two headline #183 races satisfy the rule in its strongest available form:

- `test_a_target_that_moved_before_the_write_is_a_typed_race_refusal`
  (`applier_test.py:1089`) — `assertEqual(self.read(self.repo, DOC_A), theirs)` and
  `assertEqual(self.tree(self.repo), dict(before, **{DOC_A: theirs.encode("utf-8")}))` for the
  bytes; `assertEqual(codes(result), ["apply-write-boundary-race"])`, the problem's location, and
  `assertEqual(self.staged_paths(self.repo), [])` for the state.
- `test_a_target_replaced_before_certification_never_resolves_clean`
  (`applier_test.py:1125`) — both rollback answers read back, plus
  `assertNotIn(content, self.read(self.repo, new_doc))`, plus
  `assertEqual(codes(result), ["apply-postimage-not-on-disk"])` and `"left exactly as found"`.

The two pre-existing confinement races (`applier_test.py:919`, `:950`) also assert whole-tree byte
equality alongside `apply-unconfined-change` and the rollback message.

## Where the rule's letter was not met, and what #203 did

Nine tests asserted the transaction state but not the surviving bytes — a weaker form of the same
gap the rule exists to close. **Seven were fixed in #203; two were accepted.**

(The auditor's raw output — retained verbatim in `reviewer-output-verbatim.md` — numbers these
1–7, but two of its numbered items name two tests each: item 2 covers
`apply-recovery_test.py:610` and `:621`, and item 7 covers `check-repo-integrity_test.py:87` and
`:107`. Counting items rather than tests is what produced the "six fixed" figure this record
carried before; the table below counts tests, and seven is the number the diff shows.)

| Test | Missing | Disposition |
|---|---|---|
| `apply-recovery_test.py` `test_the_branch_stands_and_nothing_reviews_it` | only `assertIsNotNone(remote_tip())` — "a push landed", not "the *verified* bytes landed" | Fixed: tip equals `verified-commit.txt`, plus `git show {verified}:docs/edited.md == AFTER` |
| `apply-recovery_test.py` `test_an_open_pull_request_for_this_approval_is_idempotent_success` | no tip assertion — a rerun that force-pushed its own commit and *then* found the open PR would still have passed as idempotent, which is the exact hole #198 exists to close | Fixed: tip unchanged from the stranded run, plus a content read-back |
| `apply-recovery_test.py` `test_an_open_pull_request_aimed_at_another_base_is_refused` | no tip assertion | Fixed: tip unchanged, plus read-back |
| `apply-recovery_test.py` `test_two_open_pull_requests_on_one_branch_are_refused` | no tip assertion | Fixed: tip unchanged, plus read-back |
| `verify-apply-bytes_test.py` `test_index_normalization_by_a_clean_filter_is_refused` | refusal code only — proved a check failed, not that bytes diverged | Fixed: `git show :docs/edited.md == AFTER.upper()`, `assertNotEqual(…, AFTER)`, certified digest named on the surface |
| `verify-apply-bytes_test.py` `test_a_hook_that_rewrote_and_restaged_a_target_is_refused` | code only | Fixed: `git show HEAD:docs/edited.md == "hooked\n"` plus the certified digest |
| `verify-apply-bytes_test.py` `test_a_matching_trailer_over_different_bytes_is_refused` | code only, despite "different bytes" being the scenario's whole point | Fixed: the existing commit's tree still holds `"not what was approved\n"`, plus the certified digest |
| `check-repo-integrity_test.py` `test_a_dirtied_tracked_evidence_source_refuses_with_a_typed_reason` (`:87`) and `test_a_fresh_checkout_cannot_re_derive_the_failure` (`:107`) | neither asserts `src/server.py` still holds `"PORT = 9090\n"` at refusal time | **Accepted.** `test_the_gate_never_repairs_what_it_refuses` (`:230`) asserts exactly that read-back, plus a non-empty `git status --porcelain`, for the gate as a whole. This is a redundancy gap, not a hole: the gate is read-only by construction and one test owns the property. |

## A known ceiling, not a defect

`verify-apply-bytes_test.py:505`'s `assertIn("apply-bytes-not-certified", completed.stdout)` is
weaker than it reads. `certify` writes that refusal to the surface *before* returning, and
`parent=None` independently trips the lineage check — so a behaviourally-neutral mutation can
escape both this suite and its sibling while the string still appears. The honest removal of the
certification does fail, so the property genuinely holds; this is recorded as a ceiling on what a
surface-string assertion can prove, not as a gap to fix. A surface string is evidence that
*something* refused, never evidence of *which* check refused.

## Proof the new assertions are load-bearing

Two were spot-checked by breaking the thing they assert and confirming only the new assertion
fails, then reverting:

- Idempotent-success: making the rerun force a commit onto the branch after the push/reuse step
  left *every pre-existing assertion passing* — the surface strings and the absence of
  `gh pr create` — and failed only the new tip equality. That is the #198 hole, demonstrated.
- Clean filter: changing the filter to `tr a-z X` left the refusal code matching and failed only
  the new bytes assertion (`'XXXXX\n' != 'AFTER\n'`), proving it pins literal surviving bytes
  rather than restating the code.

Both temporary breaks were reverted and both suites re-run green: `apply-recovery_test.py` 14/14,
`verify-apply-bytes_test.py` 31/31.
