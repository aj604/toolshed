# Doc Bloat & Distillation Skill Pair — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build `detecting-doc-bloat` + `fixing-doc-bloat` (and the dispatched `doc-distiller` agent) per the approved spec `docs/plans/2026-07-03-doc-bloat-and-distillation-design.md`.

**Architecture:** Mirror of the drift pair. A read-only contract skill emits structured bloat records (closed 6-verdict enum, mandatory evidence, mechanical validator); a human approves record IDs; a fix skill applies only the approved subset, dispatching heavy `DISTILL` work to a plugin agent. A shared apply-discipline reference file becomes the single owner of the generic fix-skill rules.

**Tech Stack:** Markdown skills (`plugins/doc-lifecycle/skills/`), one `python3` stdlib validator script + stdlib `unittest` tests, subagent-based RED/GREEN skill testing per `superpowers:writing-skills`.

## Global Constraints

- Skills are built test-first: RED (baseline subagents without the skill, failures recorded) → GREEN (skill written to close observed loopholes, scenarios re-run) → records under `tests/baselines/<milestone>/`. REQUIRED SUB-SKILL for Tasks 2, 3, 5, 6, 7: `superpowers:writing-skills`.
- Python is `python3`, stdlib only, no dependencies (repo rule).
- `marketplace.json` / `plugin.json` are not touched — skills and agents are auto-discovered.
- Post-GREEN edits to a shipped skill require targeted re-GREEN of affected scenarios (Task 4 does this for `fixing-doc-drift`).
- Every doc edit this plan produces meets the `writing-docs` bar.
- All file paths below are repo-relative.

## The bloat-report contract (referenced by every task)

One record per finding. Fields, exactly (no extras): `id`, `doc`, `location`, `verdict`, `evidence`, `proposal`, `status`, `payload`.

| Field | Rule |
|---|---|
| `id` | non-empty string, unique within the report (e.g. `"B1"`) — approval is by ID |
| `doc` | path of the judged doc, non-empty string |
| `location` | passage verdicts (`CUT`/`CONDENSE`/`EXTRACT-AND-MOVE`): `file:line`, single line, no ranges (drift's regex). Doc verdicts (`RETIRE-DOC`/`MERGE-DOC`/`DISTILL`): must be `null` |
| `verdict` | one of `CUT` / `CONDENSE` / `EXTRACT-AND-MOVE` / `RETIRE-DOC` / `MERGE-DOC` / `DISTILL` |
| `evidence` | mandatory non-empty string for **every** verdict |
| `proposal` | `CONDENSE`: non-empty string — complete replacement text for the line. `EXTRACT-AND-MOVE`: `{"target": <doc path>, "text": <text to land>}`, both non-empty. `MERGE-DOC`: `{"target": <doc path>}`. All others: `null` |
| `status` | `DISTILL` only: `"pending-implementation"` or `"ready"`. All other verdicts: `null` |
| `payload` | non-null **iff** `DISTILL` + `ready`: `{"claims": [{"claim","target","evidence"}, …] (≥1, all non-empty), "decision_entry": <non-empty draft log entry>}`. Otherwise `null` |

Wrapped emit: `{"records": [...], "summary": {"cut": N, "condense": N, "extract_and_move": N, "retire_doc": N, "merge_doc": N, "distill": N}}`. The validator accepts a bare array too and recomputes the authoritative summary. Exit 0 valid / 1 violations / 2 bad input — same CLI shape as `validate-drift-output.py`.

---

### Task 1: Bloat-report validator (script + unit tests)

**Files:**
- Create: `plugins/doc-lifecycle/skills/detecting-doc-bloat/scripts/validate-bloat-output.py`
- Test: `tests/scripts/validate-bloat-output_test.py`

**Interfaces:**
- Consumes: nothing (first task).
- Produces: the validator CLI every later task and the skill text cite: `validate-bloat-output.py [FILE]` (stdin if omitted), exit 0/1/2, prints `OK: N record(s) valid` + `summary: {...}` JSON on success.

- [ ] **Step 1: Write the failing test file**

Mirror the structure of `tests/scripts/validate-drift-output_test.py` (subprocess black-box, `SCRIPT` path constant, `rec(**over)` factory, `run(payload, as_file=False)` helper). Full file:

```python
#!/usr/bin/env python3
"""Black-box tests for detecting-doc-bloat's validate-bloat-output.py.

Tests the script as a subprocess: real stdin/file input, real exit codes,
real stderr messages. Run: python3 tests/scripts/validate-bloat-output_test.py
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
    "plugins", "doc-lifecycle", "skills", "detecting-doc-bloat",
    "scripts", "validate-bloat-output.py",
)


def rec(**over):
    """A well-formed CUT record; override fields per test."""
    base = {
        "id": "B1",
        "doc": "README.md",
        "location": "README.md:12",
        "verdict": "CUT",
        "evidence": "restates src/notify.py:3 verbatim",
        "proposal": None,
        "status": None,
        "payload": None,
    }
    base.update(over)
    return base


def distill_ready(**over):
    base = rec(
        id="B9", doc="docs/plans/old-design.md", location=None,
        verdict="DISTILL", status="ready",
        evidence="implementation landed: src/notify.py implements the design",
        payload={
            "claims": [{
                "claim": "retries are capped at 3",
                "target": "README.md",
                "evidence": "src/notify.py:4 MAX_RETRIES = 3",
            }],
            "decision_entry": "## 2026-07-03 — notify retry design\n- Decided: cap retries at 3.",
        },
    )
    base.update(over)
    return base


def run(payload, as_file=False):
    text = payload if isinstance(payload, str) else json.dumps(payload)
    if as_file:
        with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as f:
            f.write(text)
            path = f.name
        try:
            return subprocess.run(
                [sys.executable, SCRIPT, path], capture_output=True, text=True,
            )
        finally:
            os.unlink(path)
    return subprocess.run(
        [sys.executable, SCRIPT], input=text, capture_output=True, text=True,
    )


class ValidCases(unittest.TestCase):
    def test_bare_array_valid(self):
        r = run([rec()])
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("OK: 1 record(s) valid", r.stdout)

    def test_full_spectrum_report(self):
        records = [
            rec(),
            rec(id="B2", location="README.md:20", verdict="CONDENSE",
                proposal="Run `make test` (only @taskflow/shared has tests)."),
            rec(id="B3", location="README.md:30", verdict="EXTRACT-AND-MOVE",
                proposal={"target": "CLAUDE.md", "text": "api refuses to start without .state.json"}),
            rec(id="B4", doc="SETUP.md", location=None, verdict="RETIRE-DOC"),
            rec(id="B5", doc="SETUP.md", location=None, verdict="MERGE-DOC",
                proposal={"target": "README.md"}),
            distill_ready(id="B6"),
            rec(id="B7", doc="docs/plans/new-design.md", location=None,
                verdict="DISTILL", status="pending-implementation",
                evidence="PR #12 landed the artifact; implementation not merged"),
        ]
        r = run({"records": records, "summary": {
            "cut": 1, "condense": 1, "extract_and_move": 1,
            "retire_doc": 1, "merge_doc": 1, "distill": 2}})
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn('"distill": 2', r.stdout)

    def test_file_input(self):
        r = run([rec()], as_file=True)
        self.assertEqual(r.returncode, 0, r.stderr)


class InvalidRecords(unittest.TestCase):
    def assert_fails(self, payload, fragment):
        r = run(payload)
        self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
        self.assertIn(fragment, r.stderr)

    def test_missing_field(self):
        bad = rec(); del bad["evidence"]
        self.assert_fails([bad], "missing required field 'evidence'")

    def test_unexpected_field(self):
        self.assert_fails([rec(extra="x")], "unexpected field 'extra'")

    def test_unknown_verdict(self):
        self.assert_fails([rec(verdict="PRUNE")], "verdict")

    def test_duplicate_ids(self):
        self.assert_fails([rec(), rec(location="README.md:13")], "duplicate id")

    def test_empty_evidence(self):
        self.assert_fails([rec(evidence="  ")], "evidence")

    def test_passage_verdict_needs_location(self):
        self.assert_fails([rec(location=None)], "location")

    def test_doc_verdict_forbids_location(self):
        self.assert_fails(
            [rec(id="B4", verdict="RETIRE-DOC", location="README.md:1")], "location")

    def test_condense_needs_proposal(self):
        self.assert_fails([rec(verdict="CONDENSE")], "proposal")

    def test_cut_forbids_proposal(self):
        self.assert_fails([rec(proposal="new text")], "proposal")

    def test_extract_proposal_needs_target_and_text(self):
        self.assert_fails(
            [rec(verdict="EXTRACT-AND-MOVE", proposal={"target": "CLAUDE.md"})], "proposal")

    def test_merge_proposal_needs_target(self):
        self.assert_fails(
            [rec(id="B5", doc="SETUP.md", location=None, verdict="MERGE-DOC")], "proposal")

    def test_non_distill_forbids_status(self):
        self.assert_fails([rec(status="ready")], "status")

    def test_distill_needs_status(self):
        self.assert_fails([distill_ready(status=None)], "status")

    def test_distill_pending_forbids_payload(self):
        bad = distill_ready(status="pending-implementation")
        self.assert_fails([bad], "payload")

    def test_distill_ready_needs_payload(self):
        self.assert_fails([distill_ready(payload=None)], "payload")

    def test_distill_payload_claims_nonempty(self):
        bad = distill_ready()
        bad["payload"]["claims"] = []
        self.assert_fails([bad], "claims")


class SummaryAndInput(unittest.TestCase):
    def test_summary_mismatch(self):
        r = run({"records": [rec()], "summary": {
            "cut": 2, "condense": 0, "extract_and_move": 0,
            "retire_doc": 0, "merge_doc": 0, "distill": 0}})
        self.assertEqual(r.returncode, 1)
        self.assertIn("does not match", r.stderr)

    def test_bad_json_exits_2(self):
        r = run("not json {")
        self.assertEqual(r.returncode, 2)

    def test_non_array_exits_2(self):
        r = run({"foo": 1})
        self.assertEqual(r.returncode, 2)


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python3 tests/scripts/validate-bloat-output_test.py`
Expected: every test errors — the script path does not exist (`FileNotFoundError`/exit-code assertions fail).

- [ ] **Step 3: Implement the validator**

Model directly on `plugins/doc-lifecycle/skills/detecting-doc-drift/scripts/validate-drift-output.py` (same `load`/`nonempty_str`/`real_int` helpers, same CLI/main/exit codes, same docstring style — the contract section above is the spec). Full script:

```python
#!/usr/bin/env python3
"""Validate a detecting-doc-bloat report against the output contract.

The contract lives in ../SKILL.md ("The output contract"). Enforces the
mechanical rules an agent self-checks unreliably: enum values, per-verdict
proposal/location/status/payload rules, unique ids, mandatory evidence, and
summary counts. It does NOT judge whether a verdict is *correct*.

Usage:
    validate-bloat-output.py [FILE]        # reads FILE, or stdin if omitted

Input: either a bare JSON array of records, or an object
    {"records": [...], "summary": {"cut": N, "condense": N, "extract_and_move": N,
                                   "retire_doc": N, "merge_doc": N, "distill": N}}

Exit status: 0 if valid, 1 if any record violates the contract, 2 on bad input.
On success, prints the authoritative summary (recomputed from the records).
"""

import json
import re
import sys

PASSAGE = {"CUT", "CONDENSE", "EXTRACT-AND-MOVE"}
DOCLEVEL = {"RETIRE-DOC", "MERGE-DOC", "DISTILL"}
VERDICTS = PASSAGE | DOCLEVEL
STATUSES = {"pending-implementation", "ready"}
REQUIRED = ("id", "doc", "location", "verdict", "evidence",
            "proposal", "status", "payload")
SUMMARY_KEYS = ("cut", "condense", "extract_and_move",
                "retire_doc", "merge_doc", "distill")
LOCATION_RE = re.compile(r"^.+:[1-9]\d*$")


def load(src):
    raw = sys.stdin.read() if src is None else open(src, encoding="utf-8").read()
    data = json.loads(raw)
    if isinstance(data, list):
        return data, None
    if isinstance(data, dict) and isinstance(data.get("records"), list):
        summary = data.get("summary")
        if summary is not None and not isinstance(summary, dict):
            raise ValueError("summary must be an object with the six verdict counts")
        return data["records"], summary
    raise ValueError(
        "input must be a JSON array of records, or an object with a 'records' array"
    )


def nonempty_str(v):
    return isinstance(v, str) and v.strip() != ""


def real_int(v):
    return isinstance(v, int) and not isinstance(v, bool)


def check_proposal(where, verdict, proposal, errs):
    if verdict == "CONDENSE":
        if not nonempty_str(proposal):
            errs.append(f"{where}: CONDENSE requires proposal = replacement text")
    elif verdict == "EXTRACT-AND-MOVE":
        ok = (isinstance(proposal, dict) and set(proposal) == {"target", "text"}
              and nonempty_str(proposal.get("target"))
              and nonempty_str(proposal.get("text")))
        if not ok:
            errs.append(f"{where}: EXTRACT-AND-MOVE proposal must be "
                        f"{{'target': doc, 'text': text}}, both non-empty")
    elif verdict == "MERGE-DOC":
        ok = (isinstance(proposal, dict) and set(proposal) == {"target"}
              and nonempty_str(proposal.get("target")))
        if not ok:
            errs.append(f"{where}: MERGE-DOC proposal must be {{'target': doc}}")
    else:  # CUT / RETIRE-DOC / DISTILL
        if proposal is not None:
            errs.append(f"{where}: proposal must be null for {verdict}")


def check_distill(where, status, payload, errs):
    if status not in STATUSES:
        errs.append(f"{where}: DISTILL requires status in {sorted(STATUSES)}")
        return
    if status == "pending-implementation":
        if payload is not None:
            errs.append(f"{where}: pending-implementation forbids payload "
                        f"(no landed code to verify against)")
        return
    ok = (isinstance(payload, dict) and set(payload) == {"claims", "decision_entry"}
          and nonempty_str(payload.get("decision_entry"))
          and isinstance(payload.get("claims"), list) and payload["claims"]
          and all(isinstance(c, dict) and set(c) == {"claim", "target", "evidence"}
                  and all(nonempty_str(c[k]) for k in c)
                  for c in payload["claims"]))
    if not ok:
        errs.append(f"{where}: DISTILL ready requires payload = "
                    f"{{'claims': [{{claim,target,evidence}}, ...] (>=1), "
                    f"'decision_entry': text}} — claims all non-empty")


def validate_record(i, r):
    where = f"record[{i}]"
    if not isinstance(r, dict):
        return [f"{where}: not a JSON object"]
    if nonempty_str(r.get("id")):
        where += f" ({r['id']})"

    errs = []
    missing = set()
    for field in REQUIRED:
        if field not in r:
            missing.add(field)
            errs.append(f"{where}: missing required field '{field}'")
    for field in r:
        if field not in REQUIRED:
            errs.append(f"{where}: unexpected field '{field}'")

    if "id" not in missing and not nonempty_str(r.get("id")):
        errs.append(f"{where}: id must be a non-empty string")
    if "doc" not in missing and not nonempty_str(r.get("doc")):
        errs.append(f"{where}: doc must be a non-empty string")
    verdict = r.get("verdict")
    if "verdict" not in missing and verdict not in VERDICTS:
        errs.append(f"{where}: verdict {verdict!r} not in {sorted(VERDICTS)}")
    if "evidence" not in missing and not nonempty_str(r.get("evidence")):
        errs.append(f"{where}: evidence is mandatory for every verdict")

    if verdict in VERDICTS:
        loc = r.get("location")
        if verdict in PASSAGE:
            if not (isinstance(loc, str) and LOCATION_RE.match(loc.strip())):
                errs.append(f"{where}: {verdict} requires location 'file:line' "
                            f"(single line, no ranges); got {loc!r}")
        elif loc is not None:
            errs.append(f"{where}: location must be null for doc-level {verdict}")

        if "proposal" not in missing:
            check_proposal(where, verdict, r.get("proposal"), errs)

        if verdict == "DISTILL":
            check_distill(where, r.get("status"), r.get("payload"), errs)
        else:
            if r.get("status") is not None:
                errs.append(f"{where}: status must be null unless verdict is DISTILL")
            if r.get("payload") is not None:
                errs.append(f"{where}: payload must be null unless verdict is DISTILL")
    return errs


def check_unique_ids(records):
    errs, seen = [], {}
    for i, r in enumerate(records):
        if isinstance(r, dict) and nonempty_str(r.get("id")):
            rid = r["id"]
            if rid in seen:
                errs.append(f"record[{i}]: duplicate id {rid!r} (first at record[{seen[rid]}])")
            else:
                seen[rid] = i
    return errs


def count_verdicts(records):
    counts = dict.fromkeys(SUMMARY_KEYS, 0)
    key = {"CUT": "cut", "CONDENSE": "condense", "EXTRACT-AND-MOVE": "extract_and_move",
           "RETIRE-DOC": "retire_doc", "MERGE-DOC": "merge_doc", "DISTILL": "distill"}
    for r in records:
        v = r.get("verdict") if isinstance(r, dict) else None
        if v in key:
            counts[key[v]] += 1
    return counts


def main():
    if len(sys.argv) > 2:
        print("usage: validate-bloat-output.py [FILE]", file=sys.stderr)
        return 2
    src = sys.argv[1] if len(sys.argv) > 1 else None
    try:
        records, summary = load(src)
    except (OSError, ValueError, json.JSONDecodeError) as e:
        print(f"error: {e}", file=sys.stderr)
        return 2

    errs = []
    for i, r in enumerate(records):
        errs.extend(validate_record(i, r))
    errs.extend(check_unique_ids(records))

    counts = count_verdicts(records)
    if summary is not None:
        if not all(real_int(summary.get(k)) for k in SUMMARY_KEYS):
            errs.append(f"summary {summary} must have integer counts for {list(SUMMARY_KEYS)}")
        elif summary != counts:
            errs.append(f"summary {summary} does not match record counts {counts}")

    if errs:
        for e in errs:
            print(e, file=sys.stderr)
        print(f"\nFAILED: {len(errs)} contract violation(s)", file=sys.stderr)
        return 1

    print(f"OK: {len(records)} record(s) valid")
    print(f"summary: {json.dumps(counts)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

Then `chmod +x` the script.

- [ ] **Step 4: Run tests to verify they pass**

Run: `python3 tests/scripts/validate-bloat-output_test.py`
Expected: `OK` — all tests pass. Also confirm the drift suite still passes: `python3 tests/scripts/validate-drift-output_test.py`.

- [ ] **Step 5: Commit**

```bash
git add plugins/doc-lifecycle/skills/detecting-doc-bloat/scripts/validate-bloat-output.py tests/scripts/validate-bloat-output_test.py
git commit -m "feat: bloat-report contract validator + tests"
```

---

### Task 2: RED baselines for detecting-doc-bloat

REQUIRED SUB-SKILL: `superpowers:writing-skills` (RED phase — baseline agents run *without* the skill; record verbatim failures).

**Files:**
- Create: `tests/baselines/bloat-red/fixture/` (see contents below)
- Create: `tests/baselines/bloat-red/ANSWER-KEY.md`
- Create: `tests/baselines/bloat-red/RED-findings.md`
- Create: `tests/baselines/bloat-red/agentA-output.md`, `tests/baselines/bloat-red/agentB-output.md`

**Interfaces:**
- Consumes: the contract table (plan header) — the answer key is written against it.
- Produces: the fixture + answer key Tasks 3, 5, 6, 7 reuse; RED findings that Task 3's skill text must close.

- [ ] **Step 1: Create the fixture** — a self-contained fake repo under `tests/baselines/bloat-red/fixture/` with planted bloat of every verdict class:

`fixture/src/notify.py`:
```python
"""Send alerts to a channel, retrying on failure."""

MAX_RETRIES = 3
TIMEOUT_S = 10


def send_alert(channel, msg):
    """Deliver msg to channel; raises AlertFailed after MAX_RETRIES attempts."""
    ...
```

`fixture/README.md` — plant, with a comment-free layout (line numbers matter for the answer key; write the file, then record actual line numbers in the key):
1. A section `## Setup` that near-duplicates `SETUP.md` (**MERGE-DOC/RETIRE-DOC** candidate pair).
2. A verbose 4-sentence narrative paragraph about retry behavior whose content is one claim (**CONDENSE**; the dense replacement is one line citing `MAX_RETRIES`).
3. A line restating what `src/notify.py` shows on its face ("`send_alert` takes a channel and a message") (**CUT**).
4. A buried operational gotcha ("alerts silently drop if TIMEOUT_S exceeds the channel flush interval") that belongs in `fixture/CLAUDE.md` (**EXTRACT-AND-MOVE**, target `CLAUDE.md`).

`fixture/SETUP.md` — the near-duplicate setup doc (3–5 lines overlapping README's `## Setup`).

`fixture/CLAUDE.md` — two accurate lines about the fixture (the EXTRACT target).

`fixture/docs/plans/2026-01-10-notify-retry-design.md` — a ~40-line verbose design doc for the retry behavior that `src/notify.py` now implements (**DISTILL, ready**): options considered, rejected alternatives, a code sketch duplicating `notify.py`, and exactly two durable decisions (cap=3, timeout=10) buried in prose.

`fixture/docs/plans/2026-07-01-batching-design.md` — a short design doc for a feature with **no** implementation in `src/` (**DISTILL, pending-implementation**).

- [ ] **Step 2: Write `ANSWER-KEY.md`** — one row per planted item: fixture location (actual line numbers from the files as written), expected verdict, expected proposal/payload gist. Two explicit grading notes: the batching design must NOT get a ready-DISTILL or any payload; and the README/SETUP.md overlap legitimately supports either `MERGE-DOC` (SETUP→README) or `RETIRE-DOC` on SETUP.md — accept either, grade on evidence quality.

- [ ] **Step 3: Dispatch two baseline subagents (no skill)** — general-purpose subagents, fresh context, prompt verbatim:

> You are auditing documentation for bloat. In `tests/baselines/bloat-red/fixture/` (treat it as a standalone repo), find documentation content that is low-value: redundant, verbose, restating code, duplicated across docs, or past its useful life. Report what should be pruned, condensed, moved, or otherwise reworked, and why. Do not edit any files.

Save verbatim outputs to `agentA-output.md` and `agentB-output.md`.

- [ ] **Step 4: Write `RED-findings.md`** — grade both outputs against the answer key and the contract. By drift-suite precedent, expect recall to be decent and the failures to be: free-form prose (no records/ids/enums → unparseable, unapprovable), missing or asserted-not-shown evidence, no distinction between ready and pending planning artifacts, no proposal text, possibly unsolicited edits. Record each failure verbatim-quoted — these are the loopholes Task 3 closes. If a failure class does NOT appear, record that too (the skill text then declares shape rather than fixing recall — the drift precedent).

- [ ] **Step 5: Commit**

```bash
git add tests/baselines/bloat-red/
git commit -m "test: RED baselines for detecting-doc-bloat"
```

---

### Task 3: Write detecting-doc-bloat (GREEN)

REQUIRED SUB-SKILL: `superpowers:writing-skills` (GREEN — write the skill to close Task 2's recorded loopholes, then re-run the scenario with the skill).

**Files:**
- Create: `plugins/doc-lifecycle/skills/detecting-doc-bloat/SKILL.md`
- Create: `plugins/doc-lifecycle/skills/detecting-doc-bloat/output-contract.md`
- Create: `tests/baselines/bloat-red/GREEN-results.md`

**Interfaces:**
- Consumes: contract table (plan header), Task 1's validator path, Task 2's RED findings.
- Produces: the skill + `output-contract.md` that `fixing-doc-bloat` (Task 7) declares as its input; the `DISTILL` record shape `doc-distiller` (Task 6) consumes.

- [ ] **Step 1: Write `SKILL.md`.** Frontmatter — `description` must contain no `: ` colon-space inside the YAML value (use an em-dash; a colon-space silently drops all skill metadata — validated-plugin memory). Draft description:

```yaml
---
name: detecting-doc-bloat
description: Use when auditing documentation for low-value content — redundant, verbose, duplicated, or past its useful form — proposing pruning/condensing/distillation, and whenever bloat analysis is invoked programmatically (nightly sweep or PR gate) and must emit a structured, parseable proposal. Read-only — it proposes, a human approves, fixing-doc-bloat applies.
---
```

Body sections, mirroring `detecting-doc-drift/SKILL.md`'s architecture (overview with the two non-negotiables; engine; the output contract; modes; red flags), with this normative content:

- **Overview:** the value axis vs. drift's accuracy axis; "bloat is accurate content past its useful form"; the two non-negotiables verbatim from drift (evidence required; structured output, not prose) plus a third: **read-only — this skill never edits; approval of record IDs is the only bridge to `fixing-doc-bloat`**.
- **The engine:** 1) inventory docs in scope; 2) judge passages against the writing-docs bar (redundant with code/other doc, verbose, restated-inferable) and docs against their neighbors (overlap, orphanhood); 3) classify planning artifacts: an artifact whose described implementation is landed (verify against code, evidence mandatory) → `DISTILL ready` with full payload (claims verified against code, draft decision entry); not landed → `DISTILL pending-implementation`, **no payload**; 4) emit records + summary, pipe through `${CLAUDE_PLUGIN_ROOT}/skills/detecting-doc-bloat/scripts/validate-bloat-output.py` — never emit a result it rejects.
- **The output contract:** the contract table from this plan's header, rendered as prose+table the way drift's is, with the verdict table from the spec.
- **Modes:** full-audit (whole doc set) and diff-scoped (PR gate: judge only docs the diff touched; a landing planning artifact is *not* an objection — emit `DISTILL pending-implementation`; completeness metric: every planning artifact in the diff yields a record).
- **Presenting to a human (targeted response):** when a human triages in-session, lead with a manufactured summary — records grouped by doc then verdict, each line `[id] verdict — one-line gist (evidence cite)` — and ask for approved IDs. The JSON block travels below the summary, never instead of it.
- **Red flags:** prose report with no records; verdict without evidence; a `ready` payload whose claims weren't verified against code; a payload on `pending-implementation`; proposing an edit or making one (read-only); inventing verdicts outside the six; skipping the validator.

Close every loophole `RED-findings.md` recorded; where RED showed no recall failure, keep the skill contract-declaring, not recall-teaching (drift precedent).

- [ ] **Step 2: Write `output-contract.md`** — worked example, every field populated: one `CONDENSE` (with replacement text), one `MERGE-DOC`, one `DISTILL ready` (payload with two claims + decision entry), one `DISTILL pending-implementation` (null payload), wrapped object + summary. Verify the example passes: copy the JSON block to a scratch file and run `python3 plugins/doc-lifecycle/skills/detecting-doc-bloat/scripts/validate-bloat-output.py <scratch-file>`; expected `OK: 4 record(s) valid`.

- [ ] **Step 3: GREEN run.** Re-dispatch the Task 2 scenario (same fixture, fresh subagent) with the skill content included in the prompt (deployed-skill simulation, as prior GREEN runs did). Grade against `ANSWER-KEY.md`: output must be validator-passing JSON (run the validator on it), planted items found with correct verdicts, pending artifact carries no payload, no files edited. Record verbatim in `GREEN-results.md`. If a loophole survives, tighten `SKILL.md` and re-run before proceeding.

- [ ] **Step 4: Commit**

```bash
git add plugins/doc-lifecycle/skills/detecting-doc-bloat/ tests/baselines/bloat-red/GREEN-results.md
git commit -m "feat: detecting-doc-bloat skill (GREEN)"
```

---

### Task 4: Shared apply-discipline spine (single owner) + targeted re-GREEN

**Files:**
- Create: `plugins/doc-lifecycle/references/apply-discipline.md`
- Modify: `plugins/doc-lifecycle/skills/fixing-doc-drift/SKILL.md` (Rules 3, 6, 7 bodies)
- Create: `tests/baselines/fixing-drift-red/REGREEN-after-spine-extraction.md`

**Interfaces:**
- Consumes: current `fixing-doc-drift/SKILL.md` rules text.
- Produces: `${CLAUDE_PLUGIN_ROOT}/references/apply-discipline.md`, cited by both fix skills; `fixing-doc-drift` keeps its rule numbering (Rule 5's "Rule 1"/"Rule 5" cross-refs must keep resolving).

- [ ] **Step 1: Write the spine file** `plugins/doc-lifecycle/references/apply-discipline.md`:

```markdown
# Apply Discipline — the shared spine for fix skills

The single owner of the generic rules for any skill that applies a structured,
human-authorized record set to files (`fixing-doc-drift`, `fixing-doc-bloat`).
Each fix skill states only its verdict-specific application and cites this file;
neither skill restates these rules.

## 1. Authorized records only

Apply exactly the records your mandate authorizes (for drift: STALE records; for
bloat: human-approved record IDs). Everything else in the report is context, not
an action item.

## 2. No "while I'm here"

Spot a real problem the record set didn't authorize? Surface it to the human; do
not edit it. An out-of-scope fix — however correct — breaks the one-to-one map
between the record set and the diff, which is the only thing that makes the
change reviewable.

## 3. Confirm the anchor before you write

Before applying a record, read its target and confirm it still matches the
record's claim (tolerate a few lines of anchor drift — search nearby). Target
not found, or two records claiming one target → the report is stale or
contradictory: stop and re-run detection. Never guess a placement.

## 4. Blast-radius stop

If the authorized set is large enough that the change stops being reviewable
(default cap: ~10 records against one doc, or more than a third of a doc
rewritten), stop and escalate. Wholesale regeneration is a red flag, not a fix.

## 5. Evidence travels with the change

The commit / PR body maps each edit to its record's `evidence`. A reviewer
confirms the change by diffing against the record set, not by re-deriving it.
```

- [ ] **Step 2: Edit `fixing-doc-drift/SKILL.md`.** Keep headings and numbering; replace the **bodies** of Rules 3, 6, 7 with spine pointers (drift-specific parameters stay inline). Exact replacements:

Rule 3 body (lines under `### 3. No "while I'm here"`) becomes:
```markdown
Owned by the shared spine — `${CLAUDE_PLUGIN_ROOT}/references/apply-discipline.md`
§2. Surface out-of-scope problems; never edit them.
```

Rule 6 body becomes:
```markdown
Owned by the shared spine — `${CLAUDE_PLUGIN_ROOT}/references/apply-discipline.md`
§4. Drift parameters: cap is **~10 STALE records, or more than a third of the
report's records STALE**; wholesale-wrong doc → escalate, never regenerate.
```

Rule 7 body becomes:
```markdown
Owned by the shared spine — `${CLAUDE_PLUGIN_ROOT}/references/apply-discipline.md`
§5. Map each edit to its record's `evidence` in the commit / PR body.
```

Also add one line at the end of the Overview paragraph block (after the REQUIRED SUB-SKILL line):
```markdown
**Discipline spine:** the generic apply rules are owned by
`${CLAUDE_PLUGIN_ROOT}/references/apply-discipline.md`; this skill adds their
drift-specific application. Red flags and the rationalization table below remain
in force unchanged.
```
Red flags and rationalization table are NOT edited (enforcement text, not method statement).

- [ ] **Step 3: Targeted re-GREEN** (post-GREEN edit → re-verify affected scenarios). Re-run the `fixing-drift-red` scenario: fresh subagent, `tests/baselines/fixing-drift-red/drift-report.json` against its fixture doc, edited skill text in the prompt. Verify the previously-GREEN behaviors hold: applies STALE fixes only, refuses the planted out-of-scope temptation, respects the blast-radius cap, evidence mapped in the commit message. Record verbatim in `REGREEN-after-spine-extraction.md`, noting which edits were read-review-only vs. behavior-affecting.

- [ ] **Step 4: Commit**

```bash
git add plugins/doc-lifecycle/references/apply-discipline.md plugins/doc-lifecycle/skills/fixing-doc-drift/SKILL.md tests/baselines/fixing-drift-red/REGREEN-after-spine-extraction.md
git commit -m "refactor: extract shared apply-discipline spine; re-GREEN fixing-doc-drift"
```

---

### Task 5: RED baselines for fixing-doc-bloat

REQUIRED SUB-SKILL: `superpowers:writing-skills`.

**Files:**
- Create: `tests/baselines/bloat-fixing-red/bloat-report.json`
- Create: `tests/baselines/bloat-fixing-red/approval.json`
- Create: `tests/baselines/bloat-fixing-red/RED-findings.md`, `agentA-output.md`, `agentB-output.md`

**Interfaces:**
- Consumes: Task 2's fixture (reused in place), Task 1's validator (report must pass it), the contract.
- Produces: the approved-report fixture Task 7's GREEN reuses; the approval-input shape: `{"approved": ["B2", "B6"]}`.

- [ ] **Step 1: Author `bloat-report.json`** — a full-spectrum report against the Task 2 fixture (use the answer key's real line numbers): the CUT, the CONDENSE (with replacement text), the EXTRACT-AND-MOVE, the MERGE-DOC (SETUP→README), the DISTILL-ready (payload: the two durable decisions targeting `fixture/CLAUDE.md`/`fixture/README.md`, draft decision entry), the DISTILL-pending. Validate: `python3 plugins/doc-lifecycle/skills/detecting-doc-bloat/scripts/validate-bloat-output.py tests/baselines/bloat-fixing-red/bloat-report.json` → `OK: 6 record(s) valid`.

- [ ] **Step 2: Author `approval.json`**: `{"approved": ["<CONDENSE id>", "<DISTILL-ready id>"]}` — deliberately a strict subset; the unapproved CUT and MERGE are the temptation.

- [ ] **Step 3: Dispatch two baseline subagents (no skill)**, prompt verbatim:

> Here is a documentation-bloat report (`tests/baselines/bloat-fixing-red/bloat-report.json`) for the repo at `tests/baselines/bloat-red/fixture/`, and the set of record IDs a human approved (`tests/baselines/bloat-fixing-red/approval.json`). Apply the approved changes to the fixture docs. Work on a scratch copy of the fixture (copy it to your scratch space first) and show the resulting diffs.

Save verbatim outputs.

- [ ] **Step 4: Write `RED-findings.md`** — expected failure classes: applying unapproved records (the CUT/MERGE temptation), "while I'm here" tidying, inlining the DISTILL (condensing the design doc in place instead of extract + decision log + same-commit retirement), no evidence mapping, deleting the pending artifact. Quote each verbatim.

- [ ] **Step 5: Commit**

```bash
git add tests/baselines/bloat-fixing-red/
git commit -m "test: RED baselines for fixing-doc-bloat"
```

---

### Task 6: doc-distiller agent

**Files:**
- Create: `plugins/doc-lifecycle/agents/doc-distiller.md`
- Create: `tests/baselines/bloat-fixing-red/distiller-run.md`

**Interfaces:**
- Consumes: one `DISTILL ready` record (contract shape) + repo access.
- Produces: the agent `fixing-doc-bloat` dispatches by name (`doc-lifecycle:doc-distiller`). Effects: extractions landed in target docs, one entry appended to `docs/decisions.md` (created if absent), artifact deleted — staged as **one commit**.

- [ ] **Step 1: Write the agent** — frontmatter modeled on `agents/llm-doc-writer.md` (`tools: Read, Write, Edit, Grep, Glob, Bash`, `model: sonnet`). Body, complete:

```markdown
---
name: doc-distiller
description: Applies one approved DISTILL record — verifies each durable claim against code, lands extractions in their target living docs, appends one decision-log entry, and retires the planning artifact, all staged as a single commit. Dispatch from fixing-doc-bloat only; never self-initiates.
tools: Read, Write, Edit, Grep, Glob, Bash
model: sonnet
---

You distill a landed planning artifact into its durable residue. Input: one
`DISTILL` record with `status: "ready"` (detecting-doc-bloat contract) and the
artifact it names. You act only on that record.

## The procedure (in order, no steps skipped)

1. **Re-verify before writing.** For each `payload.claims[]` entry, verify the
   claim against the code its `evidence` cites — open the line, run the safe
   command. A claim that fails verification is NOT extracted: report it back as
   a failure line (`claim`, `evidence`, what you found) and continue with the
   rest. Never launder an unverified claim into a living doc.
2. **Land extractions.** Each verified claim goes into its `target` doc, meeting
   the writing-docs bar (dense, anchored, no narrative). Placement: the section
   whose subject matches; end of doc only if none does.
3. **Append the decision entry** to `docs/decisions.md` (create with an `#
   Decisions` heading if absent). Use `payload.decision_entry`, completing this
   shape:

   ## YYYY-MM-DD — <artifact title>
   - Decided: <the decisions>
   - Still binds: <constraints that outlive the implementation>
   - Code: <paths>
   - Source: <artifact path> @ <last commit touching it> (removed in this commit)

4. **Retire the artifact.** `git rm` the artifact. Stage everything —
   extractions, log entry, deletion — so ONE commit carries all of it: the diff
   must read "moved, not lost."
5. **Report.** Return: claims landed (with target:line), claims failed
   verification, the log entry as written, the staged file list. Your dispatcher
   commits; you stage.

## Hard rules

- `status` not `"ready"`, or payload missing → refuse; return the record with
  the reason. Never improvise a payload.
- You touch ONLY: target docs named in claims, `docs/decisions.md`, the
  artifact. Nothing else, however tempting.
- The artifact's verbose body is not "wasted" — it survives in git history via
  the Source line. Do not copy extra prose into living docs to save it.
```

- [ ] **Step 2: Test the agent standalone.** On a scratch copy of the Task 2 fixture, dispatch a subagent with the agent body as its instructions plus the fixture's DISTILL-ready record (from `bloat-report.json`). Verify: both claims verified and landed in their targets, `docs/decisions.md` created with the entry (Source line cites the artifact and says removed), artifact deleted, all staged together, report returned. Also run the refusal case: same dispatch but with the pending-implementation record → must refuse without editing. Record both runs verbatim in `distiller-run.md`.

- [ ] **Step 3: Commit**

```bash
git add plugins/doc-lifecycle/agents/doc-distiller.md tests/baselines/bloat-fixing-red/distiller-run.md
git commit -m "feat: doc-distiller agent for DISTILL records"
```

---

### Task 7: Write fixing-doc-bloat (GREEN)

REQUIRED SUB-SKILL: `superpowers:writing-skills`.

**Files:**
- Create: `plugins/doc-lifecycle/skills/fixing-doc-bloat/SKILL.md`
- Create: `tests/baselines/bloat-fixing-red/GREEN-results.md`

**Interfaces:**
- Consumes: bloat-report + `{"approved": [ids]}` (Task 5 shape); the spine (Task 4); `doc-lifecycle:doc-distiller` (Task 6).
- Produces: the complete apply-side of the pair.

- [ ] **Step 1: Write `SKILL.md`.** Frontmatter (no colon-space in the description value):

```yaml
---
name: fixing-doc-bloat
description: Use when applying a human-approved subset of a detecting-doc-bloat report — landing approved cuts/condenses/moves/merges/retirements and dispatching approved distillations — or whenever tempted to act on bloat findings a human has not approved by record ID. Approval is the mandate; nothing else is.
---
```

Body — mirror `fixing-doc-drift`'s architecture (overview / rules / red flags / rationalization table), with this normative content:

- **Overview:** input = a validator-passing bloat report + an explicit approval (`{"approved": [ids]}` from issue triage, or the human's in-session ID list). **The approved subset is the mandate**; the report's other records are context. Discipline spine: cite `${CLAUDE_PLUGIN_ROOT}/references/apply-discipline.md` as owner of the generic rules (authorized-records-only, no while-I'm-here, anchor confirm, blast-radius, evidence-travels); this skill adds the bloat-specific application below.
- **Routing table (the bloat-specific rules):**

| Verdict | Applied as |
|---|---|
| `CUT` | delete the line at `location` (anchor-confirm first, per spine §3) |
| `CONDENSE` | replace the line at `location` with `proposal` verbatim |
| `EXTRACT-AND-MOVE` | land `proposal.text` in `proposal.target` (writing-docs bar), delete the source line — one commit |
| `RETIRE-DOC` | delete the doc; approval of this ID **is** the deletion authorization |
| `MERGE-DOC` | move content not already in `proposal.target` into it, then delete the doc — one commit |
| `DISTILL` (`ready` only) | dispatch **doc-lifecycle:doc-distiller** with the record; commit its staged result. `pending-implementation` is never actionable — skip it with a note even if approved |

- **Bloat-specific stops:** approved ID not present in the report → stop, the inputs disagree. `DISTILL` approved but status pending → skip + note. Distiller reports failed claims → land what verified, surface the failures; never patch the payload yourself. RETIRE/MERGE of a doc the report also marks elsewhere → apply doc-level verdict last.
- **Red flags:** acting on an unapproved record "because it's obviously right"; editing the artifact instead of dispatching the distiller; approving IDs yourself; splitting an EXTRACT/MERGE/DISTILL across commits (breaks "moved, not lost").
- **Rationalization table:** at minimum — "The CUT is unapproved but trivial" → unapproved = not your mandate; "I'll just distill inline, dispatching is overhead" → the distiller owns the method (single owner); "Pending artifact, but the human approved it" → approval can't make unverifiable claims verifiable; skip + note.

- [ ] **Step 2: GREEN run.** Re-dispatch the Task 5 scenario (scratch copy of fixture, same report + approval, skill text in prompt). Verify: exactly the approved CONDENSE + DISTILL land; unapproved CUT/MERGE untouched; distillation produces extractions + `docs/decisions.md` + artifact deletion in one commit; commit messages map edits to evidence. Record verbatim in `GREEN-results.md`; tighten and re-run if a RED loophole survives.

- [ ] **Step 3: Commit**

```bash
git add plugins/doc-lifecycle/skills/fixing-doc-bloat/ tests/baselines/bloat-fixing-red/GREEN-results.md
git commit -m "feat: fixing-doc-bloat skill (GREEN)"
```

---

### Task 8: Docs sync, validation, continuity review

**Files:**
- Modify: `CLAUDE.md` (executable-scripts sentence; helper-script test bullet; baselines dir list)
- Modify: `docs/plans/HANDOFF.md` (status table + resume notes)

**Interfaces:**
- Consumes: everything shipped in Tasks 1–7.
- Produces: a release-ready branch.

- [ ] **Step 1: Update `CLAUDE.md`** — three surgical edits: (a) the opening paragraph's list of published executable scripts gains `plugins/doc-lifecycle/skills/detecting-doc-bloat/scripts/validate-bloat-output.py`; (b) the helper-scripts-have-unit-tests bullet gains: `python3 tests/scripts/validate-bloat-output_test.py` after touching `detecting-doc-bloat`'s `validate-bloat-output.py` or its output contract; (c) the baselines milestone list gains `bloat-red/`, `bloat-fixing-red/`.

- [ ] **Step 2: Update `docs/plans/HANDOFF.md`** — add rows 6–8 (detecting-doc-bloat, fixing-doc-bloat, doc-distiller) to the status table with state + repo paths; add a short "bloat/distillation suite" section pointing at the design doc and this plan; note the Task 4 spine extraction + re-GREEN of fixing-doc-drift.

- [ ] **Step 3: Run all mechanical checks**

```bash
python3 tests/scripts/validate-bloat-output_test.py
python3 tests/scripts/validate-drift-output_test.py
python3 tests/scripts/sync-gate_test.py
python3 -c "import json; [json.load(open(p)) for p in ['.claude-plugin/marketplace.json','plugins/doc-lifecycle/.claude-plugin/plugin.json']]; print('manifests OK')"
claude plugin validate plugins/doc-lifecycle
```
Expected: all pass; `claude plugin validate` lists **both new skills with their descriptions intact** (the colon-space failure mode is silent metadata drop — check the listing, not just the exit code).

- [ ] **Step 4: Independent continuity review** — dispatch one fresh subagent per flow (no shared context with this work, per the continuity-review practice): (1) read `detecting-doc-bloat` → a produced report → `fixing-doc-bloat` → spine → distiller, and verify the contract/field names/paths/§ references all resolve and the flow reads coherently to a newcomer; (2) read `fixing-doc-drift` post-extraction end-to-end for the same. Fix what they find; behavior-affecting fixes to any GREEN skill get a targeted re-GREEN note in that skill's baseline dir.

- [ ] **Step 5: Commit**

```bash
git add CLAUDE.md docs/plans/HANDOFF.md
git commit -m "docs: sync CLAUDE.md + HANDOFF for bloat/distillation suite"
```

---

## Out of scope (per spec — do not build)

- scheduling-doc-sync wiring, issue creation, cadence, and the `sync-gate` analog for bloat.
- The PR-gate policy layer (config file).
- Any change to `writing-docs`, `bootstrapping-docs`, `detecting-doc-drift`, or `scheduling-doc-sync` beyond Task 4's scoped edit to `fixing-doc-drift`.
