# Nightly Doc-Bloat Sweep — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a weekly GitHub Action (`doc-bloat.yml`) that runs `detecting-doc-bloat` full-sweep, splits findings by verdict weight, and opens two draft proposal PRs (`doc-bloat/prune`, `doc-bloat/distill`).

**Architecture:** A sibling workflow to the drift nightly. One `detect` job runs the sweep, validates it, and decides each lane; two downstream lane jobs (`prune`, `distill`) each re-derive their filtered subset from the shared report artifact, invoke `fixing-doc-bloat` on that subset, and open a draft PR. All branchy logic lives in `sync-gate.py`; all user-facing strings in `render-report.py` — both extended with bloat subcommands, never forked.

**Tech Stack:** Python 3 stdlib only (no deps), `unittest` black-box subprocess tests, GitHub Actions, `anthropics/claude-code-action@v1`.

## Global Constraints

- **Python 3 stdlib only** — no third-party imports in any script.
- **Scripts stay self-contained** — each of `sync-gate.py` / `render-report.py` runs standalone from `.github/doc-sync/`; follow the existing pattern where each duplicates small helpers (`load_records`) rather than sharing a module.
- **Lane membership has one owner:** `sync-gate.py`. `render-report.py` never re-derives it — it renders whichever already-filtered records it is handed.
- **No detection/fixing method in YAML** — the workflow invokes skills by name; verdict→lane filtering is done by `sync-gate.py`, not jq/grep in the step.
- **PR-only, draft** — every lane opens a `--draft` PR; nothing auto-merges, nothing commits to the default branch.
- **Tests are black-box** — invoke the script as a subprocess (`subprocess.run([sys.executable, SCRIPT, ...])`), assert stdout token / file contents / exit code. Match the existing `rec()`/`run()` helpers.
- **Lane verdict membership (authoritative):**
  - `prune` ← `CUT`, `CONDENSE`, `EXTRACT-AND-MOVE`
  - `distill` ← `MERGE-DOC`, `RETIRE-DOC`, and `DISTILL` **only when `status == "ready"`**
  - a `DISTILL` with `status == "pending-implementation"` belongs to **neither** lane.

---

### Task 1: Bloat gate subcommands in `sync-gate.py`

**Files:**
- Modify: `plugins/doc-lifecycle/skills/scheduling-doc-sync/scripts/sync-gate.py`
- Test: `tests/scripts/sync-gate_test.py`

**Interfaces:**
- Produces (CLI, consumed by `doc-bloat.yml` and later tasks):
  - `sync-gate.py bloat-pre --prune-pr-open N --distill-pr-open N` → prints `detect` | `skip-pending`
  - `sync-gate.py bloat-lane --report FILE --lane {prune|distill} --pr-open N --out FILE` → prints `open` | `skip-empty` | `skip-pending`; always writes `{"records":[...]}` (the lane's filtered subset) to `--out` when the report parses.
- Produces (Python, used by Task 2 tests only for shared expectations): membership rule above.

- [ ] **Step 1: Write the failing tests**

Add to `tests/scripts/sync-gate_test.py` (a new `bloat` helper + a TestCase). `run()` and the import of `SCRIPT` already exist.

```python
def brec(verdict, status=None, location=None, doc="README.md"):
    r = {"id": "B1", "doc": doc, "location": location, "verdict": verdict,
         "evidence": "x", "proposal": None, "status": status, "payload": None}
    return r


def write_report(records):
    fd, path = tempfile.mkstemp(suffix=".json")
    with os.fdopen(fd, "w") as f:
        json.dump({"records": records, "summary": {}}, f)
    return path


class BloatPreGate(unittest.TestCase):
    def test_both_prs_open_skips(self):
        out = run("bloat-pre", "--prune-pr-open", "1", "--distill-pr-open", "2")
        self.assertEqual(out.returncode, 0)
        self.assertEqual(out.stdout.strip(), "skip-pending")

    def test_one_lane_free_detects(self):
        out = run("bloat-pre", "--prune-pr-open", "1", "--distill-pr-open", "0")
        self.assertEqual(out.stdout.strip(), "detect")

    def test_both_free_detects(self):
        out = run("bloat-pre", "--prune-pr-open", "0", "--distill-pr-open", "0")
        self.assertEqual(out.stdout.strip(), "detect")


class BloatLaneGate(unittest.TestCase):
    def _run(self, records, lane, pr_open=0):
        report = write_report(records)
        out_fd, out_path = tempfile.mkstemp(suffix=".json")
        os.close(out_fd)
        res = run("bloat-lane", "--report", report, "--lane", lane,
                  "--pr-open", str(pr_open), "--out", out_path)
        with open(out_path) as f:
            filtered = json.load(f)["records"]
        os.unlink(report); os.unlink(out_path)
        return res.stdout.strip(), filtered

    def test_prune_open_with_cut(self):
        dec, filtered = self._run([brec("CUT", location="README.md:5")], "prune")
        self.assertEqual(dec, "open")
        self.assertEqual(len(filtered), 1)

    def test_prune_empty_when_only_doc_verdicts(self):
        dec, filtered = self._run([brec("RETIRE-DOC")], "prune")
        self.assertEqual(dec, "skip-empty")
        self.assertEqual(filtered, [])

    def test_distill_includes_merge_retire_and_ready_distill(self):
        recs = [brec("MERGE-DOC"), brec("RETIRE-DOC"),
                brec("DISTILL", status="ready"),
                brec("DISTILL", status="pending-implementation")]
        dec, filtered = self._run(recs, "distill")
        self.assertEqual(dec, "open")
        self.assertEqual(len(filtered), 3)  # pending-implementation excluded

    def test_distill_empty_when_only_pending(self):
        dec, filtered = self._run([brec("DISTILL", status="pending-implementation")], "distill")
        self.assertEqual(dec, "skip-empty")

    def test_pr_open_skips_pending_even_with_findings(self):
        dec, _ = self._run([brec("CUT", location="README.md:5")], "prune", pr_open=1)
        self.assertEqual(dec, "skip-pending")
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python3 tests/scripts/sync-gate_test.py`
Expected: FAIL — `bloat-pre`/`bloat-lane` are not valid subcommands (argparse exits 2), assertions on `skip-pending`/`open` fail.

- [ ] **Step 3: Implement the subcommands**

In `sync-gate.py`, after `decide_post` add:

```python
PRUNE_VERDICTS = {"CUT", "CONDENSE", "EXTRACT-AND-MOVE"}
DISTILL_DOC_VERDICTS = {"MERGE-DOC", "RETIRE-DOC"}


def in_lane(record, lane):
    verdict = record.get("verdict")
    if lane == "prune":
        return verdict in PRUNE_VERDICTS
    if lane == "distill":
        if verdict in DISTILL_DOC_VERDICTS:
            return True
        return verdict == "DISTILL" and record.get("status") == "ready"
    raise ValueError(f"unknown lane: {lane!r}")


def filter_lane(records, lane):
    return [r for r in records if isinstance(r, dict) and in_lane(r, lane)]


def decide_bloat_pre(prune_pr_open, distill_pr_open):
    if prune_pr_open > 0 and distill_pr_open > 0:
        return "skip-pending"
    return "detect"


def decide_bloat_lane(records, lane, pr_open):
    if pr_open > 0:
        return "skip-pending"
    if not filter_lane(records, lane):
        return "skip-empty"
    return "open"
```

In `main()`, register the subparsers (after the `post` parser):

```python
    bpre = sub.add_parser("bloat-pre")
    bpre.add_argument("--prune-pr-open", type=nonneg, required=True)
    bpre.add_argument("--distill-pr-open", type=nonneg, required=True)

    blane = sub.add_parser("bloat-lane")
    blane.add_argument("--report", required=True)
    blane.add_argument("--lane", choices=["prune", "distill"], required=True)
    blane.add_argument("--pr-open", type=nonneg, required=True)
    blane.add_argument("--out", required=True)
```

In `main()`, add dispatch (before the `post` block's `records` load, or alongside it):

```python
    if args.mode == "bloat-pre":
        print(decide_bloat_pre(args.prune_pr_open, args.distill_pr_open))
        return 0

    if args.mode == "bloat-lane":
        try:
            records = load_records(args.report)
        except (OSError, ValueError, json.JSONDecodeError) as e:
            print(f"error: {e}", file=sys.stderr)
            return 2
        with open(args.out, "w", encoding="utf-8") as f:
            json.dump({"records": filter_lane(records, args.lane)}, f)
        print(decide_bloat_lane(records, args.lane, args.pr_open))
        return 0
```

Update the module docstring `Usage:` block to list the two new subcommands and their decision tokens.

- [ ] **Step 4: Run the tests to verify they pass**

Run: `python3 tests/scripts/sync-gate_test.py`
Expected: PASS (all existing + new tests; `OK`).

- [ ] **Step 5: Commit**

```bash
git add plugins/doc-lifecycle/skills/scheduling-doc-sync/scripts/sync-gate.py tests/scripts/sync-gate_test.py
git commit -m "feat(doc-sync): bloat-pre + bloat-lane gate subcommands"
```

---

### Task 2: Bloat render surfaces in `render-report.py`

**Files:**
- Modify: `plugins/doc-lifecycle/skills/scheduling-doc-sync/scripts/render-report.py`
- Test: `tests/scripts/render-report_test.py`

**Interfaces:**
- Consumes: a filtered lane file (`{"records":[...]}`) written by Task 1's `bloat-lane --out`.
- Produces (CLI):
  - `bloat-pre-summary --decision {detect|skip-pending}` → step-summary line
  - `bloat-pr-body --report FILE` → markdown table on stdout
  - `bloat-pr-title --report FILE --lane L --date YYYY-MM-DD` → title on stdout
  - `bloat-pr-summary --report FILE --lane L --pr-url URL` → step-summary line
  - `bloat-skip-summary --lane L --reason {skip-empty|skip-pending}` → step-summary line

- [ ] **Step 1: Write the failing tests**

Add to `tests/scripts/render-report_test.py` (`run()`, `SCRIPT`, and a `GITHUB_STEP_SUMMARY` pattern already exist — mirror the existing summary tests for env handling). Use a local bloat record helper:

```python
def brec(verdict, location=None, doc="README.md", evidence="seven lines carry one fact"):
    return {"id": "B1", "doc": doc, "location": location, "verdict": verdict,
            "evidence": evidence, "proposal": None, "status": None, "payload": None}


def write_report(records):
    fd, path = tempfile.mkstemp(suffix=".json")
    with os.fdopen(fd, "w") as f:
        json.dump({"records": records}, f)
    return path


class BloatRender(unittest.TestCase):
    def test_pr_body_lists_each_record(self):
        report = write_report([brec("CUT", location="README.md:5"),
                               brec("CONDENSE", location="README.md:22")])
        out = run("bloat-pr-body", "--report", report)
        os.unlink(report)
        self.assertEqual(out.returncode, 0)
        self.assertIn("`CUT` @ `README.md:5`", out.stdout)
        self.assertIn("`CONDENSE` @ `README.md:22`", out.stdout)
        self.assertIn("| Change (see diff) | Why it's bloat |", out.stdout)

    def test_pr_body_uses_doc_when_location_null(self):
        report = write_report([brec("RETIRE-DOC", doc="docs/plans/old.md")])
        out = run("bloat-pr-body", "--report", report)
        os.unlink(report)
        self.assertIn("`RETIRE-DOC` @ `docs/plans/old.md`", out.stdout)

    def test_pr_body_escapes_pipe(self):
        report = write_report([brec("CUT", location="README.md:5", evidence="a | b")])
        out = run("bloat-pr-body", "--report", report)
        os.unlink(report)
        self.assertIn("a \\| b", out.stdout)

    def test_pr_title_pluralizes(self):
        one = write_report([brec("CUT", location="a:1")])
        many = write_report([brec("CUT", location="a:1"), brec("CUT", location="a:2")])
        t1 = run("bloat-pr-title", "--report", one, "--lane", "prune", "--date", "2026-07-03")
        tm = run("bloat-pr-title", "--report", many, "--lane", "prune", "--date", "2026-07-03")
        os.unlink(one); os.unlink(many)
        self.assertEqual(t1.stdout.strip(), "docs: bloat prune — 1 change (2026-07-03)")
        self.assertEqual(tm.stdout.strip(), "docs: bloat prune — 2 changes (2026-07-03)")

    def test_skip_summary_known_reasons(self):
        for reason in ("skip-empty", "skip-pending"):
            out = run("bloat-skip-summary", "--lane", "distill", "--reason", reason)
            self.assertEqual(out.returncode, 0)

    def test_skip_summary_rejects_unknown_reason(self):
        out = run("bloat-skip-summary", "--lane", "prune", "--reason", "bogus")
        self.assertEqual(out.returncode, 2)

    def test_pre_summary_known_decisions(self):
        for d in ("detect", "skip-pending"):
            out = run("bloat-pre-summary", "--decision", d)
            self.assertEqual(out.returncode, 0)
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python3 tests/scripts/render-report_test.py`
Expected: FAIL — subcommands unknown (exit 2), assertions unmet.

- [ ] **Step 3: Implement the render functions**

In `render-report.py`, after `render_pr_summary` add:

```python
def render_bloat_pre_summary(decision):
    if decision == "detect":
        return "▶️ **Weekly doc-bloat sweep** — auditing every doc (incl. `docs/plans/`)."
    if decision == "skip-pending":
        return ("⏭️ **Skipped — both bloat PRs are open.** `doc-bloat/prune` and "
                "`doc-bloat/distill` await review; the sweep resumes after they merge/close.")
    raise ValueError(f"unknown bloat-pre decision: {decision!r}")


def render_bloat_pr_body(records):
    lines = [
        "Proposed by the weekly doc-bloat sweep — each row is applied in the diff below. "
        "Draft PR: review, drop any commit you don't want, merge to accept.",
        "",
        "| Change (see diff) | Why it's bloat |",
        "|---|---|",
    ]
    for r in records:
        where = r.get("location") or r.get("doc")
        lines.append(f"| `{r['verdict']}` @ `{where}` | {md_cell(r['evidence'])} |")
    return "\n".join(lines)


def render_bloat_pr_title(records, lane, date):
    n = len(records)
    noun = "change" if n == 1 else "changes"
    return f"docs: bloat {lane} — {n} {noun} ({date})"


def render_bloat_pr_summary(records, lane, pr_url):
    n = len(records)
    return (f"🧹 **Bloat sweep — {lane} lane.** {n} proposed change(s) — review {pr_url}. "
            f"Draft PR: merge to accept, close to discard.")


def render_bloat_skip_summary(lane, reason):
    msgs = {
        "skip-empty": f"✅ **{lane} lane: nothing to propose.** The sweep found no {lane} findings.",
        "skip-pending": f"⏭️ **{lane} lane skipped.** An open `doc-bloat/{lane}` PR awaits review.",
    }
    if reason not in msgs:
        raise ValueError(f"unknown skip reason: {reason!r}")
    return msgs[reason]
```

In `main()`, register the subparsers (after `prsum`):

```python
    bpre = sub.add_parser("bloat-pre-summary")
    bpre.add_argument("--decision", required=True)

    bbody = sub.add_parser("bloat-pr-body")
    bbody.add_argument("--report", required=True)

    btitle = sub.add_parser("bloat-pr-title")
    btitle.add_argument("--report", required=True)
    btitle.add_argument("--lane", required=True)
    btitle.add_argument("--date", required=True)

    bsum = sub.add_parser("bloat-pr-summary")
    bsum.add_argument("--report", required=True)
    bsum.add_argument("--lane", required=True)
    bsum.add_argument("--pr-url", required=True)

    bskip = sub.add_parser("bloat-skip-summary")
    bskip.add_argument("--lane", required=True)
    bskip.add_argument("--reason", required=True)
```

In `main()`'s try-block dispatch, add branches. `bloat-pre-summary`, `bloat-skip-summary` take no report; the rest load the (already-filtered) file:

```python
        elif args.mode == "bloat-pre-summary":
            write_summary(render_bloat_pre_summary(args.decision))
        elif args.mode == "bloat-skip-summary":
            write_summary(render_bloat_skip_summary(args.lane, args.reason))
        elif args.mode == "bloat-pr-body":
            print(render_bloat_pr_body(load_records(args.report)))
        elif args.mode == "bloat-pr-title":
            print(render_bloat_pr_title(load_records(args.report), args.lane, args.date))
        elif args.mode == "bloat-pr-summary":
            write_summary(render_bloat_pr_summary(load_records(args.report), args.lane, args.pr_url))
```

Note: `bloat-pre-summary` and `bloat-skip-summary` must be reached **before** the `load_records(args.report)` path (they have no `--report`). Place them in the branch order shown, i.e. handle the no-report modes explicitly (like `pre-summary`/`no-drift-summary` already are). Update the module docstring `Usage:` block.

- [ ] **Step 4: Run the tests to verify they pass**

Run: `python3 tests/scripts/render-report_test.py`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add plugins/doc-lifecycle/skills/scheduling-doc-sync/scripts/render-report.py tests/scripts/render-report_test.py
git commit -m "feat(doc-sync): bloat PR/skip render surfaces"
```

---

### Task 3: The `doc-bloat.yml` workflow template

**Files:**
- Create: `plugins/doc-lifecycle/skills/scheduling-doc-sync/doc-bloat.yml`

**Interfaces:**
- Consumes: `sync-gate.py bloat-pre`/`bloat-lane` (Task 1), `render-report.py bloat-*` (Task 2), `validate-bloat-output.py` (existing), the `detecting-doc-bloat`/`fixing-doc-bloat` skills.

- [ ] **Step 1: Create the workflow file**

Write exactly (the `{{BLOAT_CRON}}` placeholder is replaced at install time by `scheduling-doc-sync`):

```yaml
# doc-bloat — weekly documentation bloat sweep (detect → propose).
# Installed by the doc-lifecycle plugin's `scheduling-doc-sync` skill; re-run that
# skill to upgrade this file. Sibling to doc-sync.yml (drift): bloat is detect-and-
# propose only — fixing-doc-bloat applies a human-approved subset, so each lane opens
# a DRAFT PR and the merge is the approval.
# Design: docs/plans/2026-07-03-doc-bloat-nightly-design.md in aj604/toolshed.
name: doc-bloat

on:
  schedule:
    - cron: "{{BLOAT_CRON}}"
  workflow_dispatch: {}

permissions:
  contents: write
  pull-requests: write
  id-token: write   # claude-code-action OAuth token exchange

concurrency:
  group: doc-bloat
  cancel-in-progress: false

jobs:
  detect:
    runs-on: ubuntu-latest
    env:
      GH_TOKEN: ${{ github.token }}
    outputs:
      prune: ${{ steps.prune.outputs.decision }}
      distill: ${{ steps.distill.outputs.decision }}
    steps:
      - uses: actions/checkout@v4
        with:
          fetch-depth: 0

      - name: Gather facts
        id: facts
        run: |
          set -euo pipefail
          PRUNE_PR=$(gh pr list --head doc-bloat/prune --state open --json number --jq length)
          DISTILL_PR=$(gh pr list --head doc-bloat/distill --state open --json number --jq length)
          {
            echo "prune_pr=${PRUNE_PR}"
            echo "distill_pr=${DISTILL_PR}"
          } >> "$GITHUB_OUTPUT"

      - name: Gate (pre-sweep)
        id: pre
        run: |
          set -euo pipefail
          DECISION=$(python3 .github/doc-sync/sync-gate.py bloat-pre \
            --prune-pr-open "${{ steps.facts.outputs.prune_pr }}" \
            --distill-pr-open "${{ steps.facts.outputs.distill_pr }}")
          echo "decision=${DECISION}" >> "$GITHUB_OUTPUT"
          python3 .github/doc-sync/render-report.py bloat-pre-summary --decision "${DECISION}"

      - name: Detect bloat (headless, full sweep)
        if: steps.pre.outputs.decision == 'detect'
        uses: anthropics/claude-code-action@v1
        with:
          claude_code_oauth_token: ${{ secrets.CLAUDE_CODE_OAUTH_TOKEN }}
          anthropic_api_key: ${{ secrets.ANTHROPIC_API_KEY }}
          plugin_marketplaces: https://github.com/aj604/toolshed.git
          plugins: doc-lifecycle@toolshed
          prompt: >-
            Use the doc-lifecycle:detecting-doc-bloat skill in full-audit mode over every
            documentation file in this repository, including docs/plans/. Write the wrapped
            result object ({"records": [...], "summary": {...}}) to bloat-report.json in the
            repository root. If nothing is bloated, emit an empty records array with a zero summary.
          claude_args: --allowedTools "Read,Grep,Glob,Write,Bash(git *),Bash(python3 *)"

      - name: Assert detect produced a report
        if: steps.pre.outputs.decision == 'detect'
        run: |
          test -f bloat-report.json || { echo "::error::detect step produced no bloat-report.json"; exit 1; }

      - name: Validate report (mechanical contract check)
        if: steps.pre.outputs.decision == 'detect'
        run: python3 .github/doc-sync/validate-bloat-output.py bloat-report.json

      - name: Upload report artifact
        if: always() && steps.pre.outputs.decision == 'detect'
        uses: actions/upload-artifact@v4
        with:
          name: bloat-report
          path: bloat-report.json
          if-no-files-found: ignore

      - name: Gate (prune lane)
        if: steps.pre.outputs.decision == 'detect'
        id: prune
        run: |
          set -euo pipefail
          DECISION=$(python3 .github/doc-sync/sync-gate.py bloat-lane \
            --report bloat-report.json --lane prune \
            --pr-open "${{ steps.facts.outputs.prune_pr }}" \
            --out "$RUNNER_TEMP/prune.json")
          echo "decision=${DECISION}" >> "$GITHUB_OUTPUT"
          if [ "${DECISION}" != "open" ]; then
            python3 .github/doc-sync/render-report.py bloat-skip-summary --lane prune --reason "${DECISION}"
          fi

      - name: Gate (distill lane)
        if: steps.pre.outputs.decision == 'detect'
        id: distill
        run: |
          set -euo pipefail
          DECISION=$(python3 .github/doc-sync/sync-gate.py bloat-lane \
            --report bloat-report.json --lane distill \
            --pr-open "${{ steps.facts.outputs.distill_pr }}" \
            --out "$RUNNER_TEMP/distill.json")
          echo "decision=${DECISION}" >> "$GITHUB_OUTPUT"
          if [ "${DECISION}" != "open" ]; then
            python3 .github/doc-sync/render-report.py bloat-skip-summary --lane distill --reason "${DECISION}"
          fi

  prune:
    needs: detect
    if: needs.detect.outputs.prune == 'open'
    runs-on: ubuntu-latest
    env:
      GH_TOKEN: ${{ github.token }}
      LANE: prune
      VERDICTS: "CUT, CONDENSE, or EXTRACT-AND-MOVE"
    steps:
      - uses: actions/checkout@v4
      - uses: actions/download-artifact@v4
        with:
          name: bloat-report
      - name: Apply (headless)
        uses: anthropics/claude-code-action@v1
        with:
          claude_code_oauth_token: ${{ secrets.CLAUDE_CODE_OAUTH_TOKEN }}
          anthropic_api_key: ${{ secrets.ANTHROPIC_API_KEY }}
          plugin_marketplaces: https://github.com/aj604/toolshed.git
          plugins: doc-lifecycle@toolshed
          prompt: >-
            Use the doc-lifecycle:fixing-doc-bloat skill to apply EVERY record in
            bloat-report.json whose verdict is CUT, CONDENSE, or EXTRACT-AND-MOVE — treat
            exactly those record IDs as the approved subset, and apply nothing else. Follow
            the skill's rules exactly.
          claude_args: --allowedTools "Read,Grep,Glob,Edit,Write,Bash(git *),Bash(python3 *)"
      - name: Open draft PR
        run: |
          set -euo pipefail
          DATE=$(date -u +%F)
          python3 .github/doc-sync/sync-gate.py bloat-lane \
            --report bloat-report.json --lane prune --pr-open 0 \
            --out "$RUNNER_TEMP/lane.json" >/dev/null
          rm -f bloat-report.json
          python3 .github/doc-sync/render-report.py bloat-pr-body \
            --report "$RUNNER_TEMP/lane.json" > "$RUNNER_TEMP/body.md"
          TITLE=$(python3 .github/doc-sync/render-report.py bloat-pr-title \
            --report "$RUNNER_TEMP/lane.json" --lane prune --date "${DATE}")
          git config user.name "doc-bloat"
          git config user.email "doc-bloat@users.noreply.github.com"
          git checkout -b doc-bloat/prune
          git add -A
          git commit -m "docs: bloat prune sweep (${DATE})"
          git push --force "https://x-access-token:${GH_TOKEN}@github.com/${GITHUB_REPOSITORY}.git" doc-bloat/prune
          PR_URL=$(gh pr create --draft \
            --title "${TITLE}" \
            --body-file "$RUNNER_TEMP/body.md" \
            --head doc-bloat/prune \
            --base "${{ github.ref_name }}")
          python3 .github/doc-sync/render-report.py bloat-pr-summary \
            --report "$RUNNER_TEMP/lane.json" --lane prune --pr-url "${PR_URL}"

  distill:
    needs: detect
    if: needs.detect.outputs.distill == 'open'
    runs-on: ubuntu-latest
    env:
      GH_TOKEN: ${{ github.token }}
    steps:
      - uses: actions/checkout@v4
      - uses: actions/download-artifact@v4
        with:
          name: bloat-report
      - name: Apply (headless)
        uses: anthropics/claude-code-action@v1
        with:
          claude_code_oauth_token: ${{ secrets.CLAUDE_CODE_OAUTH_TOKEN }}
          anthropic_api_key: ${{ secrets.ANTHROPIC_API_KEY }}
          plugin_marketplaces: https://github.com/aj604/toolshed.git
          plugins: doc-lifecycle@toolshed
          prompt: >-
            Use the doc-lifecycle:fixing-doc-bloat skill to apply EVERY record in
            bloat-report.json whose verdict is MERGE-DOC, RETIRE-DOC, or DISTILL with
            status "ready" — treat exactly those record IDs as the approved subset, and
            apply nothing else. DISTILL records dispatch the doc-distiller agent per the
            skill. Follow the skill's rules exactly.
          claude_args: --allowedTools "Read,Grep,Glob,Edit,Write,Bash(git *),Bash(python3 *)"
      - name: Open draft PR
        run: |
          set -euo pipefail
          DATE=$(date -u +%F)
          python3 .github/doc-sync/sync-gate.py bloat-lane \
            --report bloat-report.json --lane distill --pr-open 0 \
            --out "$RUNNER_TEMP/lane.json" >/dev/null
          rm -f bloat-report.json
          python3 .github/doc-sync/render-report.py bloat-pr-body \
            --report "$RUNNER_TEMP/lane.json" > "$RUNNER_TEMP/body.md"
          TITLE=$(python3 .github/doc-sync/render-report.py bloat-pr-title \
            --report "$RUNNER_TEMP/lane.json" --lane distill --date "${DATE}")
          git config user.name "doc-bloat"
          git config user.email "doc-bloat@users.noreply.github.com"
          git checkout -b doc-bloat/distill
          git add -A
          git commit -m "docs: bloat distill sweep (${DATE})"
          git push --force "https://x-access-token:${GH_TOKEN}@github.com/${GITHUB_REPOSITORY}.git" doc-bloat/distill
          PR_URL=$(gh pr create --draft \
            --title "${TITLE}" \
            --body-file "$RUNNER_TEMP/body.md" \
            --head doc-bloat/distill \
            --base "${{ github.ref_name }}")
          python3 .github/doc-sync/render-report.py bloat-pr-summary \
            --report "$RUNNER_TEMP/lane.json" --lane distill --pr-url "${PR_URL}"
```

- [ ] **Step 2: Sanity-check the YAML parses**

Run: `python3 -c "import yaml, sys; yaml.safe_load(open('plugins/doc-lifecycle/skills/scheduling-doc-sync/doc-bloat.yml'))" 2>/dev/null && echo OK || echo "no PyYAML — skip (verified at dogfood install)"`
Expected: `OK` (or the skip note if PyYAML absent — the workflow is exercised for real in Task 5).

- [ ] **Step 3: Commit**

```bash
git add plugins/doc-lifecycle/skills/scheduling-doc-sync/doc-bloat.yml
git commit -m "feat(doc-sync): doc-bloat.yml weekly sweep template (two draft-PR lanes)"
```

---

### Task 4: Install instructions + repo inventory

**Files:**
- Modify: `plugins/doc-lifecycle/skills/scheduling-doc-sync/SKILL.md`
- Modify: `CLAUDE.md`

**Interfaces:** none (docs).

- [ ] **Step 1: Update `SKILL.md`**

The skill now installs a **second** workflow. Make these edits:

1. In **Install → step 1 (knobs):** add a third knob:
   `- bloat cron: default \`0 4 * * 1\` (04:00 UTC Mondays); replaces \`{{BLOAT_CRON}}\` in doc-bloat.yml`
2. In **Install → step 2:** after copying `doc-sync.yml`, add: copy
   `doc-bloat.yml` → `.github/workflows/doc-bloat.yml`, replacing `{{BLOAT_CRON}}`.
3. In **Install → step 4:** additionally copy
   `../detecting-doc-bloat/scripts/validate-bloat-output.py` → `.github/doc-sync/validate-bloat-output.py`
   (the bloat workflow's mechanical contract check runs from the repo).
4. In **Install → step 6 (tell the user):** update the file list — now **seven** files to
   commit (`doc-sync.yml`, `doc-bloat.yml`, `sync-gate.py`, `render-report.py`,
   `validate-drift-output.py`, `validate-bloat-output.py`, and the seeded `doc-sync-marker`).
   Add a line: the weekly bloat sweep opens up to two **draft** PRs
   (`doc-bloat/prune`, `doc-bloat/distill`); a lane with no findings, or whose PR is already
   open, is skipped with a self-explaining run summary. Run it now with `gh workflow run doc-bloat`.
5. In **Rules → "Don't customize the installed YAML beyond the two knobs":** change "two
   knobs" to "the cron/cap/bloat-cron knobs" so the bloat cron is a sanctioned knob.

- [ ] **Step 2: Update `CLAUDE.md`**

In the opening paragraph inventory of runnable code, the dogfooded install list currently
names `doc-sync/sync-gate.py`, `doc-sync/render-report.py`, `doc-sync/validate-drift-output.py`,
`workflows/doc-sync.yml`. Add `doc-sync/validate-bloat-output.py` and `workflows/doc-bloat.yml`
to that list. In the **Conventions** bullet listing the helper-script unit tests, the
`sync-gate.py` and `render-report.py` entries already cover the bloat subcommands (same files) —
add a clause noting they now also gate/render the `doc-bloat.yml` lanes.

- [ ] **Step 3: Commit**

```bash
git add plugins/doc-lifecycle/skills/scheduling-doc-sync/SKILL.md CLAUDE.md
git commit -m "docs(doc-sync): scheduling-doc-sync installs the doc-bloat workflow"
```

---

### Task 5: Dogfood install into this repo's `.github/`

**Files:**
- Create: `.github/workflows/doc-bloat.yml`
- Modify: `.github/doc-sync/` (add `validate-bloat-output.py`; refresh `sync-gate.py`, `render-report.py`)

**Interfaces:** none — this exercises the shipped artifacts for real.

- [ ] **Step 1: Refresh the installed scripts + validator**

```bash
cd <repo root>
cp plugins/doc-lifecycle/skills/scheduling-doc-sync/scripts/sync-gate.py .github/doc-sync/sync-gate.py
cp plugins/doc-lifecycle/skills/scheduling-doc-sync/scripts/render-report.py .github/doc-sync/render-report.py
cp plugins/doc-lifecycle/skills/detecting-doc-bloat/scripts/validate-bloat-output.py .github/doc-sync/validate-bloat-output.py
```

- [ ] **Step 2: Install the workflow with the cron filled in**

Copy the template and replace the placeholder (default weekly Monday 04:00 UTC):

```bash
sed 's/{{BLOAT_CRON}}/0 4 * * 1/' \
  plugins/doc-lifecycle/skills/scheduling-doc-sync/doc-bloat.yml \
  > .github/workflows/doc-bloat.yml
```

Verify no placeholder remains:

Run: `grep -c '{{' .github/workflows/doc-bloat.yml`
Expected: `0`

- [ ] **Step 3: Run the full unit-test suite (regression + new)**

Run:
```bash
python3 tests/scripts/sync-gate_test.py && \
python3 tests/scripts/render-report_test.py && \
python3 tests/scripts/validate-bloat-output_test.py && \
python3 tests/scripts/validate-drift-output_test.py
```
Expected: all `OK`.

- [ ] **Step 4: Smoke-test the installed gate/render against a synthetic report**

Run:
```bash
printf '{"records":[{"id":"B1","doc":"README.md","location":"README.md:5","verdict":"CUT","evidence":"restates code","proposal":null,"status":null,"payload":null}],"summary":{"cut":1,"condense":0,"extract_and_move":0,"retire_doc":0,"merge_doc":0,"distill":0}}' > /tmp/bloat.json
python3 .github/doc-sync/validate-bloat-output.py /tmp/bloat.json
python3 .github/doc-sync/sync-gate.py bloat-lane --report /tmp/bloat.json --lane prune --pr-open 0 --out /tmp/prune.json
python3 .github/doc-sync/render-report.py bloat-pr-body --report /tmp/prune.json
```
Expected: validator `OK`; gate prints `open`; body shows `` `CUT` @ `README.md:5` ``.

- [ ] **Step 5: Commit**

```bash
git add .github/workflows/doc-bloat.yml .github/doc-sync/
git commit -m "chore(doc-sync): dogfood the doc-bloat workflow install"
```

- [ ] **Step 6: Note for the human**

`gh workflow run doc-bloat` can only be dispatched once `doc-bloat.yml` is on the default
branch (GitHub dispatches workflows from the default branch). So the first live run happens
**after this branch merges**. Surface that in the PR description; do not claim a live run was
verified when only the unit tests + local smoke test ran.

---

## Self-Review

**Spec coverage:**
- Sibling weekly workflow → Task 3. ✓
- Full sweep incl. `docs/plans/` → Task 3 detect prompt. ✓
- Two draft PRs split by verdict weight → Task 3 lane jobs + Task 1 membership. ✓
- `DISTILL pending-implementation` dropped → Task 1 `in_lane` (status gate) + test. ✓
- Both lanes apply for real, merge = approval → Task 3 apply steps + `--draft`. ✓
- Per-lane dedup → Task 1 `bloat-pre`/`bloat-lane` pr-open handling + Task 3 facts. ✓
- Extend not fork (gate/render subcommands, validator copied) → Tasks 1, 2, 4. ✓
- Install docs + repo inventory → Task 4. ✓
- Dogfood → Task 5. ✓

**Placeholder scan:** `{{BLOAT_CRON}}` is an intentional template token, resolved in Task 5 Step 2 and asserted absent. No TBD/TODO.

**Type consistency:** `filter_lane`/`in_lane`/`decide_bloat_*` names consistent across Tasks 1–2; lane keys `prune`/`distill` and verdict sets identical in design, gate code, gate tests, and the Task 3 apply prompts. Filtered-file shape `{"records":[...]}` written by Task 1 `--out` and read by Task 2 `load_records` (which unwraps it) match.
</content>
