# GREEN results — scheduled policy apply lane (#143)

The updated scheduling skill now installs four workflows and teaches the standing-policy opt-in.
The new lane chains only a successful scheduled audit, revalidates its exact artifact on the
current default branch, lets the engine decide and independently mint the eligible subset, gives
the model no repository credential, and lets only a model-free job write a derived branch and open
a real pull request.

## What flipped RED → GREEN

- `policy-workflow_test.py`: 18/18 on the initial GREEN, covering the trigger, exact run binding,
  explicit opt-in, three-job permissions split, SHA pins, separated artifacts, deterministic
  apply, exact staging, derived branch, and real non-draft PR.
- `render-apply-summary_test.py`: 78/78 on the initial GREEN, including eligible/no-eligible and
  malformed eligibility envelopes; the review follow-up keeps the envelope fail-closed while
  asserting that no finding code, policy class, or eligibility rule lives in the adapter.
- `apply-upgrade_test.py`: 46/46, including installation of the workflow and preservation without
  seeding or overwriting `.doc-lifecycle/auto-apply-policy.json`.
- `install-parity_test.py`: dogfood workflow and renderer copies are byte-identical to the shipped
  install, and the vendored engine remains identical.
- Full pre-review evidence: all 21 script suites, all 1,259 engine tests, the 52-suite release
  manifest guard, compilation, plugin validation, JSON/YAML parsing, mirror comparisons, version
  guard, and diff check passed.

## Review hardening

The shared manual/policy plan and apply logic remains visible because permissions and secrets are
job-level GitHub concepts. Parity tests now hold the repeated security seams together instead of
introducing a reusable-workflow secrets boundary. Current model-lane wording says
`repository-credential-free` and separately acknowledges model OAuth/API/id-token credentials.
The eligibility renderer names its narrow adapter-envelope role and has a guard against acquiring
policy business vocabulary.
