# Shaping docs for a larger repo

Use this once a repo crosses **more than a handful of independently-comprehensible units**
(services, shippable packages, major subsystems). Below that, the SKILL.md priority set
(one CLAUDE.md + README) is the right answer — do not build the structure here for a small
repo; that is just bloat with folders.

## The scaling principle

**The doc set scales with the number of units, not lines of code.** A "unit" is a part of
the repo someone works in without needing the whole. Minimal-high-leverage is applied
*per unit*, not as a global cap of two files:

- small repo (1 unit) → ~2 docs (the SKILL.md set).
- big repo (N units) → a grouped tree: one always-loaded router + a cross-unit overview +
  a scoped doc per unit that has non-inferable knowledge.

Same cut-test governs every line at every size. The doc *count* grows with real units; doc
*content* never grows into the inferable catalogs SKILL.md bans.

## The shape

```
AGENTS.md            ← canonical high-level agent doc (always-loaded): cross-cutting
                       commands/gotchas, architecture pointers, + the when-to-read router
CLAUDE.md            ← one-line shim: "Agent context lives in AGENTS.md." Nothing else.
docs/
  reference/             ← the entire agent doc set, contained in one subtree
    architecture.md        ← cross-unit picture: how the units relate (start here)
    auth/overview.md       ← scoped to this unit; only its non-inferable commands/gotchas
    payments/overview.md
    generated/             ← API/schema/CLI reference — auto-generated, never hand-written
  plans/  guides/ …    ← whatever else the team keeps in docs/ — untouched by the agent set
```

The two root files stay at the root because tools auto-load them. Everything read on demand
lives under `docs/reference/` — one self-contained subtree, not scattered across `docs/`.

## The cross-unit overview (`docs/reference/architecture.md`)

Each per-unit `overview.md` is scoped to its own unit, so nothing in that set owns the
**relationships between units** — the picture a router can't give because every unit doc only
sees itself. `architecture.md` is that picture, read on demand, with the router pointing to it
as the start-here for how the system fits together.

It holds **only the connective tissue** no single unit doc can own:

- dependency direction between units (who calls whom)
- cross-unit data / control flow
- shared resources both sides touch (stores, queues, auth)
- the contracts / boundaries between units

> auth issues tokens that payments validates; both read the shared session store.

Same cut-test as everywhere else. It must **not**:

- **re-describe each unit** — that's the unit's own `overview.md`; link, don't restate. An
  architecture doc that summarizes each unit is just the per-unit docs concatenated, and
  drifts the moment one changes.
- **become a design-rationale essay** — every line is a *current* relationship verifiable
  across the units, not aspirational architecture. Rationale belongs in process docs (`plans/`),
  which carry no such verifiability contract.

It **earns its place only when units actually interact.** A repo of genuinely independent units
needs no cross-unit picture — forcing one is the completeness-chasing the pyramid section
below warns against. Canonical
form: a small dependency/flow sketch (ASCII or mermaid) plus a few lines of prose, kept honest
the way `writing-docs` governs any example — verifiable against the actual wiring, or omitted.

## Rules

1. **One self-contained reference subtree — never colonize `docs/`.** The whole agent doc set
   lives under `docs/reference/`; the rest of `docs/` stays the team's. `docs/` is a shared
   convention many repos already use their own way, so the agent set borrows one subdir; it
   doesn't claim the folder.
2. **Group by domain, not doc-type.** `docs/reference/auth/`, not `docs/reference/guides/`.
   Domain names are grep-discoverable and match how people ask "where's auth." (This governs
   *inside* `docs/reference/`; the reference-vs-everything split in Rule 1 is a higher-order
   containment boundary — "tracks code" vs not — not the doc-type flavoring this rule bans.)
3. **One always-loaded doc, at the repo root.** Everything else is read on demand. Keep the
   always-on file lean — a bloated always-loaded doc makes the agent ignore your real
   instructions.
4. **Canonical agent doc = `AGENTS.md` (root), not an invented name.** Cross-tool standard,
   neutral, not coupled to one tool's auto-load. `CLAUDE.md` is a one-line pointer to it.
   (Claude-Code-only repo: skip the shim, let CLAUDE.md be the high-level doc directly.)
   Do **not** name per-unit docs `CLAUDE.md` — nested `CLAUDE.md` lazy-loads on subtree
   access, which couples your layout to a tool feature humans and other agents don't get.
5. **Per-unit docs use neutral names** (`overview.md`, or a unit `README.md` if it also
   serves humans), pointed to by the router, opened when relevant.
6. **Reference layer is generated, not transcribed.** Endpoints, config keys, schemas, CLI
   help → auto-generate into `docs/reference/generated/`. Hand-written reference is the
   route-catalog bloat SKILL.md forbids; generated reference stays in sync because it has one
   source.
7. **End the bootstrap with a deferred note** — scope is a decision, not an omission. It's a
   one-time bootstrap record, not a standing section the always-loaded root doc must carry
   forever; durable tracking of unbuilt work graduates to a planning/handoff doc.

## When a routing index earns its place

`ls` / `glob` / `grep` already give you filenames and content, always current, zero
maintenance. A hand-written index that **lists files** is a cached `ls` that drifts — the
"directory tree mirroring `ls`" anti-pattern, now with an index-by-omission no one flags.

An index is worth writing only when it carries what `ls` can't: **when-to-read intent.**
Take the root router's map of the `docs/reference/` tree:

❌ a bare list — a cached `ls` that drifts, cut it:

```
## Map
- architecture.md
- auth/overview.md
- payments/overview.md
```

✅ the same map carrying when-to-read intent — keep it:

```
## Map
- architecture.md      — start here: how auth, payments, and billing fit together
- auth/overview.md     — token issuing/rotation; start here for 401s
- payments/overview.md — charge lifecycle; webhook retries and idempotency
```

Apply the cut-test per line: would removing it make the reader open the wrong doc? Bare
filename → no, cut. When-to-read line → yes, keep. So: the **root router** is the one index
most repos need; add a per-directory index only when a unit has enough docs that "which
one?" costs more than the index costs to maintain — and only as when-to-read lines.

## The pyramid is a smell-test, not a quota

You may see "1:10:100:1000 docs per layer" guidance. Use it **only** to spot a *missing
layer* (a router pointing straight at deep detail with no unit-level overview) or a
suspiciously thin tier — never as a count to fill toward. A target ratio is a license to
chase completeness, which is the exact failure this skill exists to prevent. Units drive the
count; the ratio only flags gaps.

## Failure modes (watch for)

- **Per-unit `CLAUDE.md` files.** Couples layout to lazy subtree loading; rename to
  `overview.md` and route to it from the root.
- **The agent set scattered across `docs/` root.** `docs/auth/`, `docs/generated/` sprawled
  beside the team's own docs → contain them under one `docs/reference/` subtree.
- **`architecture.md` that restates the per-unit overviews.** Re-describing each unit drifts
  and duplicates → cut to just the relationships between units.
- **An index that restates `ls`.** Filenames with no when-to-read intent → cut; it only adds
  a surface that drifts.
- **Hand-written endpoint/config reference.** Generate it, or link to the handler/schema —
  never transcribe.
- **Treating the pyramid ratio as a target.** Filling toward "~1000 reference docs" is
  completeness-chasing in a costume.
