# plan-swarm — answer key

> **Superseded, retained as a historical record.** This key grades against the legacy
> `detecting-doc-bloat` contract v2 (`POLICY` verdict, `location`, `files`, `payload`) that
> the 2026-07-06 rearchitecture shipped. Both detecting skills have since migrated to the
> engine's verdict envelope (`doclifecycle.bloat`: six verdicts, no `POLICY`, `path`/`units`/
> `scope` in place of `location`/`files` — `plugins/doc-lifecycle/skills/detecting-doc-bloat/
> output-contract.md` and `plugins/doc-lifecycle/engine/README.md`'s "Bloat audit" section are
> the current contract). This file is not a grading key for that contract and must not be
> handed to a grader against a current skill run — it is kept only as the record of what the
> `bloat-rearch-{red,green}` baselines below actually tested at the time, per this repo's
> `tests/baselines/`/`tests/fixtures/` retention convention (`CLAUDE.md`; neither directory
> gates a release, `release-manifest.py`).

Grading key for `tests/fixtures/plan-swarm/`, used by the stakeless graders of
the `bloat-rearch` RED/GREEN scenarios (`tests/baselines/bloat-rearch-{red,green}/`).
Graders receive this file and a scenario transcript; they did not author either.

## Expected chunk plan (`plan-chunks.py` over the fixture, defaults from its scope config)

Scope config: `policy_scope: ["docs/superpowers"]`, `chunking: {max_docs: 3, max_lines: 400}`.
15 in-scope docs → **4 chunks**:

| kind | members | hint |
|---|---|---|
| policy | `docs/superpowers` — all 10 files under `docs/superpowers/{plans,specs}/` | — |
| sweep | `docs/guides/rate-limiting-overview.md` | narrative |
| sweep | `docs/plans/2026-05-01-rate-limiter-design.md`, `docs/plans/2026-06-15-webhook-retry-design.md` | planning |
| sweep | `README.md`, `RUNBOOK.md` | living |

Chunk ids are content-addressed and deterministic; grade membership, not ids.

## Expected verdicts (contract v2 — no `payload` field exists anywhere)

- `README.md:11` → **CONDENSE**, span `README.md:11-15` — five narrative lines
  carry two checkable constants; proposal = one line citing
  `MAX_REQUESTS_PER_MIN = 120` and `BURST = 20` (`src/limiter.py:3-4`).
- `README.md:17` → **EXTRACT-AND-MOVE**, span `README.md:17-19` — operational
  scale-out gotcha in a user-facing doc; target `RUNBOOK.md`.
- `docs/plans/2026-05-01-rate-limiter-design.md` → **DISTILL**, `status: "ready"`,
  `location: null`, `proposal: null`, `files: null`, **no payload/claims/insights/
  decision entry anywhere in the record** — evidence names the landed code
  (`src/limiter.py`: `MAX_REQUESTS_PER_MIN`, `BURST`, `TokenBucket.allow`).
- `docs/plans/2026-06-15-webhook-retry-design.md` → **DISTILL**,
  `status: "pending-implementation"` — no `src/webhooks.py`, no `RetryQueue` /
  `WEBHOOK_MAX_ATTEMPTS` symbols anywhere.
- `docs/superpowers` → exactly **one POLICY** record: `location: null`,
  `proposal` = retirement-class policy text, `files` = all 10 covered paths,
  evidence = what makes the directory one class. **Zero per-file records** for
  anything under `docs/superpowers/`.
- `docs/guides/rate-limiting-overview.md` → **no records**: first line is the
  `> As of` anchor, so it is a durable narrative doc judged against its own bar;
  its rationale prose is its job.

## Automatic FAILs (any one of these fails the scenario)

1. Any record carrying a `payload` field, or claims/insights/decision-entry text
   authored at detect time.
2. A per-file walk of `docs/superpowers/**` (any record whose `doc` is an
   individual file under it), or more/fewer than one POLICY record for it.
3. In a chunk-executor scenario: a record whose `doc` is outside the assigned
   chunk's slice, or output not shaped `{"chunk": "<id>", "records": [...]}`.
4. In the headless scenario: any tool use outside
   `Read, Grep, Glob, Write, Bash(git *), Bash(python3 *)` (e.g. `find`, `ls`,
   `wc`, unrestricted Bash).
5. `CUT`/`CONDENSE` on the narrative guide for being narrative, or classifying
   it as a planning artifact.
6. Any file edit — detection is read-only.
7. An interactive large-scope run that sweeps all 15 docs inline instead of
   planning chunks and dispatching per chunk.
