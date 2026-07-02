# RED — baseline agent asked to wire nightly doc sync (no skill)

Agent: Sonnet, general-purpose, prompt in the appendix. Scratch repo: taskflow fixture +
accurate docs (`tests/baselines/bootstrap-green/agent1/`), fresh git repo, no remote.
Artifacts graded: the workflow it wrote (`.github/workflows/doc-drift-sync.yml`, 200 lines),
marker file, and its README. n=1 baseline, consistent with this suite's earlier REDs.

| # | Predicted failure | Observed? | Evidence |
|---|-------------------|-----------|----------|
| 1 | Re-invents detection/fixing method inside YAML prompt text instead of invoking the skills by name | **Partially** | Skills invoked by name ("Use the doc-lifecycle detecting-doc-drift skill in diff-scoped mode…"), but the fix prompt *paraphrases three of fixing-doc-drift's rules* ("act only on STALE records, never delete UNVERIFIABLE or VERIFIED passages, land each fix verbatim") — method now has two owners that can diverge. |
| 2 | No last-synced marker → no idempotency story | **No** | Full marker mechanics: `.github/doc-sync/last-synced-sha`, seeded at HEAD; empty-range skip; marker advanced via clean-run commit or inside the PR branch (yml:55-76, 188-200). |
| 3 | Direct-commits doc edits to the default branch | **No** | PR-only for doc edits; only the marker-only commit pushes to default (yml:146-186, 188-200). |
| 4 | No blast-radius stop | **YES** | No cap anywhere. The only gate is `stale != '0'` → fix + PR (yml:138, 147). A wholesale-stale doc set becomes one giant unreviewable PR; no issue/escalation path exists at all. |
| 5 | No pending-work guard | **Mostly no** | Open-PR guard via label query (yml:41-53). But branches are timestamped (`doc-drift-sync/<ts>`, yml:155), so a closed-unmerged PR strands branches, and with no issue path there is nothing gating repeated escalations. |
| 6 | Evidence absent from PR body | **No** | Full drift-report JSON dumped into the body (yml:170-178) — raw dump rather than per-edit mapping, but evidence is present. |

## Failures observed that the checklist did not predict

- **The report artifact gets committed into the sync PR.** `drift-report.json` is written to the
  repo root before branching; the PR step does `git add -A` (yml:161) — every sync PR ships the
  report as repo content. (`pr-body.md` escapes only by luck of ordering, written post-commit.)
- **Fragile validator lookup:** `find ~/.claude -path "*validate-drift-output.py" | head -1`
  (yml:108) — guesses at the plugin cache layout; silently version-skewed, breaks if the layout
  changes.
- **All gate logic is untested YAML/inline-python:** the stale count is an inline `python3 -c`
  heredoc (yml:120-125); skip logic is compound `if:` chains across six steps. Hand-rolled per
  repo = divergent, unupgradable, untestable wiring — no two installs would behave alike.
- **First-run fallback sweeps the whole history:** missing marker → diff from the root commit
  (yml:67) — an unbounded first run instead of a seeded marker.

## Verdict

The baseline gets the *shape* right (marker, PR-only, pending guard, evidence) — consistent
with this suite's recurring lesson that capable agents nail the obvious structure. The real,
recurring failure axes the skill must own:

1. **Blast-radius stop is absent** (the one predicted failure that fully reproduced) — cap +
   issue escalation must be shipped, not hoped for.
2. **Hand-rolled gate logic** — decisions belong in a shipped, unit-tested script
   (`sync-gate.py`), not per-repo YAML improvisation.
3. **Artifact hygiene** — the report must never be committed as repo content.
4. **Method stays with its owner** — prompts invoke skills by name, never paraphrase their rules.
5. **Deterministic file provenance** — the validator ships into the target repo at install
   time, not `find`-guessed from a cache path at run time.

## Appendix: exact prompt

> You are working in the git repo at `<SCRATCH>`. Its docs (CLAUDE.md, README.md) are accurate
> today. Set up **automated nightly documentation drift sync** for this repo: every night,
> unattended, it should detect doc claims the code no longer backs and open a GitHub PR fixing
> them, with evidence. The repo's owner uses the Claude Code `doc-lifecycle` plugin, which
> provides `detecting-doc-drift` (emits structured drift records) and `fixing-doc-drift`
> (applies them). Create whatever files the automation needs. Do not ask questions; make
> reasonable choices and finish.
