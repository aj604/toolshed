# RED findings — scheduled policy apply lane (#143)

The retained RED was run before the policy workflow, consumer opt-in, installer wiring, and
renderer seam existed. The executable probes were added first and failed for the missing behavior;
this record keeps the observed boundary rather than reconstructing it from the GREEN result.

## Focused failures

| Probe | RED observation |
|---|---|
| `policy-workflow_test.py` | The shipped `doc-policy-apply.yml` template did not exist, so no completed scheduled audit could reach the policy commands or a three-job trust split. |
| `render-apply-summary_test.py PolicyEligibility` | The renderer exposed no `policy-eligibility` subcommand, no clean no-eligible stop, and no malformed-envelope refusal. |
| `apply-upgrade_test.py` | Upgrade knew only the manual audit/apply lanes and neither installed the new workflow nor proved an optional policy was preserved without being seeded. |
| `install-parity_test.py` | Dogfood had no fourth engine workflow to compare with the shipped install. |
| Skill/documentation probes | The scheduling skill and guide did not name an explicit policy file, its closed classes, the real-PR review gate, or the no-silent-opt-in rule. |

The first expanded workflow run reported 16 failures. The renderer policy slice reported three
failures, and the upgrade slice failed before implementation. Those failures established the
vertical target: trigger → deterministic eligibility/mint → repository-credential-free model plan
→ model-free confined apply → real pull request, with absence remaining a clean opt-out.

## Review RED

The later standards review added two more executable probes before its corrections:

- current user and test surfaces failed when they called an OAuth/API-authenticated model job
  merely `credential-free`;
- the renderer failed to identify its structural check as a fail-closed adapter envelope, and the
  two apply workflows had no explicit parity guard at their shared security seams.
