# Issue #57 Review Remediation Implementation Plan

> Status: ready

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Close the seven P1 and six Standards findings from the issue #57 release review: three approval/applier authority holes (fixed in code), the skill→engine schema migration (both detecting skills cut over to the engine document model), a file-bound lifecycle-state contract, and the documentation/dedup cleanups — with the auto-apply lane and scheduled bloat cadence explicitly descoped in the authoritative issue comment.

**Architecture:** All engine work happens in `plugins/doc-lifecycle/engine/doclifecycle/` (stdlib-only, tests at `tests/engine/*_test.py` via discovery). Skill work happens in `plugins/doc-lifecycle/skills/`, with helper-script suites at `tests/scripts/<name>_test.py`. Every engine edit must be re-vendored byte-identical to `.doc-lifecycle/wiring/engine/` before `install-parity_test.py` will pass. Run-surface strings render only via tested scripts, never inline YAML.

**Tech Stack:** Python 3 stdlib only (no deps), `unittest`, GitHub Actions YAML, Markdown skills.

## Global Constraints

- Engine package is stdlib-only; no new dependencies anywhere.
- Engine tests: `python3 -m unittest discover -s tests/engine -p '*_test.py'` from repo root. Script suites: `python3 tests/scripts/<name>_test.py`.
- Engine tests exercise only the two public seams (library function, `python3 -m doclifecycle` subprocess); do not add suites at private seams.
- Use CONTEXT.md vocabulary in engine code and tests (report, approval set, applier, minter, document kind, assertion unit; check its _Avoid_ lists).
- The vendored engine at `.doc-lifecycle/wiring/engine/` must remain byte-identical to `plugins/doc-lifecycle/engine/` (whole tree). Re-vendor after any engine change: `rsync -a --delete plugins/doc-lifecycle/engine/ .doc-lifecycle/wiring/engine/` (then re-run `python3 tests/scripts/install-parity_test.py`).
- Docs in this repo follow the writing-docs contract: every line a verifiable claim; no aspirational claims.
- Commit after each task with a conventional message; stage only the files the task names (`git add <explicit paths>`, never `-A`).
- Line references below were verified 2026-07-28 and may drift a few lines as earlier tasks land; anchor by the quoted code, not the number.

---

### Task 1: Policy-minter eligibility gate (Spec P1 — forged policy mint)

**Files:**
- Modify: `plugins/doc-lifecycle/engine/doclifecycle/approval.py` (structural validation ~line 641 `_minter`, `mint_approval_set` ~504, `validate_approval_set` ~975)
- Modify: `plugins/doc-lifecycle/engine/doclifecycle/policy.py` (~line where `NEVER_ELIGIBLE_CODES` is defined — repoint to the shared owner)
- Test: `tests/engine/approval_test.py`, `tests/engine/approval_cli_test.py`, `tests/engine/policy_test.py`

**Interfaces:**
- Produces: `approval.POLICY_NEVER_ELIGIBLE_CODES` — frozen tuple of the six bloat verdict codes (`"CUT"`, `"CONDENSE"`, `"EXTRACT-AND-MOVE"`, `"MERGE-DOC"`, `"RETIRE-DOC"`, `"DISTILL"`); new problem code `approval-policy-ineligible-record`.
- `policy.py` re-exports/consumes `approval.POLICY_NEVER_ELIGIBLE_CODES` (policy.py already imports approval as `approval_mod`, so this direction has no cycle). Keep the name `NEVER_ELIGIBLE_CODES` in policy.py as an alias so existing callers/tests keep working.

The rule (pure function of the artifact's own fields, so it runs in the **unconditional structural layer** of `validate_approval_set`, before the optional report/repo checks, and identically inside `mint_approval_set`): if `minter.kind == "policy"`, no approved record's `code` may be in `POLICY_NEVER_ELIGIBLE_CODES`. The precedent to follow is `approval-report-not-approvable` ("The minter's report-state refusal, re-run on the artifact") and `approval-scope-not-derived` — this file already re-runs producer defenses on the artifact because an approval set is an untracked file.

- [x] **Step 1: Write the failing library test** in `tests/engine/approval_test.py` (reuse `ApprovalTestCase`'s existing fixture helpers — it already has a way to build a report with records; follow the file's local idiom for minting):

```python
class PolicyBrandEligibility(ApprovalTestCase):
    """A policy-branded approval set may never select a bloat record.

    The restricted policy-mint door already refuses this; these tests close
    the generic door and the artifact itself (issue #57 review, P1)."""

    def test_generic_mint_refuses_policy_brand_on_bloat_record(self):
        # Build a report whose one record has code "CUT" (see how
        # policy_test.py constructs its CUT-record report and reuse that
        # construction here).
        result = mint_approval_set(
            self.cut_report, [self.cut_digest], repo_root=self.repo_root,
            minter=Minter(kind="policy", id="nightly-policy"),
        )
        self.assertIsInstance(result, Invalid)
        self.assertIn("approval-policy-ineligible-record",
                      [p.code for p in result.problems])

    def test_validate_refuses_hand_forged_policy_brand(self):
        # Mint legitimately as a human, then rewrite the minter field on the
        # artifact file — the hand-edit a producer-side check cannot see.
        approval = self.mint_human_cut_approval()
        payload = json.loads(approval_text)
        payload["minter"] = {"kind": "policy", "id": "forged-policy"}
        result = validate_approval_set(payload)  # match the file's call idiom
        self.assertIsInstance(result, Invalid)
        self.assertIn("approval-policy-ineligible-record",
                      [p.code for p in result.problems])

    def test_policy_brand_on_drift_stale_record_still_mints(self):
        # The honest path stays open (honest-path probe): STALE is eligible.
        result = mint_approval_set(
            self.stale_report, [self.stale_digest], repo_root=self.repo_root,
            minter=Minter(kind="policy", id="nightly-policy"),
        )
        self.assertNotIsInstance(result, Invalid)
```

(Adapt names to the fixture helpers actually present in `approval_test.py` — the digest/report construction exists; do not invent a parallel fixture.)

- [x] **Step 2: Run to verify failure**: `python3 -m unittest tests.engine.approval_test.PolicyBrandEligibility -v` → the two refusal tests FAIL (mint currently succeeds).
- [x] **Step 3: Implement.** In `approval.py`: define `POLICY_NEVER_ELIGIBLE_CODES` near `MINTER_KINDS`; add a `_policy_eligibility_problems(minter, records)` helper returning one `Problem(code="approval-policy-ineligible-record", message=..., location=f"records[{i}]")` per offending record — message should say what and why in the file's voice, e.g. `f"a policy minter may never approve a {code} record — bloat judgments are semantic review a standing policy cannot perform; only a human approves value judgments"`. Call it from both `mint_approval_set` and the structural layer of `validate_approval_set`.
- [x] **Step 4: Repoint policy.py** — replace its own `NEVER_ELIGIBLE_CODES` literal with `NEVER_ELIGIBLE_CODES = approval_mod.POLICY_NEVER_ELIGIBLE_CODES` (single owner; the hedge dies).
- [x] **Step 5: CLI + gate tests.** In `approval_cli_test.py`, alongside `test_a_policy_may_be_named_as_the_minter` (~line 118, which uses a drift STALE record and stays green), add `test_a_policy_brand_on_a_bloat_record_is_refused` invoking `mint-approval --minter-kind policy` against a CUT-record report, asserting exit 1 and `approval-policy-ineligible-record` in output. In `policy_test.py`'s `WhatAPolicyMayNeverMint` (~345), add a case that goes through the **generic** door (`mint_approval_set` with a policy `Minter`), so the release-gate criterion "provably cannot mint for a bloat finding" is proven against both doors.
- [x] **Step 6: Run the three suites**: `python3 -m unittest tests.engine.approval_test tests.engine.approval_cli_test tests.engine.policy_test -v` → all PASS.
- [x] **Step 7: Commit** — `fix(engine): policy minters can never select bloat records, at mint and on the artifact`.

---

### Task 2: Plan completeness — no silently omitted approval records (Spec P1)

**Files:**
- Modify: `plugins/doc-lifecycle/engine/doclifecycle/applier.py` (`_validate_plan` ~722–810, `RECORD_REMEDIES` ~106–128)
- Test: `tests/engine/applier_test.py`

**Interfaces:**
- Produces: problem codes `plan-record-not-executed` (an approval record no usable operation names) and `plan-remedy-incomplete` (a composite remedy missing a required leg); a module table `REQUIRED_REMEDY_OPERATIONS = {MERGE_DOC: (OP_MOVE, OP_RETIRE)}` beside `RECORD_REMEDIES` (MERGE-DOC is today's only composite; the table makes the next one a one-line change).

- [x] **Step 1: Write failing tests** in `applier_test.py`, following its existing fixture idiom (the suite already builds approval+plan pairs; the review reproduction built a 2-record approval with a 1-record plan from these same fixtures):

```python
class PlanCompleteness(...existing applier fixture base...):
    def test_plan_omitting_an_approved_record_is_refused(self):
        # approval approves records A and B; plan carries only A's operation
        ...build via existing helpers...
        self.assertIn("plan-record-not-executed", codes)
        self.assertIn("docs/b.md", the_problem.message)  # names what was dropped

    def test_merge_doc_plan_with_only_the_retirement_leg_is_refused(self):
        # MERGE-DOC approval; plan carries retire-document but no
        # move-with-provenance — the reproduction that destroyed the source
        self.assertIn("plan-remedy-incomplete", codes)

    def test_merge_doc_plan_with_both_legs_applies(self):
        # honest-path probe: move + retire together still lands clean

    def test_full_coverage_plan_still_applies(self):
        # honest-path probe: every approved record named -> clean
```

- [x] **Step 2: Run to verify the two refusal tests fail** (today both scenarios apply `clean`).
- [x] **Step 3: Implement in `_validate_plan`** after the per-operation binding loop (~804): compute `unexecuted = set(by_digest) - {op["record"] for op in operations}` → one `plan-record-not-executed` problem per record, message naming the record's code and path ("an approval set is the whole mandate: a plan that silently drops an approved record would let the run report work it did not do"). Then for each approved record whose code is in `REQUIRED_REMEDY_OPERATIONS`, require every listed op among that record's operations → `plan-remedy-incomplete` ("MERGE-DOC is one composite act — a move and a retirement; either leg alone is a different, unapproved change").
- [x] **Step 4: Run suite** → PASS. Also re-run `tests/scripts/render-apply-summary_test.py` — its counts become truthful via this refusal, no renderer change expected.
- [x] **Step 5: Commit** — `fix(engine): refuse edit plans that omit approved records or split composite remedies`.

---

### Task 3: Post-write confinement against written paths, not approval scope (Spec P1)

**Files:**
- Modify: `plugins/doc-lifecycle/engine/doclifecycle/applier.py` (post-write check ~1318–1330)
- Test: `tests/engine/applier_test.py` (race tests ~815–844 are the template)

**Interfaces:**
- Consumes: `_written_paths(operations)` and `_unaccounted_problem(...)`, both already in the file (the already-applied branch at ~1254–1257 uses exactly this pair — mirror it).

- [x] **Step 1: Write the failing race test**, copying the convention of the existing race test at `applier_test.py:815–844` (`stray-concurrent.md`, which hooks `worktree_changes` to inject a write between the applier's write and its post-write read) — but aim the concurrent write at an **approved-but-unplanned in-scope path** (record B's target, where the plan covers only record A after Task 2 is bypassed by making both records genuinely planned… no: keep it two records, plan covering both, but the concurrent write lands *unapproved content* on record B's path before B's operation is checked — simplest deterministic form: single-record approval for `docs/a.md`, plan for `docs/a.md`, concurrent write to `docs/b.md` **while `docs/b.md` is in the approval scope** via a second approved record whose operation the plan also carries but which writes different content; if that shape is awkward, the review's exact reproduction shape — two-record approval, one-record plan — remains constructible by temporarily building the plan through the internal seam the existing race test uses). Assert: refusal (the existing `apply-unconfined-change` code or a sibling), rollback (both files back to preimage), nothing in `changed_paths`.
- [x] **Step 2: Run to verify it fails** (today: `clean`, unapproved edit in `changed_paths`).
- [x] **Step 3: Implement**: in the post-write branch (~1318), after the scope check, add `_unaccounted_problem(sorted(set(changed) - _written_paths(operations)))` mirroring ~1254–1257, and roll back on violation exactly as the scope violation path does.
- [x] **Step 4: Keep the existing outside-scope race test green**; run the applier suite → PASS.
- [x] **Step 5: Commit** — `fix(engine): post-write confinement compares the diff to the plan's written paths`.

---

### Task 4: File-bound lifecycle state for planning documents (Spec P1)

**Files:**
- Modify: `CONTEXT.md` (document-model section, planning kind ~86–88)
- Modify: `plugins/doc-lifecycle/engine/doclifecycle/context.py` (`build_context_index`)
- Modify: `plugins/doc-lifecycle/engine/doclifecycle/bloat.py` (`_Recorder._status` ~891)
- Modify: `plugins/doc-lifecycle/skills/detecting-doc-bloat/references/planning-artifacts.md`
- Test: `tests/engine/bloat_test.py` (subclass `RecorderTestCase`), `tests/engine/context_test.py`

**Interfaces:**
- Produces: the marker contract — a planning document's lifecycle state is a block-quote unit whose normalized text starts with `Status:`, value one of `("pending-implementation", "ready")`, found the same way drift finds the narrative anchor (first matching block-quote unit via segmentation, drift.py:1152–1156 is the template — NOT a literal line-1 read). Absent or malformed marker ⇒ file-bound state is `pending-implementation` (fail-safe: never actionable). The context index exposes it (e.g. `index.lifecycle_status(path)` or a field on the planning document's entry — follow context.py's existing per-document structure). New refusal code `bloat-status-not-file-bound`.
- The design decision this encodes: **the file is the authority; the model is a reporter.** A model's DISTILL `status` must equal the file's marker. Evidence (the grep for landed symbols) now serves the *human*: a record whose evidence shows the implementation landed while the marker still says `pending-implementation` is the signal to flip the marker — and flipping it is a human, git-approved edit, which is what makes `ready` unforgeable by the model.

- [x] **Step 1: Write failing engine tests**:

```python
# tests/engine/bloat_test.py
class LifecycleStateIsFileBound(RecorderTestCase):
    # RecorderTestCase's docs/plans/p.md fixture gains variants:
    # one opening "> Status: ready", one "> Status: pending-implementation",
    # one with no marker.
    def test_ready_verdict_against_pending_marker_is_refused(self):
        # file says pending (or has no marker); model says ready
        result = self.record([self.verdict(verdict=bloat.DISTILL,
                                           status="ready")])
        self.assertIn("bloat-status-not-file-bound", problem_codes(result))

    def test_ready_verdict_against_ready_marker_records(self):
        # honest path: marker says ready, verdict says ready -> finding
    def test_pending_verdict_against_absent_marker_records(self):
        # fail-safe default: no marker == pending-implementation
    def test_pending_verdict_against_ready_marker_is_refused(self):
        # symmetry: the model may not hold a plan back either — the record
        # must state what the file states
```

Plus `context_test.py`: the index reports `ready` / `pending-implementation` / default for the three fixture variants, and a malformed value (`> Status: shipped`) reads as the default.

- [x] **Step 2: Run to verify failure.**
- [x] **Step 3: Implement**: marker extraction in `context.build_context_index` (planning-kind documents only; reuse the segmenter, mirror drift.py's `ANCHOR_PREFIX` pattern with `STATUS_PREFIX = "Status:"`); cross-check in `_status()` after the enum check: `file_status = self.index.lifecycle_status(path)`; mismatch → `self.bad("bloat-status-not-file-bound", f"the planning document's own marker says {file_status!r} — lifecycle state lives in the file (CONTEXT.md: content-coupled facts stay in the file), and a verdict may report it, never assert it", where)`.
- [x] **Step 4: Amend CONTEXT.md** planning-kind line to name the marker: planning "(temporary; carries lifecycle state as a `> Status: <pending-implementation|ready>` block-quote marker, absent meaning pending; ends in distillation or retirement)". Keep the _Avoid_ list.
- [x] **Step 5: Rewrite `planning-artifacts.md`'s derivation section**: the record's `status` **copies the file's marker**; the grep evidence proves whether the marker is *current*; "implementation landed but marker says pending" → emit `pending-implementation` with evidence naming the landed symbols and the note that the marker is stale (the human flips it, then a later audit emits `ready`). Update its Red flags to match ("a `ready` status the file's marker does not carry → the engine refuses it; do not transcribe your grep into `status`").
- [x] **Step 6: Run** bloat + context suites → PASS. **Commit** — `feat(engine): planning lifecycle state is file-bound; verdicts report it, never assert it`.

---

### Task 5: Narrative-anchor paths go through the canonical path policy (Standards P2)

**Files:**
- Modify: `plugins/doc-lifecycle/engine/doclifecycle/drift.py` (`_anchor_references` ~1048–1066)
- Test: `tests/engine/drift_test.py`

- [x] **Step 1: Write failing tests**: anchor references `docs\guide.md`, `./docs/guide.md`, `-rf.md`, `C:/x/guide.md` are **skipped as non-path prose** (extraction-filter semantics preserved — silently not treated as references), while `docs/guide.md` still resolves. Follow drift_test.py's existing anchor-test fixtures.
- [x] **Step 2: Verify failure** (today the bad spellings pass the ad-hoc filter and surface as unresolvable-reference findings or get checked under non-canonical spellings).
- [x] **Step 3: Implement**: in `_anchor_references`, replace the ad-hoc checks (leading `/`/`~`, `..` component, literal space) with `paths.repository_relative_problem(token)` — a token with any problem is skipped, matching the in-file principle stated at drift.py:701–705 ("paths.py is the single owner of what a repository-relative path is"). Keep the non-path-bare-word heuristics that decide whether a token *looks like* a path.
- [x] **Step 4: Run drift suite** → PASS. **Commit** — `fix(engine): anchor reference candidates go through the canonical path policy`.

---

### Task 6: Documentation contradiction fixes (Standards P2/P3)

**Files:**
- Modify: `plugins/doc-lifecycle/engine/README.md` (~line 7)
- Modify: `CLAUDE.md` (~line 155)
- Modify: `README.md` (repo root, ~line 97)

- [x] **Step 1:** engine README: "Nothing here writes to a repository." → scope the claim to git and name the exception, e.g. "git is read-only here; the applier — below — is the one component that writes files, and it writes the working tree directly, never the index." Verify the sentence five lines later still reads coherently.
- [x] **Step 2:** CLAUDE.md ~155: "the dogfooded `.github/` install" → "the dogfooded install (`.doc-lifecycle/` plus the three lane workflows under `.github/workflows/`)".
- [x] **Step 3:** root README ~97: "you get the staged diff back" → "you get the working-tree diff back — the applier never stages; committing it is the change approval".
- [x] **Step 4:** Grep for other instances: `grep -rn "staged diff" README.md plugins/ docs/` (fixing-docs SKILL.md's instance is Task 10's). **Commit** — `docs: fix writer/staging/install-location contradictions found in #57 review`.

---

### Task 7: Migrate detecting-doc-drift to the engine verdicts contract (Spec P1, drift half)

**Files:**
- Modify: `plugins/doc-lifecycle/skills/detecting-doc-drift/SKILL.md` (steps ~49–54, contract section ~88–119, handoff ~21–25)
- Modify: `plugins/doc-lifecycle/skills/detecting-doc-drift/output-contract.md` (worked example)
- Rewrite: `plugins/doc-lifecycle/skills/detecting-doc-drift/scripts/validate-drift-output.py`
- Rewrite: `tests/scripts/validate-drift-output_test.py`
- Modify: `.github/workflows/doc-audit.yml` (stale rationale comment, lines 99–105 only)

**Interfaces:**
- Consumes (fixed, do not redesign — extracted from the engine 2026-07-28): the verdicts artifact `{"schema_version": 1, "documents": [{"path", "status": "ok"|"failed", "verdicts": [...], "reason", "chunk"}]}`; per-verdict fields `("unit", "assertion_class", "verdict", "kind", "tier", "evidence", "fix")` with `REQUIRED_VERDICT_FIELDS = ("unit", "assertion_class")` and `VERDICT_ONLY_FIELDS = ("verdict", "kind", "tier", "evidence")`; classes `factual|normative|rationale|non-assertive`; verdicts `VERIFIED|STALE|UNVERIFIABLE`; kinds `command|path|symbol|behavior|structure|value`; tiers 1–3; evidence `{"source","line","observed","command"}` with `observed` required, exactly one of `source`/`command` for VERIFIED/STALE, no `line` with `command`, no shell syntax `;&|<>()$`\` in `command`; `fix` only and always for STALE (complete replacement text, LF rules per drift.py). `unit` is the **ordinal** integer from `segment` output (a digest string is tolerated by the engine but the skill teaches ordinals, as doc-audit.yml's prompt already does).
- The interactive flow becomes exactly the lane the CI already runs: `python3 -m doclifecycle drift-plan --repo . --mode full > drift-plan.json` → per living document `python3 -m doclifecycle segment --repo . --path <path>` → author `verdicts.json` → validate with this skill's validator → `python3 -m doclifecycle drift-audit --repo . --mode full --verdicts verdicts.json > drift-report.json`. The handoff to fixing-docs is `drift-report.json` and its record `digest` values.

- [x] **Step 1: Rewrite the validator test suite first** (RED): keep the file's black-box subprocess pattern (`rec()`/`run()` helpers, exit codes 0/1/2, stdin-or-file input) but the well-formed fixture becomes a verdicts artifact. Port each existing test class to its analogue: `ValidCases` (bare `documents` object passes; `schema_version` optional-but-1; failed entries need `reason`), `EnumViolations` (verdict/kind/tier/class), `FieldRules` (extra keys, missing `unit`/`assertion_class`, judged-unit completeness — all four `VERDICT_ONLY_FIELDS` or none for factual, none for non-assertive), `EvidenceRules` (new class: observed required, one-citation rule, command+line refusal, shell-syntax refusal), `FixRule` (STALE-only, non-empty, LF/CR/NUL rules — shape-level only; span-ownership stays the engine's), `BadInput`. Success stdout prints a recomputed `summary:` JSON line (counts of verified/stale/unverifiable across all documents) for automation to gate on, as today.
- [x] **Step 2: Run new suite against old script** → FAIL everywhere (RED confirmed).
- [x] **Step 3: Rewrite `validate-drift-output.py`** to those rules. Shape-only: it cannot check ordinals against a plan and must not try — the engine refuses what it can't. Docstring states the division: "this validator catches shape violations before dispatch; `drift-audit` is the authority."
- [x] **Step 4: Run suite** → PASS.
- [x] **Step 5: Rewrite SKILL.md's contract + steps** to the flow above. The verification method (tiers, escalation, "verified means you ran the command", writing-docs bar on every `fix`) is unchanged and stays. Delete the wrapped `{records, summary}` contract. Update the fixing-docs handoff sentence: "**`fixing-docs`** consumes the engine report this skill's audit writes — record digests are the handoff." Rewrite `output-contract.md`'s worked example in the verdicts shape (a STALE command unit, a VERIFIED behavior unit with a command citation, a non-assertive unit, a failed document entry).
- [x] **Step 6: doc-audit.yml** — replace the seven-line rationale comment (99–105) with: the skill now carries this contract natively; the prompt keeps spelling the shape inline because a headless lane states its own output contract (self-explaining), not because the skill's is wrong. Do not touch the prompt or any `run:` block. Run `python3 tests/scripts/audit-workflow_test.py` and `python3 tests/scripts/workflow-permissions_test.py` to confirm nothing pinned the old comment.
- [x] **Step 7: Commit** — `feat(drift-skill): migrate to the engine verdicts contract; retire the legacy wrapped-records shape`.

---

### Task 8: `audit_bloat` library seam + `bloat-audit` CLI (Spec P1, bloat engine half)

**Files:**
- Modify: `plugins/doc-lifecycle/engine/doclifecycle/bloat.py`
- Modify: `plugins/doc-lifecycle/engine/doclifecycle/cli.py`
- Test: `tests/engine/bloat_test.py`, `tests/engine/bloat_cli_test.py`

**Interfaces:**
- Produces:
  - `bloat.load_bloat_verdicts(path)` → payload or `Invalid` (`bloat-verdicts-unreadable`); accepted file shape `{"schema_version": 1 (optional), "verdicts": [...]}` — refusal `bloat-verdicts-invalid-shape` otherwise, mirroring drift's `_verdict_entries` top-level discipline.
  - `bloat.audit_bloat(repo_root, verdicts, registry_path=DEFAULT_REGISTRY_PATH)` → validated `Report` or `Invalid`. Composition (the docstring pattern at bloat.py:244–248 — composition in the library so the command stays one call): `build_context_index` → `report.current_lineage(...)` (mirror how `audit_drift` at drift.py:1326 builds lineage/evidence boundary; bloat declares no evidence commands) → `record_verdicts(index, lineage, verdicts)` → on success `validate_report(result.report_payload(lineage), registry_path=...)`. `verdicts` is required — there is no "planless" bloat audit; a missing verdicts list is a usage error at the CLI, not an empty report.
  - CLI `bloat-audit` with `--repo`, `--registry` (via `_add_corpus_arguments`), `--verdicts` (required); handler mirrors `_drift_audit` (load, `Invalid` short-circuit, one library call); registered after `bloat-plan` (~cli.py:420) with `set_defaults(run=..., render=None)`.
- Record codes in the resulting report are the six bloat verdicts; `mint-approval` then consumes it by record digest exactly as for drift — this is what makes fixing-docs' step 1 real for bloat.

- [x] **Step 1: Failing library tests** in `bloat_test.py` — new class `AuditBloatComposesTheReport(RepoTestCase)`: a valid CUT verdict list yields a `Report` whose `records[0]["code"] == "CUT"` and whose lineage carries the registry digest; an invalid verdict list returns `Invalid` with the recorder's codes intact; the report validates (`schema_version == 1`, records carry 64-hex `digest`).
- [x] **Step 2: Failing CLI tests** in `bloat_cli_test.py` — new class `BloatAuditCommand(RepoTestCase)` following `BloatPlanCommand`'s four-test template: agrees-with-the-library (byte-equal JSON), a semantic assertion (a CUT record's digest is mintable: pipe into `mint-approval` in-process or assert digest shape), invalid registry exits 1 with `status == "invalid"`, missing `--verdicts` exits 2.
- [x] **Step 3: Run** → FAIL. **Step 4: Implement** per interfaces. **Step 5: Run bloat + cli suites** → PASS.
- [x] **Step 6: Commit** — `feat(engine): bloat-audit — verdicts in, validated engine report out`.

---

### Task 9: Migrate detecting-doc-bloat to the engine; retire POLICY (Spec P1, bloat skill half)

**Files:**
- Modify: `plugins/doc-lifecycle/skills/detecting-doc-bloat/SKILL.md`
- Modify: `plugins/doc-lifecycle/skills/detecting-doc-bloat/output-contract.md`
- Modify: `plugins/doc-lifecycle/skills/detecting-doc-bloat/references/planning-artifacts.md` (policy-chunk section), `references/verdict-lenses.md` (POLICY references, if any)
- Rewrite: `plugins/doc-lifecycle/skills/detecting-doc-bloat/scripts/plan-chunks.py` (drop policy mode; keep sweep machinery)
- Rewrite: `plugins/doc-lifecycle/skills/detecting-doc-bloat/scripts/validate-bloat-output.py`
- Rewrite: `tests/scripts/plan-chunks_test.py`, `tests/scripts/validate-bloat-output_test.py`
- Modify: `docs/guides/auditing-doc-bloat.md` (seven verdicts → six; POLICY row out; new flow)
- Modify: `.doc-lifecycle/audit-scope.json` (drop `policy_scope` if present — consumer judgment tier, ours to edit)

**Interfaces:**
- Consumes: Task 8's `bloat-audit` and the engine verdict shape (fields `id, verdict, path, units, evidence, destination, proposal, status, scope, sample`; six verdicts, no POLICY; `FORBIDDEN_VERDICT_FIELDS = ("files", "members", "occurrences", "contention")`). Bulk directory retirement is now an enumerable-scope `RETIRE-DOC` (`scope` selector from `SCOPE_SELECTORS = ("set", "glob", "kind")`) — the "working replacement for bulk directory retirement" the 2026-07-27 decisions.md entry requires to land **in the same change** that retires `POLICY` and `policy_scope` from all four places it names (SKILL.md, plan-chunks.py, validate-bloat-output.py, the guide).
- `units` are unit digests: workers get them from `python3 -m doclifecycle segment --repo . --path <path>` output.
- Chunk-worker seam becomes `{"chunk": "<id>", "verdicts": [...]}` per chunk file; assemble merges verdict arrays and writes the verdicts artifact `{"schema_version": 1, "verdicts": [...]}` for `bloat-audit`. Worker `id`s stay unique across chunks via assemble's renumbering (keep the `B{n}` idiom).
- plan-chunks.py keeps: config-driven sweep inventory, hints, turn budgets, `--emit-prompt`/`--emit-turns`, resume via `--results-dir`, `max_chunks` ceiling, manifest `{"schema": 1, "chunks", "pending"}`. It loses: `policy_scope`, `POLICY_PROMPT`, policy chunks, the `files` slice shape. Its sweep prompt gains the segment-derived `units` instruction.

- [x] **Step 1: Rewrite the two script test suites** (RED): port class-by-class, deleting `PolicyRecords`/`PolicyChunks` and adding `ScopeRetirement` (a scope RETIRE-DOC verdict passes the final validator; a `files` key is refused with the engine's own framing — "asserted membership is what an enumeration replaces"), `DistillStatus` (status DISTILL-only, both values), `ChunkSeam` (new `{"chunk", "verdicts"}` shape; a verdict whose `path` is outside the chunk's doc list is refused), `Assembly` (merges to the verdicts artifact; `--allow-partial` still records unswept).
- [x] **Step 2: Run against old scripts** → FAIL (RED). **Step 3: Rewrite both scripts** to the interfaces. `validate-bloat-output.py` validates the engine verdict shape *by shape* (enums, field presence per verdict, DISTILL status enum, scope-verdict exclusivity, forbidden fields), with the same 0/1/2 exit contract; `bloat-audit` remains the authority (docstring says so). **Step 4: Run** → PASS.
- [x] **Step 5: Rewrite SKILL.md**: contract section → engine verdicts + the `bloat-audit` step (interactive flow: `bloat-plan` (engine) or plan-chunks.py for the dispatch ergonomics → workers emit verdicts per chunk → assemble → `python3 -m doclifecycle bloat-audit --repo . --verdicts bloat-verdicts.json > bloat-report.json` → handoff = report digests to fixing-docs). Delete the POLICY doc-kind bullet and the migration disclaimer (30–36) — it migrated. Update the frontmatter/body `fixing-docs` references (keep — that is the real door now). Rewrite `output-contract.md`'s worked example in the engine shape including one scope RETIRE-DOC and one DISTILL with file-bound status. Update `planning-artifacts.md` (drop its policy-chunk section; Task 4 already rewrote its status derivation) and the guide.
- [x] **Step 6: Run the full script-suite set** (`python3 .github/scripts/run-script-suites.py` if runnable locally, else each `tests/scripts/*_test.py`) → PASS. **Commit** — `feat(bloat-skill): migrate to the engine verdict contract; POLICY and policy_scope retire together`.

---

### Task 10: fixing-docs — cite the contract, fix the heading, keep the spine (Standards P2 + Spec P1 closure)

**Files:**
- Modify: `plugins/doc-lifecycle/skills/fixing-docs/SKILL.md`

**Interfaces:**
- Consumes: Tasks 7–9's reports (both skills now hand over engine reports; step 1's `mint-approval --report` is now real for both), Task 4's file-bound status.

- [x] **Step 1: De-restate.** Remove the operation-vocabulary list (~63–64), the remedy table (~68–76), the per-op field sets and preimage/postimage mechanics (~105–141), and the exit-code/refusal-code enumerations (~50–53, 159) — replace each with a one-line pointer into the engine README's "Approval sets" / "The applier" sections (the file already carries the pointer at line 24; honor it). Keep: the four-step spine, the step commands, the refusals section's *behavioral* rules (what the skill must refuse to do), the distillation section, red flags, rationalization table. What stays must be skill-level conduct, not engine contract.
- [x] **Step 2: Fix step 4** heading: "Present the staged diff" → "Present the working-tree diff"; body already says the applier never stages.
- [x] **Step 3: Update step 1's intake** to name both inputs ("a drift or bloat engine report — `drift-audit` / `bloat-audit` output; record digests are the selection") and the DISTILL note (~245) to cite the file-bound marker: a `pending-implementation` record is never actionable, and the marker in the planning file is the authority.
- [x] **Step 4: Re-verify no divergence**: every claim the skill still makes about engine behavior must be checkable against `engine/README.md` (grep the specific claims). Run `python3 tests/scripts/render-apply-summary_test.py` (unaffected, but the skill quotes its run surface). **Commit** — `fix(fixing-docs): cite the applier contract instead of restating it; working-tree diff, not staged`.

---

### Task 11: One strict-JSON loader, one hash helper (Standards P3)

**Files:**
- Modify: `plugins/doc-lifecycle/engine/doclifecycle/digest.py` (gains the shared loader)
- Modify: `plugins/doc-lifecycle/engine/doclifecycle/applier.py` (~209–247), `report.py` (~1400–1455), `approval.py` (~1363–1409)
- Test: `tests/engine/report_test.py`, `tests/engine/applier_test.py`, `tests/engine/approval_test.py` (existing loader tests pin behavior; add the divergence-closing cases)

**Interfaces:**
- Produces: `digest.load_strict_json(path, *, unreadable_code, unparseable_code, nesting_code, max_nesting=64)` → `(payload, None)` or `(None, Problem)` — report.py's variant is the model (dedicated `RecursionError` code + `MAX_NESTING`); the three call sites parameterize their problem codes (`report-unreadable`/`report-unparseable`/`report-nesting-too-deep`, approval's codes gaining a real `approval-nesting-too-deep`, applier's gaining `plan-nesting-too-deep` — adding codes is fine; changing existing codes is not, check each suite's pins first and keep every currently-pinned code).
- Removes: `applier._sha256` (use `digest.sha256_bytes` at its two call sites, ~882 and ~1301); the three `_reject_constant` copies.

- [x] **Step 1: Failing tests**: deep-nested JSON fed to the applier plan loader and the approval loader yields the *dedicated* nesting code (today: applier mislabels it as syntax; approval reuses its generic code). Existing loader tests must stay green.
- [x] **Step 2–4:** Implement, run the three suites plus report's, PASS. **Commit** — `refactor(engine): one strict-JSON loader and one hash helper own what four files duplicated`.

---

### Task 12: Re-vendor, full verification, version bump

**Files:**
- Modify: `.doc-lifecycle/wiring/engine/` (wholesale), `.doc-lifecycle/installed-version`, `plugins/doc-lifecycle/.claude-plugin/plugin.json`, `plugins/doc-lifecycle/engine/doclifecycle/__init__.py`

- [x] **Step 1: Version bump**: `PLUGIN_VERSION` `0.43.0` → `0.44.0` (`__init__.py`), `plugin.json` version to match, `RULESET_VERSION` `6` → `7` (audit semantics changed: file-bound status, canonical anchor paths, policy-brand refusal). `.doc-lifecycle/installed-version` → `0.44.0`.
- [x] **Step 2: Re-vendor**: `rsync -a --delete plugins/doc-lifecycle/engine/ .doc-lifecycle/wiring/engine/`.
- [x] **Step 3: Full gate, in order** (fail → fix → rerun; report every result verbatim):

```bash
python3 -m unittest discover -s tests/engine -p '*_test.py'
```
```bash
for t in tests/scripts/*_test.py; do python3 "$t" || break; done
```
```bash
python3 .github/scripts/release-manifest.py
```
```bash
claude plugin validate plugins/doc-lifecycle
```
```bash
git diff --check
```

plus JSON-validity checks on `marketplace.json` / `plugin.json` (`python3 -m json.tool`).
- [x] **Step 4: Commit** — `chore(release): re-vendor engine, bump to 0.44.0 / ruleset 7`.

---

### Task 13: Independent continuity review + targeted re-GREEN

Fresh subagent per flow, none of whom wrote the code (no self-review): (1) interactive drift loop end-to-end on a fixture repo (drift-plan → segment → verdicts → drift-audit → mint-approval → apply-plan — the loop the review proved broken must now demonstrably run); (2) interactive bloat loop likewise, including one scope RETIRE-DOC and one DISTILL against a `> Status:` marker; (3) the headless audit lane read (doc-audit.yml against the migrated skill text — comment accuracy, no contract contradiction); (4) fixing-docs text vs engine README (zero restated-contract divergence remains); (5) the upgrade lane untouched-check (`git diff` scope audit: nothing outside the planned files changed). Targeted re-GREEN per the re-GREEN discipline: for each rewritten skill (drift, bloat, fixing-docs), one grader subagent runs the skill's decisive scenario from its baseline set and confirms the shipped text still teaches it. Findings → fix → re-run the affected gate from Task 12.

### Task 14: Decisions, GitHub closure, PR

- [x] **Step 1: decisions.md entries** (newest-first, house format — `## 2026-07-28 — <claim> (#57)`, bullets `Evidence:/Decided:/Rejected:/Still binds:/Code:`): (a) policy brand refused at mint and on the artifact; (b) plan completeness + written-paths confinement; (c) lifecycle state file-bound via `> Status:` marker; (d) both detecting skills on the engine contract, POLICY retired (supersede the 2026-07-27 entry — mark it superseded per the file's header convention, don't delete); (e) auto-apply lane and scheduled bloat cadence explicitly descoped to successor issues.
- [ ] **Step 2: Post to GitHub** (user-authorized 2026-07-28): amend the #57 authoritative comment (append an "Amendments — 2026-07-28" section: vendor path is `.doc-lifecycle/wiring/engine/` per #133; auto-apply wiring descoped to successor issue; scheduled bloat cadence descoped to successor issue; the seven review P1s' disposition). Create successor issues: "Wire the auto-apply policy lane" (notes #73 closed with only the engine half; cites the spec sentence it completes) and "Scheduled bloat audit cadence" (bloat-audit now exists; wiring it into doc-audit.yml is this issue). Comment on #73 linking its successor. **Partially landed:** the successor issues (#143, #144) are filed and #73 carries the linking comment; the #57 authoritative comment's own "Amendments — 2026-07-28" section has not been posted. Left unchecked until that amendment lands.
- [ ] **Step 3: PR** to `main` from this branch: title `fix: close the #57 release-review P1s — approval authority, applier completeness, skill→engine migration`; body lists finding→commit mapping, the two descopes, and the verification transcript summary; end with the required attribution footer. **Not yet landed:** no PR exists for this branch (`gh pr list --head ajones/issue-57-review-failures-b6b9e9` returns none as of this pass) — the branch was still absorbing the final whole-branch review's fix waves. Left unchecked.

## Self-Review Notes

- Spec coverage: review P1s 1–3 → Tasks 1–3; P1 4 (schema) → 7+8+9+10; P1 5 (auto-apply) → descope, Task 14; P1 6 (lifecycle) → Task 4; P1 7 (bloat cutover) → 8+9 (engine+skill) with scheduled cadence descoped in Task 14; Standards 1 → Task 10; 2 → Task 5; 3 (cache) → accepted as library-only, no code change (documented boundary already in engine README; revisit only if a CLI surface ever reaches it); 4 → Task 6; 5 → Tasks 6+10; 6 → Task 11.
- Order: Tasks 1–6 are parallel-safe (disjoint files; 2+3 share applier.py and run as one sequence). 7 ∥ 8 after 1–6; 9 after 8; 10 after 7+9; 11 after 1–3; 12–14 strictly last.
- The one deliberate non-fix: cache-dir placement (Standards claim 3) — verification showed no CLI/skill/workflow reaches it and the write API is documented; a location constraint without a consumer would be speculative (YAGNI).
