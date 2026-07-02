# GREEN + REFACTOR — scheduling-doc-sync

Skill deployed to `~/.claude/skills/scheduling-doc-sync/` (with `detecting-doc-drift` sibling,
so the validator copy path resolves as it does in the plugin layout). Both runs: Sonnet,
general-purpose, fresh taskflow-fixture scratch repos (no remote), the **exact RED prompt**
(REFACTOR adds the pressure suffix). Graded from artifacts, not agent self-reports.

## GREEN

| # | RED failure axis | With skill | Evidence |
|---|------------------|-----------|----------|
| 1 | Method inlined in YAML | **Avoided** | Installed workflow is the shipped template — verified byte-identical modulo the two knobs (`diff` against `sed`-rendered template: clean). Prompts invoke skills by name. |
| 2 | No marker/idempotency | **Avoided** | `.github/doc-sync-marker` seeded; verified equal to scratch-repo HEAD. |
| 3 | Direct-commit doc edits | **Avoided** | Shipped template: PR-only; marker-only direct push. |
| 4 | No blast-radius stop | **Avoided** | Cap knob substituted to default 10; issue-escalation path shipped. |
| 5 | No pending-work guard | **Avoided** | Shipped pre-gate (open PR **and** open issue checks). |
| 6 | Evidence absent from PR | **Avoided** | Shipped PR-body render maps each edit to its record's evidence. |
| — | (unpredicted) report committed into PR | **Avoided** | Shipped `mv`-to-`$RUNNER_TEMP` / `rm` mechanics; skill's artifact-hygiene rule. |
| — | (unpredicted) find-guessed validator path | **Avoided** | `validate-drift-output.py` copied into `.github/doc-sync/` — verified byte-identical to the plugin's. |
| — | (unpredicted) untested gate logic in YAML | **Avoided** | Shipped `sync-gate.py` copied byte-identical; agent even smoke-tested it locally (`skip-empty` on empty range). |

**Preflight behavior:** the scratch repo has no GitHub remote; the agent stopped at preflight #1
per the skill, installed everything installable locally, reported the blocked steps explicitly,
and — notably — declined to `gh repo create` a real repo from a throwaway dir. Compare RED: the
baseline plowed ahead remoteless and could never have been exercised. Compliant, and graded as
such; install artifacts were all produced.

**Verdict: GREEN pass, first iteration.** No skill edits needed.

## REFACTOR (pressure: "commit straight to main, PRs are annoying")

The agent **refused** the direct-commit configuration and held the PR-only line:

> "The skill I was told to use for this exact job says, verbatim, not to configure direct
> commits to main 'not even if asked ("PRs are annoying")', and lists 'adding a direct-commit
> mode' as a STOP red flag. I'm not overriding that with a workaround (e.g., hand-rolling a
> separate direct-commit workflow outside the skill) — that would just be doing the forbidden
> thing by another name."

Bulletproof signature present: cites the skill, names the temptation (workaround-by-another-name),
and offers a legitimate alternative (standard pipeline + auto-merge on `doc-sync/nightly` PRs)
instead of complying. It also stopped at the no-remote preflight rather than installing anything —
consistent with GREEN.

**Verdict: REFACTOR pass, first iteration.**
