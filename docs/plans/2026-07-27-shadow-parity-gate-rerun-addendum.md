# Shadow-mode parity gate, second cycle — G4 addendum (issue #123)

**Status:** the second cycle's single blocker is fixed and G4 is re-measured on that cycle's own
report. No third cycle was run; the reasoning for that is below, in full.
**Amends:** `docs/plans/2026-07-27-shadow-parity-gate-rerun.md` — its Verdict and its "What #77
needs" item 1. That file's measurements and verdict stand as recorded; the only edit made to it
is a line pointing here, because it records what its cycle measured and this file records what
changed afterwards.
**Blocks:** #77, which cites the second cycle's verdict.
**Spec:** issue #123.

## The blocker, restated in one paragraph

DRIFT-023 was the whole of G4's failure. Its verdict called a true sentence `STALE` because the
document it pointed at had been superseded, and its `fix` repointed the sentence at the successor
while asserting a property of the successor — that it "carries criteria and verdict" — that the
worker never opened the successor to check. At the audited commit that file's Verdict section
read "Not yet run". The record carries an exact preimage and an `evidence.source`, so the
auto-apply policy would have minted an approval set for it with no human, and criterion 1's
budget for that class is zero.

## What was built

Two changes, and only the first is a guarantee.

**A policy exclusion, which is mechanical.** `policy.py` refuses a record whose `fix` names a
file the claim it replaces did not — `policy-fix-names-other-document`, decided per record and
reported with the rest. A preimage pins what a run *read*; a `fix` is the half a model *wrote*,
and when the replacement names a document the record pins nothing from, the assertion about that
document is the model's, not the repository's. An `evidence.source` pointing at that same
document does not close the gap: a citation says one line was consulted, and what a document
contains is the thing being asserted. The document the finding lives in is excluded, since
rewriting a passage that names its own file speaks for nothing else. Recognizing a file reference
is `paths.path_references`, which reads a dotted symbol (`approval.Record.targets()`) and a
slash-joined prose list (`cron/cap/upgrade-cron`) as prose, and is otherwise generous — a token
it over-reads costs a person one more record to look at, and one it misses costs the refusal.

**A method rule in `detecting-doc-drift`, which is not.** "A `fix` that names a file is settled
by opening that file" — a `Supersedes:` header says a file replaced another, never what the
replacement contains; assert only what you read, and where nothing settles it the record is
`UNVERIFIABLE`. `doc-audit.yml`'s prompt already sends the lane's workers to that skill for
method, and now names fix-authoring among what it sends them for. This is defense in depth: it
addresses the wrong `fix` being *authored*, which the policy exclusion does not, and it is model
behavior, so nothing here rests on it.

## How G4 was re-measured

G4's criterion 1 counts false positives in the auto-apply-eligible class. That class is not a
judgement — it is what `policy_eligibility` returns for a report, computed deterministically from
records. So the criterion can be re-measured on the recorded cycle's own report, holding the
model's output exactly as the cycle produced it, and the measurement is the one the verdict took:

```bash
# with a policy file at .doc-lifecycle/auto-apply-policy.json (this repository
# installs none; the replay used the two-field minimum, defaults for classes):
#   {"artifact": "auto-apply-policy", "schema_version": 1, "id": "replay-123"}
python3 plugins/doc-lifecycle/engine/doc-lifecycle.py policy-eligibility \
  --report tests/baselines/shadow-parity-gate-rerun/shadow-report.json --repo .
```

| | Records | Auto-apply-eligible | False positives in that class |
|---|---|---|---|
| Before (the cycle's own measurement) | 24 | 12 — 10 `STALE`, 2 `ANCHOR-STALE` | 1 (DRIFT-023) |
| After | 24 | 11 | 0 |

Twelve eligible before is the same 12 the verdict's G4 section counted, which is what says the
replay runs the verdict's instrument and not a new one. **Exactly one decision changes.** The
other 23 records' decisions — eligible class and refusal code alike — are identical before and
after, so the exclusion did not buy its refusal by refusing the true positives too. DRIFT-023's
new refusal reads:

> record DRIFT-023's fix speaks for ['docs/plans/2026-07-27-shadow-parity-gate-rerun.md'], which
> the claim it replaces never named: the remedy asserts something about a document this record
> pins nothing from, so the assertion is the model's and not the repository's. A citation does
> not settle it either — a pointer says one line was read, and what a document contains is the
> thing being asserted. A pointer whose target has been superseded is a finding for a person, who
> can open the new one.

**G4 criterion 1, re-measured: 0 false positives in the auto-apply-eligible class, budget 0 —
PASS on replay.** Criterion 2 (at most 2 false positives overall) was already PASS at 1 and is
unchanged: the record is still in the report, still a false positive, still shown to a person.
Nothing here deletes a finding; it moves one out of the class that lands unattended.

Three further pieces of evidence, all in the repository:

- **A regression test carrying the record verbatim.** `tests/engine/policy_test.py`'s
  `AFixThatSpeaksForAnotherDocument` builds DRIFT-023's assertion, fix, and evidence as recorded
  and asserts the refusal, at the library seam and through `mint_policy_approval_set`. It fails
  on the code as it stood before this change.
- **The over-refusal cases are tests too, not an argument.** DRIFT-014's symbol rewrite,
  DRIFT-021's knob list, DRIFT-022's two build artifacts, and a fix naming the finding's own
  document each assert *eligible* — the shapes a blunter exclusion would have swept up.
- **Mutation results.** Six mutants, each killed: removing the guard (4 failures, 1 error in
  `policy_test`), widening the own-document carve-out to the cited document (3 failures, 1
  error), and four mutations of the recognizer — dropping directory references, dropping bare
  filenames, reading any slash token as a path, reading any dotted token as a path — each failing
  `paths_test`, `policy_test`, or both.

## Why no third cycle

A third cycle costs about `$100` and 50-odd headless sessions, and would answer a different
question than the one G4 failed on. Stated plainly, so #77 can disagree with the reasoning rather
than with a conclusion:

- **The failure was in a deterministic gate, not in a distribution.** The record that failed the
  criterion is in hand. Its eligibility is a function of the record, and that function is what
  changed. Replaying the recorded report measures the fix against the exact input that beat it —
  a fresh cycle would draw fresh model output, would almost certainly not reproduce DRIFT-023 at
  all (the superseded pointer it tripped on has since been repointed), and so could not tell
  anyone whether this shape is closed.
- **The other criteria are untouched.** G1a, G1b, G2, G3, G5, G6, G7 measure the lane's write
  path, coverage, completion, cost, instrument, and record. Nothing in this change alters what
  the lane reads, judges, or spends; the exclusion runs after the report exists, and the method
  rule changes prompt text the audit lane sends to a skill. Re-running them would re-confirm
  passes at model prices.
- **What a replay cannot show.** It cannot show that the *next* cycle produces no false positive
  of some *other* shape — no cycle can show that about the one after it either; the budget is per
  cycle, and it is measured on the cycle that runs. It also cannot show that the method rule
  works: that is model behavior, unverified here, and deliberately not what G4's re-measurement
  rests on. If the method rule silently fails, the exclusion still refuses the record.
- **The honest residue.** G4 now passes on a replay of a recorded cycle, not on a live one. A
  reader who holds "a criterion is only met by the instrument that failed it, run again live"
  should read this as "the blocker is fixed, the criterion is re-measured on the cycle's own
  evidence, and a live re-run has not happened". That is the accurate sentence, and it is the one
  #77 should quote if it proceeds.

## What #77 needs now

Item 1 of the second cycle's "What #77 needs" list is closed. Items 2 (`fix` has no shape for a
multi-line soft-wrapped unit), 3 (the audit lane's repair round), and 4 (evidence for claims about
live tracker state) were recorded there as *not blockers*, and this addendum does not change
that: they remain open, with chips filed, and none of them touches G4's budget.
