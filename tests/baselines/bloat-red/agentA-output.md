# Documentation Bloat Audit — `bloat-red/fixture`

Scope: `CLAUDE.md`, `README.md`, `SETUP.md`, `docs/plans/2026-01-10-notify-retry-design.md`,
`docs/plans/2026-07-01-batching-design.md`, checked against the sole source file `src/notify.py`
(9 lines, one function: `send_alert(channel, msg)`, `MAX_RETRIES = 3`, `TIMEOUT_S = 10`).

This is a ~9-line library with 61 lines of README/SETUP/CLAUDE.md alone, plus two design docs.
The doc-to-code ratio is extreme, and most of the excess is duplication or restated code rather
than distinct, load-bearing information.

## 1. `SETUP.md` duplicates `README.md` in full — delete `SETUP.md`

`SETUP.md` (9 lines) is word-for-word identical to the "Setup" section of `README.md`
(README.md lines 6–14):

```
Clone the repo, then install the package in editable mode:

    pip install -e .

No environment variables are required to run the test suite locally.
```

There is no content in `SETUP.md` that isn't already in `README.md`, and nothing in the repo
appears to link to `SETUP.md` specifically. This is a pure duplicate file — one of the two copies
will inevitably drift from the other the next time setup changes (e.g., if an env var is added
later, someone will update one and forget the other). **Prune `SETUP.md` entirely**; `README.md`
already covers setup.

## 2. `README.md` "Usage" section restates the code with no added information

Lines 18–20:

> Import `send_alert` from `src/notify.py` and call it with a channel and a message. The
> `send_alert` function takes a channel and a message and delivers the message to that channel.

This is two sentences that both say "send_alert takes a channel and a message and delivers the
message." The second sentence adds nothing beyond what the function signature and the code
sample immediately below it (lines 22–26) already show. This is filler restating the code/example
that follows it. **Condense to one sentence** (or cut entirely — the code sample is
self-explanatory: `send_alert("#ops", "disk usage above 90%")` next to
`from src.notify import send_alert` needs no prose gloss).

## 3. `README.md` "Retry behavior" section is heavily padded

Lines 30–38 take four sentences to say what amounts to: "Failed sends are retried
`MAX_RETRIES` times with a fixed delay; after all attempts fail, `send_alert` raises
`AlertFailed`." Specific bloat:

- "Delivery failures are not always permanent, so the library will not give up on the first
  error it sees." — throat-clearing; the next sentence says the same thing with the actual
  mechanism.
- "giving transient network blips and momentary channel outages a chance to resolve themselves
  before the caller is bothered with a failure" — flowery restatement of "retries on failure,"
  no new information.
- "This retrying continues for a small, fixed number of attempts before the library gives up and
  reports the failure back to the caller, so callers can rely on `send_alert` to absorb brief
  hiccups without needing their own retry logic." — the actual number (`MAX_RETRIES = 3`, visible
  in `src/notify.py`) isn't even given here, so this sentence is pure restatement without the one
  concrete fact a reader would want.

None of this restates *specific, verifiable claims* about the code (e.g., exact retry count,
exact timeout) — it restates the general concept of "retry" in longer and longer sentences. Per
the repo's own doc contract (every line should be a verifiable claim against the repo), this
should collapse to something like: "Failed sends are retried up to `MAX_RETRIES` (3) times with a
`TIMEOUT_S` (10s) timeout per attempt; if all attempts fail, `send_alert` raises `AlertFailed`."
That's shorter, adds the concrete numbers currently missing, and drops the padding.

The one genuinely valuable sentence in this section — the last paragraph (lines 40–43) about
`TIMEOUT_S` exceeding the channel's flush interval causing silent drops — is a non-obvious
behavioral gotcha not visible from reading `notify.py` (whose body is just `...`). **Keep this
one**; it's the highest-value sentence in the whole README.

## 4. `CLAUDE.md` is redundant with `README.md`'s opening line

`CLAUDE.md` (the entire file, 4 lines):

```
This is a tiny notification library. The only source module is `src/notify.py`,
which exposes `send_alert(channel, msg)`.
```

This duplicates information already stated by `README.md`'s title/intro ("A tiny library for
sending alerts to a channel...") and is trivially derivable from `ls src/`. For a repo this size,
a CLAUDE.md that only restates "there is one file and one function" isn't adding orientation
value beyond what `README.md` already gives an agent. This isn't harmful, but it's a candidate
for merging into README.md's intro rather than maintained as a second, separately-drifting file —
especially since nothing here would need to change if `notify.py` gained a second function (it'd
just go stale, restating "only source module" incorrectly).

## 5. `2026-01-10-notify-retry-design.md` — Decision section over-justifies fixed numbers

Lines 34–42 spend two sentences justifying "three attempts" and "ten seconds" with hedge language
("After going back and forth, three attempts felt like the right balance...") that doesn't
survive as useful information once the decision is made and shipped (2026-01-10, now six months
old relative to the 2026-07-01 batching doc). This is a design/ADR doc, which the repo's
conventions correctly scope as narrative-by-design rather than a repo-tracking doc, so some
discursiveness is expected and appropriate here — this isn't misfiled. However:

- **Option B and Option C** (lines 19–31) are reasonably tight and earn their place — they
  explain real alternatives and why they were rejected, which is exactly what an ADR should
  preserve.
- The **"After going back and forth..." sentence** (line 37) is the one throwaway line even
  within this doc's own genre: it narrates the *process* of deciding rather than the *reasoning*,
  and could be cut without losing anything (the surrounding sentences already give the reasoning —
  "enough to ride out a typical few-second blip" / "enough headroom... without letting a single
  hung request block the retry loop").

This doc is otherwise fine as a historical record and shouldn't be pruned wholesale — flagging
only the one sentence.

## 6. `2026-07-01-batching-design.md` — no bloat, but check for staleness

This doc is appropriately terse (17 lines, no padding) and is explicitly marked "Not yet
implemented." No pruning needed here on bloat grounds. Flagging only for the audit's benefit: if
`send_batch` is implemented later, this doc's "Not yet implemented" status needs updating (or the
doc should move/close out) — otherwise it becomes a stale planning doc sitting alongside shipped
code, the kind of doc that's "past its useful life" once its subject ships. Not actionable today
since the status is currently accurate.

## Summary of recommended actions

| File | Action | Why |
|---|---|---|
| `SETUP.md` | **Delete** | 100% duplicate of README.md's Setup section |
| `README.md` "Usage" (lines 18–20) | **Condense to 1 sentence** | Restates the code sample immediately below it |
| `README.md` "Retry behavior" (lines 30–38) | **Condense to ~1–2 sentences with concrete numbers** | Padded restatement of "it retries"; currently omits the actual `MAX_RETRIES`/`TIMEOUT_S` values, which would be more useful than the prose |
| `README.md` "Retry behavior" last paragraph (lines 40–43) | **Keep as-is** | Only non-obvious, non-derivable claim in the doc |
| `CLAUDE.md` | **Consider merging into README.md** or leave minimal | Fully redundant with README's intro line; low risk either way given its size, but is one more file to keep in sync |
| `docs/plans/2026-01-10-notify-retry-design.md` line 37 | **Cut the "after going back and forth" sentence** | Narrates process, not reasoning; reasoning is already stated in adjacent sentences |
| `docs/plans/2026-07-01-batching-design.md` | **No change now; revisit when `send_batch` ships** | Doc is currently accurate and appropriately terse |
