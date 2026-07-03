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
