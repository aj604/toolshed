# Issue #203 — the seven leaf reviewers' raw output, verbatim

`reviewer-output-verbatim.md` retains the three agents this ticket dispatched directly. It is not
the whole review: **each of the two axes fanned out again internally**, and the aggregates those
seven leaves fed are what the sibling file holds. This file is the leaves.

It exists because one of them was lost, and that loss is the reason two real defects reached the
pull-request review instead of this record.

## What actually happened

| Agent | Returned (UTC) | Fate |
|---|---|---|
| `spec-review-203` (parent) | **14:38:35.302Z** | retained — aggregate |
| ├ `rev-integrity` | 14:32:43.303Z | incorporated |
| ├ `rev-workflow` | 14:33:18.763Z | incorporated |
| ├ `rev-docs` | 14:33:48.520Z | incorporated |
| ├ `rev-occurrence` | 14:36:45.241Z | incorporated |
| └ `rev-policy-cache` | **14:39:20.675Z** | **LOST — 45.4s after its parent had already returned** |
| `standards-review-203` (parent) | 14:41:02.782Z | retained — aggregate |
| ├ `std-applier-approval` | 14:36:57.083Z | incorporated |
| └ `std-cache-policy` | 14:40:27.463Z | incorporated |

`rev-policy-cache` was dispatched at 14:29:44.772Z as "Review policy provenance and cache digest"
— user stories 16-24, the #186 and #187 halves. It found both defects the #203 pull-request
review later raised, and its report is below in full. Its finding 5 opens
`**5. US24 — PARTIAL / implementation-wrong (real finding).**` and names the exact fix that
landed. Its closing `**Minor:**` paragraph is the `policy_path` asymmetry now filed as #230.

Its parent never received it. Searching the parent's transcript, `US24` and `policy_path` appear
only twice: in the **dispatch prompt** at 14:29:44.772Z, and in a `Read` of `approval.py` source
at 14:37:49.030Z. Neither is a returned result. The aggregate the parent produced 45 seconds
before the leaf finished contains neither finding.

**Four of five Spec leaves landed in time; the only one that found a real defect did not.**

## Correcting this record's own earlier claim

An earlier version of `reviewer-output-verbatim.md` said the two defects "were not paraphrased
away; the three agents retained here never reported them. That is a finding about the reviews
themselves."

**That was wrong, and the truth is worse.** Every clause of it is true of the three *retained*
agents and materially false about what happened. It described a reviewer blind spot — reviewers
who looked and missed. What actually occurred is a structural loss: a reviewer looked, found it,
wrote it up, and the result was discarded by a race between a background agent and its parent's
aggregation. A human closing #57 would have read the earlier sentence as established fact about
how reliable the review apparatus was, and drawn precisely the wrong lesson.

The earlier claim was itself made from evidence — the three retained transcripts, which genuinely
do not contain the findings. It was wrong because the evidence was incomplete and I did not check
whether the retained set *was* the whole set. That is the same defect class as the count drift
recorded in `gate-results.md`: a claim in prose outrunning the artifact under it.

## Why the fix is retention, not a promise to be careful

Nothing about the sibling file's three aggregates reveals that seven other agents existed. The
loss was invisible from every artifact this ticket produced until someone walked the transcripts.
Retaining the leaves is what makes a recurrence detectable: a future reader can compare leaf
findings against the aggregate that claims to summarize them.

All seven are below, unedited, recovered from `~/.claude/projects/.../subagents/agent-<id>.jsonl`
(the `assistant` text blocks). **No leaf output was unrecoverable.** All seven transcripts survive
and all seven reports are complete.

---

## rev-integrity

- Axis: **Spec**
- Agent id: `a5369aec5a0df56df`
- Reviewed: repository-integrity gate (#185), user stories 11-15
- Started 2026-08-05T14:29:32.364Z, finished **2026-08-05T14:32:43.303Z**

Verbatim:

---

<!-- BEGIN VERBATIM -->
I'll start by fetching the spec and examining the diff.
## Verdict: US11–US15 met. No MISSING items in scope; two small PARTIALs, no implementation-wrong.

**1. Four surfaces + placement — MET.** `/Users/.../plugins/doc-lifecycle/skills/scheduling-doc-sync/scripts/check-repo-integrity.py:89` (HEAD vs `--expected-head`), `:103` (`diff --name-only` tracked worktree), `:111` (`diff --cached … HEAD` index), `:123` (`ls-files --others`, deliberately *without* `--exclude-standard`). Gate sits at `doc-audit.yml:238`, after the model step and **before** the only assembly call (`doc-audit.yml:261 "Run the drift audit"`), gated `:262 if: ${{ always() && steps.integrity.outcome == 'success' }}`. Ordering asserted at `tests/scripts/audit-workflow_test.py:263-278`. Satisfies US11/US13 ("dirty tracked evidence sources rejected before report assembly").

**2. Same gate on both lanes — MET (US14).** `doc-bloat-audit.yml:239` invokes the identical script from the same release-pinned marketplace path; the old inline shell is deleted. Behavioral cases moved to `tests/scripts/check-repo-integrity_test.py`, wiring asserted in `bloat-audit-workflow_test.py:241-267`.

**3. Allowlist — EXACT (US15).** `--allow verdicts.json` only (`doc-audit.yml:246`); matching is exact set membership (`check-repo-integrity.py:124`), no prefix/glob, and it exempts only *untracked additions* — the same name tracked-and-modified still refuses (`check-repo-integrity.py:100-110`, test `check-repo-integrity_test.py:156`). Bloat passes no `--allow` at all. Asserted `audit-workflow_test.py:290-306`.

**4. Fail-closed — YES.** Step uses `set -euo pipefail` with python3 last; exit 2 fails the step, no `continue-on-error`, `outcome` is pre-continue-on-error. Assembly skipped ⇒ no `drift-report.json` ⇒ upload is `if-no-files-found: ignore` ⇒ nothing publishable. Audit job failure ⇒ workflow conclusion ≠ success ⇒ policy lane blocked at `doc-policy-apply.yml:45`. Gate never repairs (`check-repo-integrity.py:20-22`, test `:230`).

**5. US12 — satisfied by construction, never asserted (PARTIAL).** Nothing cross-checks `report.base_commit == integrity.expected_head`; the binding rests on no step running between `doc-audit.yml:238` and `:261`. Spec: *"every cited repository evidence source to come from the declared base commit."*

**6. `bash -e {0}` / #107 — correct.** No `$?` read. The new `[ ! -s "${AUDIT_DIR}/drift-report.json" ]` terminal state (`doc-audit.yml:313-318`) closes the redirect-failure-reads-as-typed-report hole, with an executed regression test (`audit-workflow_test.py:539`).

**Minor fail-open (run surface only):** `doc-audit.yml:455` / `doc-bloat-audit.yml:387` pass `--integrity` only `[ -f … ]`, and the download is `continue-on-error` (`:390`). A lost integrity artifact renders the report with no integrity evidence. Low risk (a report exists only if the gate passed in-job), but it is the one place the rendering defaults open.

**Testing-decision PARTIAL:** the "fresh-checkout" test (`check-repo-integrity_test.py:107`) proves the failure *cannot be re-derived later* — the motivation for terminality — but no test asserts the policy lane cannot consume a refused run's output; that guarantee is structural only.

**Scope creep: none material.** The bloat-lane rewrite is required by US14, not "unrelated workflow duplication". The out-of-tree artifact move, `PYTHONDONTWRITEBYTECODE`, and `--add-dir` all follow from "keep verdict data outside repository state". The `wrote no report` check is new behavior beyond US11-15 but is a direct consequence of moving the redirect out of tree.

All in-scope suites pass: `check-repo-integrity_test` (12), `audit-workflow_test` (34), `bloat-audit-workflow_test` (9), `render-audit-summary_test` (26), `install-parity_test` (7), `workflow-permissions_test` (16).
<!-- END VERBATIM -->

---

## rev-workflow

- Axis: **Spec**
- Agent id: `a825a00fe745819d1`
- Reviewed: apply-workflow recovery (#198) and the rendered run surface (#189), user stories 29-33
- Started 2026-08-05T14:29:16.784Z, finished **2026-08-05T14:33:18.763Z**

Verbatim:

---

<!-- BEGIN VERBATIM -->
I'll start by getting the spec and the diff.
All three suites pass locally (31, 14, 10 tests). Findings below; paths absolute.

**Answers**

1. **Yes — real blob content.** Index entries come from `ls-files --stage -z`, blobs are read via `git cat-file --batch` on the listed oids, and compared `sha256(stored) != digest`: `/Users/averyjones/Repos/skills/toolshed/.claude/worktrees/agent-ab321bca63ef8c93a/plugins/doc-lifecycle/skills/scheduling-doc-sync/scripts/verify-apply-bytes.py:449-461`. Not worktree hashes, not path names.
2. **Yes — post-commit, and the push names the verified id.** `verify_commit` runs after `git commit` (doc-apply.yml step "Verify the commit tree…", `.../doc-apply.yml:552-560`), resolves `HEAD^{commit}`, certifies, and only then writes `--out` (`verify-apply-bytes.py:582-607`, the write at :601 deliberately after certification). Push is `git push origin "${commit}:refs/heads/${branch}"` from that file (`doc-apply.yml:637-638`, policy `doc-policy-apply.yml:519-520`). US9 satisfied.
3. **Yes.** `null` postimage ⇒ entry must be absent, and `compare()` is used for both index and tree (`verify-apply-bytes.py:427-436`, callers :493 and :562). Tests: `/…/tests/scripts/verify-apply-bytes_test.py:217, 224, 236`.
4. **No force path.** Neither template contains `--force`/`+refspec`; a static guard with its own positive cases exists (`/…/tests/scripts/workflow-permissions_test.py:291-337`).
5. **Complete tree + approval binding.** `verify_reuse` checks the approval trailer in full (`verify-apply-bytes.py:673-709`), the fetched ref still equals the read id (`:636-670`, `apply-branch-moved`), the same manifest certification incl. whole-diff confinement (`:513-565`), and parent identity (`:763-774`) — parent equality plus confined, byte-matched diff is complete-tree equivalence, not name/digest matching.
6. **Identical.** Every `run:` block in both `apply` jobs is byte-compared (`/…/tests/scripts/apply-lane-parity_test.py:124-131`, passing); non-command differences are confined to ref/if/BASE/artifact names (:218-240).
7. **Bytes and state.** Race/conflict tests assert the surviving remote tip commit id and the typed surface heading, not path sets (`/…/tests/scripts/apply-recovery_test.py:512-513, 519, 525, 538, 567, 592, 478-481`).

**PARTIAL / minor**

- `/Users/averyjones/Repos/skills/toolshed/.claude/worktrees/agent-ab321bca63ef8c93a/.github/scripts/release-manifest.py:113-120` — the "workflow permission checks" criterion gained `check-repo-integrity_test.py` (#185) but **not** `verify-apply-bytes_test.py`, `apply-recovery_test.py`, or `apply-lane-parity_test.py`. Discovery still runs them, so the gate is green, but US40 ("regression tests for every reproduced sign-off failure, so that a green gate proves the properties…") is not pinned by criterion for the byte-binding work; a deletion would go unnamed.
- `/…/scripts/verify-apply-bytes.py:159-164` — one closing for all stages, including `branch reuse`: "Nothing was pushed and no pull request was created… Inspect the checkout, then re-run the audit and mint afresh." At reuse a foreign/earlier branch *does* exist, and `render-apply-summary.py` deliberately introduced `NOTHING_TOUCHED` for exactly that ("telling a reader nothing was created would be false", `/…/scripts/render-apply-summary.py:128-138`). Wrong remediation advice for `apply-branch-approval-conflict` / `apply-branch-moved`; no test asserts this text.

No scope creep found; no implementation-looks-wrong findings on US7–US10, US29–US32.
<!-- END VERBATIM -->

---

## rev-docs

- Axis: **Spec**
- Agent id: `aa5f951bcea553fdd`
- Reviewed: documentation contracts (#194) and tracker retirement (#200), user stories 34-37
- Started 2026-08-05T14:30:16.346Z, finished **2026-08-05T14:33:48.520Z**

Verbatim:

---

<!-- BEGIN VERBATIM -->
I'll start by gathering the spec and the diff.
## Verified

**US33 — PASS.** `render-report.py` gains `upgrade-pr-title` / `upgrade-commit-subject` (`plugins/doc-lifecycle/skills/scheduling-doc-sync/scripts/render-report.py:42-60`); `doc-sync-upgrade.yml:416,420` now `git commit -F` and `--title "$(cat …)"`. No inline commit/title literal remains in that file — the only other `--title` (`:139`, `:150`) reads the rendered `notice-title.txt`. Guarded by `upgrade-workflow_test.py:390-437` (`test_no_commit_message_is_typed_into_the_yaml`, `test_no_title_is_typed_into_the_yaml`, scanned across **all** jobs) and `render-report_test.py:187-225`, including that the blocked-upgrade summary dictates the same subject. 22/38/25 tests green.

**US34 — PASS.** `plugins/doc-lifecycle/engine/README.md:7-13` — "the only component that writes a repository document"; `cache.put()` and `approval.write_approval_set()` named as the two artifact writers, with `put()` documented at `:706-714`. Mirrored in `CONTEXT.md:10,14`.

**US35 — PASS.** The contradictory "raw flag … credits a policy without consulting one" text is gone; `engine/README.md:1935-1944` now states `policy-mint` is the sole `policy` producer and `mint-approval` refuses the kind (`approval-policy-minter-not-generic`). `fixing-docs/SKILL.md:162-164` reconciled.

**US36 — PASS.** `scheduling-doc-sync/SKILL.md:103-110,240-247` and `docs/guides/scheduling-doc-sync.md:174-177` ("The one job the schedule can reach that authors a change is `doc-policy-apply.yml`").

**Parity — PASS.** `diff -r plugins/doc-lifecycle/engine/ .doc-lifecycle/wiring/engine/` differs only by `__pycache__`. `installed-version` = `plugin.json` version = `0.46.9`. `install-parity_test.py` 7/7 green; `release-manifest.py` exits 0 ("60 suite(s) wired").

**Scope creep — none found.** Every file flagged traces to a story: CONTEXT.md/doc-distiller/output-contract are the hull→occurrence rename (US25-27) and writer-boundary (US34); README.md/auditing-doc-bloat.md/principles.md/detecting-doc-drift SKILL.md serve US36/US11/US14/US15; release-manifest.py `+6` wires the new integrity suite. `doc-contract_test.py` explicitly pins phrases, not files (`:19-22`), which is what "do not replace prose review with brittle full-file snapshots" permits.

## Findings

**PARTIAL — US37, dangling references (P2).** The retirement repaired CLAUDE.md's two inbound links but not `docs/decisions.md`:
- `docs/decisions.md:1028` — "the two detecting skills' own read-only tooling (`HANDOFF.md`, 2026-07-27 entry)"
- `docs/decisions.md:1711` — "per `docs/plans/HANDOFF.md`'s Row 5 note"

Both are unpinned citations to a file deleted at HEAD, unlike the convention every other retired-plan citation uses (`docs/design-rationale.md:16,28,36…` — `path @ <sha>`). Spec: *"completed planning trackers retired or distilled, so that repository context no longer instructs agents to resume finished work."* (`tests/fixtures/`, `tests/baselines/` hits are frozen artifacts — not findings.)

**PARTIAL — stale narrative anchors (P3).** Three guides were edited in this diff but kept `> As of 2026-07-30 (doc-lifecycle 0.45.0…)` while now describing 0.46.9 behavior: `docs/guides/scheduling-doc-sync.md:3`, `docs/guides/principles.md:3`, `docs/guides/auditing-doc-bloat.md:3`. The new `docs/guides/building-skills-test-first.md:3` correctly reads `2026-08-05 (doc-lifecycle 0.46.9…)`. Per CLAUDE.md, each guide carries growing-docs' `> As of` anchor — this is exactly the narrative-anchor-refresh class the repo's own policy exists to fix.

**Implementation-wrong: none in scope A.**
<!-- END VERBATIM -->

---

## rev-occurrence

- Axis: **Spec**
- Agent id: `a29b12ab09aa7d9d1`
- Reviewed: occurrence-bound approval (#193), user stories 25-28
- Started 2026-08-05T14:30:01.321Z, finished **2026-08-05T14:36:45.241Z**

Verbatim:

---

<!-- BEGIN VERBATIM -->
I'll start by getting the spec and the diff.
Verified against code; both engine suites (1344 tests) and `doc-contract_test.py` (22) are green.

**1. Storage + identity — PRESENT.** `occurrences: Tuple[int, ...]` on `ApprovedRecord` at `/Users/averyjones/Repos/skills/toolshed/.claude/worktrees/agent-ab321bca63ef8c93a/plugins/doc-lifecycle/engine/doclifecycle/approval.py:316`, serialized at `:333`, required field at `:194`, and inside `ApprovalSet.content["records"]` (`:409`) which is exactly what `digest` hashes (`:417`). So occurrences are in approval identity, as "Occurrence-bound approval data is included in approval identity" requires.

**2. Committed baseline — PRESENT.** `approval.py:720`: `data, problem = repository_mod.head_bytes(repo_root, path)` inside `baseline_units()`, docstring "HEAD, deliberately, and not through the inventory" (`:713`). Re-derivation at validate time via `_occurrence_problems` (`:825`) and at apply time via `occurrence_passages` (`:886`). Proven by `tests/engine/approval_test.py:834` (`test_the_binding_is_read_off_the_baseline_not_the_working_tree`). Satisfies US27.

**3. Hull gone — YES.** `_approved_hull` and its `return (min(s for s, _ in lines), max(e for _, e in lines))` were deleted (old `applier.py:134-164`). Replacement `approval.py:917-925` builds one passage per *run* of consecutive ordinals. Only two `min`/`max` remain, both inside message strings (`applier.py:769`, `approval.py:853`) — neither computes a span. Applier requires an operation to fit inside a single passage: `applier.py:621` `if not any(first <= start and end <= last for first, last in passages)` and `applier.py:606` for inserts — so non-contiguous occurrences refuse a spanning op.

**4. Old artifacts — FAIL CLOSED, typed.** `SCHEMA_VERSION = 3` / `PRE_OCCURRENCE_SCHEMA_VERSION = 2` (`approval.py:117-119`), table entry `"approval-schema-pre-occurrence"` (`:139`), refused before any field is read (`:1642-1652`). Tests `tests/engine/approval_test.py:656`, `:662`, `:668` (`test_it_is_refused_rather_than_bound_to_a_constructed_hull`). Ambiguity at mint is `approval-occurrence-ambiguous` (`approval.py:768`), tested at `approval_test.py:729`.

**5. US28 — PARTIAL (missing test).** Structurally correct: `finding.py` and `segment.py` are untouched by the diff, and `finding_digest` covers only `{code, path, units, lineage}` (`plugins/doc-lifecycle/engine/doclifecycle/finding.py:134-141`) — occurrences never enter finding identity. But **no test asserts reorder-stability of finding identity**. Nearest are `tests/engine/finding_test.py:143` (order units were *listed* in) and `approval_test.py:834` (working-tree shift), neither of which reorders document content and asserts an unchanged finding digest. Spec line: *"finding identity to remain stable across harmless document reordering"* — the property holds, the regression guard does not exist.

**6. Repeated-text test — PRESENT.** `tests/engine/applier_test.py:1980` `class OccurrenceBoundPassages`, fixture `REPEAT_DOC_TEXT` (`tests/engine/approval_test.py:84-95`) repeats one sentence with a `## Queues` section between. Four assertions: `test_the_other_occurrence_is_outside_the_approved_passage` (`:2073`), `test_the_span_from_one_occurrence_to_its_twin_is_refused` (`:2088`), `test_the_material_between_the_occurrences_is_outside_it` (`:2106`), `test_an_insert_between_the_occurrences_is_outside_it` (`:2127`) — all assert `["plan-span-outside-approved-units"]` plus an untouched tree. Plus the gap case at `:2158-2200`. Fully meets the Testing Decision.

**7. Scope creep — NONE.** No segmenter change; `report.py`'s only hunk extracts the `DIGEST_MISMATCH` constant for cache use, unrelated to occurrences. Vendored `.doc-lifecycle/wiring/engine/doclifecycle/{approval,applier}.py` byte-identical to source.

**Secondary note (US26, "or explicitly selected"):** minting always refuses ambiguity — there is **no public producer** for an explicitly-selected occurrence set. `cli.py` has no occurrence flag; `applier_test.py:1995 declared()` hand-constructs `ApprovalSet`. Validation accepts such a hand-written artifact, so the "explicitly selected" half of US26 exists only as an artifact-level contract, not a door a reviewer can use. Not wrong, but worth confirming it's intended.

**Doc-contract tests:** 22 tests, all schema/policy/lane claims; none assert the occurrence contract (e.g. no analogue of `test_the_pre_provenance_refusal_is_documented` at `tests/scripts/doc-contract_test.py:169` for `approval-schema-pre-occurrence`), though `plugins/doc-lifecycle/engine/README.md:1953,1958,2013-2026` does document it.
<!-- END VERBATIM -->

---

## rev-policy-cache  — THE LOST ONE

- Axis: **Spec**
- Agent id: `ad84c7787e886f6d2`
- Reviewed: policy provenance (#186) and cache payload digest (#187), user stories 16-24
- Started 2026-08-05T14:29:46.784Z, finished **2026-08-05T14:39:20.675Z**  — after its parent returned at 14:38:35.302Z

Verbatim:

---

<!-- BEGIN VERBATIM -->
I'll start by fetching the spec and examining the diff.
**Verified by execution** (285 in-scope engine tests + 23 policy acceptance tests pass; source/vendor engine byte-identical), plus independent mutation probes.

**1. Policy provenance — MET.** `Minter.policy_digest` (`/Users/averyjones/Repos/skills/toolshed/.claude/worktrees/agent-ab321bca63ef8c93a/plugins/doc-lifecycle/engine/doclifecycle/approval.py:278`) is inside the approval digest (`:397-407`), so re-branding requires re-hashing. `AutoApplyPolicy.digest` (`.../policy.py:179-193`) is over id+classes. `_policy_provenance` (`approval.py:1507-1583`) reloads the declaration from the repo, compares digests, then recomputes `policy_eligibility` and demands **set equality both directions** (`approval.py:1567-1583`, reports `selected - eligible` and `eligible - selected`). Not per-record.

**2. Absent/changed policy — FAILS CLOSED.** Unreadable/absent → `approval-policy-changed` stale reason (`approval.py:1541-1552`); moved digest → same code (`:1553-1564`). `POLICY_REASON_CODES` is not in `PREIMAGE_REASON_CODES`, so `apply_edit_plan` refuses with `stale` (`applier.py:1463-1476`). A selection the policy doesn't derive is `Invalid`, not stale (`approval.py:1816-1818`).

**3. Generic mint — refused at BOTH doors.** `mint_approval_set` returns `approval-policy-minter-not-generic` before construction (`approval.py:944-957`); CLI help states it (`cli.py:757-765`). Validation independently refuses a `policy` brand with no provenance and a `human` carrying provenance (`approval.py:1134-1152`). US18/19/20 re-reached through the artifact for all six classes (`tests/engine/policy_test.py:961-1000`, `AnArtifactNoPolicyDerived`).

**4. Cache digest — COMPLETE.** `put()` declares `validate_report(...).digest` (`cache.py:223-231`), covering lineage, records at any depth, incomplete, scope, examined (`report.py:590-617`). I probed every payload field: nested record mutation, record digest, `evidence_boundary.sources` → `cache-miss-payload-digest-mismatch`; `status`, `schema_version`, injected `scope`/`examined`/extra keys → `cache-miss-invalid-payload` (cross-validated elsewhere). **No uncovered field found.**

**5. US24 — PARTIAL / implementation-wrong (real finding).** `.../doclifecycle/cache.py:268-272` catches only `OSError` around `open(path, encoding="utf-8").read()`. A cache entry with invalid UTF-8 bytes (torn write, disk corruption, poisoning) raises `UnicodeDecodeError` out of `cache.get()` — proven by probe. This contradicts US24 *"a corrupted cache entry to trigger re-evaluation rather than a hard crash"* and the module's own claim at `cache.py:38-41`: "never an exception raised in the middle of an audit." Fix: catch `(OSError, UnicodeDecodeError)` or read bytes; no test covers non-UTF-8 (`tests/engine/cache_test.py:121` covers only unparseable JSON).

**6. Versioning — MET for approvals** (`SCHEMA_VERSION = 3`, typed `approval-schema-pre-provenance` / `-pre-occurrence` refusals ahead of all structural checks, `approval.py:117-147, 1637-1652`). Cache got no version bump, but pre-digest entries fail closed as `cache-miss-undeclared-payload-digest` (`cache.py:321-336`) and it is documented in `engine/README.md` — acceptable.

**7. No scope creep.** No new eligibility classes; `POLICY_NEVER_ELIGIBLE_CODES = BLOAT_VERDICTS` unchanged (`approval.py:159`); sha256 only, no signatures/remote service.

**Minor:** `apply_edit_plan` (`applier.py:1418-1440`) has no `policy_path`, pinning revalidation to `DEFAULT_POLICY_PATH`, while `policy-mint`/`validate-approval` accept `--policy` (`cli.py:158-164`). Harmless for shipped templates (they pass the default path) but a consumer with a relocated declaration mints cleanly and then fails closed at apply.
<!-- END VERBATIM -->

---

## std-applier-approval

- Axis: **Standards**
- Agent id: `a5dd1cbe3a22b8fad`
- Reviewed: the engine's applier and approval modules
- Started 2026-08-05T14:29:20.542Z, finished **2026-08-05T14:36:57.083Z**

Verbatim:

---

<!-- BEGIN VERBATIM -->
I'll start by reading the authorities and the diff.
Read all authorities, ran both gates, executed both suite sets.

## Verified clean

- **Rule 1 (run-surface strings)** — clean. All five templates route every summary/PR string through `render-audit-summary.py` / `render-apply-summary.py` / `render-report.py`. The four `--jq` uses (`doc-apply.yml:115`, `doc-sync-upgrade.yml:88,322,325`) extract `gh` JSON fields, not render surface text. No heredoc writes `$GITHUB_STEP_SUMMARY`; the only direct append is `gh pr create … >> "$GITHUB_STEP_SUMMARY"` (`doc-apply.yml:671`, `doc-policy-apply.yml:538`) — the created PR URL, not a rendered string.
- **Rule 2** — `python3 .github/scripts/release-manifest.py` → `release manifest guard: 60 suite(s) wired, every gate criterion covered.` / `EXIT=0`. The literal command in the brief fails (`ImportError: Start directory is not importable: .../tests/scripts` — no `__init__.py`; CI never runs it that way). CI's actual runner: `python3 .github/scripts/run-script-suites.py` → `28/28 suite(s) passed`. `python3 -m unittest discover -s tests/engine -p '*_test.py'` → `Ran 1344 tests … OK`. All five new script suites carry `if __name__ == "__main__"` guards (guard failure mode #4).
- **Rule 4** — clean. No `git add -A`; both apply lanes stage via `git add --pathspec-from-file=…` (`doc-apply.yml:498`, `doc-policy-apply.yml:380`). Every `inputs.*` reaches shell through `env:` only, never `run:` text. Model jobs are `contents: read` + `id-token: write` (`doc-apply.yml:294-296`). The single `--force` (`doc-sync-upgrade.yml:418`) is the documented, test-scoped exemption.
- **Rule 5** — clean. `/Users/averyjones/Repos/skills/toolshed/.claude/worktrees/agent-ab321bca63ef8c93a/tests/engine/cache_test.py:29-31` imports `doclifecycle.cache` and `doclifecycle.report.current_lineage`; every symbol exercised (`cache.get/put/cache_key/entry_path`, `MISS_*`) is public and non-underscore, matching the established pattern in `applier_test.py`, `approval_test.py`, `bloat_test.py`.

## HARD VIOLATION — `doc-contract_test.py` is undocumented and mis-shelved

`/Users/averyjones/Repos/skills/toolshed/.claude/worktrees/agent-ab321bca63ef8c93a/tests/scripts/doc-contract_test.py` (+318, new). No `scheduling-doc-sync/scripts/doc-contract.py` exists, so it violates CLAUDE.md's `tests/scripts/<script-name>_test.py` convention. The existing carve-out is exhaustive and was not widened — CLAUDE.md:178 still reads:

> `Three suites cover the wiring itself rather than one script: workflow-permissions_test.py … install-parity_test.py … engine-capability_test.py`

The suite's own docstring calls it "A wiring suite, like engine-capability_test.py" — i.e. a fourth. CLAUDE.md's Conventions (normative; enumerates every `tests/scripts` suite) names the other four new suites (`verify-apply-bytes_test.py`, `apply-lane-parity_test.py`, `apply-recovery_test.py`, `check-repo-integrity_test.py`) and never names `doc-contract_test.py`. `grep -c doc-contract CLAUDE.md` → 0. Ironic given #194's stated goal is docs that stop contradicting the implementation.

## JUDGEMENT CALL — Duplicated Code / Shotgun Surgery across the apply lanes

16 `run:` blocks (144 shell lines) are byte-identical between `doc-apply.yml` and `doc-policy-apply.yml`, ×2 with the `.github/workflows/` copies. `apply-lane-parity_test.py` institutionalizes rather than removes it: adding one recovery step now means four identical edits. Defensible (GitHub Actions has no cross-workflow `run:` include short of a composite action), and the parity test is the right mitigation — but the duplication is real and worth naming.

## Minor — GATE_MANIFEST coverage is uneven

`.github/scripts/release-manifest.py:113-119` adds only `check-repo-integrity_test.py` to "workflow trust boundary". `apply-lane-parity_test.py` and `apply-recovery_test.py` guard the same boundary (force-push, staging confinement, branch reuse) and are unmapped, so deleting them stays green. Not a guard failure (exit 0; `policy-workflow_test.py` is likewise unmapped pre-existing), but the criterion is now under-declared relative to what protects it.
<!-- END VERBATIM -->

---

## std-cache-policy

- Axis: **Standards**
- Agent id: `ac849d82f81d2eb3b`
- Reviewed: the cache and policy diffs
- Started 2026-08-05T14:37:21.245Z, finished **2026-08-05T14:40:27.463Z**

Verbatim:

---

<!-- BEGIN VERBATIM -->
I'll start by reading the authorities and then the new scripts.
## Standards review — new/changed helper scripts (8ded7d7…HEAD)

### Rule 1 — stdlib-only python3: CLEAN
`verify-apply-bytes.py:70-77` imports `argparse, json, os, re, subprocess, sys, unicodedata, hashlib`. `check-repo-integrity.py:50-53` imports `argparse, json, subprocess, sys`. No third-party imports in either.

### Rule 2 — vendoring: THE FLAGGED DEFECT IS REFUTED
`check-repo-integrity.py` is **not** run from the install. Both invocations name the release-pinned marketplace clone:
- `/Users/.../.github/workflows/doc-audit.yml:243` — `python3 "${RUNNER_TEMP}/toolshed-marketplace/plugins/doc-lifecycle/skills/scheduling-doc-sync/scripts/check-repo-integrity.py"`
- `/Users/.../.github/workflows/doc-bloat-audit.yml:239` — same path.

The clone step (`doc-audit.yml:99-105`, `git clone --depth 1 --branch "v${VERSION}"`) is in the same `audit` job (job spans lines 65-353), so the path exists at line 243. Its absence from `wiring/` and `NEW_LANE_SCRIPTS` is deliberate and documented (`CLAUDE.md:74`, `scheduling-doc-sync/SKILL.md:86`); vendoring it would *fail* `install-parity_test.py` (7 tests, passing). `verify-apply-bytes.py` is correctly vendored (`apply-upgrade.py:145`) and byte-identical to `.doc-lifecycle/wiring/verify-apply-bytes.py`.

### Rule 3 — CONTEXT.md vocabulary: CLEAN
No `_Avoid_` term used in its avoided sense. The two near-hits are innocent: `verify-apply-bytes.py:257` "position" refers to argv position, not assertion occurrence; `check-repo-integrity.py:9` "claim" is ordinary English, not the assertion unit. `"status"` as a JSON wire key matches the established engine artifact convention (`applier.py:273`, `approval.py:421`), not the prose sense CONTEXT.md bars.

### Rule 4 — run-surface via tested script: CLEAN
`tests/scripts/verify-apply-bytes_test.py` (31 tests, pass) and `check-repo-integrity_test.py` (12, pass) both exist. The workflow diff introduces no inline run-surface string — the only `>> "$GITHUB_STEP_SUMMARY"` hunks are pre-existing `gh pr create` stdout redirects.

### Rule 5 / Duplicated Code — ONE REAL FINDING
**JUDGEMENT CALL — Duplicated Code.** `_unsafe_path_reason` is *code-identical* (verified by diff with comments/docstrings stripped — zero differing lines) between:
- `plugins/doc-lifecycle/skills/scheduling-doc-sync/scripts/verify-apply-bytes.py:316-344`
- `plugins/doc-lifecycle/skills/scheduling-doc-sync/scripts/render-apply-summary.py:492-520`

Both live in the same directory and are both vendored into `.doc-lifecycle/wiring/`. Independence from the engine's `paths.authorize_path` is the stated (and sound) design; independence from the *sibling script in the same folder* is not argued anywhere and buys nothing — a shared module in `scripts/` would preserve the engine-independence while removing the copy. The two new scripts otherwise do not overlap: integrity uses `git diff`/`ls-files` status only; byte verification hashes blobs from the object store.

**JUDGEMENT CALL — inconsistent hardening of one concern.** `check-repo-integrity.py:67-78` (`_git`) runs git with inherited environment and no timeout. Its sibling `verify-apply-bytes.py:172-193` scrubs `GIT_DIR`/`GIT_WORK_TREE`/… (`REDIRECTING_VARS`, lines 98-107) and applies `TIMEOUT_SECONDS = 30`, giving explicit rationale for both. The integrity gate is the more security-critical of the two and has the weaker invocation; a hung git there blocks the audit job with no typed refusal.

**JUDGEMENT CALL (minor) — Speculative Generality.** `render-report.py` `render_upgrade_pr_title` delegates verbatim to `render_upgrade_commit_subject`; a second subcommand producing byte-identical output. The docstring argues the seam; low weight.

### Clean axes
Mysterious Name, Primitive Obsession, Data Clumps, Long Function, Repeated Switches, Message Chains: no findings worth raising. The `(stage, code, message, details)` refusal tuple and the `{code, message, location}` problem dict deliberately mirror the engine's `Problem` shape.
<!-- END VERBATIM -->

---

