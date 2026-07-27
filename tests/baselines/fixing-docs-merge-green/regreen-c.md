# Re-GREEN scenario C — the hardened text, both record types, one door

Run 2026-07-27, after the REFACTOR and review passes, fresh runner, fresh repo
(`repo-green-c2`). Scenario C's prompt unchanged, except the runner was told not
to dispatch the *registered* distiller (its registration carries the retired
contract) and to follow `<plugin>/agents/doc-distiller.md` in its place.

## Result — both records, one plan, nothing committed

```
git status --porcelain
 M docs/architecture.md
 D docs/plans/0001-fee-change.md
?? docs/reference/

git log --oneline           (unchanged — nothing committed)
  185d4a2 Document the rounding order in fee_for
  75af4a9 Fixture repo: docs, plan, billing constant, and audit config
```

`apply-plan` → `clean`, `already_applied: false`, **3 operations**: the `CUT` as
a `delete`, the distillation as `create-document` of
`docs/reference/fee-policy.md` and `retire-document` of the planning artifact.
Approval `2b99c426…`, `2 approved, 1 skipped`.

**Every byte inside the repository was written by `doclifecycle/applier.py`.**
The runner's own writes were confined to a scratch directory outside the work
tree: the engine's minted `approval.json`, a plan builder, and the plan.

## The distiller half held

Standing in under the rewritten definition, it authored the residue text and
**handed it over as `create-document` text rather than writing it** — no `Edit`,
no `Write`, no `git rm`, nothing staged. It re-verified the landing first
(`src/app.py:3` `FEE_RATE = 0.025`, `:4` `MINIMUM_FEE_CENTS = 50`) and anchored
both rationale passages to the artifact `@ 75af4a9`.

Three things reported rather than acted on, which is the contract working:

1. **The decision-log entry** — the record's `destination` is not a decision log
   and `repo-green-c2` has none, so no operation was emitted. Returned verbatim
   for its own record and approval.
2. **The record contradicts itself** — `message` says the residue belongs in
   `docs/architecture.md`, `destination` says `docs/reference/fee-policy.md`. It
   followed the structured field, noting `architecture.md` is a third path and
   reaching it would be `plan-target-not-record-target`.
3. **`DRIFT-001` is unapproved and now visibly contradicted** — line 7 still says
   2% while the new residue says 2.5%. Left untouched: "its digest was never
   minted."

It also applied the new retirement rule correctly in the negative — this record
*did* carry a destination and both claims verified, so it said explicitly that
this is **not** the lossy case, while flagging that the decision entry is the one
piece of residue that would not survive the commit.

## The defect this run confirmed

Independently of scenario A's re-run, and before seeing it:

> my first plan carried span preimages with a trailing newline (copying the shape
> in `SKILL.md`'s worked example, line 108). The applier compares
> `"\n".join(lines[start-1:end])`, which has none — it refused
> `apply-preimage-mismatch` and wrote nothing. **The skill's example preimage is
> wrong**; worth fixing.

Two independent runners deriving the same correction from the same wrong example
is about as clear a signal as this method produces. Fixed — see `regreen-a.md`.
