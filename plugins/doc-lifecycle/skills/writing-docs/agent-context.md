# Writing agent-context docs (CLAUDE.md / AGENTS.md)

Reader: an AI agent starting a session in the repo. Maps to the **reference** lens, with
how-to elements (see readme.md's lens list). Agent rendering: maximum signal-per-token, no
narrative, pointers over inline copies — density is mandatory here, not optional.

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

`# CLAUDE.md` above is shorthand for the canonical agent doc. Per bootstrapping-docs'
repo-shape.md Rule 4, that's root `AGENTS.md`, with `CLAUDE.md` a one-line pointer to it —
only a Claude-Code-only repo skips the shim and makes `CLAUDE.md` canonical directly.

## The router rule (owns always-loaded placement, suite-wide)

**The always-loaded file is a router, not a repository.** Every line costs every session,
so a line earns *inline* placement only when it is **unprompted-critical** — the agent
needs it *before it would know to look*: cross-cutting commands, trap gotchas that bite on
the first action, the when-to-read map. Everything else lives in an on-demand doc **named
for discovery** (progressive disclosure: `docs/reference/release-checklist.md` routes by
filename alone) and appears in the always-loaded file as at most one when-to-read line with
a short snippet — or not at all, when the filename already routes.

This rule binds anything that *lands* content, not just hand-editing: an extraction, a
distilled claim, or a merge aimed at CLAUDE.md/AGENTS.md must either clear the
unprompted-critical bar in its densest one-line form, or target a reference doc instead.
Condensing the always-loaded file and correcting its false claims is always in scope;
growing it is what needs the justification.

## Pointers over inline copies

Inline code goes stale. Reference `file:line` so the agent reads current source instead of
a snapshot you have to keep in sync. This is also what keeps drift detection cheap.

## Failure modes (observed in baselines)

- **Inferable bloat.** Baseline CLAUDE.md restated the file layout, "ESM only", and
  indentation — all readable from the repo in seconds. Cut.
- **Unanchored rationale.** The gzip-in-memory "why" was stated as timeless prose with no
  `file:line`. Mark it and anchor it.
- **Inline snapshots that rot.** Copied code/output instead of a pointer.
- **Accretion via landings.** Sweeps and distills that each add "one small paragraph" to
  the always-loaded file — none unprompted-critical, together a second README. Route them
  to reference docs; the router rule above is the gate.
