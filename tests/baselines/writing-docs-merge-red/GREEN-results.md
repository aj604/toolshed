# GREEN — merged `writing-docs` (one door)

**Date:** 2026-06-20
**Skill under test:** `plugins/doc-lifecycle/skills/writing-docs/` after the merge — description
absorbs the `writing-for-llms` triggers; "One bar, every reader — then route" carries density
inline and dispatches `llm-doc-writer` for heavy agent-facing jobs; `writing-for-llms` retired.

## Execution test (same bloated agent-facing doc as RED)

| Run | Model | Output | Result |
|-----|-------|--------|--------|
| GREEN-1 | Opus-class | `GREEN-opus-output.md` | **PASS** both RED axes |

Against RED Finding 1 (specialist never reached):
- **Dispatched `llm-doc-writer`**, quoting the router line verbatim as the driver. The baselines
  (A, B) never dispatched; the merged door makes dispatch the recognized path for a whole-doc
  agent-facing job.

Against RED Finding 2 (inferable bloat / under-applied density):
- **Withheld** the cheaply-inferable facts the RED baseline *added*: default `PORT 8080`, default
  `WORKER_INTERVAL_MS 5000`, `lint.js` dir-walk, helper signatures — explicitly citing Rule 4 /
  "density mandatory / pointers over inline copies." 1197 → 310 words (~74%), every line
  `file:line`-anchored. Also corrected the source's `make dev` `&` nuance (`Makefile:14-18`).

## Routing test (single-door skill list)

| Run | What it saw | Result |
|-----|-------------|--------|
| GREEN-2 | merged `writing-docs` description, no `writing-for-llms` in list | **PASS, with caveat** |

- Against the single-door list: *"isn't really ambiguous… something does NOT feel missing… no pull
  to a second skill."* The Run C dead-end ("first matching door ends the search, but the boundary
  is blurry") is gone — there is no competing door to be blurry against.
- **Load-bearing caveat (the agent surfaced it):** in its *actual* environment `writing-for-llms`
  still exists, so it "can see writing-for-llms sitting right there" and the pull returns. **The
  fix is only real once `writing-for-llms` is retired in the repo AND removed from the deployed
  `~/.claude/skills`.** An unrecommended-but-present second door still competes.

## Conclusion

The merged door fixes both RED axes (dispatch reached; inferable bloat cut) and removes the
routing ambiguity — **conditional on actually retiring `writing-for-llms`**. That retirement +
the dangling-reference cleanup + deploy are the REFACTOR/deploy step, not optional polish: GREEN-2
shows the second door re-creates the RED if left standing.
