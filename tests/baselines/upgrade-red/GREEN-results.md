# GREEN results — scheduling-doc-sync upgrade/pinning

Two fresh subagents ran the rubric scenarios against the **updated** skill (upgrade scenario +
fresh-install scenario), design spec and baselines off-limits. A third fresh, stakeless grader
scored both against `RUBRIC.md` and cross-checked every claim against the shipped
skill/templates/scripts and the dogfood install. **Clean GREEN — R1–R6 PASS in both scenarios.**

| # | Criterion | Upgrade | Fresh install |
|---|-----------|:---:|:---:|
| R1 | Pin `#v<tag>`, `plugins:` bare, `@version` rejected | PASS | PASS |
| R2 | `installed-version` lockfile as source of truth | PASS | PASS |
| R3 | Dedicated `doc-sync-upgrade.yml` (resolve→gate→PR) | PASS | PASS |
| R4 | Preserve knobs on upgrade (re-inject, never reset) | PASS | PASS |
| R5 | Marker + audit-scope untouched | PASS | PASS |
| R6 | Compare/render in tested scripts; workflow owns git | PASS | PASS |

## What flipped RED → GREEN

- Both GREEN agents **cite the skill** ("Upgrade mode", the twelve-file list, the pin rule) rather
  than reinventing — the mechanisms are now taught, not guessed.
- The RED shared error — `plugins: doc-lifecycle@toolshed@<v>` (an unsupported selector) — is now
  **explicitly rejected** by both agents, because the skill states the pin lives only in the
  `#v<version>` ref and the `@version` selector is invalid.
- The RED agent that **declined the third workflow** (citing the old "two workflows" contract) is
  resolved: the skill now ships three workflows and the upgrade agent adds `doc-sync-upgrade.yml`
  (handling the "install predates it" case per the Upgrade-mode note).

## Grader verification (against shipped repo)

Every mechanism the transcripts describe is backed by shipped artifacts: the `#v{{PLUGIN_VERSION}}`
pin + bare `plugins:` in all three templates; `installed-version` (dogfooded at `0.8.0`, matching
the manifest); `doc-sync-upgrade.yml`'s resolve/gate/PR shape; `upgrade-gate.py`'s semver compare
(`upgrade|current|ahead`, exit 2 on malformed); `render-report.py`'s five `upgrade-summary`
statuses + `upgrade-pr-body`. No plausible-but-wrong artifacts; no version-parse leaked into YAML;
no model self-commit. Grader verdict: **clean GREEN, driven by the skill text.**

Script suites (`upgrade-gate_test.py`, `render-report_test.py`) pass; `claude plugin validate .`
passes; all workflow YAML parses.
