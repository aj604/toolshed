# toolshed

A personal [Claude Code plugin marketplace](https://docs.claude.com/en/docs/claude-code/plugins). Its first plugin is **`doc-lifecycle`**.

## Install

```
/plugin marketplace add averyjones/toolshed
/plugin install doc-lifecycle@toolshed
```

> Replace `averyjones/toolshed` with this repo's actual `owner/repo` slug (or a full git URL) once it's pushed.

---

# doc-lifecycle

**Docs an AI agent can trust — and a machine can keep honest.**

A suite of composable skills covering the documentation lifecycle — **bootstrap → write → detect drift** — unified by one rule strict enough to enforce mechanically: *every line of a doc is a claim that must be true of the repo.*

## What's in it

| Component | Type | Use it when |
|-----------|------|-------------|
| `bootstrapping-docs` | skill | Pointing at an undocumented repo — produces the smallest high-leverage doc set, then deliberately stops. |
| `writing-docs` | skill | Writing or editing any doc — enforces that every line is a verifiable claim, with rationale marked and anchored. |
| `detecting-doc-drift` | skill | Auditing docs against the code — extracts each claim, verifies it at the cheapest sufficient tier, emits a structured, parseable record. |
| `writing-for-llms` | skill | Rewriting docs for LLM consumption — signal-per-token, pointers over inline copies, scannable structure. |
| `llm-doc-writer` | agent | A dispatchable subagent that produces LLM-optimized documentation with maximum context efficiency. |

## The contract: a doc is a set of claims

Every line is exactly one of two kinds:

- **Verifiable claim** — a command, path, symbol, behavior, output, or structure checkable against the repo *as it is now* (`make test`, `config lives in src/config.ts`, `retries 3 times with backoff`).
- **Rationale claim** — the "why," allowed but quarantined to a marked section and **anchored** to a source ref (`> **Why (as of bin/cli.js:34):** reads the whole buffer because…`).

If a line is neither — marketing prose, an aspirational "should," a restatement of the file tree — it gets cut. Because the bar is mechanical, tooling can enforce it instead of a reviewer's patience.

## Why one contract, three enforcement points

```
writing-docs        mandates verifiable claims
detecting-doc-drift extracts and verifies those same claims, with evidence
doc-sync-automation re-verifies them on every diff and opens a PR   (next addition)
```

`writing-docs` makes claims a machine can check; `detecting-doc-drift` checks them and emits a record; automation acts on the record. Nothing in the chain has to *guess* whether a doc is honest.

The fourth lifecycle step — `doc-sync-automation`, which turns drift records into an automatic docs-update PR — is the suite's next addition; the drift contract it builds on already lives in `detecting-doc-drift`.

For the full rationale and a worked example, see [`docs/PITCH.md`](docs/PITCH.md).

## Try it locally (before publishing)

```
/plugin marketplace add /Users/averyjones/Repos/skills/toolshed
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
docs/                             # design, pitch, plans (not published)
tests/                            # RED/GREEN records + fixtures (not published)
```
