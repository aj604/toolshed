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
- big repo (N units) → a grouped tree: one always-loaded router + a scoped doc per unit
  that has non-inferable knowledge.

Same cut-test governs every line at every size. The doc *count* grows with real units; doc
*content* never grows into the inferable catalogs SKILL.md bans.

## The shape

```
AGENTS.md            ← canonical high-level agent doc (always-loaded): cross-cutting
                       commands/gotchas, architecture pointers, + the when-to-read router
CLAUDE.md            ← one-line shim: "Agent context lives in AGENTS.md." Nothing else.
docs/
  auth/overview.md       ← scoped to this unit; only its non-inferable commands/gotchas
  payments/overview.md
  generated/             ← API/schema/CLI reference — auto-generated, never hand-written
```

## Rules

1. **Group by domain, not doc-type.** `docs/auth/`, not `docs/guides/`. Domain names are
   grep-discoverable and match how people ask "where's auth."
2. **One always-loaded doc, at the repo root.** Everything else is read on demand. Keep the
   always-on file lean — a bloated always-loaded doc makes the agent ignore your real
   instructions.
3. **Canonical agent doc = `AGENTS.md` (root), not an invented name.** Cross-tool standard,
   neutral, not coupled to one tool's auto-load. `CLAUDE.md` is a one-line pointer to it.
   (Claude-Code-only repo: skip the shim, let CLAUDE.md be the high-level doc directly.)
   Do **not** name per-unit docs `CLAUDE.md` — nested `CLAUDE.md` lazy-loads on subtree
   access, which couples your layout to a tool feature humans and other agents don't get.
4. **Per-unit docs use neutral names** (`overview.md`, or a unit `README.md` if it also
   serves humans), pointed to by the router, opened when relevant.
5. **Reference layer is generated, not transcribed.** Endpoints, config keys, schemas, CLI
   help → auto-generate into `docs/generated/`. Hand-written reference is the route-catalog
   bloat SKILL.md forbids; generated reference stays in sync because it has one source.
6. **End with `## Not yet documented`** in the root doc — scope is still a decision.

## When a routing index earns its place

`ls` / `glob` / `grep` already give you filenames and content, always current, zero
maintenance. A hand-written index that **lists files** is a cached `ls` that drifts — the
"directory tree mirroring `ls`" anti-pattern, now with an index-by-omission no one flags.

An index is worth writing only when it carries what `ls` can't: **when-to-read intent.**

```
❌ ls already shows this — cut it:    ✅ ls can't show this — keep it:
- auth/oauth2.md                      - oauth2.md — read when tokens expire early
- auth/jwt.md                         - jwt.md    — token signing/rotation; start here for 401s
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
- **An index that restates `ls`.** Filenames with no when-to-read intent → cut; it only adds
  a surface that drifts.
- **Hand-written endpoint/config reference.** Generate it, or link to the handler/schema —
  never transcribe.
- **Treating the pyramid ratio as a target.** Filling toward "~1000 reference docs" is
  completeness-chasing in a costume.
