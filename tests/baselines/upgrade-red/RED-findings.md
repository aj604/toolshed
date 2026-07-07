# RED findings — scheduling-doc-sync upgrade/pinning

Two fresh subagents (general-purpose, current skill only, design spec off-limits) ran the upgrade
scenario in `RUBRIC.md`. Graded against the rubric below. **Confirmed RED: the skill teaches none
of R1–R4/R6; both agents had to invent them, and both picked a broken pin mechanism.**

| # | Criterion | Scenario A | Scenario B |
|---|-----------|-----------|-----------|
| R1 | Pin marketplace ref | **FAIL** — invented a pin, but wrong mechanism | **FAIL** — same |
| R2 | Version lockfile | **FAIL** — improvised a header-comment stamp | **FAIL** — invented `installed-version` (right idea, skill silent) |
| R3 | Dedicated upgrade workflow | **FAIL** — *declined* one, citing skill's "two workflows" | **FAIL** — invented one (skill silent) |
| R4 | Preserve knobs on upgrade | **FAIL** — preserved via careful reasoning, skill silent | **FAIL** — invented a refresh-mode table, skill silent |
| R5 | Preserve marker/audit-scope (control) | **PASS** — skill teaches it, agent followed exactly | **PASS** — same |
| R6 | Method out of YAML | PARTIAL — cited the principle, shipped no tested mechanism | **FAIL** — invented a tested gate (right instinct, skill silent) |

R5 PASS on both confirms the agents actually read the skill — so the R1–R4 failures are the skill's
silence, not inattention.

## Key verbatim signals

- Scenario A: *"The skill as written gives me no knob to pin a version and no currency-check."*
- Scenario A **declined the needed third workflow** because the skill's contract says "two
  workflows": *"No new file, no new workflow… its rule 'Don't customize the installed YAML' …
  steer[s] me away."* — the current text actively steers away from the fix.
- **Both** agents reached for `plugins: doc-lifecycle@toolshed@0.7.0` — a version selector
  `claude-code-action` does **not** support (confirmed: only `#ref` on `plugin_marketplaces`
  pins). Even strong agents pick the broken mechanism when the skill is silent. GREEN must teach
  `#vX.Y.Z`-only pinning and explicitly forbid the `@version` plugin selector.

## Improvements the baselines surfaced (fold into GREEN)

1. **Tested semver gate, not inline `!=`.** Scenario B's `upgrade-gate.py compare` with a third
   `ahead` state (installed newer than any release → do nothing, never downgrade) is more robust
   than the design's inline string-inequality and matches the repo's "thin YAML, tested script"
   rule. Adopt it; add `tests/scripts/upgrade-gate_test.py`.
2. **`installed-version` stores the bare `plugin.json` version** (`0.7.0`), so install reads it
   straight from `jq .version`; the pin ref and release-tag compare add/strip the `v`.

## GREEN target

R1–R6 all PASS, driven by explicit skill text: pinned templates (`{{PLUGIN_REF}}`, `#vX.Y.Z`
only), a `doc-sync-upgrade.yml` template, an `installed-version` lockfile, a tested `upgrade-gate.py`,
and a Refresh-mode section codifying state-vs-wiring ownership + knob preservation. Graded by a
fresh subagent (authors don't grade their own GREEN).
