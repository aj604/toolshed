# Issue #228 — production lane checkout

Retained production evidence for the model-bearing documentation lanes. The checkout started on
2026-08-06 from `main` at `32b65fcac8c6a7616d7e260983ae04e862674013`. At that commit,
`.doc-lifecycle/installed-version` contains `0.46.10`.

## Results

| Surface | Result | Evidence |
|---|---|---|
| Release prerequisite | PASS | [`v0.46.10`](https://github.com/aj604/toolshed/releases/tag/v0.46.10) is a non-draft, non-prerelease release of the checkout commit, published at `2026-08-06T01:36:35Z`. The [release run](https://github.com/aj604/toolshed/actions/runs/31063129773) passed its CI and release jobs. |
| `doc-audit` | PASS | After the workflow was re-enabled, [run 31063266048](https://github.com/aj604/toolshed/actions/runs/31063266048) passed both jobs. The lane invoked the model against its full declared corpus, repository integrity passed before assembly, and the model-free publisher revalidated freshness. |
| `doc-apply` | PASS | [Run 31063772739](https://github.com/aj604/toolshed/actions/runs/31063772739) passed revalidation, model planning, and model-free apply. It opened [PR #233](https://github.com/aj604/toolshed/pull/233) from the derived approval branch. |
| `doc-bloat-audit` | PASS | [Run 31063268796](https://github.com/aj604/toolshed/actions/runs/31063268796) passed its audit and publish jobs. The bounded first pass, trusted validation, single retry, repository-integrity gate, typed report assembly, and model-free freshness check all executed. The report is truthfully `partial`: 13 of 23 chunks completed, 10 remained missing, 26 documents were examined, and 19 documents were named incomplete. |
| `doc-policy-apply` | SCHEDULE BOUNDARY | The manual audit correctly produced [skipped run 31063678415](https://github.com/aj604/toolshed/actions/runs/31063678415): this lane admits only a successful `schedule`-origin audit. Its next eligible proof is the next `doc-audit` cron (`0 1 * * *`, nominally 2026-08-07 at 01:00 UTC); issue acceptance remains open until that run is successful or the lane is deliberately disabled with a recorded rationale. |

## Manual approval used for the apply proof

The drift report from run `31063266048` was `partial`, with report digest
`24d8057c735efc5b9c4cf529a408993d5a062781e316adef69a86a68736f9089`. Only the
`ANCHOR-STALE` occurrence for `docs/guides/auditing-doc-bloat.md` was approved, after comparing
the guide with every referenced source change since its anchor date. The occurrence digest was
`9d26bfdfaede228de5d73c58a84edaa2c47b23577cdf16bd790388b14b8eb89f`; other findings were not
included. The resulting PR changes only the guide's date and version anchor to 2026-08-05 and
0.46.10.

## Why the policy proof was not manufactured from the manual audit

`doc-policy-apply` uses `github.event.workflow_run.event == 'schedule'` as an origin boundary.
Adding a manual bypass merely to turn this checkout green would weaken the production contract it
is meant to test. The two earlier scheduled failures also should not be rerun against today's
default branch: both refused because the audit artifact's configuration digest no longer matched
the repository checked out for policy revalidation. That is the intended fail-closed result for a
stale artifact, not evidence that a stale run can be made authoritative later.

The next eligible scheduled audit is therefore the remaining production proof. Until it runs,
the honest state of #228 is three model-bearing lanes green and the schedule-only policy lane
pending.
