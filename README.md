<p align="center">
  <img src="assets/social-card.png" alt="doc-lifecycle — Reference docs as checkable claims." width="720">
</p>

# toolshed

A personal [Claude Code plugin marketplace](https://docs.claude.com/en/docs/claude-code/plugins). Today it ships one plugin — **`doc-lifecycle`**: reference docs as checkable claims.

---

# doc-lifecycle

<p align="center">
  <a href="LICENSE"><img src="https://img.shields.io/github/license/aj604/toolshed?color=3fb950" alt="License: MIT"></a>
  <img src="https://img.shields.io/badge/dynamic/json?url=https%3A%2F%2Fraw.githubusercontent.com%2Faj604%2Ftoolshed%2Fmain%2Fplugins%2Fdoc-lifecycle%2F.claude-plugin%2Fplugin.json&query=%24.version&label=version&color=3fb950" alt="version">
  <a href="https://docs.claude.com/en/docs/claude-code/plugins"><img src="https://img.shields.io/badge/Claude_Code-plugin-da7756" alt="Claude Code plugin"></a>
</p>

**Reference docs as checkable claims — so when the code moves, the drift surfaces as a record, not a silent surprise.**

A suite of skills covering the documentation lifecycle — **bootstrap → write → detect → fix** — that share one record format and one rule: *every line of a repo-tracking doc is a claim that must be true of the repo.*

## The problem, in two lines

A `CLAUDE.md` says `make reset` resets state and the worker "accepts schema 2, exits 5." Code moves; the doc doesn't. Now an agent runs a command that no longer exists and writes an error handler for the wrong exit code:

```diff
  what the doc claims          the code as of today
- make reset                   make clean              (target renamed)
- schema 2 → exits 5           schema 3 → exits 4      (worker bumped)
```

`detecting-doc-drift` flags each stale line and drafts the corrected claim; `fixing-doc-drift` lands those drafts surgically — because every line was a checkable claim, not prose.

## What's in it

| Component | Type | Use it when |
|-----------|------|-------------|
| `bootstrapping-docs` | skill | Pointing at an undocumented repo — produces the smallest high-leverage doc set, then deliberately stops. |
| `writing-docs` | skill | Writing or editing a repo-tracking doc (README, runbook, CLAUDE.md/AGENTS.md, reference), human- or agent-facing — every line a verifiable claim, rationale marked and anchored; carries the agent-density bar and routes heavy agent docs to the `llm-doc-writer` agent. |
| `detecting-doc-drift` | skill | Auditing docs against the code — extracts each claim, verifies it at the cheapest sufficient tier, emits a structured, parseable record. |
| `fixing-doc-drift` | skill | Applying a drift report to the docs — lands each STALE fix surgically, never deletes, never touches what the report didn't flag, stops on a large blast radius. |
| `llm-doc-writer` | agent | A dispatchable subagent that produces LLM-optimized documentation with maximum context efficiency. |

## Install

```
/plugin marketplace add aj604/toolshed
/plugin install doc-lifecycle@toolshed
```

## Using it

Once installed, point Claude Code at a repo and ask for what you want. Three things you'll do
most:

### Bootstrap docs for a repo that has none

```
/doc-lifecycle:bootstrapping-docs
```

Explores the repo and writes the smallest high-leverage doc set — a `CLAUDE.md`/`AGENTS.md`
first, then a README skeleton — then stops, instead of cataloguing everything that's already
readable in the code.

### Catch docs that drifted from the code

```
/doc-lifecycle:detecting-doc-drift CLAUDE.md
```

Extracts each claim in the doc, verifies it against the repo, and emits one structured record
per claim — with a drafted `fix` on every stale one:

```json
{
  "claim": "Reset state = `make reset`",
  "location": "CLAUDE.md:18",
  "kind": "command",
  "tier": 1,
  "verdict": "STALE",
  "evidence": "Makefile has `clean:`, no `reset` target",
  "fix": "Reset state = `make clean`"
}
```

### Apply the fixes

```
/doc-lifecycle:fixing-doc-drift
```

Takes that report and lands only the flagged fixes — here, `make reset` → `make clean` at
`CLAUDE.md:18` — and touches nothing the report didn't flag, so the diff maps one-to-one to the
evidence.

## The contract: a doc is a set of claims

This governs the docs whose job is to track the repo — README, runbooks, agent context, reference. (Tutorials, conceptual overviews, and design-rationale docs are narrative by design and out of scope; the claim bar would wrongly gut them.) For those repo-tracking docs, every line is either a **verifiable claim** — a command, path, symbol, behavior, or structure checkable against the repo *as it is now* — or a **rationale claim**, the "why," quarantined to a marked section and **anchored** to a `file:line` ref. Anything else — marketing prose, an aspirational "should," a restatement of the file tree — gets cut.

The bar is mechanical enough that tooling enforces its *shape* — every claim carries evidence, every verdict a valid enum — without leaning on a reviewer's patience. What tooling does **not** do is decide whether a claim is *true*: that's model judgment at the chosen verification tier, and a cheap static check confirms a path still resolves, not that it still means the same thing. The contract makes drift *checkable*; it doesn't make correctness *automatic*.

That one contract runs through the whole suite, which is what lets the pieces compose instead of fight:

```
writing-docs        mandates verifiable claims
detecting-doc-drift extracts and verifies those same claims, with evidence
fixing-doc-drift    lands the drafted fixes, one diff hunk per record
─── not yet built ───
doc-sync-automation runs detect→fix on every diff and opens a PR
```

The four skills above ship today. The automation layer on top — `doc-sync-automation`, which runs detect→fix unattended on every diff and opens a docs-update PR — is the suite's next addition; it's wiring on top of the contract, which already lives in `detecting-doc-drift` and `fixing-doc-drift`.

## Try it locally

```
/plugin marketplace add /path/to/toolshed
/plugin install doc-lifecycle@toolshed
```

## How it was built

Every skill was written test-first — RED (baseline agents fail) → GREEN (skill fixes it) → REFACTOR (pressure-test for loopholes). Rules target failures that actually showed up in baseline runs, not best-practice folklore. Test records live under [`tests/`](tests/).

## Repo layout

```
.claude-plugin/marketplace.json   # the toolshed marketplace
plugins/doc-lifecycle/            # the published plugin
  .claude-plugin/plugin.json
  skills/                         # 4 skills
  agents/                         # llm-doc-writer
assets/                           # social-card.png (README hero + GitHub social preview)
docs/                             # plans: design docs + handoff (not part of the installed plugin)
tests/                            # RED/GREEN records + fixtures (not part of the installed plugin)
```

## License

MIT — see [`LICENSE`](LICENSE).
