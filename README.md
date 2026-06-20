# toolshed

A personal [Claude Code plugin marketplace](https://docs.claude.com/en/docs/claude-code/plugins). Its first plugin is **`doc-lifecycle`**.

## Install

```
/plugin marketplace add aj604/toolshed
/plugin install doc-lifecycle@toolshed
```

---

# doc-lifecycle

**Docs an AI agent can trust — and a machine can keep honest.**

A suite of composable skills covering the documentation lifecycle — **bootstrap → write → detect drift** — unified by one rule strict enough to enforce mechanically: *every line of a doc is a claim that must be true of the repo.*

## The problem, in two lines

A `CLAUDE.md` says `make reset` resets state and the worker "accepts schema 2, exits 5." Code moves; the doc doesn't. Now an agent runs a command that no longer exists and writes an error handler for the wrong exit code:

```diff
  what the doc claims          the code as of today
- make reset                   make clean              (target renamed)
- schema 2 → exits 5           schema 3 → exits 4      (worker bumped)
```

`detecting-doc-drift` flags each stale line and emits the fix — because every line was a checkable claim, not prose. [See the full worked example →](docs/PITCH.md)

## What's in it

| Component | Type | Use it when |
|-----------|------|-------------|
| `bootstrapping-docs` | skill | Pointing at an undocumented repo — produces the smallest high-leverage doc set, then deliberately stops. |
| `writing-docs` | skill | Writing or editing any doc, human- or agent-facing — every line a verifiable claim, rationale marked and anchored; carries the agent-density bar and routes heavy agent docs to the `llm-doc-writer` agent. |
| `detecting-doc-drift` | skill | Auditing docs against the code — extracts each claim, verifies it at the cheapest sufficient tier, emits a structured, parseable record. |
| `fixing-doc-drift` | skill | Applying a drift report to the docs — lands each STALE fix surgically, never deletes, never touches what the report didn't flag, stops on a large blast radius. |
| `llm-doc-writer` | agent | A dispatchable subagent that produces LLM-optimized documentation with maximum context efficiency. |

## The contract: a doc is a set of claims

Every line is either a **verifiable claim** — a command, path, symbol, behavior, or structure checkable against the repo *as it is now* — or a **rationale claim**, the "why," quarantined to a marked section and **anchored** to a `file:line` ref. Anything else — marketing prose, an aspirational "should," a restatement of the file tree — gets cut. Because the bar is mechanical, tooling enforces it instead of a reviewer's patience.

That one contract runs through the whole suite, which is what lets the pieces compose instead of fight:

```
writing-docs        mandates verifiable claims
detecting-doc-drift extracts and verifies those same claims, with evidence
doc-sync-automation re-verifies them on every diff and opens a PR   (designed, next addition)
```

The fourth lifecycle step — `doc-sync-automation`, which turns drift records into an automatic docs-update PR — is the suite's next addition; the drift contract it builds on already lives in `detecting-doc-drift`. [Full rationale and the per-skill breakdown →](docs/PITCH.md)

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
docs/                             # design, pitch, plans (not published)
tests/                            # RED/GREEN records + fixtures (not published)
```

## License

MIT — see [`LICENSE`](LICENSE).
