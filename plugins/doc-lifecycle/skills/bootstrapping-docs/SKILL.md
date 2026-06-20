---
name: bootstrapping-docs
description: Use when a repo has no doc set yet (or a bare one) and you need to create the baseline from scratch — "document this project" / "add docs" / "set up documentation" — producing the smallest high-leverage doc set and deliberately stopping, instead of cataloguing everything. This is the whole-repo, what-to-create-and-when-to-stop skill; for writing or editing one individual doc, use writing-docs (this skill routes each doc's quality to it).
---

# Bootstrapping Docs

## Overview

**Goal: the smallest doc set that makes the next work session productive — not
comprehensive documentation.** A bootstrapped repo gets just enough that a new agent or
teammate stops rediscovering the same facts every session. Everything else is deferred.

Capable agents already find the build commands, gotchas, and architecture. The failure
this skill prevents is **completeness-chasing**: cataloguing every API route, helper
signature, convention, and directory into docs that are inferable from code and will drift.

**REQUIRED SUB-SKILL:** Use **writing-docs** for the quality of every doc you write here
(run-or-omit example output, marked+anchored rationale, no aspirational claims). This skill
governs *what to create and when to stop*; writing-docs governs *how each doc reads*.

## Process: explore, then write the minimum

1. **Explore** the repo: read the build/test orchestration (Makefile, package.json scripts,
   CI config), the entry points, and the env/config surface. Run the key commands if you can.
2. **Write the priority set below, in order**, applying **writing-docs** to each as you go
   (run-or-omit output, marked+anchored rationale, no aspirational claims). Stop when the
   high-leverage facts are captured.
3. **Write a deferred note** listing what you did NOT document and why.

## Priority order (create in this order; stop early if that's enough)

1. **CLAUDE.md / AGENTS.md — first, always.** Highest leverage for agent performance. It
   holds only what an agent can't cheaply infer (see checklist). Agent rendering — max
   signal-per-token, pointers over inline copies; the `writing-docs` skill carries this bar
   (dispatch the `llm-doc-writer` agent for a whole-doc job).
2. **README skeleton** — human front door: one-line what-and-why, setup, the run/test
   commands. A skeleton, not a manual.
3. **Operational stubs** — only if real operational knowledge surfaced during exploration;
   otherwise a one-line "runbooks: TODO" and move on.

**Larger repo (more than a handful of services/packages/subsystems)?** The 2-doc set is for
a single-unit repo. Once there are many units, the same minimal-high-leverage rule scales
*per unit* into a self-contained `docs/reference/` subtree (root `AGENTS.md` router → a
cross-unit `architecture.md`, a scoped doc per unit, and generated reference) — see
**repo-shape.md**. Do not build that structure for a small repo.

## The high-leverage checklist (what the agent file MUST capture)

Only things an agent burns tokens rediscovering:

- [ ] **Commands it can't guess** — build, test, run, lint — especially where they differ
  from defaults (e.g. `make test`, not `npm test`).
- [ ] **Ordering & setup gotchas** — steps that must happen first (migrations, codegen),
  and the symptom if skipped.
- [ ] **Required env / config** — what must be set, and what breaks without it.
- [ ] **Architecture as pointers** — the major components and where they live (`services/api`,
  `packages/shared`), NOT descriptions of them.
- [ ] **Runtime version / toolchain** — if non-obvious.

## STOP — do not document these (the completeness traps)

These are inferable from the repo and will drift. Cutting them is the whole point.

- ❌ API route catalogs (endpoints, status codes, request-field tables) — readable in the handler.
- ❌ Function/helper signatures — readable in the source.
- ❌ Convention lists a formatter/linter already enforces (quotes, semicolons, indentation).
- ❌ Directory trees that just mirror `ls`.
- ❌ Invented sections: contributing guides, changelogs, badges, API references nobody asked for.

Test each line: **would an agent make a mistake without it?** If the agent could get it by
reading one obvious file, leave it for them to read — link, don't transcribe.

## End the bootstrap with a deferred note

When you finish bootstrapping, state what you intentionally left undocumented, so scope is a
decision, not an omission:

```
## Not yet documented
- Per-endpoint API reference (read services/api/server.js)
- Operational runbooks (no incident procedures captured yet)
```

This is a **one-time bootstrap record**, not a section every doc must carry forever. Once the
doc set is established, durable tracking of unbuilt work belongs in a planning or handoff doc
— don't keep a standing `## Not yet documented` section in an always-loaded agent file
(CLAUDE.md/AGENTS.md), where it becomes maintained residue re-read every session.

## Red flags — STOP

- Writing a table of API routes / status codes → cut; link to the handler.
- Listing every helper's signature → cut; link to the module.
- A directory tree mirroring the filesystem → cut.
- Adding contributing/changelog/badges nobody asked for → cut.
- Aiming for "comprehensive" or "complete" → wrong target; aim for minimal-high-leverage.
- Finishing the bootstrap with no deferred note → you haven't decided scope, you've just
  stopped. (A bootstrap-time check — don't lint established docs for a standing section.)
