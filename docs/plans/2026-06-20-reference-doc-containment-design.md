# Reference-doc containment + cross-unit overview

**Date:** 2026-06-20
**Status:** implemented (containment + `architecture.md` in `repo-shape.md`; deferred-note
softening in `SKILL.md` + `repo-shape.md` — see addendum)
**File changed:** `plugins/doc-lifecycle/skills/bootstrapping-docs/repo-shape.md` (skill reference doc only — no change to this repo's own `docs/`).

## Problem

`repo-shape.md` tells a larger repo to scatter its agent doc set across `docs/`
(`docs/auth/overview.md`, `docs/generated/`), and offers no cross-unit overview at all. Two gaps:

1. **No home for the cross-unit picture.** Each `docs/<unit>/overview.md` is scoped to its
   own unit. Nothing owns "auth issues tokens payments validates; both read the shared
   session store" — the system-level relationships no single unit doc can hold. A reader gets
   a router and per-unit docs but never the picture of how the pieces fit.

2. **The doc set colonizes `docs/`.** Claiming `docs/<unit>/` + `docs/generated/` at the
   `docs/` root collides with a folder many teams already use their own way (plans, guides,
   handoffs). The footprint should be one polite subdir, not the whole folder.

## Decisions

### 1. Contain the agent doc set in one self-contained subtree

The entire on-demand agent doc set lives under `docs/reference/`, never scattered across
`docs/` root. Root files stay at root because tools auto-load them.

```
AGENTS.md              ← lean router (root, always-loaded); points into docs/reference/
CLAUDE.md              ← one-line shim → AGENTS.md
docs/
  reference/           ← the entire agent doc set, contained
    architecture.md    ← cross-unit picture (see decision 2)
    auth/overview.md   ← per-unit, scoped
    payments/overview.md
    generated/         ← auto-generated reference
  plans/  guides/ …    ← the team's own docs/, untouched
```

Rationale: `docs/` is a shared convention; the skill borrows one subdir rather than owning
the folder. This keeps the footprint small and avoids forcing a team off its own `docs/`
layout.

**Interaction with Rule 1 ("group by domain, not doc-type").** Still governs *inside*
`docs/reference/` — `reference/auth/`, not `reference/guides/`. The reference-vs-everything
split is a higher-order *containment* boundary (tracks-code vs not), not the doc-type
flavoring Rule 1 bans. The new guidance must say this explicitly so it doesn't read as
contradicting Rule 1.

### 2. `architecture.md` — the cross-unit overview

A read-on-demand doc at `docs/reference/architecture.md`, peer to the per-unit subdirs. The
router points to it as the start-here for how the system fits together.

Holds **only the connective tissue** no single unit doc can own:
- dependency direction between units
- cross-unit data / control flow
- shared resources (stores, queues, auth both sides touch)
- the contracts/boundaries between units

Constraints (same minimal-high-leverage / cut-test frame as the rest of the skill):
- **Does NOT re-describe each unit** — that is the unit's own `overview.md`. Link, don't
  restate. An architecture doc that summarizes each unit is the per-unit docs concatenated,
  and drifts the moment one changes.
- **Does NOT become a design-rationale essay.** Every line is a *current* relationship
  verifiable across the units, not aspirational architecture. (Rationale belongs in process
  docs like `plans/`, which carry no such verifiability contract.)
- **Earns its place only when units actually interact.** A repo of genuinely independent
  units needs no cross-unit picture; forcing one is the pyramid "fill-the-layer" trap the
  doc already warns against.
- **Canonical form:** a small dependency/flow sketch (ASCII or mermaid) plus a few lines of
  prose, kept honest the way `writing-docs` governs any example — verifiable against the
  actual wiring, or omitted.

## Concrete edits to `repo-shape.md`

1. Rewrite "The shape" code block to nest the agent set under `docs/reference/` and show the
   team's own `docs/` siblings as untouched.
2. Add a containment rule near the top of "Rules" (one self-contained subtree; never claim
   `docs/` root), with the Rule 1 clarification.
3. Add a short section defining `architecture.md` (decision 2).
4. Update the "router points to per-unit docs" wording to point into `docs/reference/`.
5. Add one failure mode: "architecture.md that restates the per-unit overviews → cut to just
   the relationships."

## Out of scope (for the containment + `architecture.md` work)

- Restructuring this repo's own `docs/` (it has no `reference/` tier — it is a marketplace,
  not a multi-unit app).
- The `architecture.md` / containment gaps do not exist for the single-unit case, so
  `SKILL.md` needed no change *for them*. (It was edited separately — see the addendum below
  — for an unrelated convention change.)

## Addendum (2026-06-20): deferred-note convention softened

Came up after the work above, while trimming this repo's own CLAUDE.md.

**Problem.** The skill mandated a standing `## Not yet documented` section as a hard rule
(`SKILL.md` "Always end with a deferred note" + a red flag; `repo-shape.md` Rule 7). In an
always-loaded agent file (CLAUDE.md/AGENTS.md) that section is bootstrap-time process residue
the agent re-reads every session, and the mandate meant an agent following the skill would
re-add it after it was removed.

**Decision.** Scope the deferred note to **bootstrap time**: it forces a conscious stop when
the doc set is created, and is a one-time decision record — not a section every maintained doc
must carry forever. Durable tracking of unbuilt work graduates to a planning/handoff doc, not a
standing section in the always-loaded file.

**Edits.**
- `SKILL.md` — retitled the section "End the bootstrap with a deferred note"; added a paragraph
  on the one-time/graduates-to-planning-doc framing; reworded the red flag as a bootstrap-time
  check ("don't lint established docs for a standing section").
- `repo-shape.md` — Rule 7 reworded to match.
- `CLAUDE.md` (this repo) — removed the section; its one fact (doc-sync-automation
  designed-not-built) already lives in `HANDOFF.md`.

Verified nothing else in the plugin (including `detecting-doc-drift`) enforces the section.
