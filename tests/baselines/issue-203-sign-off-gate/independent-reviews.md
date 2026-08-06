# Issue #203 — independent Standards and Spec reviews, and the disposition of every finding

#168's Testing Decisions require: *"After implementation is green, run fresh independent Standards
and Spec review agents against the authoritative Issue #57 comment and this remediation spec. The
reviewers must not be agents that authored the fixes."*

## How the reviews were dispatched

**Raw output is retained verbatim in two files — read them first.** This file is disposition, and
a disposition table written by the party under review is not itself evidence of an independent
review. `reviewer-output-verbatim.md` holds the three dispatched agents' aggregate reports;
`reviewer-leaf-output-verbatim.md` holds the seven leaf reports beneath them, and the record of
the one that was lost.

Via the `mattpocock-skills:code-review` skill: two axes, dispatched in parallel, **with no
aggregation or reranking _across_ axes** so neither can mask the other.

> **That is the whole of what the axis separation guarantees, and an earlier version of this line
> overstated it** by saying "no aggregation or reranking" without qualification. There was
> aggregation — *inside* each axis. Spec fanned out into five leaf reviewers and Standards into
> two, each aggregating its leaves before returning. That is exactly where the review's one real
> failure occurred: the Spec aggregate returned 45 seconds before its fifth leaf finished, and
> that leaf was the one carrying two live defects. The cross-axis property held; the intra-axis
> path had no guarantee at all, and nothing in the three aggregates revealed that seven other
> agents existed. See `reviewer-leaf-output-verbatim.md`.

Fixed point **`8ded7d7`**, head **`c75fd59`** — the remediation head, before #203's own commits.
The reviewers' own reports name the diff as `8ded7d7...HEAD`, which is how they were briefed; at
the time they ran, `HEAD` *was* `c75fd59`, and the stats they quote (81 files, +10469/-1471) are
`8ded7d7...c75fd59`. The spelling is pinned here because `8ded7d7...HEAD` no longer reproduces
what was reviewed: at this branch's head it resolves to a larger diff.

**A limit, stated rather than papered over: #203's own commits were reviewed by no independent
agent.** The three reviews all predate them. Everything #203 changed — the manifest criterion, the
US28 guard, the race-test byte assertions, the `cache.py` fix, the static policy guard, and these
records — carries only the #203 pull-request review, which is a separate mechanism from #168's
User Story 42. This is not fixable by my reviewing my own work, so it is recorded as a gap.

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

Neither of those two reviews found a P1.

**The #203 pull-request review did.** It ran mutation testing across all six P1s and found two
with real gaps — #185's lane wiring guarded only by static strings that survive `|| true` on the
gate's own invocation, and a live crash in #187's `cache.get()`. Both are dispositioned below.

The `cache.get()` crash and the `policy_path` asymmetry are marked `PR` in the source column
because that review is where they reached *this record*. **But they were found earlier**, by the
`rev-policy-cache` leaf under the Spec axis, whose report was discarded by a race before its
parent aggregated. Marking them `PR` alone would repeat the earlier mistake of crediting the
finding to the wrong mechanism, so the column reads `PR (found by rev-policy-cache, lost)`.
`reviewer-leaf-output-verbatim.md` has that report in full and the timeline.

The per-P1 picture the PR review established is in `gate-results.md`.

## Disposition of every finding

Criterion: fixed, or explicitly accepted with rationale, or filed as its own issue. Deferral is a
decision, not silence.

Source column: **S** = Standards reviewer, **P** = Spec reviewer, **R** = race-test auditor
(the three aggregates verbatim in `reviewer-output-verbatim.md`, the seven leaves beneath them in
`reviewer-leaf-output-verbatim.md`), **PR** = the #203 pull-request review.

### Fixed in #203

| Finding | Source | Disposition |
|---|---|---|
| **P1 #187: `cache.get()` crashes on a non-UTF-8 entry.** `UnicodeDecodeError` is a `ValueError`, so it escaped `except OSError` — reachable from `bloat.load_chunk`, contradicting `get()`'s own docstring and #187's acceptance text | PR (found by `rev-policy-cache`, lost) | **Fixed test-first.** No existing test could reach it (every corrupt-payload test writes *with* `encoding="utf-8"` and fails at the parser). New test writes real non-UTF-8 bytes, verified RED before GREEN. Forces the 0.46.10 bump |
| **P1 #185: the lane's integrity wiring has no execution-level guard.** Appending `\|\| true` to the gate invocation lets a dirty checkout publish a report, and `audit-workflow_test`, `workflow-permissions_test`, and `check-repo-integrity_test` all stay green | PR | **Fixed.** New execution-based class in `audit-workflow_test.py` runs the step's real `run:` body under `bash -e` against a dirtied repository. Verified by running that exact mutation: two new tests fail, the other two suites stay green as before |
| `audit-workflow_test.py` carries the only lane-level assertions for #185 but is not in the criterion | PR | Fixed — pinned alongside `check-repo-integrity_test.py`, with why neither alone covers that P1 |
| `approval_cli_test.py`, `render-apply-summary_test.py`, `render-audit-summary_test.py` are pinned by no criterion, and #203's own rationale covers them | PR | Fixed — pinned; the criterion now names seventeen suites |
| `policy_test.py` monkeypatches the private `approval._mint_approval_set`, against "engine suites test only the two public seams" | S | **Fixed, having first been wrongly accepted.** The acceptance rationale ("no public seam observes which function was called") was contradicted later in the same file, where an equally un-runtime-observable property is proven statically. Replaced with a static AST guard; verified load-bearing by adding a second producer to `policy.py` |
| `doc-contract_test.py` is the one new suite CLAUDE.md never documented, while the other four were | S | Fixed — documented as the fourth wiring suite, and the "Three suites" count corrected |
| CLAUDE.md's run-surface renderer list omits `verify-apply-bytes.py`, which writes its own refusals to `$GITHUB_STEP_SUMMARY` | S | Fixed — added, with why it states them itself rather than handing back to the summary renderer |
| `docs/decisions.md` cites `docs/plans/HANDOFF.md` at two places; #200 deleted it | S + P (US37) | Fixed — both pinned `@ b7efcb5`, matching the `path @ <sha>` convention already used in `design-rationale.md` |
| `verify-apply-bytes_test.py`, `apply-recovery_test.py`, `apply-lane-parity_test.py`, `doc-contract_test.py` are wired to no gate criterion, so a silent deletion would go unreported | P (US40) | Fixed — new `issue #168 sign-off regressions` criterion in `release-manifest.py` |
| US28's "identity stable across harmless reordering" has no test; #193's ordinals could leak into `finding_digest` with a green gate | P (US28, US40) | Fixed — new guard in `tests/engine/finding_test.py`, proven load-bearing |
| Nine race tests assert transaction state without surviving bytes | R | Seven fixed, two accepted — see `race-test-audit.md` |

### Filed as issues

All are labelled with this repo's canonical triage labels and listed in a comment on #57, so the
deferrals are visible in the tracker a human would actually use rather than only in this file.

| Finding | Source | Issue | Triage |
|---|---|---|---|
| Nothing asserts the report's `base_commit` equals the head the integrity gate verified; the binding rests on step ordering alone | P (US12) | [#223](https://github.com/aj604/toolshed/issues/223) | `ready-for-agent` |
| Only the refusal half of US26 shipped — no public way to name which occurrence was reviewed, so a legitimately repeated passage has no supported remedy | P (US26) | [#224](https://github.com/aj604/toolshed/issues/224) | `ready-for-human` |
| `--integrity` is passed only under `[ -f … ]`, so a missing verdict artifact renders a summary with no integrity evidence rather than refusing — the one place this rendering defaults open | P | [#225](https://github.com/aj604/toolshed/issues/225) | `ready-for-agent` |
| `check-repo-integrity.py` runs git with inherited env and no timeout while its sibling `verify-apply-bytes.py` scrubs `GIT_DIR`/`GIT_WORK_TREE` and bounds every call — the more security-critical script has the weaker invocation | S | [#226](https://github.com/aj604/toolshed/issues/226) | `ready-for-agent` |
| Residue an insight walk misses is permanently unreachable by the fix door once an artifact is retired; the only control is a prose gate in `fixing-docs/SKILL.md` | known item, published-plugin gap | [#227](https://github.com/aj604/toolshed/issues/227) | `ready-for-human` |
| The hardened lanes do not run, and the release tag their tooling fetch names is not cut | known item | [#228](https://github.com/aj604/toolshed/issues/228) | `ready-for-human` |
| `apply_edit_plan` does not thread `policy_path` into `validate_approval_set`, so a policy approval is revalidated against a different declaration than the one that minted it | PR (found by `rev-policy-cache`, lost) | [#230](https://github.com/aj604/toolshed/issues/230) | `ready-for-human` |
| **#185's third acceptance clause is untested**: nothing links evidence-integrity failure to policy eligibility. The similarly-named `test_a_fresh_checkout_cannot_re_derive_the_failure` asserts the converse | PR | [#231](https://github.com/aj604/toolshed/issues/231) | `ready-for-human` |

#228 is a native `blocked_by` edge on #57 — the one deferral that leaves this remediation's
central claim unproven rather than merely incomplete. It is a visibility mechanism, removable in
one click, not a veto on a human's decision.

### Accepted, with rationale

> **One acceptance was withdrawn.** An earlier version of this record accepted
> `policy_test.py`'s private-symbol spy, on the rationale that no public seam observes which
> function was called. The #203 pull-request review showed that premise is contradicted later in
> the same file, where an equally un-runtime-observable property is proven statically
> with `inspect`. The spy is now a static AST guard and the finding moved to the fixed table.
> Recorded here rather than quietly deleted, because an acceptance that did not survive scrutiny
> is the most useful thing in this file: it is what a rationale looks like when it is doing work
> for the author rather than for the reader.

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
