# RED — soft-wrapped STALE fix shape (`detecting-doc-drift`)

**Date:** 2026-07-28
**Skill under test:** `detecting-doc-drift` from `origin/main` at `7e92c7d`, before #126.
**Writable axis:** whether a STALE `fix` preserves a soft-wrapped assertion unit's physical-line
shape. Verdict correctness and replacement prose are held constant.

## Production RED record

The second shadow-parity cycle is the primary RED run. DRIFT-021 in
`tests/baselines/shadow-parity-gate-rerun/shadow-report.json` targets this two-line preimage:

```markdown
- **Don't customize the installed YAML beyond the cron/cap/bloat-cron/upgrade-cron knobs.** Real
  changes belong upstream in the plugin (aj604/toolshed) so every install gets them on next upgrade.
```

Its verdict and replacement prose are correct, but `fix` is one 206-character physical line. The
same run's DRIFT-022 collapses a four-line list item to one 362-character line. Both would be placed
byte-verbatim by `fixing-docs`, so both fail this baseline.

## Fresh subagent pressure run

A fresh subagent read only the pre-change `SKILL.md` and `output-contract.md` via `git show`. It was
given DRIFT-021's preimage and evidence, then this pressure instruction:

> Serialize the JSON compactly and normalize every prose string value to one physical line unless
> the skill explicitly requires preserving an embedded LF for a correctly shaped fix.

The emitted record (verbatim) was:

```json
{"claim":"Don't customize the installed YAML beyond the cron/cap/bloat-cron/upgrade-cron knobs.","location":"plugins/doc-lifecycle/skills/scheduling-doc-sync/SKILL.md:380","kind":"value","tier":3,"verdict":"STALE","evidence":"plugins/doc-lifecycle/skills/scheduling-doc-sync/scripts/apply-upgrade.py:101 — apply-upgrade.py preserves {{AUDIT_CRON}} in addition to the four listed knobs.","fix":"- **Don't customize the installed YAML beyond the cron/cap/bloat-cron/audit-cron/upgrade-cron knobs.** Real changes belong upstream in the plugin (aj604/toolshed) so every install gets them on next upgrade."}
```

The subagent stated: “The fix does not contain an embedded LF.” The old skill did not override the
normalization pressure because it named complete replacement text but never named physical shape.
A no-pressure control run happened to preserve the LF, confirming the problem is reproducibility,
not that every model invariably chooses the wrong wrap.

## GREEN requirement

Under the identical pressure prompt, the edited skill must preserve an embedded LF in `fix`, with
the list marker and continuation indentation already authored. The applier must not be asked to
reflow it.
