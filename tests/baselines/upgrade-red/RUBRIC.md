# Rubric — scheduling-doc-sync upgrade/pinning (RED → GREEN)

Milestone: pinned wiring + self-upgrade PR (design:
`docs/superpowers/specs/2026-07-07-doc-sync-self-upgrade-design.md`).

**Scenario given to the agent:** a consumer repo already has doc-sync installed at an older
plugin version; the plugin has since cut a newer release and the vendored wiring in
`.github/doc-sync/` has drifted from what the skill now ships. The user asks the agent to
**upgrade the install to the latest plugin version and make sure the wiring can't silently fall
behind the skills again.** The agent works only from the `scheduling-doc-sync` skill.

Each criterion is PASS (agent does it, unprompted, from the skill) or FAIL. Grade the artifact
the skill *taught*, not whether the agent happened to guess it.

| # | Criterion | Notes |
|---|-----------|-------|
| R1 | **Pins the marketplace ref.** Installed workflows use `plugin_marketplaces: …/toolshed.git#<release-tag>`, NOT bare `…/toolshed.git` (main). | The core "stop the skills floating" fix. |
| R2 | **Machine-readable version lockfile.** Establishes/advances `.github/doc-sync/installed-version` (single release tag) as the source of truth for the installed version; not re-derived by parsing YAML. | |
| R3 | **Dedicated upgrade workflow.** A third installed workflow (`doc-sync-upgrade.yml`) that resolves the latest release, gates on lockfile-vs-latest, and opens a reviewable upgrade PR — not a hand-rolled one-off. | |
| R4 | **Preserves knobs on upgrade.** Re-applies the consumer's existing cron / blast-radius cap / bloat-cron / upgrade-cron, NEVER resets them to template defaults. | Reset-to-defaults = FAIL. |
| R5 | **Preserves state (control).** Marker and `audit-scope.json` untouched on upgrade. | Current skill already teaches this — expected PASS even at baseline; sanity that the agent read the skill. |
| R6 | **Method stays out of YAML.** Version resolution/compare and run-surface strings go through tested scripts (`render-report.py` subcommands, inline string-equality gate), not durable hand-rolled logic/templating in workflow YAML. | |

**RED expectation:** R1–R4 FAIL, R6 likely FAIL/partial (current skill teaches none of them);
R5 PASS. **GREEN target:** R1–R6 all PASS.

Grading is done by a fresh subagent with this rubric (authors don't grade their own runs).
