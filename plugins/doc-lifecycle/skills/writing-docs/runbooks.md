# Writing a runbook

Reader: an on-call engineer, paged, under pressure, possibly unfamiliar with the tool.
Maps to the **how-to** lens (see readme.md's lens list; task-oriented, goal = resolve the incident). Human rendering,
but ruthlessly skimmable. Every command and output is a verifiable claim (see SKILL.md).

## The 3am test

Each step is a command, a check, or a decision — never a paragraph. The reader is stressed
and skimming. If a step needs prose to explain it, the step is wrong.

## Structure

```
# Runbook: <symptom as the on-call sees it>

## What this is / when you're here   (1–2 lines: the trigger, e.g. "CI step X failed")
## Reproduce locally                 (exact commands, in order, with prerequisites)
## Output & exit codes               (the real contract — what each code/line means)
## Failure modes → fix               (table: symptom → cause → action)
## Decision flow                     (short branch list to pick the failure mode fast)
## Escalation                        (who owns what; when to hand off)
```

## Copy-pasteable steps with real output

```sh
node --version            # must be >=20.6.0
npm run build             # produce dist/bundle.js — REQUIRED before the next step
node bin/cli.js           # reproduce what CI ran
```

State expected output so the operator recognizes success/failure:

```
OK   dist/bundle.js  0.1kb / 5.0kb     ← within budget
FAIL dist/bundle.js  6.2kb / 5.0kb     ← over budget (a real FAIL line, format-accurate)
```

## Failure-mode table pattern

| Symptom in the log | Cause | Action |
|--------------------|-------|--------|
| `FAIL <path> Xkb / Ykb`, clean exit | real budget regression | shrink artifact, or raise `maxKb` |
| stack trace, `ENOENT dist/bundle.js` | build didn't run first | run build before the check |
| `unknown flag: --x`, exit 2 | bad CI invocation | fix the command |

## Failure modes (watch for)

- **Overloaded exit codes documented as clean.** Verify what each code *actually* covers —
  a single exit 1 can mean over-budget OR crash. Run the cases; don't assume one-to-one.
- **Steps that assume prior state.** The build-before-run prerequisite must be explicit, or
  the operator hits a misleading error that doesn't match how CI failed.
- **Invented output.** Reproduce locally and paste real lines; don't illustrate from memory.
