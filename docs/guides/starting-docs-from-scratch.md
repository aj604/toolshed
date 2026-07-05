# Starting docs from scratch with `bootstrapping-docs` and `growing-docs`

> As of 2026-07-05 (doc-lifecycle 0.6.2 @ e5201b8; `plugins/doc-lifecycle/skills/bootstrapping-docs/SKILL.md`, `growing-docs/SKILL.md`)

**You should already have:** the plugin installed (`/plugin install doc-lifecycle@toolshed`)
and read [the principles](principles.md). This is the entry point for a repo with no doc
set yet.

## Ask for it

> document this project

That triggers `bootstrapping-docs`. No flags, no config — the skills key off ordinary
requests.

## What you get — and why it's small

The skill explores the repo (build/test orchestration, entry points, env surface), then
writes a deliberately minimal set, in priority order:

1. **CLAUDE.md / AGENTS.md first** — the agent context file, holding only what an agent
   burns tokens rediscovering: non-default commands, ordering gotchas and their symptoms,
   required env, architecture as pointers. Highest leverage, written densest.
2. **A README skeleton** — the human front door: what-and-why, setup, run/test commands.
   A skeleton, not a manual.
3. **Operational stubs** — only if real operational knowledge surfaced during
   exploration; otherwise deferred.

Then it **stops**. Deliberately. It will not produce API route catalogs, helper-signature
tables, directory trees, or a contributing guide — the skill's own STOP list forbids
them, because they're inferable from the code and will drift. The target is "the next
work session stops rediscovering the same facts," not "comprehensive."

## The stop is recorded, not silent

The bootstrap ends by writing **`docs/doc-scope.md`**: a list of what was deliberately
*not* documented, each item with the demand signal that would promote it
(`- runbook: … — promote when: <signal>`). Scope becomes a decision that survives the
session instead of a chat-only note.

## Growing later — on demand, never on a calendar

When the docs stop being enough, `growing-docs` takes over, and its trigger is a
**demand signal**, not a milestone:

- **The second-rediscovery rule:** the first time a fact is derived the hard way,
  answering is fine. The second time, it has earned a doc — written where the reader
  would have looked first.
- One signal → **one smallest artifact**: a re-explained fact becomes a gotcha line or
  README section; an incident with no runbook becomes a runbook; a recurring "why is it
  like this?" becomes a marked, anchored rationale section or an ADR.
- A `docs/doc-scope.md` item whose `promote when:` condition fires is the same thing in
  recorded form — say "should we document X?" and the skill reads the scope record
  alongside the live signal.

The STOP list still binds during growth: a demand signal is not a license to catalogue.

## Next

Once docs exist they start aging. When they've picked up weight, run
[a bloat audit](auditing-doc-bloat.md); once that loop feels routine,
[schedule it](scheduling-doc-sync.md).
