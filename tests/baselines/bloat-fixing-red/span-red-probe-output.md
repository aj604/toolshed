# Span RED probe — approved-CUT shared-line apply path (2026-07-03)

**Context:** the 2026-07-03 whole-branch review found the bloat contract's
single-line `location` rule leaves passage extent only in free-text evidence,
while `fixing-doc-bloat`'s routing rows said "delete/replace **the line** at
`location`". The RED fixture's CUT sentence spans `README.md:19-20` and shares
line 19 with the tail of another sentence — applied literally, "delete the line
at location" corrupts the doc. This apply path was unexercised by the original
GREEN run (its approval was `["B2", "B5"]`, no CUT).

**Probe setup (skill text UNEDITED, pre-span-contract):** fresh Sonnet-tier
subagent, fixing-doc-bloat SKILL.md + apply-discipline.md as deployed, scratch
git repo containing the bloat-red fixture, report =
`span-reverify-bloat-report.json` (B1's evidence opening with the
`fixture/README.md:19-20` span), approval = `{"approved": ["B1"]}`.

**Result: no corruption — the agent overrode the literal routing text.** Its
own report: "anchor confirmed before editing — the evidence's quoted sentence
… spanned lines 19–20 (it begins mid-line 19, after 'message.' which ends the
preceding sentence). Deleted exactly that sentence; the surrounding sentence is
intact." Controller-verified diff of its commit (`bbd068e`):

```diff
 Import `send_alert` from `src/notify.py` and call it with a channel and a
-message. The `send_alert` function takes a channel and a message and delivers
-the message to that channel.
+message.
```

1 file changed, 1 insertion(+), 2 deletions(-); approved-only discipline held
(B2–B6 untouched); evidence traveled in the commit body.

**RED classification:** the failure the review predicted did not reproduce at
this tier — the spine's anchor-confirm (§3) plus the evidence quote contained
it, exactly as the review judged ("non-blocking because the human gate + spine
anchor-confirm contain it"). What the probe *does* establish, together with the
original GREEN run's CONDENSE (which replaced all nine lines of
`README.md:30-38` despite "replace the line"), is that **every correct run
contradicts the normative routing text** — agents succeed by overriding the
letter of the rule. That is the defect being fixed: the contract under-describes
its own passing runs and leaves correctness to discretionary override. The fix
makes the span normative (detecting-doc-bloat: passage-verdict evidence must
open with `file:start-end` anchored at `location`, validator-enforced;
fixing-doc-bloat: routing rows reworded to the passage the evidence span
delimits), so the letter and the passing behavior agree.
