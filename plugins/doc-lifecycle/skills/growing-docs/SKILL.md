---
name: growing-docs
description: 'Use when a repo already has baseline docs but a demand signal says they are no longer enough — the same question answered twice, a fact re-derived the hard way across sessions, an incident with no runbook, onboarding pain, a recurring "why is it like this?", someone asking "should we document X?", or a docs/doc-scope.md item whose promotion signal has fired. The demand-driven counterpart to bootstrapping-docs, which creates the minimum for a repo with no docs.'
---

# Growing Docs

## Overview

**A demand signal — not a sense of completeness — is what earns a new doc.** bootstrapping-docs
creates the smallest high-leverage doc set and deliberately stops; this skill is the other half
of that bargain. When reality asks for more — the same fact re-derived, an incident with no
runbook — the doc set grows by exactly the artifact that absorbs the signal, and no further.

## Route first: gap or drift?

| What you found | Owner |
|----------------|-------|
| An existing doc line is now **false** | detecting-doc-drift → fixing-doc-drift |
| The fact is simply **absent** — no doc line contradicts reality | **this skill** |

Drift tooling audits claims that exist; a pure gap has nothing to flag. Do not wait for a
drift report to legitimize growth — it never will.

## The second-rediscovery rule

The first time a fact is asked for or derived the hard way, answering is fine. **The second
time, it has earned a doc — write it where the reader would have looked first** (the doc they
opened, the section they scanned, the file they read). This is the positive twin of
writing-docs Rule 5: "cheaply inferable" is an empirical claim, and a second hard derivation
falsifies it.

Name the signal before writing ("second teammate this week hit exit 3", "third session
re-deriving the migrate order"). If you cannot name one, you are completeness-chasing — stop.

## Signal → smallest artifact

One signal → one smallest artifact. bootstrapping-docs' STOP list (route catalogs, signature
lists, directory trees) still binds — a demand signal is not a license to catalogue.

| Signal | Smallest artifact that absorbs it |
|--------|-----------------------------------|
| Fact re-explained / re-derived | CLAUDE.md gotcha, README section, or reference entry — whichever the reader would consult first (always-loaded placement must clear writing-docs' router rule) |
| Incident with no runbook | runbook (writing-docs' runbooks.md) |
| Onboarding pain | deepen README setup — or a narrative walkthrough (template below) |
| Recurring "why is it like this?" | marked+anchored rationale section — or an ADR (template below) |
| Unit became load-bearing / repo grew multi-unit | `docs/reference/` per bootstrapping-docs' repo-shape.md |

## The scope record: `docs/doc-scope.md` (this skill owns the format)

- **On entry:** if `docs/doc-scope.md` exists, read it alongside the live signal — the item
  may already carry a promotion condition that just fired.
- **On exit:** update it — create it if absent. Log what you wrote in Done with the signal
  that fired (moving the item from Deferred if it was listed there); add any new deliberate
  deferrals, each with a `promote when:` signal.

```markdown
# Doc scope record
<!-- format: doc-lifecycle growing-docs -->

## Deferred
- <artifact>: <what> — promote when: <signal>

## Done
- <date> <artifact> ← <signal that fired>
```

Read on demand; never a standing section in an always-loaded agent file (CLAUDE.md/AGENTS.md)
— a pointer line is fine.

## Quality routing

- **Repo-tracking doc** (README, runbook, CLAUDE.md/AGENTS.md, reference) → **writing-docs**,
  the one door — exactly as bootstrapping-docs routes.
- **Narrative doc** (walkthrough, tutorial, ADR) → writing-docs scopes these out by design;
  the template below is carried here and is REQUIRED.

### Where narrative docs live

A narrative doc is a **durable** doc — it tracks the current repo, and must never
be mistaken for a retire-on-landing planning artifact. Its home:

- Repo with a `docs/reference/` tree: **inside it**, domain-grouped like everything
  else (a unit's walkthrough beside its `overview.md`; cross-unit narrative beside
  `architecture.md`). One containment subtree holds the whole agent doc set,
  claim-style and narrative alike.
- Repo without one: under `docs/` beside the team's docs; it moves into
  `docs/reference/` if that tree later exists.
- **Never in `docs/plans/`** — that is where planning artifacts go to be distilled
  once their implementation lands; a narrative doc placed there will read as one.

### Narrative doc template (REQUIRED)

1. **First line under the title, always:**
   `> As of <YYYY-MM-DD> (<commit or file:line anchors current at writing>)`
   — the staleness anchor readers can check against; a hook for future drift tooling
   (today's drift skills audit repo-tracking claims, not narrative docs). This line
   is also the doc's **durable-narrative marker**: bloat tooling classifies an
   anchored doc as narrative — never as a planning artifact to distill — wherever
   it sits.
2. **Every command, path, symbol, and output inside the narrative is true of the repo now
   and was actually run.** Narrative structure is exempt from the claim bar; fabrication
   is not.
3. **Still the smallest doc that absorbs the signal.**

## Rationalizations

| Thought | Reality |
|---------|---------|
| "I'll just answer in chat again" | The second answer is the signal. Write it where the reader would have looked first. |
| "Adding this violates the cut test — it's inferable" | A second hard derivation just proved it isn't cheap. That is the falsification writing-docs Rule 5 invites. |
| "The drift report didn't flag it, so there's nothing to fix" | Drift audits existing claims; gaps are this skill's job. |
| "The walkthrough isn't governed by writing-docs, so no rules apply" | The narrative template above applies — anchor line first, every embedded claim true and run. |

## Red flags — STOP

- Answering the same question a second time and moving on → it has earned a doc; write it.
- Growing docs with no nameable signal (a milestone, a release, "while I'm here") → wrong
  trigger; demand grows docs, calendars don't.
- One signal producing a catalogue (routes, signatures, trees) → one smallest artifact;
  bootstrapping-docs' STOP list still binds.
- A walkthrough/tutorial/ADR without the `> As of …` first line → the anchor is REQUIRED.
- Finishing without updating `docs/doc-scope.md` (creating it if absent) → the scope
  decision evaporates with the session.
- Pasting doc-scope.md contents into CLAUDE.md/AGENTS.md → read on demand; a pointer line
  at most.
