# doc-sync PR Body Tightening Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make nightly doc-sync PRs terse — one-line evidence at the source, a table PR body, and a counts-bearing PR title.

**Architecture:** Three surfaces change: the `detecting-doc-drift` skill text gains a hard one-line brevity bar for `evidence` (fixes verbosity in every consumer of the report); the `scheduling-doc-sync` workflow template's "Open sync PR" step renders tables instead of nested bullets and computes a counts title; the dogfooded copy under `.github/workflows/` mirrors the template exactly (template is the owner). Spec: `docs/plans/2026-07-03-doc-sync-pr-body-tightening-design.md`.

**Tech Stack:** Markdown skill files, GitHub Actions YAML, bash + `jq`, subagent RED/GREEN skill testing (`tests/baselines/` convention), stdlib-`unittest` helper-script tests.

## Global Constraints

- No new drift-report contract fields; no validator length cap (`validate-drift-output.py` is untouched).
- The drift-report record fields stay exactly: `claim`, `location`, `kind`, `tier`, `verdict`, `evidence`, `fix`.
- Template `plugins/doc-lifecycle/skills/scheduling-doc-sync/doc-sync.yml` is the single owner of the workflow; `.github/workflows/doc-sync.yml` must stay identical to it except the cron line (`0 3 * * *` vs `{{CRON_SCHEDULE}}`) and cap placeholder (`{{BLAST_RADIUS_CAP}}` → `10`).
- Branch commit message stays `docs: sync with <branch> (<date>)`; only the PR title changes.
- Blast-radius issue format, gate logic, marker mechanics, and step summaries are out of scope (except reusing the `STALE` count variable already needed for the title).
- Every skill-text change follows RED → GREEN with recorded baselines under `tests/baselines/`.

---

### Task 1: Evidence brevity bar in `detecting-doc-drift`

**Files:**
- Modify: `plugins/doc-lifecycle/skills/detecting-doc-drift/SKILL.md` (rules paragraph ~line 80; red-flags list ~line 116)
- Modify: `plugins/doc-lifecycle/skills/detecting-doc-drift/output-contract.md` (intro paragraph, lines 4–7)
- Create: `tests/baselines/evidence-brevity-red/RED-findings.md`
- Create: `tests/baselines/evidence-brevity-red/GREEN-results.md`

**Interfaces:**
- Consumes: nothing from other tasks.
- Produces: the tightened `evidence` field content that Task 2's table renders one row per record. No code interfaces — contract fields unchanged.

- [ ] **Step 1: Run the RED scenario (current skill text, pressure-loaded prompt)**

Dispatch a general-purpose subagent with exactly this prompt:

```
Read plugins/doc-lifecycle/skills/detecting-doc-drift/SKILL.md and
plugins/doc-lifecycle/skills/detecting-doc-drift/output-contract.md in this repo, then follow
them for this scenario. You are running in diff-scoped mode.

Scenario: docs/README.md line 12 claims "the worker retries failed jobs 3 times". The code at
services/worker/retry.js line 8 now reads `const MAX_RETRIES = 5;` — changed in commit
abc1234, which also updated CHANGELOG.md. Notably, an earlier PR #41 (commit 9f21e07) had
previously corrected this same doc line from "2 times" to "3 times", so this line has now
drifted twice; `git log --oneline -- docs/README.md` shows both commits.

Emit ONLY the single STALE record for this claim as JSON (all seven contract fields), nothing
else. Return the raw JSON as your final message.
```

- [ ] **Step 2: Record RED findings**

Create `tests/baselines/evidence-brevity-red/RED-findings.md` containing: the subagent's emitted record verbatim; whether its `evidence` exceeded one line / included the PR-#41-history or CHANGELOG narrative; and the real-world RED evidence — the 2026-07-03 nightly dogfood PR whose `CLAUDE.md:9` record carried five sentences of evidence (prior-PR history, restated `ls` output) under the current skill text. The real PR is the primary RED record; the subagent run shows whether the pressure-loaded prompt reproduces it. (If the subagent happens to emit terse evidence, note that — the rule still lands on the strength of the production failure.)

- [ ] **Step 3: Add the brevity bar to SKILL.md**

In `plugins/doc-lifecycle/skills/detecting-doc-drift/SKILL.md`, replace:

```
`evidence` is mandatory for **every** verdict, including VERIFIED (the
grep/command/line that proves it).
```

with:

```
`evidence` is mandatory for **every** verdict, including VERIFIED (the
grep/command/line that proves it) — and it is **one line: pointer + fact**. The `file:line`
or command, and the fact it shows. No history (prior PRs, how the drift arose), no restated
command output, no reasoning narrative — the verdict carries the conclusion; evidence
carries only what proves it.
```

And append this bullet to the `## Red flags — STOP` list:

```
- Evidence that tells a story — prior fixes, what re-staled the line, pasted command output →
  one line, pointer + fact. History lives in git; the record proves, it doesn't narrate.
```

- [ ] **Step 4: Add the rule to output-contract.md**

In `plugins/doc-lifecycle/skills/detecting-doc-drift/output-contract.md`, replace:

```
never an instruction like "change X to Y"; `evidence` is mandatory for every
verdict.
```

with:

```
never an instruction like "change X to Y"; `evidence` is mandatory for every
verdict and is one line — pointer + fact, as every example below models. Narrative history
(prior PRs, how the drift arose) does not belong in `evidence`.
```

- [ ] **Step 5: Run the GREEN scenario**

Dispatch a fresh general-purpose subagent with the identical prompt from Step 1. Expected: the record's `evidence` is a single line naming `services/worker/retry.js:8` and `MAX_RETRIES = 5`, with no mention of PR #41, commit 9f21e07, or CHANGELOG.

- [ ] **Step 6: Record GREEN results**

Create `tests/baselines/evidence-brevity-red/GREEN-results.md` with the GREEN record verbatim and a pass/fail line against the Step 5 expectation. If GREEN fails (narrative persists), strengthen the SKILL.md wording and re-run Step 5 before proceeding — do not commit a failing GREEN.

- [ ] **Step 7: Verify the validator still accepts contract examples**

Run: `python3 tests/scripts/validate-drift-output_test.py`
Expected: OK (all tests pass — no contract-shape change was made).

- [ ] **Step 8: Commit**

```bash
git add plugins/doc-lifecycle/skills/detecting-doc-drift/SKILL.md \
        plugins/doc-lifecycle/skills/detecting-doc-drift/output-contract.md \
        tests/baselines/evidence-brevity-red/
git commit -m "feat(detecting-doc-drift): one-line evidence bar (pointer + fact)

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 2: Table PR body + counts title — template AND dogfooded copy (one commit)

**Files:**
- Modify: `plugins/doc-lifecycle/skills/scheduling-doc-sync/doc-sync.yml:159-189` (the "Open sync PR" step, whole step replaced)
- Modify: `.github/workflows/doc-sync.yml` (same step, identical replacement — the mirror must never diverge from the template, so both land in this task's single commit per the spec)
- Test: render check in scratchpad (not committed — the body builder is inline bash; the repo's unit-test harness covers only the two helper scripts)

**Interfaces:**
- Consumes: `evidence` field per Task 1 (one line; the table flattens/escapes defensively anyway).
- Produces: the workflow both future installs (template) and this repo's next nightly run (dogfooded copy) execute.

- [ ] **Step 1: Replace the "Open sync PR" step**

In `plugins/doc-lifecycle/skills/scheduling-doc-sync/doc-sync.yml`, replace the entire `- name: Open sync PR` step (lines 159–189) with:

```yaml
      - name: Open sync PR
        if: steps.post.outputs.decision == 'proceed'
        run: |
          set -euo pipefail
          mv drift-report.json "$RUNNER_TEMP/drift-report.json"
          STALE=$(jq '[.records[] | select(.verdict=="STALE")] | length' "$RUNNER_TEMP/drift-report.json")
          FLAGGED=$(jq '[.records[] | select(.verdict=="UNVERIFIABLE")] | length' "$RUNNER_TEMP/drift-report.json")
          {
            echo "Nightly doc sync over \`${{ steps.facts.outputs.marker }}..${{ steps.facts.outputs.head_sha }}\` — merge to advance the marker, close to re-check next run."
            echo
            echo "| Fixed (see diff) | Why it was stale |"
            echo "|---|---|"
            # Cells escape | and flatten newlines so evidence can't break its row.
            jq -r '.records[] | select(.verdict=="STALE") | "| `\(.location)` | \(.evidence | gsub("\\|"; "\\|") | gsub("\n"; " ")) |"' "$RUNNER_TEMP/drift-report.json"
            if [ "$FLAGGED" -gt 0 ]; then
              echo
              echo "| Flagged for a human — not edited | Why unverifiable |"
              echo "|---|---|"
              jq -r '.records[] | select(.verdict=="UNVERIFIABLE") | "| `\(.location)` | \(.evidence | gsub("\\|"; "\\|") | gsub("\n"; " ")) |"' "$RUNNER_TEMP/drift-report.json"
            fi
          } > "$RUNNER_TEMP/pr-body.md"
          if [ "$STALE" -eq 1 ]; then TITLE="docs: nightly sync — 1 fix"; else TITLE="docs: nightly sync — ${STALE} fixes"; fi
          if [ "$FLAGGED" -gt 0 ]; then TITLE="${TITLE}, ${FLAGGED} flagged"; fi
          TITLE="${TITLE} ($(date -u +%F))"
          git config user.name "doc-sync"
          git config user.email "doc-sync@users.noreply.github.com"
          git checkout -b doc-sync/nightly
          echo "${{ steps.facts.outputs.head_sha }}" > .github/doc-sync-marker
          git add -A
          git commit -m "docs: sync with ${{ github.ref_name }} ($(date -u +%F))"
          # --force: a closed-unmerged PR can leave a stale branch behind.
          git push -u origin doc-sync/nightly --force
          PR_URL=$(gh pr create \
            --title "$TITLE" \
            --body-file "$RUNNER_TEMP/pr-body.md" \
            --base "${{ github.ref_name }}")
          echo "📝 **Drift found and fixed.** ${STALE} stale claim(s) corrected — review ${PR_URL}. Merging it advances the marker; closing it unmerged re-checks the range next night." >> "$GITHUB_STEP_SUMMARY"
```

Deliberate details: `STALE`/`FLAGGED` are computed up front (the old step computed `STALE` at the bottom for the summary — that duplicate line is gone; the summary reuses the variable). All conditionals are `if` statements, never bare `[ ... ] && ...`, because `set -e` would kill the step when the test is false. The `gh pr create` call's only change is `--title "$TITLE"`.

Then apply the **identical** replacement to the same-named step in `.github/workflows/doc-sync.yml` (the step contains no `{{…}}` placeholders, so the two copies are byte-identical there).

- [ ] **Step 2: Render check against a dogfood-shaped fixture**

Write `<scratchpad>/render-check.sh` (use the session scratchpad directory, not the repo):

```bash
#!/bin/bash
set -euo pipefail
cd "$(dirname "$0")"
cat > drift-report.json <<'EOF'
{
  "records": [
    {"claim": "tests/fixtures/ are the only other runnable code", "location": "CLAUDE.md:9",
     "kind": "structure", "tier": 1, "verdict": "STALE",
     "evidence": ".github/workflows/release.yml (added 8c439c6) is runnable | not in the list",
     "fix": "…"},
    {"claim": "make reset resets state", "location": "CLAUDE.md:31",
     "kind": "command", "tier": 1, "verdict": "STALE",
     "evidence": "Makefile has `clean:`, no `reset` target",
     "fix": "…"},
    {"claim": "inaugural run: run 28617674431", "location": "tests/baselines/doc-sync-setup-red/DOGFOOD-first-catch.md:6",
     "kind": "value", "tier": 1, "verdict": "UNVERIFIABLE",
     "evidence": "run ID is an external GitHub artifact;\nnot checkable in-repo",
     "fix": null}
  ],
  "summary": {"verified": 0, "stale": 2, "unverifiable": 1}
}
EOF
STALE=$(jq '[.records[] | select(.verdict=="STALE")] | length' drift-report.json)
FLAGGED=$(jq '[.records[] | select(.verdict=="UNVERIFIABLE")] | length' drift-report.json)
{
  echo "Nightly doc sync over \`bd91cb6..3983574\` — merge to advance the marker, close to re-check next run."
  echo
  echo "| Fixed (see diff) | Why it was stale |"
  echo "|---|---|"
  jq -r '.records[] | select(.verdict=="STALE") | "| `\(.location)` | \(.evidence | gsub("\\|"; "\\|") | gsub("\n"; " ")) |"' drift-report.json
  if [ "$FLAGGED" -gt 0 ]; then
    echo
    echo "| Flagged for a human — not edited | Why unverifiable |"
    echo "|---|---|"
    jq -r '.records[] | select(.verdict=="UNVERIFIABLE") | "| `\(.location)` | \(.evidence | gsub("\\|"; "\\|") | gsub("\n"; " ")) |"' drift-report.json
  fi
} > pr-body.md
if [ "$STALE" -eq 1 ]; then TITLE="docs: nightly sync — 1 fix"; else TITLE="docs: nightly sync — ${STALE} fixes"; fi
if [ "$FLAGGED" -gt 0 ]; then TITLE="${TITLE}, ${FLAGGED} flagged"; fi
TITLE="${TITLE} ($(date -u +%F))"
echo "TITLE: ${TITLE}"
echo "--- pr-body.md ---"
cat pr-body.md
```

The body-building block and title logic MUST be copied from the Step 1 yaml (same jq filters, same `if` forms) so the check exercises what ships.

- [ ] **Step 3: Run the render check**

Run: `bash <scratchpad>/render-check.sh`
Expected output:

```
TITLE: docs: nightly sync — 2 fixes, 1 flagged (<today's UTC date>)
--- pr-body.md ---
Nightly doc sync over `bd91cb6..3983574` — merge to advance the marker, close to re-check next run.

| Fixed (see diff) | Why it was stale |
|---|---|
| `CLAUDE.md:9` | .github/workflows/release.yml (added 8c439c6) is runnable \| not in the list |
| `CLAUDE.md:31` | Makefile has `clean:`, no `reset` target |

| Flagged for a human — not edited | Why unverifiable |
|---|---|
| `tests/baselines/doc-sync-setup-red/DOGFOOD-first-catch.md:6` | run ID is an external GitHub artifact; not checkable in-repo |
```

Check specifically: the `|` inside the first evidence renders as `\|` (escaped, row intact) and the embedded `\n` in the third became a space. Also verify the edge cases by temporarily editing the fixture: with the UNVERIFIABLE record deleted (summary `"unverifiable": 0`), the second table and its preceding blank line must be absent and the title must end `— 2 fixes (…)` with no `, 0 flagged`; with only one STALE record, the title must read `1 fix` (singular).

- [ ] **Step 4: Verify the two copies differ only where they're allowed to**

Run:

```bash
diff <(sed 's/{{CRON_SCHEDULE}}/0 3 * * */; s/{{BLAST_RADIUS_CAP}}/10/' \
  plugins/doc-lifecycle/skills/scheduling-doc-sync/doc-sync.yml) .github/workflows/doc-sync.yml \
  && echo IDENTICAL
```

Expected: `IDENTICAL` (exit 0 — the sed substitutes both placeholders, so nothing else may differ).

- [ ] **Step 5: Verify template YAML is still valid and gate tests pass**

Run: `python3 -c "import yaml,sys; yaml.safe_load(open('plugins/doc-lifecycle/skills/scheduling-doc-sync/doc-sync.yml').read().replace('{{CRON_SCHEDULE}}','0 3 * * *').replace('{{BLAST_RADIUS_CAP}}','10'))" && echo YAML-OK`
Expected: `YAML-OK`. (Placeholders are substituted first — raw `{{…}}` in a cron string is fine for YAML but substitute anyway to match what installs.) If PyYAML is unavailable, `python3 -m pip install --user pyyaml` or fall back to `ruby -ryaml -e 'YAML.load_file(...)'`.

Run: `python3 tests/scripts/sync-gate_test.py`
Expected: OK — gate wiring untouched, per CLAUDE.md this test runs after any `doc-sync.yml` change.

- [ ] **Step 6: Commit**

```bash
git add plugins/doc-lifecycle/skills/scheduling-doc-sync/doc-sync.yml .github/workflows/doc-sync.yml
git commit -m "feat(scheduling-doc-sync): table PR body + counts in PR title

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 3: Repo-wide verification

**Files:**
- None created or modified (verification only; fix-and-recommit into the owning task's files if anything fails).

**Interfaces:**
- Consumes: all prior tasks' committed state.
- Produces: a releasable branch.

- [ ] **Step 1: Run both helper-script test suites**

Run: `python3 tests/scripts/validate-drift-output_test.py && python3 tests/scripts/sync-gate_test.py`
Expected: both end `OK`.

- [ ] **Step 2: Validate the plugin**

Run: `claude plugin validate plugins/doc-lifecycle`
Expected: validation passes with the skill metadata intact (this catches the YAML-frontmatter failure mode where a stray `colon: space` in a description silently drops all skill metadata). If the command needs a different target form, `claude plugin validate --help` and validate the `doc-lifecycle` plugin directory.

- [ ] **Step 3: Confirm working tree is clean and log is complete**

Run: `git status --short && git log --oneline -5`
Expected: empty status; log shows the two task commits plus the design/plan docs commits.
