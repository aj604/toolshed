# Issue #203 — independent Standards and Spec reviews, and the disposition of every finding

#168's Testing Decisions require: *"After implementation is green, run fresh independent Standards
and Spec review agents against the authoritative Issue #57 comment and this remediation spec. The
reviewers must not be agents that authored the fixes."*

## How the reviews were dispatched

Via the `mattpocock-skills:code-review` skill, which is built for exactly this shape: two axes,
two parallel sub-agents, no aggregation or reranking across axes so neither can mask the other.
Fixed point `8ded7d7`, diff `git diff 8ded7d7...HEAD` (81 files, +10469/-1471).

Both reviewers were fresh general-purpose agents that authored none of the ten fixes. Neither was
given a summary of the remediation written by the ticket's own agent: they were pointed at the
authoritative record and told to fetch it — `gh issue view 57 --comments` (the "Distilled
decisions (grilling session, 2026-07-26)" comment and its "Amendments — 2026-07-29"),
`gh issue view 168` (the 42 user stories, Implementation Decisions, Testing Decisions, Out of
Scope), the ten closed child issues, and the ten merged PRs. Both were told explicitly not to
defer to any correctness or completeness claim in a commit message, PR body, or issue comment.

The Standards reviewer additionally received the repo's documented standards sources (CLAUDE.md's
Conventions, CONTEXT.md's ubiquitous language, the engine README's contracts, `docs/decisions.md`,
`docs/guides/principles.md`) plus the skill's Fowler smell baseline, with the rule that a
documented repo standard overrides the baseline and that baseline smells are always judgement
calls.

A third agent ran the criterion-3 race-test audit separately; its record is `race-test-audit.md`.

## What each concluded

**Standards.** Four hard violations, all documentation or coverage rather than behaviour, plus
seven judgement calls. It verified independently that the engine and its vendored mirror are
byte-identical, that everything is stdlib-only, that no run-surface string is inline YAML `jq`,
that no `git add -A` and no `inputs.*` appears in any `run:` block, and that CONTEXT.md's _Avoid_
lists are respected. It found no correctness defect.

**Spec.** It traced the load-bearing claim — *"no report, approval, apply result, staged index,
commit, or cache hit may claim authority over bytes that were not part of its validated inputs"* —
end to end and reported it holds: write-boundary recheck against the captured preimage, read-back
certification of final bytes, compare-aware rollback, index blobs compared via `cat-file --batch`,
the post-hook commit tree re-certified, and the push naming the verified commit id rather than
`HEAD`. It confirmed the `_approved_hull` min/max is genuinely gone, that the cache digest covers
lineage, nested records, and scope, and that policy provenance reloads the declaration and asserts
exact set equality in both directions. Six findings, no scope creep, and nothing contradicting
#57's distilled decisions.

Neither review found a P1. Both are recorded below by disposition rather than verbatim, because a
finding's disposition is what a later reader needs.

## Disposition of every finding

Criterion: fixed, or explicitly accepted with rationale, or filed as its own issue. Deferral is a
decision, not silence.

### Fixed in #203

| Finding | Axis | Disposition |
|---|---|---|
| `doc-contract_test.py` is the one new suite CLAUDE.md never documented, while the other four were | Standards | Fixed — documented as the fourth wiring suite, and the "Three suites" count corrected |
| CLAUDE.md's run-surface renderer list omits `verify-apply-bytes.py`, which writes its own refusals to `$GITHUB_STEP_SUMMARY` | Standards | Fixed — added, with why it states them itself rather than handing back to the summary renderer |
| `docs/decisions.md` cites `docs/plans/HANDOFF.md` at two places; #200 deleted it | Standards + Spec (US37) | Fixed — both pinned `@ b7efcb5`, matching the `path @ <sha>` convention already used in `design-rationale.md` |
| `verify-apply-bytes_test.py`, `apply-recovery_test.py`, `apply-lane-parity_test.py`, `doc-contract_test.py` are wired to no gate criterion, so a silent deletion would go unreported | Spec (US40) | Fixed — new `issue #168 sign-off regressions` criterion in `release-manifest.py` |
| US28's "identity stable across harmless reordering" has no test; #193's ordinals could leak into `finding_digest` with a green gate | Spec (US28, US40) | Fixed — new guard in `tests/engine/finding_test.py`, proven load-bearing |
| Seven race tests assert transaction state without surviving bytes | Criterion 3 | Fixed — see `race-test-audit.md` |

### Filed as issues

| Finding | Axis | Issue |
|---|---|---|
| Nothing asserts the report's `base_commit` equals the head the integrity gate verified; the binding rests on step ordering alone | Spec (US12) | [#223](https://github.com/aj604/toolshed/issues/223) |
| Only the refusal half of US26 shipped — no public way to name which occurrence was reviewed, so a legitimately repeated passage has no supported remedy | Spec (US26) | [#224](https://github.com/aj604/toolshed/issues/224) |
| `--integrity` is passed only under `[ -f … ]`, so a missing verdict artifact renders a summary with no integrity evidence rather than refusing — the one place this rendering defaults open | Spec | [#225](https://github.com/aj604/toolshed/issues/225) |
| `check-repo-integrity.py` runs git with inherited env and no timeout while its sibling `verify-apply-bytes.py` scrubs `GIT_DIR`/`GIT_WORK_TREE` and bounds every call — the more security-critical script has the weaker invocation | Standards | [#226](https://github.com/aj604/toolshed/issues/226) |
| Residue an insight walk misses is permanently unreachable by the fix door once an artifact is retired; the only control is a prose gate in `fixing-docs/SKILL.md` | known item, published-plugin gap | [#227](https://github.com/aj604/toolshed/issues/227) |
| The hardened lanes do not run, and the release tag their tooling fetch names is not cut | known item | [#228](https://github.com/aj604/toolshed/issues/228) |

### Accepted, with rationale

- **`tests/engine/policy_test.py` monkeypatches `approval_mod._mint_approval_set`**, a private
  cross-module symbol, against CLAUDE.md's "engine suites test only the two public seams".
  Accepted. The property under test is *"the policy mints through the one minting function"* —
  that there is not a second producer where reconciliation, path, and preimage refusals could be
  forgotten. #186 made the shared constructor private deliberately; there is no public seam that
  observes which function was called, and the sibling test immediately below already proves
  equivalence of *output* through the public door. Two implementations can agree today and diverge
  tomorrow, so the call assertion is not redundant with it. Noted honestly: #168's own carve-out
  for private tests is narrower than this ("canonical hashing or parsing edge cases"), so this is
  an accepted stretch of it rather than a clean fit.
- **`_unsafe_path_reason` and `write_surface` are byte-identical between `verify-apply-bytes.py`
  and `render-apply-summary.py`.** Accepted. Both are vendored, standalone, stdlib-only scripts
  that a consumer's install copies and runs independently; a shared module between them would be a
  third vendored file and a new import path for the upgrade lane's path authority to own. Both
  copies are separately unit-tested.
- **Sixteen `run:` blocks are byte-identical between `doc-apply.yml` and `doc-policy-apply.yml`.**
  Accepted, and deliberate: GitHub Actions has no cross-workflow `run:` include, and
  `apply-lane-parity_test.py` (#191) exists precisely to hold selection and trigger to being the
  only differences. The duplication is the enforced invariant, not an accident.
- **`approval.py`'s `AcceptedRecord` docstring says occurrences are "one per approved unit"**,
  which is imprecise for a whole-document record over a repeated unit, where `_derive_occurrences`
  takes every occurrence. Accepted here: `_derive_occurrences`' own docstring documents that case
  correctly and at length, the imprecision is in prose rather than behaviour, and correcting it
  would touch `plugins/doc-lifecycle/` and force a four-carrier version bump on a sign-off ticket
  whose diff is otherwise release-neutral. Worth folding into the next engine change.
- **`docs/guides/{principles,scheduling-doc-sync,auditing-doc-bloat}.md` carry
  `> As of 2026-07-30 (0.45.0)` while describing 0.46.9 behaviour**, and were edited in this
  range. Accepted, not fixed: growing-docs' `> As of` anchor asserts that the *whole* document was
  re-validated on that date, and refreshing it here would assert a validation of three narrative
  guides that #203 did not perform. Refreshing an anchor is a claim, so it belongs to whoever
  re-reads the guide.
- **`render-apply-summary.py` has grown to ~1200 lines and now carries branch derivation and
  recovery-state decisions alongside run-surface strings** (Divergent Change), and
  `approval.mint_approval_set` is now largely a brand refusal delegating to `_mint_approval_set`
  (Middle Man). Both accepted as judgement calls the reviewer itself labelled non-binding: the
  first is where #198's recovery contract has to live if it is to stay tested outside YAML, and the
  second is the shape #186's "one policy-branded producer" decision requires.
