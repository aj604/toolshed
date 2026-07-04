---
name: bootstrapping-docs
description: 'Use when a repo has no doc set yet (or a bare one) and you need to create the baseline from scratch — "document this project" / "add docs" / "set up documentation" — producing the smallest high-leverage doc set and deliberately stopping, instead of cataloguing everything. This is the whole-repo, what-to-create-and-when-to-stop skill; for writing or editing one individual doc, use writing-docs (this skill routes each doc''s quality to it). Ends by writing the docs/doc-scope.md scope record, handing growth to growing-docs.'
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
3. **Write `docs/doc-scope.md`** (format owned by **growing-docs**) listing what you
   deliberately did NOT document, each with the demand signal that would promote it.

## Priority order (create in this order; stop early if that's enough)

1. **CLAUDE.md / AGENTS.md — first, always.** Highest leverage for agent performance. It
   holds only what an agent can't cheaply infer (see checklist). Agent rendering — max
   signal-per-token, pointers over inline copies; the `writing-docs` skill carries this bar
   (dispatch the `llm-doc-writer` agent for a whole-doc job).
2. **README skeleton** — human front door: one-line what-and-why, setup, the run/test
   commands. A skeleton, not a manual.
3. **Operational stubs** — only if real operational knowledge surfaced during exploration;
   otherwise defer it in the scope record (`- runbook: … — promote when: <signal>`) and move on.

Larger repo (many independently-comprehensible units)? See **repo-shape.md** — it scales this same minimal-high-leverage rule per unit.

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

## End the bootstrap with a scope record

When you finish bootstrapping, write `docs/doc-scope.md` — format owned by **growing-docs**;
follow it — so scope is a decision that survives the session, not a chat-only note. List what
you intentionally left undocumented, each item with the demand signal that would promote it.
Deferral is *deferred until a signal*, not permanent; when a signal fires, **growing-docs**
owns the promotion.

The record is a **file**, read on demand — don't keep a standing `## Not yet documented`
section in an always-loaded agent file (CLAUDE.md/AGENTS.md), where it becomes maintained
residue re-read every session. A pointer line to `docs/doc-scope.md` is fine.

## Red flags — STOP

- Writing a table of API routes / status codes → cut; link to the handler.
- Listing every helper's signature → cut; link to the module.
- A directory tree mirroring the filesystem → cut.
- Adding contributing/changelog/badges nobody asked for → cut.
- Aiming for "comprehensive" or "complete" → wrong target; aim for minimal-high-leverage.
- Finishing the bootstrap with no scope record (`docs/doc-scope.md`) → you haven't decided
  scope, you've just stopped — and the decision dies with the session. (A bootstrap-time
  check — don't lint established docs for a standing section.)
