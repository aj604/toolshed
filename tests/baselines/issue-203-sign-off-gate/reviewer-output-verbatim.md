# Issue #203 — the three dispatched reviewers' aggregate output, verbatim

> Titled "aggregate" deliberately. An earlier version called these "the three reviewers' raw
> output", which concealed that two of the three are themselves summaries of a fan-out. The seven
> leaves are in `reviewer-leaf-output-verbatim.md`.

Retained because a disposition table written by the party under review is not evidence of an
independent review — it is the reviewed agent's account of one. #168's User Story 42 exists so
#57 closes "on evidence rather than implementation self-assessment", and a paraphrase cannot
discharge that. `tests/baselines/shadow-parity-gate/` sets the precedent: keep the raw artifact,
not a summary of it.

Everything below is each agent's final report exactly as returned, recovered from the session's
subagent transcripts (`~/.claude/projects/.../subagents/agent-<id>.jsonl`, the `assistant` text
blocks). Nothing is edited, reordered, or trimmed. `independent-reviews.md` holds the disposition
of each finding and is the file to read second.

## Dispatch record

| Role | Agent id | Model | Dispatched with |
|---|---|---|---|
| Standards | `a37d5c3995ee7c02d` | opus | the repo's documented standards sources + the Fowler smell baseline |
| Spec | `a3281ff30ced7ae50` | opus | instructions to fetch #57, #168, the ten child issues and merged PRs itself |
| Race-test audit (criterion 3) | `a869539bbcd452d7a` | opus | #168's surviving-bytes rule and the four suites carrying race tests |

All three were fresh `general-purpose` agents that authored none of the ten remediation fixes.
The Standards and Spec pair ran in parallel via the `mattpocock-skills:code-review` skill; the
race audit ran separately.

**This file is the aggregates, not the whole review — and one leaf was lost.**

Each axis fanned out again internally: Spec into five leaf reviewers, Standards into two. The
seven leaf reports are retained in **`reviewer-leaf-output-verbatim.md`**, which should be read
alongside this file.

The two findings the #203 pull-request review later raised — the `cache.get()` non-UTF-8 crash
and the `apply_edit_plan` `policy_path` asymmetry — appear nowhere in the three aggregates below.
**One of the Spec leaves found both.** `rev-policy-cache` (user stories 16-24, the #186 and #187
halves) returned at **14:39:20.675Z**, 45.4 seconds *after* its parent had already aggregated and
returned at 14:38:35.302Z. Its report opens finding 5 with
`**5. US24 — PARTIAL / implementation-wrong (real finding).**` and names the exact fix that
landed. Its parent never received it. Four of five Spec leaves landed in time; the only one that
found a real defect did not.

> **An earlier version of this paragraph said the opposite** — that "the three agents retained
> here never reported them", framing it as a reviewer blind spot. Every clause of that was true
> of the three retained agents and materially wrong about what happened. A reviewer looked, found
> it, wrote it up, and a race between a background agent and its parent's aggregation discarded
> the result. The correction is kept visible rather than silently applied, because a human closing
> #57 would have drawn precisely the wrong lesson about how reliable this apparatus is.
> `reviewer-leaf-output-verbatim.md` carries the full timeline and the lost report in full.

---

## Standards review

Agent `a37d5c3995ee7c02d`, verbatim:

---

<!-- BEGIN VERBATIM -->
I'll start by reading the documented standards, then the diff.
## Standards review — `8ded7d7...HEAD`

### HARD VIOLATIONS (documented standards)

**1. `tests/scripts/doc-contract_test.py` (new, 318 lines) is mis-shelved and undocumented.**
CLAUDE.md requires script suites at `tests/scripts/<script-name>_test.py`; no `doc-contract.py` exists. The carve-out for wiring suites is exhaustive and was not widened — CLAUDE.md:178 still reads *"Three suites cover the wiring itself rather than one script: `workflow-permissions_test.py` … `install-parity_test.py` … `engine-capability_test.py`"*, yet the file's own docstring calls itself "A wiring suite, like engine-capability_test.py". `grep -c doc-contract CLAUDE.md` → 0, while the diff *did* document the other four new suites. Ironic for a suite whose stated job (#194) is stopping docs contradicting the implementation.

**2. `tests/engine/policy_test.py:707-714` tests a private cross-module symbol.**
```python
original = approval_mod._mint_approval_set
approval_mod._mint_approval_set = spy
```
CLAUDE.md:257-258: engine suites *"test only the two public seams (the library function, and `python3 -m doclifecycle` as a subprocess)"*. Monkeypatching another module's underscore-private is neither.

**3. CLAUDE.md:259-262 is now false about the apply lane's renderer.**
It names `render-apply-summary.py` as the apply lane's run-surface script. `verify-apply-bytes.py:125-166` (`write_surface`/`refuse`) also appends apply-lane refusal Markdown to `$GITHUB_STEP_SUMMARY`. Tested (a suite exists) but the documented single owner is stale.

**4. `docs/decisions.md:1711` cites `docs/plans/HANDOFF.md`**, deleted by c75fd59. Dangling path claim.

### JUDGEMENT CALLS

- **Duplicated Code.** `_unsafe_path_reason` is code-identical between `verify-apply-bytes.py:316-344` and `render-apply-summary.py:492-520` (same directory, both vendored). `write_surface` likewise identical (`verify-apply-bytes.py:125-132` / `render-apply-summary.py:114-120`).
- **Inconsistent hardening of one concern.** `check-repo-integrity.py:67-78` runs git with inherited env and *no* timeout; sibling `verify-apply-bytes.py:172-193` scrubs `GIT_DIR`/`GIT_WORK_TREE`/… and applies `TIMEOUT_SECONDS`. The integrity gate is the more security-critical and has the weaker invocation.
- **Divergent Change / Mysterious Name.** `render-apply-summary.py` (now 1200 lines) gained `branch_name`, `remote_branch`, `existing_pull_request`, `recovery` — branch derivation and recovery-state decisions, not run-surface strings.
- **Doc/impl mismatch inside the diff.** `approval.py:301-303` says occurrences are *"one per approved unit"*; `_derive_occurrences`'s whole-document branch `chosen.extend(found)` yields more than one per unit when a unit repeats.
- **Middle Man.** `approval.mint_approval_set` is now a type-check + brand refusal that delegates wholly to `_mint_approval_set`.
- **Duplicated Code (workflows).** 16 `run:` blocks byte-identical between `doc-apply.yml` and `doc-policy-apply.yml`, ×2 with the `.github/workflows/` copies; `apply-lane-parity_test.py` institutionalizes rather than removes it. Defensible — Actions has no cross-workflow `run:` include.
- **Under-declared gate.** `release-manifest.py:113-119` adds only `check-repo-integrity_test.py`; `apply-lane-parity_test.py` and `apply-recovery_test.py` guard the same boundary unmapped.

### Clean, verified
Engine ↔ `.doc-lifecycle/wiring/engine/` byte-identical. Stdlib-only throughout (engine + both new scripts). No inline `jq`/heredoc run-surface strings. No `git add -A`; no `inputs.*` in any `run:`. `check-repo-integrity.py`'s non-vendoring is correct and documented (it runs from the release-pinned clone: `doc-audit.yml:243`). CONTEXT.md `_Avoid_` lists respected. `release-manifest.py` exit 0 (60 suites); 1344 engine tests and 28/28 script suites pass.
<!-- END VERBATIM -->

---

## Spec review

Agent `a3281ff30ced7ae50`, verbatim:

---

<!-- BEGIN VERBATIM -->
I'll start by fetching the authoritative spec and the diff.
Full gate rerun locally: **1344 engine tests OK, 28/28 script suites PASS.**

## Load-bearing claim: holds end to end

I traced the chain myself. `applier.py` re-reads each target at the write boundary against the captured preimage (`_write`, `apply-write-boundary-race`), re-reads final bytes after writing (`_certify`, `apply-postimage-not-on-disk`), returns those read-back digests as `ApplyResult.postimages` (empty on every refusal), and rollback is compare-aware (`_rollback` skips a path no longer holding this run's bytes). `doc-apply.yml:519/558` feeds that same `apply-result.json` to `verify-apply-bytes.py`, which compares real index blobs via `cat-file --batch` (`:449-461`), re-certifies the post-hook commit tree (`:582-607`), and `doc-apply.yml:637` pushes `${commit}:refs/heads/...` — the verified id, not `HEAD`. The `_approved_hull` min/max is genuinely deleted; passages are runs of consecutive occurrence ordinals read from HEAD. Cache digest covers lineage + nested records + incomplete + scope + examined. Policy provenance reloads the declaration and asserts exact set equality both directions (`approval.py:1568-1583`).

## (a) Missing / partial

1. **US12** — "every cited repository evidence source to come from the declared base commit." Nothing asserts `report.base_commit == --expected-head`; the binding rests only on no step existing between the gate (`doc-audit.yml:238`) and assembly (`:261`). Structural, unasserted.
2. **US28** — "finding identity to remain stable across harmless document reordering." Property holds (`finding.py:134-141` digests only code/path/units/lineage; segmenter untouched), but **no test reorders document content and asserts an unchanged finding digest**. Against US40 ("regression tests for every reproduced sign-off failure"), this one is guard-free.
3. **US26** — "ambiguous repeated occurrences refused *or explicitly selected*." Only refusal ships (`approval-occurrence-ambiguous`, `approval.py:768`); `cli.py` has no occurrence-selection flag, so the "explicitly selected" half exists only as a hand-writable artifact shape.
4. **US37** — "repository context no longer instructs agents to resume finished work." `docs/decisions.md:1028` and `:1711` still cite the deleted `docs/plans/HANDOFF.md` unpinned, unlike the `path @ <sha>` convention used at `docs/design-rationale.md:16,28`.
5. **US40 coverage pinning** — `.github/scripts/release-manifest.py:113-120` wires `check-repo-integrity_test.py` but not `verify-apply-bytes_test.py`, `apply-recovery_test.py`, or `apply-lane-parity_test.py`. Discovery runs them; no criterion names them, so a silent deletion would go unreported.

## (b) Scope creep

None material — every touched file traces to a story. Side note (repo convention, not #168): `docs/guides/scheduling-doc-sync.md:3`, `principles.md:3`, `auditing-doc-bloat.md:3` were edited in this diff but kept `> As of 2026-07-30 (0.45.0)` while describing 0.46.9 behavior.

## (c) Implementation looks wrong

6. **Run-surface fail-open.** `doc-audit.yml:455` / `doc-bloat-audit.yml:387` pass `--integrity` only under `[ -f … ]`, and the artifact download is `continue-on-error` (`:390`). A lost integrity artifact renders the summary with no integrity evidence rather than refusing — the one place the rendering defaults open. Low blast radius (the report only exists if the gate passed in-job).

Nothing found contradicts #57's distilled decisions: approval sets stay untracked artifacts, the applier stays sole writer, the registry stays closed-world, and policy minting is still refused for bloat at both doors.
<!-- END VERBATIM -->

---

## Race-test audit (criterion 3)

Agent `a869539bbcd452d7a`, verbatim:

---

<!-- BEGIN VERBATIM -->
I'll start by examining the diff range to find all race/concurrency tests.
## Scope of the sweep

`git diff 8ded7d7...HEAD` touches 22 test files. Race/concurrency/interference tests live in exactly four of them: `tests/engine/applier_test.py` (#183), `tests/scripts/apply-recovery_test.py` (#198, new file), `tests/scripts/verify-apply-bytes_test.py` (#191, new file), `tests/scripts/check-repo-integrity_test.py` (#185, new file). `apply-lane-parity_test.py` is static YAML parity only (no scenario execution); `approval_test.py`, `cache_test.py`, `policy_test.py`, `acceptance/scenario_policy_test.py` contain tamper/poison tests, not concurrency. Two pre-existing race tests in `applier_test.py` (`Confinement`) are *unchanged* in the range but are included for completeness since they cover the same seam.

Helper semantics that matter for grading: `self.tree(root)` (applier_test.py:70) returns `{relpath: raw bytes}` for the whole worktree, so `assertEqual(before, self.tree(self.repo))` **is** a whole-tree byte assertion. In `apply-recovery_test.py`, `remote_tip()` returns a commit SHA — content-addressed, so SHA equality pins the exact surviving tree bytes (it is not a path-set check), though no test reads the surviving file content back as text.

---

## A. `tests/engine/applier_test.py` (#183)

**1. `test_a_target_that_moved_before_the_write_is_a_typed_race_refusal` — /Users/averyjones/Repos/skills/toolshed/.claude/worktrees/agent-ab321bca63ef8c93a/tests/engine/applier_test.py:1089**
- BYTES: yes — `self.assertEqual(self.read(self.repo, DOC_A), theirs)` and `self.assertEqual(self.tree(self.repo), dict(before, **{DOC_A: theirs.encode("utf-8")}))`
- STATE: yes — `self.assertEqual(codes(result), ["apply-write-boundary-race"])`, `self.assertEqual(result.problems[0].location, DOC_A)`, `self.assertEqual(self.staged_paths(self.repo), [])`
- **BOTH**

**2. `test_a_target_replaced_before_certification_never_resolves_clean` — applier_test.py:1125**
- BYTES: yes, both rollback answers — `self.assertEqual(self.read(self.repo, new_doc), theirs)`, `self.assertEqual(self.read(self.repo, PLAN_DOC), PLAN_DOC_TEXT)`, `self.assertEqual(self.tree(self.repo), dict(before, **{new_doc: theirs.encode("utf-8")}))`, `self.assertNotIn(content, self.read(self.repo, new_doc))`
- STATE: yes — `self.assertEqual(codes(result), ["apply-postimage-not-on-disk"])`, `self.assertIn("left exactly as found", result.problems[0].message)`
- **BOTH** (the strongest test in the range)

**3. `test_a_clean_apply_certifies_the_bytes_it_read_back` — applier_test.py:1171** (certification, not a race)
- BYTES: by digest — `self.assertEqual(result.postimages, ((DOC_A, sha256_text(post)),))`
- STATE: `self.assertEqual(result.status, STATE_CLEAN, result)`, `self.assertTrue(again.already_applied)` — **BOTH**

**4. `test_a_retired_document_is_certified_as_absent` — applier_test.py:1185** — postimage `(PLAN_DOC, None)` + `STATE_CLEAN` — **BOTH** (non-race).
**5. `test_a_refused_run_certifies_nothing` — applier_test.py:1194** — `result.postimages == ()` + `STATE_STALE` — **BOTH** (non-race).

**Pre-existing, unchanged in range (same seam):**
- `test_unaccounted_change_after_the_write_fails_and_rolls_back` — applier_test.py:919 — `self.assertEqual(before, self.tree(self.repo))` + `self.assertIn("apply-unconfined-change", codes(result))` + `self.assertIn("rolled back", result.problems[0].message)` — **BOTH**
- `test_concurrent_write_outside_the_written_paths_rolls_back` — applier_test.py:950 — same pair of assertions (lines 1022–1027) — **BOTH**

---

## B. `tests/scripts/apply-recovery_test.py` (#198)

`assert_refused` (line 418) supplies the state half everywhere: `self.assertIn(f"`{code}`", run.surface(), run.transcript())` plus `self.assertNotIn("gh pr create", " ".join(run.gh_calls()))`.

| Test | Line | Bytes | State | Verdict |
|---|---|---|---|---|
| `test_a_first_run_creates_the_branch_and_opens_the_pull_request` | :439 | `self.assertEqual(self.remote_tip(), verified)` (tip == the commit verify-apply-bytes certified) | `self.assertIn("## Doc apply: branch created", run.surface())` | BOTH |
| `test_the_branch_stands_and_nothing_reviews_it` | :454 | only `self.assertIsNotNone(self.remote_tip(), "the push did not land")` | `self.assertIn("Open the pull request", failed[0])`, `"## Doc apply: branch created"` | **STATE-ONLY** |
| `test_the_branch_is_reused_and_the_pull_request_opened` | :466 | `self.assertEqual(self.remote_tip(), landed)` + `self.assertNotEqual(fh.read().strip(), landed)` | `self.assertIn("## Doc apply: branch reused", rerun.surface())` | BOTH |
| `test_an_open_pull_request_for_this_approval_is_idempotent_success` | :491 | none | `"branch reused"`, `"pull request already open"`, `self.assertNotIn("pr create", ...)` | **STATE-ONLY** |
| `test_a_matching_approval_on_a_conflicting_tree_is_refused` | :506 | `self.assertEqual(self.remote_tip(), planted, "a refused run moved the branch it refused")` | `assert_refused(run, "apply-bytes-not-certified")` + `"REFUSED at branch reuse"` | BOTH |
| `test_a_branch_carrying_no_approval_trailer_is_refused` | :515 | `self.assertEqual(self.remote_tip(), planted)` | `"apply-branch-approval-conflict"` | BOTH |
| `test_a_branch_carrying_another_approvals_trailer_is_refused` | :521 | `self.assertEqual(self.remote_tip(), planted)` | `"apply-branch-approval-conflict"` | BOTH |
| `test_the_same_postimages_on_another_base_are_refused` | :527 | `self.assertEqual(self.remote_tip(), planted)` | `"apply-branch-lineage-conflict"` | BOTH |
| `test_a_fast_forward_between_the_read_and_the_fetch_is_refused` | :554 | `self.assertEqual(self.remote_tip(), moved[0])` (the concurrent writer's commit survives intact) | `assert_refused(run, "apply-branch-moved")`, `self.assertIn("REFUSED at branch reuse", run.surface())`, `self.assertNotIn("branch reused", run.surface())` | BOTH |
| `test_a_branch_replaced_between_the_read_and_the_fetch_is_refused` | :569 | `self.assertEqual(self.remote_tip(), replaced[0])` | `assert_refused(run, "apply-branch-moved")` | BOTH |
| `test_an_open_pull_request_for_another_approval_is_refused` | :596 | `self.assertEqual(self.remote_tip(), landed)` | `"apply-pull-request-conflict"` | BOTH |
| `test_an_open_pull_request_aimed_at_another_base_is_refused` | :610 | none | `"apply-pull-request-conflict"` | **STATE-ONLY** |
| `test_two_open_pull_requests_on_one_branch_are_refused` | :621 | none | `"apply-pull-request-conflict"` | **STATE-ONLY** |

---

## C. `tests/scripts/verify-apply-bytes_test.py` (#191)

This script never writes to the repository, so "surviving bytes" has no rollback dimension; the transaction-state half is strong everywhere via `assert_refused` (line 141): `self.assertEqual(completed.returncode, 1, ...)`, `self.assertIn(f"`{code}`", self.surface())`, `self.assertIn("Nothing was pushed and no pull request was created", self.surface())`, and `self.assertFalse(os.path.exists(self.out), "a refused run left a commit id behind for the push to name")`.

| Test | Line | Bytes | State | Verdict |
|---|---|---|---|---|
| `test_a_faithful_index_and_commit_tree_pass_and_name_the_commit` | :154 | `self.assertEqual(verified, self.git("rev-parse", "HEAD").strip(), "the commit named for the push is not the one verified")` | `self.assertIn("Commit tree verified", self.surface())` | BOTH |
| `test_a_written_path_whose_bytes_did_not_change_is_still_verified` | :167 | none beyond exit 0 | `self.assertEqual(self.index(result).returncode, 0, self.surface())` | STATE-ONLY |
| `test_a_manifest_entry_git_does_not_hold_is_refused` | :178 | none | `"apply-bytes-not-certified"` + `self.assertIn("the index does not carry it", self.surface())` | STATE-ONLY |
| `test_an_approved_path_rewritten_before_staging_is_refused` (mutate-after-apply) | :188 | reported digest — `self.assertIn(sha256(AFTER), self.surface())` | `"apply-bytes-not-certified"` + `--out` unwritten | BOTH (digest-level) |
| `test_index_normalization_by_a_clean_filter_is_refused` | :197 | none | `"apply-bytes-not-certified"` | **STATE-ONLY** |
| `test_a_symlink_where_a_document_belongs_is_refused` | :207 | mode only — `self.assertIn("120000", self.surface())` | `"apply-bytes-not-certified"` | STATE + mode |
| `test_a_retired_document_still_in_the_index_is_refused` | :217 | none | `"apply-bytes-not-certified"` + `"the index still carries it"` | STATE-ONLY |
| `test_a_retired_document_written_back_before_the_commit_is_refused` | :224 | none | `"apply-bytes-not-certified"` + `"the commit tree still carries it"` | STATE-ONLY |
| `test_a_deletion_absent_from_both_boundaries_passes` | :236 | absence at both boundaries — `self.assertNotIn("docs/retired.md", self.git("ls-files"))`, `self.assertNotIn("docs/retired.md", self.git("ls-tree", "-r", "--name-only", "HEAD"))` | exit 0 both subcommands | BOTH |
| `test_a_hook_that_rewrote_and_restaged_a_target_is_refused` | :249 | none | `"apply-bytes-not-certified"` + `--out` unwritten | **STATE-ONLY** |
| `test_a_commit_carrying_an_uncertified_path_is_refused` | :263 | none | `"apply-commit-not-confined"` + `self.assertIn("docs/smuggled.md", self.surface())` | STATE-ONLY (+path) |
| `test_a_merge_commit_is_refused` | :275 | none | `"apply-commit-not-linear"` | STATE-ONLY |
| `test_a_matching_trailer_over_different_bytes_is_refused` | :415 | none | `assert_reuse_refused(..., "apply-bytes-not-certified")` + `"REFUSED at branch reuse"` | **STATE-ONLY** |
| `test_a_ref_that_holds_a_descendant_of_the_read_commit_is_refused` (the fail-open race) | :434 | reported surviving tip — `self.assertIn(advanced, self.surface())`, `self.assertNotEqual(advanced, existing)` | `assert_reuse_refused(..., "apply-branch-moved")` | BOTH (id-level) |
| `test_this_runs_own_earlier_result_is_reusable` | :399 | none | exit 0 + `"Existing branch verified"` | STATE-ONLY (honest path) |
| `test_a_refusal_falls_back_to_stdout_when_no_summary_is_set` | :482 | none | `self.assertIn("apply-bytes-not-certified", completed.stdout)` | STATE-ONLY |

(Remaining `TheManifestIsTheOnlyAuthority` / ref-shape tests at :292–:335, :422–:478 are malformed-input refusals, not races — all STATE-ONLY by design.)

---

## D. `tests/scripts/check-repo-integrity_test.py` (#185) — model-step interference

| Test | Line | Bytes | State | Verdict |
|---|---|---|---|---|
| `test_the_gate_never_repairs_what_it_refuses` | :230 | `self.assertEqual(f.read(), "PORT = 9090\n")` (exact surviving bytes of the interfering write) + `assertNotEqual(git status --porcelain, "")` | `self.assertEqual(self.run_gate(repo, head).returncode, REFUSED)` | BOTH |
| `test_a_dirtied_tracked_evidence_source_refuses_with_a_typed_reason` | :87 | none | `verdict["status"] == "refused"`, `self.assertEqual(self.codes(), ["evidence-integrity-tracked-modified"])`, `verdict["head"] == head`, location `src/server.py` | STATE-ONLY |
| `test_a_fresh_checkout_cannot_re_derive_the_failure` | :107 | none | REFUSED then VERIFIED + `dirty_codes == ["evidence-integrity-tracked-modified"]` | STATE-ONLY |
| `test_a_moved_head_is_refused_and_names_where_it_moved_to` | :198 | commit id — `verdict["problems"][0]["location"] == moved`, `verdict["expected_head"] == head` | `["evidence-integrity-head-moved"]` | BOTH (id-level) |
| `:134, :145, :156, :173, :191, :210, :240` | — | none | typed code lists / locations | STATE-ONLY |

---

## Verdict against the rule

**No test in the range is PATH-SET-ONLY.** Every race/interference test asserts a typed refusal code, status, or exit code, so none "calls a race fixed merely because the final path set is correct." The two headline #183 races (applier_test.py:1089, :1125) satisfy the rule in full and with the strongest form available (whole-worktree byte equality plus the typed code plus the rollback message).

**Tests that fail the letter of the rule (state asserted, surviving bytes not):**

1. `apply-recovery_test.py:491` `test_an_open_pull_request_for_this_approval_is_idempotent_success` — asserts only surface strings and the absence of `pr create`. Missing: `self.assertEqual(self.remote_tip(), landed)` against the stranded run's tip (the sibling at :466 has exactly this). Without it, a rerun that force-pushed its own commit and then found the open PR would still pass as "idempotent".
2. `apply-recovery_test.py:610` and `:621` (`...aimed_at_another_base_is_refused`, `two_open_pull_requests...`) — no tip assertion at all. Missing: capture `landed = self.remote_tip()` after the stranded run and assert it is unchanged after the refusal, as :596 does.
3. `apply-recovery_test.py:454` `test_the_branch_stands_and_nothing_reviews_it` — only `assertIsNotNone(self.remote_tip())`. Missing: assert the tip equals the commit in `verified-commit.txt` (as :439 does), so "the push landed" means the *verified* bytes landed rather than some commit.
4. `verify-apply-bytes_test.py:197` `test_index_normalization_by_a_clean_filter_is_refused` — asserts the code only. Missing: an assertion of what git actually holds vs. what was certified (e.g. `git show :docs/edited.md` == `"AFTER\n"` uppercased, or the certified `sha256(AFTER)` appearing in the surface as :188 does), so the test proves the *bytes* diverged rather than merely that some check failed.
5. `verify-apply-bytes_test.py:249` `test_a_hook_that_rewrote_and_restaged_a_target_is_refused` — code only. Missing: assert the committed blob is `"hooked\n"` (`git show HEAD:docs/edited.md`) alongside the certified `sha256(AFTER)` in the surface.
6. `verify-apply-bytes_test.py:415` `test_a_matching_trailer_over_different_bytes_is_refused` — code only, despite the scenario's whole point being different bytes under a matching trailer. Missing: assert the existing commit's tree still holds `"not what was approved\n"` and that the certified digest `sha256(AFTER)` is what the surface names.
7. `check-repo-integrity_test.py:87` / `:107` — the dirtied-evidence pair asserts the typed refusal but never that `src/server.py` still holds `"PORT = 9090\n"` at refusal time. `:230` covers that property once for the whole gate, so this is a redundancy gap rather than a hole; :87 would comply by adding the same read-back it already implies.

Note on grading convention: I counted commit-SHA equality (`remote_tip() == planted/moved/landed`, `verified == rev-parse HEAD`) as a surviving-bytes assertion, since a commit id is a cryptographic commitment to the exact tree. If the rule is read to require literal content read-back, then every `apply-recovery_test.py` row marked BOTH degrades to "id-level bytes", and the fix in each case is one extra `git show <tip>:docs/edited.md` comparison against the expected text.
<!-- END VERBATIM -->

---

