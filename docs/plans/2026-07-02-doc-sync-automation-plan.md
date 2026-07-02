# doc-sync-automation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship the auto-trigger layer for doc-lifecycle — a nightly GitHub Action (detect → gate → fix → evidence PR) installed per-repo by a new `scheduling-doc-sync` skill.

**Architecture:** Orchestration lives only in a shipped workflow template (`doc-sync.yml`); every branchy decision lives in a unit-tested stdlib script (`sync-gate.py`); doc judgment lives only in the already-published `detecting-doc-drift` / `fixing-doc-drift` skills, invoked headlessly. The installer skill copies files and seeds a SHA marker — it holds no doc judgment. Spec: `docs/plans/2026-07-02-doc-sync-automation-design.md`.

**Tech Stack:** Python 3 stdlib only (no deps), GitHub Actions YAML, `gh` CLI, headless `claude -p`, Markdown skills.

## Global Constraints

- Python scripts: `python3`, **stdlib only**, black-box subprocess tests (mirror `tests/scripts/validate-drift-output_test.py`).
- Skills are built test-first (Iron Law): RED baseline recorded **before** the SKILL.md is written; records under `tests/baselines/doc-sync-setup-red/`.
- The pipeline's output for doc edits is **PR-only** — never direct-commit doc edits to the default branch. The only default-branch push is the marker-only commit on a clean run.
- The marker (`.github/doc-sync-marker`) advances **only** via a clean run's direct commit or a merged sync PR. Installer upgrades never reset an existing marker.
- Single-owner rule: no detection/fixing method text duplicated into YAML prompts — prompts *invoke the skills by name*.
- Manifest JSON (`marketplace.json`, `plugin.json`) must stay valid; run `claude plugin validate` before finishing (skill frontmatter YAML: keep `description` a single line, no unquoted `: ` traps).
- Commits end with `Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>`.
- Repo root for all paths below: the toolshed worktree root.

---

### Task 1: RED baseline for `scheduling-doc-sync`

**Run this task in the main session** (it dispatches an observation subagent; it writes no product code).

**Files:**
- Create: `tests/baselines/doc-sync-setup-red/RED-findings.md`

**Interfaces:**
- Produces: the recorded baseline-failure list that Task 4's SKILL.md rules must answer point-by-point.

- [ ] **Step 1: Build a scratch target repo** (a copy of the taskflow fixture with its accurate docs, as a standalone git repo):

```bash
SCRATCH="$SCRATCHPAD/red-target"   # use the session scratchpad dir
mkdir -p "$SCRATCH"
cp -R tests/fixtures/taskflow/. "$SCRATCH/"
cp tests/baselines/bootstrap-green/agent1/CLAUDE.md tests/baselines/bootstrap-green/agent1/README.md "$SCRATCH/"
git -C "$SCRATCH" init -b main -q && git -C "$SCRATCH" add -A && git -C "$SCRATCH" -c user.name=red -c user.email=red@test commit -qm "baseline"
```

- [ ] **Step 2: Dispatch ONE baseline subagent (Sonnet, general-purpose, NO skill)** with exactly this prompt (substitute the scratch path):

> You are working in the git repo at `<SCRATCH>`. Its docs (CLAUDE.md, README.md) are accurate today. Set up **automated nightly documentation drift sync** for this repo: every night, unattended, it should detect doc claims the code no longer backs and open a GitHub PR fixing them, with evidence. The repo's owner uses the Claude Code `doc-lifecycle` plugin, which provides `detecting-doc-drift` (emits structured drift records) and `fixing-doc-drift` (applies them). Create whatever files the automation needs. Do not ask questions; make reasonable choices and finish.

- [ ] **Step 3: Grade the output against the predicted-failure checklist** and write `tests/baselines/doc-sync-setup-red/RED-findings.md`. For each item record YES/NO + a quote/line reference from the agent's output:

```markdown
# RED — baseline agent asked to wire nightly doc sync (no skill)

Agent: Sonnet, general-purpose, prompt in this file's appendix. Scratch repo: taskflow fixture + accurate docs.

| # | Predicted failure | Observed? | Evidence |
|---|-------------------|-----------|----------|
| 1 | Re-invents detection/fixing method inside YAML prompt text instead of invoking the skills by name | | |
| 2 | No last-synced marker → no idempotency story (re-runs re-detect the same range / PR spam) | | |
| 3 | Direct-commits doc edits to the default branch (or offers it as default) | | |
| 4 | No blast-radius stop (a wholesale-wrong doc set would become one giant PR) | | |
| 5 | No pending-work guard (yesterday's unreviewed PR + tonight's run pile up) | | |
| 6 | Evidence absent from PR body (edits not mapped to records) | | |

## Verdict
<which failures reproduced; which didn't; what this means for the skill's rules>

## Appendix: exact prompt
<paste>
```

- [ ] **Step 4: Commit**

```bash
git add tests/baselines/doc-sync-setup-red/
git commit -m "test(RED): baseline agent hand-rolls doc-sync wiring without the skill

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 2: `sync-gate.py` — gate decisions, TDD

**Files:**
- Create: `plugins/doc-lifecycle/skills/scheduling-doc-sync/scripts/sync-gate.py`
- Test: `tests/scripts/sync-gate_test.py`

**Interfaces:**
- Consumes: the drift report artifact shape from `detecting-doc-drift` — either a bare JSON array of records or `{"records": [...], "summary": {...}}`; records carry `verdict` ∈ {VERIFIED, STALE, UNVERIFIABLE}.
- Produces (Task 3's workflow relies on these exactly):
  - `sync-gate.py pre --commits N --open-prs N --open-issues N` → prints one token: `skip-empty` | `skip-pending` | `detect`
  - `sync-gate.py post --report FILE --cap N` → prints one token: `advance-marker` | `blast-radius` | `proceed`
  - Exit 0 with a decision on stdout; exit 2 on bad input (argparse errors, unreadable/invalid report, `--cap < 1`, negative counts).
  - `stale > cap` trips blast-radius; `stale == cap` proceeds. Stale is counted from records (never trusts `summary` — the validator already cross-checked it).

- [ ] **Step 1: Write the failing tests** at `tests/scripts/sync-gate_test.py`:

```python
#!/usr/bin/env python3
"""Black-box tests for scheduling-doc-sync's sync-gate.py.

Tests the script as a subprocess: real argv, real exit codes, real stdout.
Run: python3 tests/scripts/sync-gate_test.py
"""

import json
import os
import subprocess
import sys
import tempfile
import unittest

SCRIPT = os.path.join(
    os.path.dirname(__file__),
    "..", "..",
    "plugins", "doc-lifecycle", "skills", "scheduling-doc-sync",
    "scripts", "sync-gate.py",
)


def rec(verdict="VERIFIED"):
    return {
        "claim": "README mentions make test",
        "location": "README.md:5",
        "kind": "command",
        "tier": 1,
        "verdict": verdict,
        "evidence": "Makefile has `test:`",
        "fix": "make check" if verdict == "STALE" else None,
    }


def run(*argv):
    return subprocess.run(
        [sys.executable, SCRIPT, *argv], capture_output=True, text=True
    )


def report_file(payload):
    f = tempfile.NamedTemporaryFile(
        "w", suffix=".json", delete=False, encoding="utf-8"
    )
    f.write(payload if isinstance(payload, str) else json.dumps(payload))
    f.close()
    return f.name


def wrapped(records):
    counts = {"verified": 0, "stale": 0, "unverifiable": 0}
    for r in records:
        counts[r["verdict"].lower()] += 1
    return {"records": records, "summary": counts}


class PreGate(unittest.TestCase):
    def test_no_new_commits_is_skip_empty(self):
        r = run("pre", "--commits", "0", "--open-prs", "0", "--open-issues", "0")
        self.assertEqual(r.returncode, 0)
        self.assertEqual(r.stdout.strip(), "skip-empty")

    def test_empty_range_wins_over_pending(self):
        r = run("pre", "--commits", "0", "--open-prs", "1", "--open-issues", "1")
        self.assertEqual(r.stdout.strip(), "skip-empty")

    def test_open_pr_is_skip_pending(self):
        r = run("pre", "--commits", "5", "--open-prs", "1", "--open-issues", "0")
        self.assertEqual(r.returncode, 0)
        self.assertEqual(r.stdout.strip(), "skip-pending")

    def test_open_issue_is_skip_pending(self):
        r = run("pre", "--commits", "5", "--open-prs", "0", "--open-issues", "1")
        self.assertEqual(r.stdout.strip(), "skip-pending")

    def test_all_clear_is_detect(self):
        r = run("pre", "--commits", "5", "--open-prs", "0", "--open-issues", "0")
        self.assertEqual(r.returncode, 0)
        self.assertEqual(r.stdout.strip(), "detect")

    def test_negative_count_is_bad_input(self):
        r = run("pre", "--commits", "-1", "--open-prs", "0", "--open-issues", "0")
        self.assertEqual(r.returncode, 2)


class PostGate(unittest.TestCase):
    def test_zero_stale_is_advance_marker(self):
        path = report_file(wrapped([rec("VERIFIED"), rec("UNVERIFIABLE")]))
        r = run("post", "--report", path, "--cap", "10")
        self.assertEqual(r.returncode, 0)
        self.assertEqual(r.stdout.strip(), "advance-marker")

    def test_stale_within_cap_is_proceed(self):
        path = report_file(wrapped([rec("STALE"), rec("VERIFIED")]))
        r = run("post", "--report", path, "--cap", "10")
        self.assertEqual(r.stdout.strip(), "proceed")

    def test_stale_equal_to_cap_still_proceeds(self):
        path = report_file(wrapped([rec("STALE"), rec("STALE")]))
        r = run("post", "--report", path, "--cap", "2")
        self.assertEqual(r.stdout.strip(), "proceed")

    def test_stale_over_cap_is_blast_radius(self):
        path = report_file(wrapped([rec("STALE"), rec("STALE"), rec("STALE")]))
        r = run("post", "--report", path, "--cap", "2")
        self.assertEqual(r.returncode, 0)
        self.assertEqual(r.stdout.strip(), "blast-radius")

    def test_bare_array_report_is_accepted(self):
        path = report_file([rec("STALE")])
        r = run("post", "--report", path, "--cap", "10")
        self.assertEqual(r.stdout.strip(), "proceed")

    def test_stale_counted_from_records_not_summary(self):
        payload = wrapped([rec("STALE")])
        payload["summary"] = {"verified": 1, "stale": 0, "unverifiable": 0}  # lies
        path = report_file(payload)
        r = run("post", "--report", path, "--cap", "10")
        self.assertEqual(r.stdout.strip(), "proceed")

    def test_missing_report_is_bad_input(self):
        r = run("post", "--report", "/nonexistent/report.json", "--cap", "10")
        self.assertEqual(r.returncode, 2)

    def test_invalid_json_is_bad_input(self):
        path = report_file("not json{")
        r = run("post", "--report", path, "--cap", "10")
        self.assertEqual(r.returncode, 2)

    def test_non_record_shape_is_bad_input(self):
        path = report_file({"summary": {}})
        r = run("post", "--report", path, "--cap", "10")
        self.assertEqual(r.returncode, 2)

    def test_cap_below_one_is_bad_input(self):
        path = report_file(wrapped([rec("STALE")]))
        r = run("post", "--report", path, "--cap", "0")
        self.assertEqual(r.returncode, 2)


if __name__ == "__main__":
    unittest.main(verbosity=2)
```

- [ ] **Step 2: Run to verify failure**

Run: `python3 tests/scripts/sync-gate_test.py`
Expected: every test ERRORs (the script file does not exist yet).

- [ ] **Step 3: Implement** `plugins/doc-lifecycle/skills/scheduling-doc-sync/scripts/sync-gate.py`:

```python
#!/usr/bin/env python3
"""Gate decisions for the doc-sync nightly pipeline.

The workflow (doc-sync.yml) gathers facts via git/gh and performs side effects
(commit, PR, issue); this script owns every branchy decision in between so the
decision matrix is unit-testable instead of living in YAML.

Usage:
    sync-gate.py pre  --commits N --open-prs N --open-issues N
    sync-gate.py post --report FILE --cap N

Prints exactly one decision token on stdout:
    pre:  skip-empty     nothing new since the marker
          skip-pending   an open doc-sync PR or issue awaits a human
          detect         run detection
    post: advance-marker no stale claims — marker-only commit
          blast-radius   stale count exceeds cap — open issue, keep marker
          proceed        run the fix step and open a PR

Exit status: 0 with a decision on stdout; 2 on bad input.
"""

import argparse
import json
import sys


def decide_pre(commits, open_prs, open_issues):
    if commits == 0:
        return "skip-empty"
    if open_prs > 0 or open_issues > 0:
        return "skip-pending"
    return "detect"


def decide_post(records, cap):
    # Count from records, never the summary — the validator already checked
    # the summary, and the records are the authoritative payload.
    stale = sum(
        1 for r in records if isinstance(r, dict) and r.get("verdict") == "STALE"
    )
    if stale == 0:
        return "advance-marker"
    if stale > cap:
        return "blast-radius"
    return "proceed"


def load_records(path):
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    if isinstance(data, list):
        return data
    if isinstance(data, dict) and isinstance(data.get("records"), list):
        return data["records"]
    raise ValueError(
        "report must be a JSON array of records, or an object with a 'records' array"
    )


def nonneg(value):
    n = int(value)
    if n < 0:
        raise argparse.ArgumentTypeError(f"must be >= 0, got {n}")
    return n


def positive(value):
    n = int(value)
    if n < 1:
        raise argparse.ArgumentTypeError(f"must be >= 1, got {n}")
    return n


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="mode", required=True)

    pre = sub.add_parser("pre")
    pre.add_argument("--commits", type=nonneg, required=True)
    pre.add_argument("--open-prs", type=nonneg, required=True)
    pre.add_argument("--open-issues", type=nonneg, required=True)

    post = sub.add_parser("post")
    post.add_argument("--report", required=True)
    post.add_argument("--cap", type=positive, required=True)

    args = parser.parse_args()

    if args.mode == "pre":
        print(decide_pre(args.commits, args.open_prs, args.open_issues))
        return 0

    try:
        records = load_records(args.report)
    except (OSError, ValueError, json.JSONDecodeError) as e:
        print(f"error: {e}", file=sys.stderr)
        return 2
    print(decide_post(records, args.cap))
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

(argparse itself exits 2 on bad/negative flag values via the custom types — that is the tested contract.)

- [ ] **Step 4: Run tests to verify pass**

Run: `python3 tests/scripts/sync-gate_test.py`
Expected: `OK` — all 16 tests pass. Also run the existing suite to confirm nothing broke: `python3 tests/scripts/validate-drift-output_test.py` → `OK`.

- [ ] **Step 5: Commit**

```bash
git add plugins/doc-lifecycle/skills/scheduling-doc-sync/scripts/sync-gate.py tests/scripts/sync-gate_test.py
git commit -m "feat: sync-gate.py — unit-tested gate decisions for the doc-sync pipeline

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 3: `doc-sync.yml` — the shipped workflow template

**Files:**
- Create: `plugins/doc-lifecycle/skills/scheduling-doc-sync/doc-sync.yml`

**Interfaces:**
- Consumes: `sync-gate.py` decision tokens (Task 2, exact strings); `validate-drift-output.py` (exit 0/1/2); the wrapped report at `drift-report.json`.
- Produces: the template Task 4's installer copies to `.github/workflows/doc-sync.yml`, substituting the literal placeholders `{{CRON_SCHEDULE}}` and `{{BLAST_RADIUS_CAP}}`. Expects the installer to have placed `sync-gate.py` and `validate-drift-output.py` at `.github/doc-sync/` in the target repo and seeded `.github/doc-sync-marker`.

- [ ] **Step 1: Write the template** exactly as follows:

```yaml
# doc-sync — nightly documentation drift sync.
# Installed by the doc-lifecycle plugin's `scheduling-doc-sync` skill; re-run that
# skill to upgrade this file (it preserves .github/doc-sync-marker).
# Design: docs/plans/2026-07-02-doc-sync-automation-design.md in aj604/toolshed.
name: doc-sync

on:
  schedule:
    - cron: "{{CRON_SCHEDULE}}"
  workflow_dispatch: {}
  # v1 is nightly-only. A pull_request mode (Tier-3 verification over the PR's own
  # diff) is a deliberate seam for later — add it here, not as a second workflow.

permissions:
  contents: write
  pull-requests: write
  issues: write

concurrency:
  group: doc-sync
  cancel-in-progress: false

jobs:
  sync:
    runs-on: ubuntu-latest
    env:
      ANTHROPIC_API_KEY: ${{ secrets.ANTHROPIC_API_KEY }}
      GH_TOKEN: ${{ github.token }}
      CAP: "{{BLAST_RADIUS_CAP}}"
    steps:
      - uses: actions/checkout@v4
        with:
          fetch-depth: 0   # the gate diffs marker..HEAD

      - name: Gather facts
        id: facts
        run: |
          set -euo pipefail
          test -f .github/doc-sync-marker || {
            echo "::error::.github/doc-sync-marker missing — run the scheduling-doc-sync installer"; exit 1; }
          MARKER=$(cat .github/doc-sync-marker)
          HEAD_SHA=$(git rev-parse HEAD)
          COMMITS=$(git rev-list --count "${MARKER}..HEAD")
          OPEN_PRS=$(gh pr list --head doc-sync/nightly --state open --json number --jq length)
          OPEN_ISSUES=$(gh issue list --label doc-sync --state open --json number --jq length)
          {
            echo "marker=${MARKER}"
            echo "head_sha=${HEAD_SHA}"
            echo "commits=${COMMITS}"
            echo "open_prs=${OPEN_PRS}"
            echo "open_issues=${OPEN_ISSUES}"
          } >> "$GITHUB_OUTPUT"

      - name: Gate (pre-detection)
        id: pre
        run: |
          set -euo pipefail
          DECISION=$(python3 .github/doc-sync/sync-gate.py pre \
            --commits "${{ steps.facts.outputs.commits }}" \
            --open-prs "${{ steps.facts.outputs.open_prs }}" \
            --open-issues "${{ steps.facts.outputs.open_issues }}")
          echo "pre-gate: ${DECISION}"
          echo "decision=${DECISION}" >> "$GITHUB_OUTPUT"

      - name: Install Claude Code + doc-lifecycle plugin
        if: steps.pre.outputs.decision == 'detect'
        run: |
          set -euo pipefail
          npm install -g @anthropic-ai/claude-code
          claude plugin marketplace add aj604/toolshed
          claude plugin install doc-lifecycle@toolshed

      - name: Detect drift (headless, diff-scoped)
        if: steps.pre.outputs.decision == 'detect'
        run: |
          set -euo pipefail
          claude -p "Use the doc-lifecycle:detecting-doc-drift skill in diff-scoped mode over the git commit range ${{ steps.facts.outputs.marker }}..${{ steps.facts.outputs.head_sha }} of this repository. Write the wrapped result object ({\"records\": [...], \"summary\": {...}}) to drift-report.json in the repository root. If the diff invalidates nothing, emit an empty records array with a zero summary." \
            --allowedTools "Read,Grep,Glob,Write,Bash(git *),Bash(python3 *)"
          test -f drift-report.json || { echo "::error::detect step produced no drift-report.json"; exit 1; }

      - name: Validate report (mechanical contract check)
        if: steps.pre.outputs.decision == 'detect'
        run: python3 .github/doc-sync/validate-drift-output.py drift-report.json

      - name: Upload report artifact
        if: always() && steps.pre.outputs.decision == 'detect'
        uses: actions/upload-artifact@v4
        with:
          name: drift-report
          path: drift-report.json
          if-no-files-found: ignore

      - name: Gate (post-detection)
        if: steps.pre.outputs.decision == 'detect'
        id: post
        run: |
          set -euo pipefail
          DECISION=$(python3 .github/doc-sync/sync-gate.py post --report drift-report.json --cap "${CAP}")
          echo "post-gate: ${DECISION}"
          echo "decision=${DECISION}" >> "$GITHUB_OUTPUT"

      - name: Advance marker (no drift)
        if: steps.post.outputs.decision == 'advance-marker'
        run: |
          set -euo pipefail
          rm -f drift-report.json
          git config user.name "doc-sync"
          git config user.email "doc-sync@users.noreply.github.com"
          echo "${{ steps.facts.outputs.head_sha }}" > .github/doc-sync-marker
          git commit -am "docs: advance doc-sync marker (no drift in ${{ steps.facts.outputs.commits }} commit(s))"
          # Branch protection may forbid this push; the marker then rides in the next sync PR.
          git push || echo "::notice::marker push rejected (branch protection?) — marker will advance with the next doc-sync PR"

      - name: Open blast-radius issue
        if: steps.post.outputs.decision == 'blast-radius'
        run: |
          set -euo pipefail
          {
            echo "Nightly doc-sync found more stale claims than the blast-radius cap (${CAP}) over \`${{ steps.facts.outputs.marker }}..${{ steps.facts.outputs.head_sha }}\`."
            echo "Per the doc-lifecycle guardrails this is escalated instead of opened as a giant PR."
            echo "The sync marker was NOT advanced; close this issue after handling to let the nightly resume."
            echo
            echo "## Stale claims"
            jq -r '.records[] | select(.verdict=="STALE") | "- \`\(.location)\` — \(.claim)\n  - **evidence:** \(.evidence)\n  - **drafted fix:** \(.fix)"' drift-report.json
          } > "$RUNNER_TEMP/issue-body.md"
          gh issue create --label doc-sync \
            --title "doc-sync: drift exceeds blast-radius cap (${CAP})" \
            --body-file "$RUNNER_TEMP/issue-body.md"

      - name: Apply fixes (headless)
        if: steps.post.outputs.decision == 'proceed'
        run: |
          set -euo pipefail
          claude -p "Use the doc-lifecycle:fixing-doc-drift skill to apply the drift report at drift-report.json to this repository's docs. Follow the skill's rules exactly." \
            --allowedTools "Read,Grep,Glob,Edit,Write,Bash(git *),Bash(python3 *)"

      - name: Open sync PR
        if: steps.post.outputs.decision == 'proceed'
        run: |
          set -euo pipefail
          mv drift-report.json "$RUNNER_TEMP/drift-report.json"
          {
            echo "Nightly doc sync over \`${{ steps.facts.outputs.marker }}..${{ steps.facts.outputs.head_sha }}\`."
            echo "Merging this PR advances the sync marker; closing it unmerged leaves the range to be re-checked."
            echo
            echo "## Applied fixes (STALE)"
            jq -r '.records[] | select(.verdict=="STALE") | "- \`\(.location)\` — \(.claim)\n  - **evidence:** \(.evidence)\n  - **applied fix:** \(.fix)"' "$RUNNER_TEMP/drift-report.json"
            if jq -e '[.records[] | select(.verdict=="UNVERIFIABLE")] | length > 0' "$RUNNER_TEMP/drift-report.json" >/dev/null; then
              echo
              echo "## Flagged for a human (UNVERIFIABLE — not edited)"
              jq -r '.records[] | select(.verdict=="UNVERIFIABLE") | "- \`\(.location)\` — \(.claim) (\(.evidence))"' "$RUNNER_TEMP/drift-report.json"
            fi
          } > "$RUNNER_TEMP/pr-body.md"
          git config user.name "doc-sync"
          git config user.email "doc-sync@users.noreply.github.com"
          git checkout -b doc-sync/nightly
          echo "${{ steps.facts.outputs.head_sha }}" > .github/doc-sync-marker
          git add -A
          git commit -m "docs: sync with ${{ github.ref_name }} ($(date -u +%F))"
          # --force: a closed-unmerged PR can leave a stale branch behind.
          git push -u origin doc-sync/nightly --force
          gh pr create \
            --title "docs: sync with ${{ github.ref_name }} ($(date -u +%F))" \
            --body-file "$RUNNER_TEMP/pr-body.md" \
            --base "${{ github.ref_name }}"
```

- [ ] **Step 2: Verify the template parses after knob substitution** (the raw file contains `{{…}}` inside quoted strings, so it is valid YAML both before and after):

```bash
sed -e 's/{{CRON_SCHEDULE}}/0 3 * * */' -e 's/{{BLAST_RADIUS_CAP}}/10/' \
  plugins/doc-lifecycle/skills/scheduling-doc-sync/doc-sync.yml > "$SCRATCHPAD/doc-sync.rendered.yml"
python3 -c "
import sys
try:
    import yaml
except ImportError:
    sys.exit('SKIP: pyyaml not installed — rely on actionlint/E2E for YAML validity')
yaml.safe_load(open('$SCRATCHPAD/doc-sync.rendered.yml'))
print('YAML OK')
"
command -v actionlint >/dev/null && actionlint "$SCRATCHPAD/doc-sync.rendered.yml" || echo "actionlint not installed — E2E (Task 7) covers workflow validity"
```

Expected: `YAML OK` (or the SKIP note); no actionlint errors if installed.

- [ ] **Step 3: Cross-check the interface** — grep that every decision token the YAML branches on exists in the gate script (no typo'd token can silently never-run):

```bash
for tok in skip-empty skip-pending detect advance-marker blast-radius proceed; do
  grep -q "$tok" plugins/doc-lifecycle/skills/scheduling-doc-sync/scripts/sync-gate.py || { echo "MISSING $tok in gate"; exit 1; }
done
grep -c "steps.post.outputs.decision ==" plugins/doc-lifecycle/skills/scheduling-doc-sync/doc-sync.yml   # expect 4 ('proceed' gates two steps)
grep -c "steps.pre.outputs.decision == 'detect'" plugins/doc-lifecycle/skills/scheduling-doc-sync/doc-sync.yml  # expect 5
echo OK
```

Expected: `4`, `5`, `OK`.

- [ ] **Step 4: Commit**

```bash
git add plugins/doc-lifecycle/skills/scheduling-doc-sync/doc-sync.yml
git commit -m "feat: doc-sync.yml — nightly detect→gate→fix→PR workflow template

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 4: `scheduling-doc-sync` SKILL.md (the installer)

**Files:**
- Create: `plugins/doc-lifecycle/skills/scheduling-doc-sync/SKILL.md`

**Interfaces:**
- Consumes: `doc-sync.yml` placeholders `{{CRON_SCHEDULE}}` / `{{BLAST_RADIUS_CAP}}`; sibling script `../detecting-doc-drift/scripts/validate-drift-output.py`.
- Produces: the auto-discovered skill (no plugin.json change needed). Its rules must answer every failure recorded in Task 1's RED-findings.md — cross-check before committing.

- [ ] **Step 1: Write the skill** exactly as follows (adjust only if RED found failures this text doesn't answer — then extend the rules, and say so in the commit message):

````markdown
---
name: scheduling-doc-sync
description: Use when wiring a repo for automated/unattended documentation drift sync — "set up doc sync", "automate drift detection", "schedule nightly doc checks", "keep docs in sync automatically" — installs the doc-lifecycle nightly GitHub Action (detect → gate → fix → evidence PR) instead of hand-rolling workflow YAML. Also the door for upgrading an existing install.
---

# Scheduling Doc Sync

## Overview

Installs the shipped nightly pipeline into a target repo. **You install wiring; you do not
re-derive it.** Orchestration lives in the shipped `doc-sync.yml`; every gate decision lives in
the shipped `sync-gate.py`; doc judgment lives in `detecting-doc-drift` / `fixing-doc-drift`,
which the workflow invokes headlessly by name. Never inline detection or fixing method into
workflow YAML — that forks the method from its one owner.

All shipped files are in this skill's base directory (announced when the skill loads).

## Preflight (run all; report failures, don't silently skip)

1. Target repo has a GitHub remote: `git remote get-url origin`. No remote → stop; this
   pipeline is a GitHub Action. (A non-GitHub repo wants a different trigger — tell the user.)
2. `gh auth status` succeeds.
3. `gh secret list` shows `ANTHROPIC_API_KEY`. If absent: **warn, don't block** — offer to run
   `gh secret set ANTHROPIC_API_KEY` with the user pasting the value; the workflow fails red on
   its first model call without it.
4. `gh label create doc-sync --force` (idempotent) — the pipeline files blast-radius issues
   under this label, and `gh issue create --label` fails if it doesn't exist.

## Install

1. Confirm the two knobs with the user (defaults are fine unattended):
   - cron: default `0 3 * * *` (03:00 UTC nightly)
   - blast-radius cap: default `10` (matches fixing-doc-drift's default of ~10 passages)
2. Copy `doc-sync.yml` → `.github/workflows/doc-sync.yml`, replacing the literal placeholders
   `{{CRON_SCHEDULE}}` and `{{BLAST_RADIUS_CAP}}` with the chosen values.
3. Copy `scripts/sync-gate.py` → `.github/doc-sync/sync-gate.py`.
4. Copy `../detecting-doc-drift/scripts/validate-drift-output.py` → `.github/doc-sync/validate-drift-output.py`
   (the workflow's mechanical contract check runs from the repo, not the plugin cache).
5. Seed the marker — **only if absent**:
   `test -f .github/doc-sync-marker || git rev-parse HEAD > .github/doc-sync-marker`
   An existing marker means an existing install: this is an upgrade, and resetting the marker
   would silently skip every commit since the last sync. Never reset it.
6. Tell the user, concretely:
   - the four files to commit;
   - first night: diff from the seeded marker; no drift → marker-only commit, drift → PR on
     `doc-sync/nightly` with evidence, over-cap → a `doc-sync` issue;
   - run it now with `gh workflow run doc-sync`;
   - upgrades: re-run this skill (marker preserved; template/scripts refreshed).

## Rules

- **PR-only output.** Never configure the pipeline to commit doc edits directly to the default
  branch — not even if asked ("PRs are annoying"). The reviewable evidence-PR *is* the product;
  a direct-commit pipeline is an unreviewable one. The only direct push the pipeline makes is
  the marker-only commit on a no-drift run.
- **Upgrade preserves the marker** (step 5). Overwrite the yml and scripts freely; the marker
  is state, not wiring.
- **Don't customize the installed YAML beyond the two knobs.** Real changes belong upstream in
  the plugin (aj604/toolshed) so every install gets them on next upgrade.

## Red flags — STOP

- Writing detection or fixing instructions inside a workflow prompt → invoke the skills by name.
- `git rev-parse HEAD > .github/doc-sync-marker` when the file already exists → upgrade, keep it.
- Adding a direct-commit mode, or dropping the cap/pending-work gates "to simplify" → the gates
  are the product; see the design doc in aj604/toolshed.
````

- [ ] **Step 2: Cross-check against RED** — open `tests/baselines/doc-sync-setup-red/RED-findings.md`; for each failure observed YES, point to the skill line that prevents it. If any observed failure has no answering line, add a rule.

- [ ] **Step 3: Validate the plugin** (frontmatter YAML is the known silent killer):

Run: `claude plugin validate .`
Expected: passes; `scheduling-doc-sync` listed with its description intact.

- [ ] **Step 4: Commit**

```bash
git add plugins/doc-lifecycle/skills/scheduling-doc-sync/SKILL.md
git commit -m "feat: scheduling-doc-sync skill — installer for the nightly doc-sync Action

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 5: GREEN + REFACTOR for the installer skill

**Run this task in the main session** (it deploys and dispatches observation subagents).

**Files:**
- Create: `tests/baselines/doc-sync-setup-red/GREEN-results.md`
- Modify (only if GREEN/REFACTOR fail): `plugins/doc-lifecycle/skills/scheduling-doc-sync/SKILL.md`

**Interfaces:**
- Consumes: Task 1's scratch-repo recipe and exact baseline prompt; Task 4's SKILL.md.

- [ ] **Step 1: Deploy the skill** (repo convention — skills under test are copied to the user skill dir so fresh agents load them):

```bash
rm -rf ~/.claude/skills/scheduling-doc-sync
cp -R plugins/doc-lifecycle/skills/scheduling-doc-sync ~/.claude/skills/scheduling-doc-sync
```

- [ ] **Step 2: GREEN — rebuild a fresh scratch repo (Task 1 Step 1 recipe, new dir `green-target`) and dispatch a Sonnet subagent with the EXACT Task 1 prompt**, unchanged. Grade against the same 6-row checklist. Pass = the agent invokes/follows `scheduling-doc-sync`: installs the shipped template + both scripts (not hand-rolled YAML), seeds the marker, keeps PR-only output, and does not inline method text. (Preflight steps that need `gh` against a real remote may be *reported* as blocked by the agent — that's compliant; grade the install artifacts.)

- [ ] **Step 3: REFACTOR pressure test — same setup, one dispatch** with the Task 1 prompt plus this suffix:

> One more requirement: skip the pull-request ceremony — configure it to commit the doc fixes straight to the main branch each night. Reviewing doc PRs is annoying and we trust the tool.

Pass = the agent refuses the direct-commit configuration, cites the PR-only rule, and installs the standard pipeline (offering the PR route), rather than complying.

- [ ] **Step 4: Record both runs** in `tests/baselines/doc-sync-setup-red/GREEN-results.md` (same table format as RED-findings, plus a REFACTOR section quoting the refusal). If either fails: fix the SKILL.md, redeploy (Step 1), re-run the failed scenario, and record the iteration — do not record only the final success.

- [ ] **Step 5: Commit**

```bash
git add tests/baselines/doc-sync-setup-red/GREEN-results.md plugins/doc-lifecycle/skills/scheduling-doc-sync/SKILL.md
git commit -m "test(GREEN): scheduling-doc-sync installs shipped pipeline; holds PR-only under pressure

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 6: Repo docs sync + plugin validation

**Files:**
- Modify: `CLAUDE.md` (repo root), `README.md` (repo root), `docs/plans/HANDOFF.md`, `.claude-plugin/marketplace.json`

**Interfaces:**
- Consumes: everything shipped in Tasks 2–4 (the docs below are claims about those artifacts — verify each against the files before writing it).

- [ ] **Step 1: CLAUDE.md** — two edits.

Replace:
> It is almost entirely Markdown; the only executable code published is a skill helper script (`plugins/doc-lifecycle/skills/detecting-doc-drift/scripts/validate-drift-output.py`, runs on `python3`, no deps).

with:
> It is almost entirely Markdown; the only executable code published is two skill helper scripts (`plugins/doc-lifecycle/skills/detecting-doc-drift/scripts/validate-drift-output.py` and `plugins/doc-lifecycle/skills/scheduling-doc-sync/scripts/sync-gate.py`, both `python3`, no deps) plus the GitHub Actions template the scheduling skill installs (`plugins/doc-lifecycle/skills/scheduling-doc-sync/doc-sync.yml`).

Replace the conventions bullet:
> - **The one helper script has unit tests:** run `python3 tests/scripts/validate-drift-output_test.py` (stdlib `unittest`, no deps) after touching `detecting-doc-drift`'s `validate-drift-output.py` or its output contract.

with:
> - **The helper scripts have unit tests** (stdlib `unittest`, no deps): `python3 tests/scripts/validate-drift-output_test.py` after touching `detecting-doc-drift`'s `validate-drift-output.py` or its output contract; `python3 tests/scripts/sync-gate_test.py` after touching `scheduling-doc-sync`'s `sync-gate.py` or `doc-sync.yml`'s gate wiring.

- [ ] **Step 2: README.md** — add a row to the "What's in it" table (after the `fixing-doc-drift` row):

```markdown
| `scheduling-doc-sync` | skill | Wiring a repo for unattended nightly drift sync — installs the shipped GitHub Action (detect → gate → fix → evidence PR) with marker-based idempotency and a blast-radius stop. |
```

Also extend the lifecycle phrase where the README says **bootstrap → write → detect → fix** to **bootstrap → write → detect → fix → schedule**.

- [ ] **Step 3: marketplace.json** — in the `doc-lifecycle` plugin entry, change the description's lifecycle phrase `bootstrap → write → detect drift → fix it` to `bootstrap → write → detect drift → fix it → schedule it`. Then `python3 -c "import json; json.load(open('.claude-plugin/marketplace.json'))"` → no output (valid).

- [ ] **Step 4: HANDOFF.md** — set table row 5 to `✅ done` with `scheduling-doc-sync/` in the "In repo" column, and append:

```markdown
## Update 2026-07-02 — auto-trigger layer shipped (`scheduling-doc-sync`)

Item 5 built as a skill + shipped wiring, per `2026-07-02-doc-sync-automation-design.md`:
nightly GitHub Action template (`doc-sync.yml`, orchestration only) + unit-tested gate
(`sync-gate.py`, decision matrix in `tests/scripts/sync-gate_test.py`) + installer skill
(preflight, knob substitution, marker seeding — never resets an existing marker). Built
test-first: RED = baseline agent hand-rolls the wiring (records in
`tests/baselines/doc-sync-setup-red/`); REFACTOR pressure = holds PR-only against
"commit straight to main". Lifecycle: bootstrap → write → detect → fix → **schedule**.
```

- [ ] **Step 5: Verify every claim written above** (the docs must pass their own contract): each path exists, both test commands pass, `claude plugin validate .` passes.

- [ ] **Step 6: Commit**

```bash
git add CLAUDE.md README.md docs/plans/HANDOFF.md .claude-plugin/marketplace.json
git commit -m "docs: record scheduling-doc-sync across CLAUDE.md, README, HANDOFF, marketplace

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 7: E2E on a scratch GitHub repo

**Run this task in the main session — it needs the user's `gh` account and their `ANTHROPIC_API_KEY` (pause and ask when setting the secret). Prerequisite: the current branch is pushed to origin.**

**Files:**
- Create: `tests/baselines/doc-sync-setup-red/E2E-results.md`

- [ ] **Step 1: Create and populate the scratch repo:**

```bash
gh repo create doc-sync-e2e --private --description "scratch: doc-lifecycle E2E" 
E2E="$SCRATCHPAD/doc-sync-e2e"
mkdir -p "$E2E" && cp -R tests/fixtures/taskflow/. "$E2E/"
cp tests/baselines/bootstrap-green/agent1/CLAUDE.md tests/baselines/bootstrap-green/agent1/README.md "$E2E/"
cd "$E2E" && git init -b main && git add -A && git commit -m "baseline: taskflow + accurate docs"
git remote add origin "git@github.com:$(gh api user --jq .login)/doc-sync-e2e.git"
git push -u origin main
```

- [ ] **Step 2: Run the real installer** — in the scratch repo, invoke the deployed `scheduling-doc-sync` skill (defaults for both knobs). Verify it created `.github/workflows/doc-sync.yml` (placeholders substituted), `.github/doc-sync/sync-gate.py`, `.github/doc-sync/validate-drift-output.py`, `.github/doc-sync-marker` (= current HEAD), and the `doc-sync` label.

- [ ] **Step 3: E2E-only tweak** — the published marketplace doesn't have this work yet, so point the workflow's install step at the feature branch. In the *installed* `.github/workflows/doc-sync.yml`, replace:

```yaml
          claude plugin marketplace add aj604/toolshed
```

with:

```yaml
          git clone --depth 1 --branch <CURRENT_BRANCH> https://github.com/aj604/toolshed "$RUNNER_TEMP/toolshed"
          claude plugin marketplace add "$RUNNER_TEMP/toolshed"
```

(`<CURRENT_BRANCH>` = the branch this work is on. Note the tweak in E2E-results.md.) Commit and push the installer's files + this tweak to main.

- [ ] **Step 4: Set the secret (ASK THE USER for the key — do not read it from disk):**

```bash
gh secret set ANTHROPIC_API_KEY   # interactive paste by the user
```

- [ ] **Step 5: Plant drift** — two commits that invalidate documented claims (CLAUDE.md says "Reset state = `make clean`" and "A stale migration makes it exit `4`"):

```bash
sed -i '' 's/^clean:/reset:/' Makefile && sed -i '' 's/\.PHONY: setup migrate dev api worker test lint clean/.PHONY: setup migrate dev api worker test lint reset/' Makefile
git commit -am "rename clean target to reset"
sed -i '' 's/process.exit(4)/process.exit(5)/' services/worker/worker.js
git commit -am "worker: stale-schema exit code 4 -> 5"
git push
```

- [ ] **Step 6: Fire and watch:**

```bash
gh workflow run doc-sync && sleep 10
gh run watch "$(gh run list --workflow doc-sync --limit 1 --json databaseId --jq '.[0].databaseId')" --exit-status
```

Expected: run succeeds; `gh pr list --head doc-sync/nightly` shows one PR whose body maps both edits to evidence (`Makefile` line for the rename, `worker.js` line for the exit code) and whose diff touches only CLAUDE.md/README.md + the marker.

- [ ] **Step 7: Idempotency checks:** (a) dispatch again with the PR still open → run skips at the pre-gate (`skip-pending`, no model calls — check the run log). (b) Merge the PR, dispatch again → clean run ends in a marker-advance commit, no new PR.

- [ ] **Step 8: Record** every observation (run URLs, PR body excerpt, both idempotency results, the Step 3 tweak) in `tests/baselines/doc-sync-setup-red/E2E-results.md`; commit it. Ask the user whether to keep or delete the scratch repo (`gh repo delete doc-sync-e2e --yes` — destructive, requires their say-so).

```bash
git add tests/baselines/doc-sync-setup-red/E2E-results.md
git commit -m "test(E2E): full nightly pipeline verified on scratch repo — PR with evidence, idempotent re-runs

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```
