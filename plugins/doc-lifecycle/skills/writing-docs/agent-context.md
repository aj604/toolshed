# Writing agent-context docs (CLAUDE.md / AGENTS.md)

Reader: an AI agent starting a session in the repo. Maps to the **reference + imperative
rules** lenses. Agent rendering: maximum signal-per-token, no narrative, pointers over
inline copies — density is mandatory here, not optional.

**Ownership.** The full densify+verify method lives in exactly one place — the
`llm-doc-writer` agent. For a whole-doc or verification-heavy job, **dispatch it** (it runs
in its own context — see SKILL.md "One bar, every reader — then route"). What follows here is
the **inline essentials** for a one-line tweak not worth a dispatch: the minimum bar to apply
in place, a deliberate subset of the agent's method — not a second copy that can drift from it.

## The cut test (the dominant discipline here)

For every line: **would removing it cause the agent to make a mistake?** If not, cut it. A
bloated CLAUDE.md dilutes the signal — the more inferable filler the agent wades through, the
more it skims past your actual instructions. This test bites harder here than anywhere else.

Cut on sight:
- Anything derivable from the code, types, or file tree (layout tables, "this is ESM",
  indentation/quote conventions a formatter enforces).
- Restated obvious facts ("write clean code").
- Long explanations — link to the file instead (`see bin/cli.js:34`).

## Include only what an agent can't cheaply infer

- Build / test / lint / run commands it can't guess (and which differ from defaults — e.g.
  `npm run check`, not `npm test`).
- Non-obvious gotchas (build-before-run; required runtime version; env vars).
- Conventions that differ from language defaults.
- Architecture *pointers* (where things live), not descriptions.
- Design rationale worth preserving — marked and **anchored** (see SKILL.md rule 2).

## Structure

```
# CLAUDE.md
## Commands        (table: task → exact command)
## Gotchas         (non-inferable, would-cause-mistakes-if-missing)
## Conventions     (only those differing from defaults)
## Design notes    (anchored rationale: "as of <file:line> …")
```

## Pointers over inline copies

Inline code goes stale. Reference `file:line` so the agent reads current source instead of
a snapshot you have to keep in sync. This is also what keeps drift detection cheap.

## Failure modes (observed in baselines)

- **Inferable bloat.** Baseline CLAUDE.md restated the file layout, "ESM only", and
  indentation — all readable from the repo in seconds. Cut.
- **Unanchored rationale.** The gzip-in-memory "why" was stated as timeless prose with no
  `file:line`. Mark it and anchor it.
- **Inline snapshots that rot.** Copied code/output instead of a pointer.
