# Documentation Bloat Audit

## Findings

### 1. README.md — Redundant and verbose setup/usage sections

**Location:** README.md, lines 6–26

**Issue:** Setup and usage instructions are duplicated across three documents:
- `README.md` (Setup section, lines 6–12)
- `SETUP.md` (entire file — identical setup instructions)
- `CLAUDE.md` (minimal, agent-facing version)

The Setup section in README is identical to SETUP.md verbatim. This is pure duplication.

**Recommendation:** Delete the "Setup" section from README (lines 6–12) and replace with a cross-reference: "See SETUP.md." SETUP.md becomes the single source of truth for installation. README becomes a quick overview pointing to deeper docs.

---

### 2. README.md — Restates what's in the code docstring

**Location:** README.md, lines 17–26

**Issue:** The "Usage" section restates the function docstring from `src/notify.py`:
- Docstring: "Deliver msg to channel; raises AlertFailed after MAX_RETRIES attempts."
- README says: "`send_alert` takes a channel and a message and delivers the message to that channel" and describes the retry behavior.

This is code-in-prose. The example is useful, but the prose description ("takes a channel and a message and delivers the message to that channel") is redundant with the docstring and the code itself.

**Recommendation:** Condense to: "Import `send_alert(channel, msg)` from `src/notify.py`. Example: `send_alert("#ops", "disk usage above 90%")`" Move retry semantics to the dedicated "Retry behavior" section.

---

### 3. README.md — Verbose explanation of retry behavior

**Location:** README.md, lines 28–43

**Issue:** The "Retry behavior" section is verbose (16 lines) but doesn't add insight beyond what's already in the design doc (2026-01-10-notify-retry-design.md):
- README says: "waits briefly and tries again," "fixed number of attempts," "absorb brief hiccups"
- Design doc already explains the choice of 3 retries and 10s timeout and rationale.

The README also adds a conditional warning about `TIMEOUT_S` and channel flush intervals (lines 40–43), which is implementation detail that belongs in code comments, not user-facing docs.

**Recommendation:** 
- Condense to a single line in README: "Retries on transient failures (3 attempts, 10s timeout per attempt). Raises `AlertFailed` if all attempts fail."
- Move the `TIMEOUT_S` / flush-interval edge case to an inline comment in `src/notify.py` if it's a real gotcha, or delete it if it's speculative.

---

### 4. Design doc (2026-01-10) — "Sketch" section is pseudocode that doesn't match implementation

**Location:** 2026-01-10-notify-retry-design.md, lines 44–55

**Issue:** The "Sketch" section is pseudocode, but the actual implementation in `src/notify.py` is stubbed (`...`). The sketch is not code; it's aspirational documentation that may diverge as the implementation evolves. It adds a third place (after README and SETUP.md) where setup/retry logic is explained differently.

**Recommendation:** Delete the "Sketch" section. It's a design artifact, not living documentation. Pair the design decision with the actual implementation via a code comment, not a separate pseudocode block. If design docs need to reference code, link to the source file instead of copying pseudocode.

---

### 5. Design doc (2026-07-01) — Speculative, unactionable content

**Location:** 2026-07-01-batching-design.md, entire file (17 lines)

**Issue:** This is a design proposal with "Not yet implemented" status and an open question ("Needs a decision on max batch size before work starts"). It's a design sketch, not documentation of the actual system. It belongs in a tracking system (e.g., GitHub Issues) or a decision log, not living documentation.

**Recommendation:** Either:
- Move to a `docs/decisions/` or `docs/rfc/` directory if this repo formally tracks unimplemented proposals.
- Delete if the decision has been made elsewhere (e.g., in a PR or issue) and this doc is now stale.
- If keeping, update status and max batch size decision before merging.

---

### 6. CLAUDE.md vs. README.md — Unclear separation

**Location:** CLAUDE.md (5 lines) vs. README.md (49 lines)

**Issue:** CLAUDE.md is a minimal agent-facing summary, but it doesn't signal why it exists or how it differs from README. The README is much more verbose, yet CLAUDE.md doesn't link to it or suggest what to read next. For a human reader, it's unclear which doc to start with.

**Recommendation:** Add a one-liner to README or CLAUDE.md clarifying the audience:
- CLAUDE.md: "Agent-facing reference. For human setup and usage, see README.md."
- README.md heading: "For agent-facing reference, see CLAUDE.md."

---

## Summary

| Category | Count | Action |
|----------|-------|--------|
| **Duplication** | 2 | Remove README setup section; merge/dedupe retry explanation |
| **Verbose/restating code** | 2 | Condense usage and retry sections in README |
| **Speculative/unactionable** | 1 | Move or delete unimplemented batching design |
| **Pseudocode drift** | 1 | Delete sketch section; pair design decisions with code comments |
| **Unclear separation** | 1 | Clarify CLAUDE.md vs. README audience |

**Total lines to remove/condense:** ~30 lines (setup duplication + verbose retry + pseudocode sketch + stale design doc). **Effort:** Low (deletions + brief edits).

