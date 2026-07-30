---
name: detecting-doc-drift
description: Use when auditing documentation against the code it describes, checking whether a README/CLAUDE.md/runbook is still accurate, or finding which doc passages a code change invalidates — and whenever drift detection is invoked programmatically (by a PR check or nightly sync) and must emit a structured, parseable result.
---

# Detecting Doc Drift

## Overview

**A doc is a set of claims about the repo; drift is a claim the repo no longer backs.**
This skill declares the *shape* of drift detection so it runs the same way every time and
can be **invoked programmatically to trigger updates** — not a one-off prose review.

Two non-negotiables make the output usable by automation:

1. **A verdict requires evidence.** Never mark a claim VERIFIED because doc and code "seem
   consistent." Verified means you ran the command, opened the line, or matched the grep.
2. **The result is structured, not prose.** Answer in the verdicts shape below. A human
   summary on top is fine; the artifact is what the engine reads and downstream tooling parses.

**REQUIRED SUB-SKILL:** Use **writing-docs** for any fix you propose — every `fix` must meet
its bar (real output, no aspirational claims, marked+anchored rationale). This skill finds
and classifies drift; writing-docs governs how the correction reads. **`fixing-docs`**
consumes the engine report this skill's audit writes — record digests are the handoff, and
`mint-approval` takes them (an optional auto-trigger layer, designed and shipped as the
`scheduling-doc-sync` skill, wires detect→fix to cron/PR).

## The audit (run these steps, in order)

The engine owns scope, segmentation, and validation; this skill owns the judgment in the
middle. Every command below is `python3 -m doclifecycle …` with the plugin's `engine/`
directory on `PYTHONPATH` (`plugins/doc-lifecycle/engine/README.md` covers both spellings).

Every artifact this audit writes — the plan, the verdicts, the report — goes to
`${TMPDIR:-/tmp}/`, never the work tree: `fixing-docs`' applier confines a run to its
approval set's paths, so an audit artifact sitting in the tree reads as an unaccounted
change and the apply refuses (`apply-working-tree-not-confined`). The steps below reuse
that same destination; only the filename changes per artifact.

**Exception — the scheduled headless audit lane (`doc-audit.yml`).** That job's checkout is
throwaway (`persist-credentials: false`, no write-capable credential reaches it at all) and
`fixing-docs`' applier never runs against it — the job ends and the checkout is discarded
before any apply could see it, so a stray artifact there can never trip
`apply-working-tree-not-confined`. That workflow's own deterministic steps already write
`drift-plan.json` and `drift-report.json` to the repository root outside the model's turn, and
its model step's prompt is this lane's own restated copy of the output contract (a headless run
states its own contract rather than depending on a plugin version resolved at run time — see
that prompt's comment) — it names `verdicts.json` in the repository root to match. When this
skill is invoked from `doc-audit.yml`, follow *that prompt's* file destination, not the
`${TMPDIR:-/tmp}/` rule above: the workflow's own instructions are authoritative for that lane,
and its deterministic steps read `verdicts.json` from the root. Every other invocation —
interactive, local, or a future lane whose checkout an apply might run against — keeps the
out-of-tree rule above; it exists to protect exactly the checkout an apply could later touch,
which this one structurally is not.

1. **Plan the scope.** `python3 -m doclifecycle drift-plan --repo . --mode full >
   "${TMPDIR:-/tmp}/drift-plan.json"` (diff-scoped: `--mode incremental --since <commit>`). Deterministic — no
   model — so the scope is re-derivable rather than trusted. Each `documents[]` entry carries a
   `path` and an `obligation`: `assertions` is a living document whose claims you judge;
   `anchor` is a narrative document whose `As of` line the engine checks itself, and for which
   it refuses claim verdicts outright (`drift-verdict-on-narrative-document`). Write none.
2. **Segment each `assertions` document.** `python3 -m doclifecycle segment --repo . --path
   <path>` returns its assertion units — one per sentence, list item, or table row — each with
   an `ordinal`, its source `line`, and `assertion_capable`. The `ordinal` is how you answer for
   a unit. The parser is fixed and model-free, so the same bytes always yield the same units.
3. **Classify every assertion-capable unit** — `factual`, `normative`, `rationale`, or
   `non-assertive`. Leaving one out is refused (`classification-missing`): an unclassified unit
   is indistinguishable from one nobody found a claim in. Classification never waives a living
   truth obligation: factual, normative, and rationale units must all be judged; only
   non-assertive prose takes no verdict.
4. **Judge each assertion** at the appropriate tier (below), tagged by `kind` — one of
   exactly: `command`, `path`, `symbol`, `behavior`, `structure`, `value` (use these strings
   verbatim; automation switches on them) — and record the obligation discharged:
   `evidence` for factual assertions, `governing-source` or `owner-judgment` for normative
   assertions, and `coherence` for rationale. The governing source, owner judgment, or current
   evidence that settles coherence is cited through the same evidence contract as a factual
   judgment. Pure prose is not a claim — **except** lines that
   *sound* factual but name no checkable thing ("robust", "production-ready", "reasonably
   fast", "handles most workloads"). Extract those too, kind `value`: they become
   `UNVERIFIABLE`. Do not skip them — an unbacked quality claim is the most common drift a
   human eye waves through. And they stay `UNVERIFIABLE` even when you can build a code case
   that the boast overreaches ("handles arbitrarily large inputs" vs. a whole-buffer read):
   put that argument in `evidence`, not in the verdict. `STALE` is reserved for claims with a
   checkable true value to restore — puffery has none, so any replacement text you'd draft is
   new authorship, and cutting or rewording it is a human decision, not a sync. In a
   scheduled install the human's third option is a durable waiver
   (`.doc-lifecycle/drift-waivers.json`, owned by scheduling-doc-sync): an accepted claim
   stops resurfacing on run surfaces, while this skill keeps emitting it — detection stays
   pure; disposition is the pipeline's job. Lines
   already marked `> UNVERIFIED: <claim>` (the marker
   llm-doc-writer writes) are extracted like any claim and default to `UNVERIFIABLE` unless
   the repo now makes them checkable.
   Each judgment is `VERIFIED` / `STALE` / `UNVERIFIABLE`, and carries its `kind`, its `tier`,
   and its `evidence`.
5. **Write `"${TMPDIR:-/tmp}/verdicts.json"`** in the contract below, then **validate it
   mechanically** before the audit: pipe it through
   `${CLAUDE_PLUGIN_ROOT}/skills/detecting-doc-drift/scripts/validate-drift-output.py`
   (reads the JSON on stdin or as a file arg). It enforces the enum, field-set, `evidence`, and
   `fix` rules, and that no unit is answered twice within a document, and exits nonzero on any
   violation. Run it — neither thing the engine does with a
   shape violation is a loud failure. A violation inside a document's `verdicts` drops that
   whole document to an unexamined coverage gap (`the verdicts returned for this document did
   not validate: <code>`), and the run still exits with a report; a violation in the *entry* — a
   bad `status`, an unexpected field, a duplicate `path`, a document the plan never declared —
   refuses the whole run instead. The validator checks *shape*, not whether a verdict is *right*; that judgment
   is still yours, and `drift-audit` is the authority on everything the shape check cannot see
   (whether an ordinal names a real unit, whether a multi-line `fix` owns its span).
6. **Run the audit.** The run's evidence boundary is **empty unless you declare it**: a
   verdict citing `evidence.command` is refused (`drift-evidence-outside-boundary`) — which
   discards that *whole document's* verdicts, STALE and UNVERIFIABLE records included —
   unless the tool it names was passed to `--evidence-command`. Before running, check for
   `.doc-lifecycle/evidence-tools.json` (`scheduling-doc-sync` owns the file; a repo without
   it, or with `{"tools": []}`, declares none): pass one `--evidence-command <tool>` per
   name it lists. No declared tools means the run is tool-free — cite `source` only, never
   `command`; a claim only a command could settle becomes `UNVERIFIABLE`, with what you tried
   in `evidence.observed`, not a `command` citation nothing declared permits.
   `python3 -m doclifecycle drift-audit --repo . --mode full --verdicts
   "${TMPDIR:-/tmp}/verdicts.json" [--evidence-command <tool> ...] >
   "${TMPDIR:-/tmp}/drift-report.json"` writes the validated report: your STALE and
   UNVERIFIABLE judgments as records with digests, your VERIFIED ones as coverage, and the
   narrative documents' anchors checked engine-side. Exit 0 is a complete report, 4 partial
   (something was not examined), 1 refused (e.g. a document the plan never declared).
   **Pass the same `--mode` (and `--since`) you planned with in step 1** — the audit
   re-derives the scope from these flags, so a diff-scoped plan audited `--mode full` is
   measured against every living document instead of the planned ones: the documents you
   were never given become unexamined scope, and a correct incremental run exits 4 partial
   rather than producing the report that was asked for.

### Verification tiers + escalation rule

| Tier | Cost | Does | Catches |
|------|------|------|---------|
| 1 STATIC | seconds | grep/glob: path/symbol exists, command exists in Makefile/package.json, link resolves | renames, moves, deletions |
| 2 SHALLOW | moderate | read the cited line; run safe `--help`/`--version`/dry-run | changed flags, values, signatures |
| 3 DEEP | expensive | read implementing code; run the documented workflow where safe | behavior drift |

Running a Tier 2 `--help`/`--version`/dry-run only earns a `command` citation when that
tool is declared per step 6 above; against an undeclared or tool-free run it is still a
legitimate read, but the verdict it settles cites `source` (or, if nothing repository-side
settles it either, stays `UNVERIFIABLE`) rather than a `command` the audit would refuse.

**Every claim starts at Tier 1.** Escalate a claim only when (a) Tier 1 flags suspicion,
(b) the claim's subject is in the diff (diff-scoped mode), or (c) a deep audit was
requested. This concentrates cost where drift is likely.

**Anchors: open the line, but judge the claim, not the line number.** A `file:line` anchor
is not evidence — open it. But the anchor is *metadata on a claim, never its own claim*: do
not extract "the exit is at line 14" as a separate verdict and grade its precision. Classify
the underlying claim on whether the *referenced construct* is there and the *stated value* is
right. An anchor that lands a few lines off the exact statement (points at the guard instead
of the `exit()` it guards) but still locates the right code is `VERIFIED`. **Never emit a
STALE verdict whose `fix` only changes a line number** — a line-number-only correction is not
drift. Mark `STALE` only when the value/behavior/symbol is wrong or the anchor points to a
construct that moved or no longer exists.

**A `fix` that names a file is settled by opening that file.** Every property the replacement
asserts of another document — that it exists, that it carries a section, that it is now the
live one — is read there first. A `Supersedes:` header, a filename, or a commit message says a
file replaced another, never what the replacement contains. Assert only what you read: if the
target does not carry it yet, the fix says what the target actually shows, and if nothing in
the repository settles it, the verdict is `UNVERIFIABLE` with the pointer in `evidence` rather
than a `STALE` with a drafted replacement. This is the rule that makes a repointing fix safe to
land, and the auto-apply policy refuses one anyway (`policy-fix-names-other-document`) — a fix
that changes which files the line names is a person's to approve.

## The output contract (this is the "shape")

`verdicts.json` is the engine's verdicts artifact — one entry per document the plan declared,
each carrying one verdict per assertion unit `segment` printed:

```json
{"schema_version": 1, "documents": [{"path": "CLAUDE.md", "status": "ok", "verdicts": []}]}
```

`schema_version` is optional and must be `1` when present. An entry's fields are exactly
`path`, `status`, `verdicts`, `reason`, `chunk` — no extras. `status` is `ok` or `failed`: an
`ok` entry carries `verdicts` and no `reason`; a `failed` entry carries a one-line `reason` and
no `verdicts`, which is how you declare a document you did not examine — a gap with no reason is
indistinguishable from a document nobody thought about. Narrative (`anchor`) documents get no
entry at all; the engine checks their `As of` anchors itself.

A verdict's fields are exactly `unit`, `assertion_class`, `obligation`, `verdict`, `kind`, `tier`,
`evidence`, `fix`. Two are always required: `unit` is the `ordinal` `segment` printed for that
unit, and `assertion_class` is one of `factual` / `normative` / `rationale` / `non-assertive`.

`obligation`, `verdict`, `kind`, `tier`, and `evidence` travel together — all five, or none.
Every factual, normative, and rationale unit owes all five; a `non-assertive` unit takes none of
them, because it asserts nothing the code could contradict. `obligation` is `evidence` for a
factual unit, `governing-source` or `owner-judgment` for a normative unit, and `coherence` for a
rationale unit; any other value or class/obligation pairing is refused. `verdict` is one of
`VERIFIED` / `STALE` / `UNVERIFIABLE`; `kind` is one of
`command` / `path` / `symbol` / `behavior` / `structure` / `value`; `tier` is the integer `1`,
`2`, or `3` — literal enum values, no invented ones.

`fix` is present only, and always, for `STALE`, and it is the **complete replacement text** for
that unit — never an instruction like "change X to Y" — and must meet the
writing-docs bar. Preserve the target document's physical-line convention: when the source unit
is soft-wrapped, draft `fix` already wrapped, with LF embedded in the JSON string and the exact
list marker and continuation indentation the replacement needs. Do not leave reflow to
`fixing-docs` or the applier; both place the approved string byte-verbatim. The engine accepts
embedded LF only for a unit that already spans multiple source lines and owns every line in that
span (no neighboring assertion unit shares either boundary line), and every physical line must be
non-empty (no CR or NUL). The replacement may take a different number of physical lines when its
corrected content wraps differently, but it remains one logical assertion unit.

`evidence` is an object, mandatory for **every** judged unit, VERIFIED included: `{"observed":
<the fact you read>, "source": <repository-relative path>, "line": <int>, "command": <the one
command line that settled it>}`. `observed` is always required and is **one line** — the fact
the citation shows. No history (prior PRs, how the drift arose), no restated command output, no
reasoning narrative: the verdict carries the conclusion; evidence carries only what proves it.
VERIFIED and STALE each rest on **exactly one** citation — `source` or `command`, never both,
because a verdict rests on one place a reader goes. `line` points into a file, so it never
accompanies `command`. A cited `command` is one read-only command line, not a shell program: it
may not carry `;`, `&`, `|`, `<`, `>`, `(`, `)`, `$`, a backtick, or a backslash. UNVERIFIABLE
needs no citation — it records that nothing in the repository settles the claim — but it still
carries `observed`.

On success the validator prints a `summary:` line as JSON, recomputed from your verdicts
(`verified` / `stale` / `unverifiable`, counted across every document), that automation can
gate on.

See **output-contract.md** for a worked example covering all four assertion classes and a
`failed` document entry.

## Modes

- **Full audit** (manual / nightly sweep): extract every claim across the target docs,
  Tier 1 by default, escalate per the rule. Emit the full drift report, severity-ordered
  (wrong command/behavior before stale prose).
- **Diff-scoped** (PR check / what automation calls): input is a diff or commit range. For
  each changed file/symbol/value, **grep every doc for passages referencing it** — including
  command output blocks and examples, not just the obvious gotcha line — then verify each
  referencing claim, **escalating past Tier 1 to the tier that settles it**. A changed subject
  in the diff is exactly the `(b)` escalation trigger, so do not stop at a Tier-1 grep that
  only confirms the name still appears: read the cited line (Tier 2), and read implementing
  code (Tier 3) for any `behavior`/`value` claim, where the rename-grep gives false comfort. A
  rename/move/deletion is settled cheaper — don't pay Tier 3 for a claim Tier 1–2 already
  resolves. Judge only the units carrying touched claims. Completeness is the metric: a changed
  symbol referenced in five docs must produce five verdicts.

## Red flags — STOP

- Writing "looks consistent" / "should be fine" without opening the file → not a verdict.
- Trusting a `file:line` anchor instead of reading that line → anchors drift a few lines;
  read the line and judge the claim (the anchor rule above).
- Emitting a prose report instead of `verdicts.json` → the engine has nothing to audit.
- A VERIFIED verdict with no `evidence.observed` → unverified; go get the evidence.
- Diff-scoped run that checked the one obvious doc → grep ALL docs for the changed subject.
- Eyeballing a command table instead of grepping the Makefile/package.json for each target.
- Skipping a "robust"/"fast"/"production-ready" line because it's "just prose" → extract it
  as UNVERIFIABLE; that is the finding.
- Marking a quality boast STALE because the code argues against it, and drafting a
  replacement → still UNVERIFIABLE; the contradiction goes in `evidence`. A `fix` must
  restore a checkable true value, not reword puffery.
- A verdict with an invented `kind` (e.g. `schema_mismatch`) → use the six enum values only.
- Marking an anchor STALE for being off by a line, or emitting a `fix` that only changes a
  line number → not drift. The anchor is metadata, not its own claim.
- Repointing a claim at a superseding document you did not open → the header says it supersedes,
  not what it contains. Open the target; assert only what it shows.
- Evidence that tells a story — prior fixes, what re-staled the line, pasted command output →
  one line, pointer + fact. History lives in git; the evidence proves, it doesn't narrate.
- Citing `evidence.command` without first declaring it to `drift-audit` — the boundary is
  empty by default, so this discards the whole document's verdicts, not just the one citation.
  Check `.doc-lifecycle/evidence-tools.json` and pass `--evidence-command` per step 6 before
  writing a single `command` citation, or use `source` instead.
