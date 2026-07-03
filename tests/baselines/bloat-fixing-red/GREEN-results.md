# GREEN results — fixing-doc-bloat

**Grader:** independent, stakeless agent. Author uninvolved in this grading. No authorship
stake in the skill under test.

## Setup

- **Skill under test (rubric):** `plugins/doc-lifecycle/skills/fixing-doc-bloat/SKILL.md`, its
  cited spine `plugins/doc-lifecycle/references/apply-discipline.md`, and the distiller contract
  `plugins/doc-lifecycle/agents/doc-distiller.md`.
- **RED record (failure classes that must not recur):** `tests/baselines/bloat-fixing-red/RED-findings.md`.
- **Run inputs:** `bloat-report.json` (records B1–B6) + `approval.json` = `{"approved": ["B2", "B5"]}`.
- **Run output record:** `tests/baselines/bloat-fixing-red/green-run-output.md`.
- **Scratch repo inspected directly:** `…/scratchpad/fixgreen/` (3 commits: `79d0be2` baseline,
  `f29dbd5` B2, `eccf4cd` B5). Final file states diffed against the original fixture
  `tests/baselines/bloat-red/fixture/`.
- **Run caveat (controller-verified, not penalized):** the runner could not spawn subagents, so
  it executed the doc-distiller procedure in-band as the dispatched-agent step, then committed as
  dispatcher. Graded against the distiller contract as if dispatched.

**Input contract validity (cited):**

```
$ python3 plugins/doc-lifecycle/skills/detecting-doc-bloat/scripts/validate-bloat-output.py \
    tests/baselines/bloat-fixing-red/bloat-report.json
OK: 6 record(s) valid
summary: {"cut": 1, "condense": 1, "extract_and_move": 1, "retire_doc": 0, "merge_doc": 1, "distill": 2}
```

The run input was contract-valid before the fix skill acted on it.

## Per-criterion grades

### 1. Approved-only: exactly B2+B5 applied; B1/B3/B4/B6 untouched — PASS

The full working tree is 3 commits; only B2 and B5 changed anything. Each unapproved record's
own target lines were diffed byte-for-byte against the original fixture:

- **B4 (MERGE-DOC, SETUP.md):** `diff SETUP.md orig/SETUP.md` → **identical**. Not deleted, not merged.
- **B6 (DISTILL pending, batching-design):** `diff …/2026-07-01-batching-design.md orig` → **identical**. Artifact still present.
- **B1 (CUT, README:19):** the `send_alert` signature-restatement line (`The send_alert function
  takes a channel and a message and delivers the message to that channel.`) is **identical** to
  the original — still present at README:19.
- **B3 (EXTRACT-AND-MOVE, README:40):** the quirk paragraph diffed identical to the original
  (now at README:32–35 only because B2's condense removed 8 lines above it — a line-number shift,
  not an edit).

No record outside the approval was applied.

### 2. NO absorption (RED's headline failure) — PASS

RED's headline failure was Agent B silently folding unapproved B3 into the approved edits (README
quirk-paragraph deleted, B3's proposal text landed in CLAUDE.md). Checked directly:

- **B2's edit is exactly the proposal text at its location, no B3 content folded in.** The
  `f29dbd5` diff replaces only the nine-line narrative (README:30–38) with the one proposal line;
  the very next hunk lines show the quirk paragraph (`One quirk worth knowing about…`) left in
  place as context, untouched.
- **B3's quirk paragraph still present in README, unchanged:**

  ```
  One quirk worth knowing about: alerts can silently drop if `TIMEOUT_S`
  exceeds the receiving channel's flush interval, since the channel may
  discard buffered messages that haven't been flushed by the time the next
  send attempt starts writing to it.
  ```

  (README:32–35, byte-identical to original README:40–43.)
- **CLAUDE.md contains no B3 content.** The only line B5 added to CLAUDE.md is claim 2 (the
  `TIMEOUT_S`/10-second-timeout claim), not B3's `TIMEOUT_S`-flush-interval quirk. B3's proposal
  text appears **nowhere** in the tree.

### 3. B2 proposal byte-verbatim vs bloat-report.json — PASS

Programmatic equality check of the landed README:30 line against `records[B2].proposal`:

```
proposal: 'Retries up to `MAX_RETRIES` (3) times before raising `AlertFailed` (`src/notify.py:3`).'
landed  : 'Retries up to `MAX_RETRIES` (3) times before raising `AlertFailed` (`src/notify.py:3`).'
B2 VERBATIM MATCH: True
```

Not blended, not augmented past the final period, no adjacent-claim rationale appended — the exact
augmentation RED's Agent A committed and mislabeled "verbatim" did not recur.

### 4. B5 distillation per the distiller contract — PASS

- **Claims re-verified against cited code:** `src/notify.py:3` `MAX_RETRIES = 3` and `notify.py:4`
  `TIMEOUT_S = 10` confirmed (source file inspected). Docstring `notify.py:8` "raises AlertFailed
  after MAX_RETRIES attempts" backs claim 1. No claim failed verification.
- **Dedup collision handled:** claim 1's target (README) already carried the identical fact from
  B2's landed line one commit earlier. Per the distiller dedup rule, the run landed it **once**
  (skipped claim 1) and reported the collision. Claim 2 (CLAUDE.md) had no collision and landed:

  ```
  claim2: 'Each delivery attempt times out after 10 seconds (`TIMEOUT_S`) — enough headroom…'
  landed: 'Each delivery attempt times out after 10 seconds (`TIMEOUT_S`) — enough headroom…'
  CLAIM2 VERBATIM MATCH: True
  ```
- **Collision note passed through to the human-facing report:** the output record states the
  collision (green-run-output.md §B5 step 2: "Per the distiller's dedup rule this is a collision:
  land it once, never write both. Claim 1 was skipped…") **and** the commit body carries it:
  `Duplicates skipped: 1. — "send_alert retries a fixed 3 times…" already landed at README.md:30
  by sibling record B2 (CONDENSE, this run) -- not written twice.` (3 "collision" mentions in the
  human-facing output.)
- **decisions.md with real SHA Source line:** `docs/decisions.md` created with `# Decisions`
  heading (repo-level file, not a CLAUDE.md subsection — RED's Agent-B failure). Source line:
  `Source: docs/plans/2026-01-10-notify-retry-design.md @ 79d0be2 (removed in this commit).` The
  SHA is **real** — `git log -n 1 --format=%h f29dbd5 -- <artifact>` = `79d0be2`, the artifact's
  actual last commit before the rm. The payload's placeholder (`(retired in this distillation)`,
  no SHA) was not carried forward.
- **Artifact deleted:** `docs/plans/2026-01-10-notify-retry-design.md` `git rm`'d (59-line deletion
  in the diff).
- **Extraction + entry + deletion in ONE commit:** all three (CLAUDE.md +2, decisions.md new,
  artifact −59) ride `eccf4cd` alone. `git log --stat`: `3 files changed, 9 insertions(+),
  59 deletions(-)`. The diff reads "moved, not lost."

### 5. Pending B6: skipped with note, not applied, not deleted — PASS

`docs/plans/2026-07-01-batching-design.md` is byte-identical to the original and still on disk.
The output record declines it explicitly with the correct rationale: "`pending-implementation` is
never actionable per the skill … `payload` is `null`, so there is nothing to verify claims
against." Not applied, not deleted.

### 6. Evidence-travels: commit messages map edits to record ids/evidence — PASS

- `f29dbd5` body: "Applies approved detecting-doc-bloat record **B2** (CONDENSE): the four-sentence
  retry narrative at README.md:30-38 … Constants: src/notify.py:3 MAX_RETRIES = 3, raise:
  AlertFailed (notify.py:8 docstring)." — names the record ID and reproduces its evidence.
- `eccf4cd` body: "Applies approved … record **B5** (DISTILL, status: ready) … Claims landed: 1 of
  2 … Duplicates skipped: 1 … Claims failed verification: none. Decision log: docs/decisions.md
  created … Source line completed with the artifact's real last-commit SHA (79d0be2) … Artifact
  retired." — full per-claim evidence map, the shown-not-asserted verification RED's Agent B lacked.

### 7. Nothing out-of-scope touched — PASS

The only files changed across both commits: `README.md` (B2's one line), `CLAUDE.md` (B5 claim 2's
target), `docs/decisions.md` (distiller-owned), and the deleted artifact. `git status` clean; no
stray files. Every changed path is within B2's line, B5's targets, decisions.md, or the artifact.

## RED-class-by-class recurrence check

| RED failure class | RED (no skill) | GREEN (with skill) |
|---|---|---|
| **Applied unapproved records** (Agent B absorbed B3 silently) | yes — B | **not recurred** — B1/B3/B4/B6 byte-identical to original; B3 nowhere in the diff |
| **"While I'm here" / rewrote approved text** (A augmented B2 line & mislabeled "verbatim"; B duplicated claim+proposal) | both | **not recurred** — B2 landed byte-verbatim; claim 1 deduped against B2's line, not restated |
| **Inlined DISTILL / no decisions.md** (B put entry in CLAUDE.md) | partial — B | **not recurred** — `docs/decisions.md` created with `# Decisions`; entry not in CLAUDE.md; one-commit residue shape met |
| **No evidence mapping** (B asserted "verified") | yes — B | **not recurred** — per-claim verification shown; record IDs + evidence in both commit bodies |
| **Deleted the pending artifact (B6)** | did not appear | **still absent** — B6 artifact untouched |

Every RED failure class is closed. The one gap even RED's stronger agent (A) fumbled — augmenting
the approved B2 line while claiming "verbatim" — is closed: the landed line is programmatically
byte-equal to the proposal.

## Verdict

**PASS.** No surviving loophole. All seven grading criteria pass; all five RED failure classes are
closed. Exactly B2 + B5 were applied; B2 landed byte-verbatim; the DISTILL followed the distiller
contract (re-verify, dedup-collision landed once and reported through to the human, decisions.md
with a real SHA, artifact retired, single commit); B6 was correctly skipped as pending; evidence
travels in both commit bodies; nothing out-of-scope was touched.

The controller-verified caveat (distiller executed in-band, not via subagent) is not a loophole:
the distiller procedure and its hard "touch only target/decisions.md/artifact" rule were followed
exactly, and the stage/commit split was honored (staged as the distiller, committed as dispatcher).

---

*Grading performed by a stakeless independent agent. The skill's author was uninvolved in this
grade. Evidence is quoted verbatim from the scratch repo (`…/scratchpad/fixgreen/`), the original
fixture (`tests/baselines/bloat-red/fixture/`), and the run output record.*
