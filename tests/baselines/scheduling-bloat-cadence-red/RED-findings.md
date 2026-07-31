# RED findings — scheduled bloat cadence (#144)

The retained RED began before the scheduling skill shipped a bloat workflow. The executable
probes were written against the public installation seam first; this record keeps the observed
failure boundary rather than reconstructing it from the finished workflow.

## Initial cadence RED

| Probe | RED observation |
|---|---|
| `bloat-audit-workflow_test.py` | `doc-bloat-audit.yml` did not exist, so there was no scheduled public-plan preflight, budgeted Task fan-out, completion assembly, or read-only report surface to inspect. |
| `render-audit-summary_test.py` | The shared renderer had no bloat surface selector and could only label a typed partial report as a doc audit. |
| `apply-upgrade_test.py` | Upgrade knew no `{{BLOAT_AUDIT_CRON}}`, did not preserve/default/fail on that knob, and declared no bloat workflow path. |
| `install-parity_test.py` | The dogfood install had no bloat workflow mirror for deterministic regeneration to compare. |
| Skill/documentation probes | The scheduling contract still described drift as the only recurring audit and had no separate cadence, bounded-worker, #152 completion, or interactive-apply handoff. |

The first focused workflow run failed because the template was absent. The renderer slice then
failed on its unknown bloat selector, and a tightened regeneration assertion failed until the
installer actually wrote the new workflow rather than merely preserving a synthetic fixture.

## Standards-review RED

The hard Standards review exposed a second boundary and its tests were again run before the fix:

- `bloat-audit-workflow_test.py` ran six tests with one failure and three errors: the workflow had
  no trusted integrity step to extract or order, assembly and audit were still unconditional after
  the model, and the workflow still called the ambiguous renderer flag;
- `render-audit-summary_test.py` ran twenty tests with two failures: `--audit-surface bloat` was
  unknown while the ambiguous legacy `--kind bloat` remained accepted;
- the model and its Task workers had local `Write`, `Bash(git *)`, and `Bash(python3 *)` despite
  their read-only repository token. A dirty checkout could therefore reach deterministic
  completion assembly without a trusted refusal, making “read-only” a permission claim rather
  than an end-to-end worktree invariant.

Those failures set the review target: the immutable workflow graph must check HEAD plus staged,
unstaged, ignored, and ordinary untracked state after all model retries, refuse without cleaning,
and make both assembly and report production unreachable on failure.
