# Scenario (b) — policy-scope directory of 10 ephemeral artifacts

## Prompt (verbatim, to a fresh subagent)

> First read the skill file plugins/doc-lifecycle/skills/detecting-doc-bloat/SKILL.md and follow it exactly.
>
> Task: run a documentation-bloat audit over the directory docs/superpowers/ of the repository at tests/fixtures/plan-swarm (treat that directory as the repository root; all doc paths relative to it). The repo's scope config (.github/doc-sync/audit-scope.json) declares docs/superpowers as policy-scope: the maintainers consider everything under it one class of ephemeral process artifact. The work all these artifacts describe has already merged (the repo's src/ is the landed state). Emit your structured result as the skill prescribes.
>
> Final message: 1. "RECORDS:" (verbatim JSON) 2. "APPROACH:" 3. "TIME PROXY:".

## Runner behavior

Ran `plan-chunks.py` (found on disk), got the single policy chunk, spot-checked 3 of 10 artifacts, and emitted **one POLICY record** with all 10 paths in `files` and a retirement-class policy proposal — passing both the seam and final validators. TIME PROXY: "I opened 3 of the 10 artifacts (plus `src/limiter.py` and the scope config) and authored 1 record."

Contract source, in the runner's own words: "the SKILL.md/output-contract.md prose in this worktree still describes contract v1 (six verdicts, DISTILL payloads), but the validator the skill mandates enforces v2 … — I followed the validator, since the skill forbids emitting anything it rejects."

## Grader verdict (stakeless, held the answer key): overall **FAIL**

- C1 (one POLICY record, files = all 10): PASS.
- C2 (zero per-file walk): PASS — "So instead of authoring ten per-artifact DISTILL records, I spot-checked a sample".
- C3 (no detect-time payload authoring): PASS.
- C4 (skill text itself taught it): **FAIL** — grader verified against the on-disk skill: "line 115 '`DISTILL`, `status: \"ready\"`, with a full `payload`' … No POLICY verdict exists in the skill text. The correct output was reached by tool-driven improvisation, not by instruction."

Rationalizations captured (verbatim):
- "I followed the validator, since the skill forbids emitting anything it rejects." — "a self-supplied conflict-resolution rule; the skill text never says the validator overrides its own prose."
- "the contract (enforced by `validate-bloat-output.py --chunk --manifest`) requires exactly one POLICY record covering the directory" — "contract learned by reading/running the enforcement tooling, not from the skill."

Grader's close: "correct behavior currently depends on validator archaeology, not skill instruction."

## Production anchor

Without the landed harness (career-compass run 28833711517, pre-rearchitecture), this same class of directory produced 47 per-file `DISTILL ready` records with full payloads — most of the run's ~$30 spend. The structural harness prevented the walk here; the skill text still teaches it.

## What the GREEN text must therefore teach

The POLICY verdict and its rules in the skill's own references (one record, `files` from the manifest verbatim, never a file-by-file walk), reachable without reading tool source.
