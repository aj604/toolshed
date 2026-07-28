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

**A policy exclusion, which is mechanical.** `policy.py` refuses a record whose `fix` changes
which documents its passage names — `policy-fix-names-other-document`, decided per record and
reported with the rest. A preimage pins what a run *read*; a `fix` is the half a model *wrote*,
and a document the replacement adds or drops is one the record pins nothing from, so what the
replacement says about it is the model's and not the repository's. An `evidence.source` pointing
at that same document does not close the gap: a citation says one line was consulted, and what a
document contains is the thing being asserted. Both directions, not only additions — a preimage
that *mentions* a file has pinned the sentence and not the file, so an additions-only rule would
still admit a repointing that swapped which document the sentence is about. The document the
finding lives in is excluded, by its repository path and not its filename: rewriting a passage
that names its own file speaks for nothing else, while a bare filename names no one document.
Recognizing a file reference is `paths.path_references`, which reads a dotted symbol
(`approval.Record.targets()`) and a slash-joined prose list (`cron/cap/upgrade-cron`) as prose,
and is otherwise generous — a token it over-reads costs a person one more record to look at, and
one it misses costs the refusal.

Two references are past what shape can settle, and the method rule below is what covers them: a
document named without its suffix (`docs/plans/2026-07-27-rerun`) and one named in prose alone
("the second cycle's rerun plan"). Both are recorded as limits rather than left to be discovered.

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

> record DRIFT-023's fix changes which documents this passage speaks for —
> ['docs/plans/2026-07-27-shadow-parity-gate-rerun.md'] is named on one side of the replacement
> and not the other. The assertion pins the passage's own text, never another file's contents, so
> what the replacement says about that document is the model's and not the repository's. A
> citation does not settle it either: a pointer says one line was read, and what a document
> contains is the thing being asserted. A pointer whose target has been superseded is a finding
> for a person, who can open the new one

**G4 criterion 1, re-measured: 0 false positives in the auto-apply-eligible class, budget 0 —
PASS on replay.** Criterion 2 (at most 2 false positives overall) was already PASS at 1 and is
unchanged: the record is still in the report, still a false positive, still shown to a person.
Nothing here deletes a finding; it moves one out of the class that lands unattended.

One instrument note, so a third cycle is not read off the wrong number.
`compare-shadow-lanes.py`'s `auto_apply_eligible` is a second, coarser reading of the class —
`STALE` plus a `fix` plus an `evidence.source`, with no engine import — and it does not know this
refusal, so its worklist would still list a record of DRIFT-023's shape as eligible. The verdict
did not measure G4 with it: its G4 section takes the class "as the landed policy defines it
(`doclifecycle/policy.py`'s `CLASS_CODES`)", which is where its 12 comes from and where this
replay's 12 comes from. The script splits an adjudication worklist; `policy-eligibility` is the
authority, and the script leaves with the legacy lane (#77).

Four further pieces of evidence, all in the repository:

- **A regression test carrying the record verbatim.** `tests/engine/policy_test.py`'s
  `AFixThatSpeaksForAnotherDocument` builds DRIFT-023's assertion, fix, and evidence as recorded
  and asserts the refusal, at the library seam and through `mint_policy_approval_set`. It fails
  on the code as it stood before this change.
- **The over-refusal cases are tests too, not an argument.** DRIFT-014's symbol rewrite,
  DRIFT-021's knob list, DRIFT-022's two build artifacts, and a fix naming the finding's own
  document each assert *eligible* — the shapes a blunter exclusion would have swept up.
- **The bypass an adversarial spec review found, and closed.** The first implementation refused
  only files the fix *added*. Given a preimage that mentioned the successor in passing — "the gate
  record is `a.md` (a rerun is planned at `b.md`)" — a fix repointing the sentence at `b.md` named
  no new file and stayed eligible: DRIFT-023 with one clause added to the claim. The comparison is
  now equality in both directions, which refuses that and costs nothing on this corpus (still 11
  eligible, still the same 23 decisions). `test_a_preimage_that_merely_mentions_a_file_has_not_pinned_it`
  is that record.
- **Mutation results.** Eleven mutants, each killed: removing the guard; relaxing the comparison
  to added names only, and to dropped names only; removing the own-document carve-out, widening
  it to the bare filename, and widening it to the cited document; skipping a `fix` that is not
  text; and four mutations of the recognizer — dropping directory references, dropping bare
  filenames, reading any slash token as a path, reading any dotted token as a path. Each fails
  `policy_test`, `paths_test`, or both. Recorded because it is the point of the exercise: the
  first round had six mutants and one of them, *removing* the carve-out, **survived** — the test
  that named the branch had a preimage that already named the document, so the carve-out was
  never what admitted the record. A claim of "each killed" is worth what the mutants are worth,
  and this one is worth what review made of it.

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
