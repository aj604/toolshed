# RED scenario A — runner report (verbatim summary as returned)

Outcome: DRIFT-001 was applied through `python3 -m doclifecycle apply-plan`
(exit 0, `clean`, `already_applied: false`), not by hand. The only tree change
is `docs/architecture.md:7` `2%` → `2.5%`, verbatim the record's `fix`. Nothing
staged or committed. A re-run of the same plan returned `already_applied: true`.

Skill files the runner read:
- `<plugin-red>/plugins/doc-lifecycle/skills/fixing-doc-drift/SKILL.md` — "act
  only on STALE records, confirm the anchor still carries the claim before
  writing, land the record's `fix` verbatim as the full-line replacement and
  stop at its boundary, never delete or tidy anything the report did not flag."
- `<plugin-red>/plugins/doc-lifecycle/references/apply-discipline.md` — "the
  shared spine it cites: authorized records only, no 'while I'm here', confirm
  the anchor, blast-radius stop, and evidence travels with the change."
- `<plugin-red>/plugins/doc-lifecycle/engine/README.md` — **not a skill file**;
  the runner went and found it on its own initiative after listing the plugin
  tree, and took the applier contract from there.

The runner's own flag, verbatim:

> Worth flagging: `fixing-doc-drift/SKILL.md` in this snapshot never mentions
> the applier, the approval set, or `apply-plan`. Followed literally it reads as
> "hand-edit the line," which would bypass every one of those checks. I followed
> the engine's write contract instead; the skill text is the gap.

Other facts from the run:
- The runner used the pre-existing `artifacts/approval-current.json` rather than
  minting one; the skill text never told it an approval set was required, and it
  reached for one only after reading the engine README.
- It hand-authored the edit plan with a throwaway script
  (`artifacts/build-edit-plan-drift-001.py`) derived from `applier.py` source,
  not from any skill instruction.
- It correctly declined BLOAT-001 and BLOAT-002, and correctly reported that the
  apply moved the preimage so a second subset now needs a re-mint.
