# GREEN — soft-wrapped STALE fix shape (`detecting-doc-drift`)

**Date:** 2026-07-28
**Setup:** fresh subagent, the identical DRIFT-021 scenario and normalization-pressure prompt from
RED, run against the edited working-tree `SKILL.md` and `output-contract.md`.

## Emitted record

The record (verbatim, with the JSON escape representing an embedded LF in `fix`) was:

```json
{"claim":"Don't customize the installed YAML beyond the cron/cap/bloat-cron/upgrade-cron knobs. Real changes belong upstream in the plugin (aj604/toolshed) so every install gets them on next upgrade.","location":"plugins/doc-lifecycle/skills/scheduling-doc-sync/SKILL.md:380","kind":"value","tier":3,"verdict":"STALE","evidence":"plugins/doc-lifecycle/skills/scheduling-doc-sync/scripts/apply-upgrade.py:101 — apply-upgrade.py preserves {{AUDIT_CRON}} in addition to the four listed knobs.","fix":"- **Don't customize the installed YAML beyond the cron/cap/bloat-cron/audit-cron/upgrade-cron knobs.** Real\n  changes belong upstream in the plugin (aj604/toolshed) so every install gets them on next upgrade."}
```

The subagent stated: “Yes, `fix` contains an embedded LF.”

## Evaluation

- Same stale fact and replacement prose as RED: **yes**.
- Embedded LF preserved despite the normalization pressure: **yes**.
- List marker and continuation indentation authored in `fix`: **yes**.
- Applier-side reflow requested: **no**.

**PASS.** The explicit physical-line rule, rather than agent taste, now determines the output.

## REFACTOR review

The two-axis code review then removed an applier-mechanics restatement from `fixing-docs`, renamed
the boolean engine helper as a predicate, and replaced legacy “claim” vocabulary introduced in
engine tests with “assertion.” The skill rule that produced this GREEN result was unchanged.
