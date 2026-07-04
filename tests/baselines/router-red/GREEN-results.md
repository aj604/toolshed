# router-red GREEN results

2026-07-04. Arm setup: two general-purpose subagents (router-green-A, router-green-B),
fresh context, same neutral prompt as the RED arm, auditing the same untouched
`fixture/` against the **current** `detecting-doc-bloat` skill text with the router rule
(writing-docs `agent-context.md`: always-loaded files are routers; inline placement is a
scope test; landings must not fatten CLAUDE.md; the reverse lens is deliberately
conservative). Outputs: `router-green-A-output.json`, `router-green-B-output.json`. Both
pass the validator; no fixture files were edited. Graded against `ANSWER-KEY.md`.

## Scorecard

| Item | Expected (GREEN) | router-green-A | router-green-B |
|------|------------------|----------------|----------------|
| R1 `make seed` gotcha | kept in place | **PASS** — no record | **PASS** — no record |
| R2 golden-regen section → `docs/reference/testing.md` | EXTRACT-AND-MOVE out, correct target | **PASS** (B1) — "it moves out of the always-loaded file"; proposal preserves all four facts of the procedure (regen command, rewrites-not-validates, inspect diff by hand, run-twice/cache-spurious-pass) | **PASS** (B1) — same target; evidence adds "leaving at most a when-to-read line", the key's exact allowance |
| R3 503 line — no placement record | no record, or neutral CUT | **NEUTRAL** (B4) — CUT for code restatement, the key's carved-out judgment call; not a placement record | **PASS** — no record (the cleaner outcome) |
| R4 port-lock → CLAUDE.md, ONE dense line | EXTRACT-AND-MOVE in, densest form | **PASS** (B2) — one line: "- **After any crash, delete `.portlock` before restarting** — the dev server keeps the port lock file and silently binds a random port on the next start." | **PASS** (B2) — one line: "- **Delete `.portlock` before restarting the dev server after any crash** — a stale lock file makes the next start silently bind a random port." |
| R5 Windows newline → `docs/reference/export.md`, NOT CLAUDE.md | EXTRACT-AND-MOVE to export.md | **PASS** (B3) — "it belongs beside" export.md:4-5's existing binary-mode claim | **PASS** (B3) — "it fails the router bar for CLAUDE.md and lands in the reference doc" |

Both agents explicitly invoked the rule by name where a grade depends on it:
router-green-A on R2 ("Always-loaded placement fails agent-context.md's router scope
test — most sessions never regenerate goldens") and on R4 ("broad and
unprompted-critical (the random-port bind is silent — a session would not know to
look), so it clears agent-context.md's router rule"); router-green-B on R2 ("Per
agent-context.md's router rule it moves out") and on R5 ("not unprompted-critical …
fails the router bar for CLAUDE.md"). The scope test is doing the routing, not taste —
the exact gap the RED arm documented.

## Net-effect check (the user's actual requirement)

CLAUDE.md under each agent's proposals, line for line:

- **router-green-A**: −7 (R2 section, CLAUDE.md:9-15 incl. header) +1 (R4) −1 (R3 CUT
  of CLAUDE.md:7) = **net −7. Leaner. PASS.**
- **router-green-B**: −7 (R2) +1 (R4) = **net −6. Leaner. PASS.**

Contrast the RED arm: +1 / +1, nothing out. The delta is entirely the reverse lens plus
the one-line landing bar.

## Residual weaknesses

1. **Passage-span contract is line-granular (known contract edge, not a router-rule
   failure).** The R4 passage begins mid-line after "Run `exporter run --tenant
   NAME`." on README.md:11. All four agents across both arms flagged it —
   router-green-B: "The `exporter run --tenant NAME` usage sentence opening line 11
   stays in README.md"; router-green-A: "The usage sentence opening line 10 … is not
   part of the passage and stays." The record shape has no way to express
   "second-sentence-of-line-onward", so the location/span understates what stays.
   Agents compensate in prose evidence; a fix step consuming spans mechanically would
   not see the compensation.
2. **router-green-A off-by-one anchors on R4.** Its location is "README.md:10" and its
   evidence span "README.md:10-13"; the quoted text ("One thing worth knowing: the dev
   server keeps a port lock file … delete `.portlock` before restarting.") actually
   sits at 11-14 (line 10 is blank). The quote is verbatim-correct so the record is
   findable, but the anchor itself is wrong — an evidence-discipline blemish
   independent of the router rule (RED-A/B and GREEN-B all anchored 11-14 correctly).
3. **router-green-A's CUT on the 503 line (B4): defensible, not churn.** Checked
   against the no-churn guard: the guard governs *placement* records on
   borderline-scope lines, and the key's note explicitly carves this out ("a `CUT` for
   restating `src/client.py:3`'s comment is a defensible judgment — grade it neutral,
   not a churn failure"). The agent's rationale is the redundancy-with-code lens, not
   placement: "restates the very code line it cites: src/client.py:3 `RETRIES_503 = 2
   # retry twice on 503, then raise` … the fact is self-evident from the cited code" —
   which is true against the fixture. Graded neutral. Worth recording all the same:
   GREEN-B declined the same record, so the R3 borderline still splits on agent
   judgment under the new text — deliberately so per the key, but it means GREEN runs
   are not byte-identical on this item.
4. **No when-to-read pointer proposed for R2.** The key allows "at most a when-to-read
   line" in CLAUDE.md; neither agent's proposal includes one (GREEN-B mentions the
   allowance in evidence only — the record's single target/text pair carries just the
   destination text). Within spec, but a session hitting a golden mismatch now has no
   CLAUDE.md breadcrumb to `docs/reference/testing.md`; the record shape carries one
   target per record, so the optional pointer has nowhere structured to live.
