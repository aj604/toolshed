---
name: writing-docs
description: Use when writing or editing ANY documentation — README, runbook, CLAUDE.md/AGENTS.md, guides, or agent-facing context packs — including converting human or marketing docs into dense agent-facing form, or when tempted to add example output, install steps, or "why" prose. Covers both human and AI/agent readers (token bloat, context rot); every line must be a claim verifiable against the repo, with rationale marked and anchored so docs stay drift-checkable.
---

# Writing Docs

## Overview

**A doc is a set of claims that must be true of the repo.** This is the spine: when any
guideline conflicts with verifiability, verifiability wins. A smaller all-true doc beats a
complete one with unverifiable parts.

Every line is one of two kinds of claim:

- **Verifiable claim** — commands, paths, symbols, behavior, output, structure. Must be
  mechanically checkable against the repo *as it is now*.
- **Rationale claim** — the "why", tradeoffs, rejected alternatives. Allowed, but only in
  a marked section and **anchored** to a `file:line`, commit, or date.

If a line is neither, cut it.

## The rules (these address what agents get wrong)

Strong agents already read `package.json` and get commands and flags right. They fail on
the subtler things below. Spend your discipline here.

### 1. Example output is a claim — run it or omit it

Never invent illustrative numbers, sample output, or "looks-right" results. Output you
didn't produce is a fabricated claim, even when it's "just an example."

- Run the command, paste the **real** output.
- If output is environment-dependent (byte sizes, timestamps, hashes), say so instead of
  pinning a fragile exact value.
- Can't run it? Don't show output.

### 2. Rationale must be marked and anchored

Do not weave the "why" into prose as timeless fact. Put it in a marked section and anchor
it: `> **Why (as of `bin/cli.js:34`):** reads the whole buffer because gzip ratio…`.
Unanchored rationale can't be audited for relevance and will rot silently.

### 3. No aspirational claims

Document the repo as it is, not as you assume it will be. No `npm install <pkg>` for an
unpublished package, no "supports X" for unbuilt features. If a claim isn't true yet, omit
it or mark it explicitly as not-yet-true.

### 4. Cut what the reader can already infer

Apply the test: **would removing this line cause the reader to make a mistake?** If not,
cut it. Don't restate what the code, types, or git history plainly show. This bites hardest
in agent docs (see agent-context.md).

### 5. Document-at-all counter-test

Before writing a doc, ask: does the code, a type signature, or git history already say
this? If yes, link to it; don't duplicate it into a doc that will drift.

## Where a doc lives (reader + moment of need)

| Reader, at this moment | Artifact | Guide |
|------------------------|----------|-------|
| Newcomer evaluating / setting up | README | readme.md |
| On-call mid-incident, under pressure | runbook | runbooks.md |
| AI agent starting a session in the repo | CLAUDE.md / AGENTS.md | agent-context.md |

## One bar, every reader — then route

The contract above governs **every** doc; verifiability never bends. Audience and job size
decide only *how dense* and *who writes it* — never *whether it's true*. This is the one door
for doc writing: don't go looking for a second skill. Two questions, answered once:

**1. Who reads it?**

- **Human** (README, runbook, guide): orient first, skimmable, some warmth OK.
- **Agent** (CLAUDE.md/AGENTS.md, context pack): **density is mandatory, not optional.**
  Maximum signal-per-token, pointers over inline copies, no narrative. The reader can read the
  repo on demand — spend tokens only on what it *can't* reconstruct. This is Rule 4 at full
  strength: an agent doc that "reads fine" but restates inferable facts has **failed**, even if
  every line is true.

**2. How big is the job?**

- **A line or a section, and you're already in the repo** → write it inline, applying the bar.
- **A whole doc, or it needs real repo exploration to verify** → dispatch, so that exploration
  stays out of your context:
  - **human-facing** → a generalist subagent carrying this skill.
  - **agent-facing** → the **`llm-doc-writer` agent** — it owns the densify+verify method and
    runs in its own context. Pass it: *what to write from* (source path, raw content, or topic +
    findings), *the repo path* (puts it in verify mode — anchors every claim to `file:line`,
    runs safe commands), and *the output path*. A one-line agent-doc tweak isn't worth a
    dispatch — apply the density rule inline.

**Do not stop at the first thing that feels sufficient.** If the reader is an agent, the density
pass — inline or via `llm-doc-writer` — is part of *this* job, not a separate skill you may skip.

## Red flags — STOP

- About to type example output you didn't run → run it or delete it.
- Writing "because…" / "the reason is…" in body prose → move to a marked, anchored section.
- `npm install <thing>`, "just run X" you haven't confirmed exists → verify or cut.
- A sentence the reader could get from reading one obvious file → cut it.
- Reader is an agent and you wrote it like a human doc (narrative, restated-inferable facts) →
  the density pass is owed; it is not optional.
- Agent doc that's a whole-doc or needs verification, and you didn't dispatch `llm-doc-writer`
  → you skipped the specialist that enforces density+anchoring in its own context.
- "This skill covers it, I'll just start" on an agent doc → you still owe the density half.

## Reference files

- **readme.md** — README structure, coverage checklist, one verified example, failure modes.
- **runbooks.md** — runbook structure for 3am usability; copy-pasteable steps, real output.
- **agent-context.md** — CLAUDE.md/AGENTS.md; the cut-test, pointers-over-inline, when to
  dispatch the `llm-doc-writer` agent.
