# Turn for the `impl-380` notification

## Tool calls

None.

The notification is not a final hand-back. Its result is "This agent has not reported yet", and its summary says `impl-380` is waiting on its own background work (a build or suite run). Step 2.3 of the skill covers this case: it needs no turn from me, so I ignore it and keep waiting.

So I do not:

- dispatch `workbench:spec-reviewer` for #380, because there is no implementer report and no PR to review;
- `SendMessage` `impl-380`, because nothing about its ground has moved and it is still working;
- re-dispatch or replace `impl-380`, because it is alive, 25 minutes in at most;
- query the frontier, since nothing merged and no edge can have opened;
- poll `gh` for its branch, PR or CI;
- call `AskUserQuestion`.

Ending the turn is safe: four lanes are in flight, and each will wake me with its own hand-back.

## Output

One line, and nothing else:

> Still waiting: `impl-380` is on its own background work and hasn't reported. 4 lanes in flight, nothing landed yet.

## Next

The next turn starts when a lane delivers a real hand-back (a draft PR open with `Closes #<n>`). That lane then goes to Step 4: dispatch `workbench:spec-reviewer` as `review-<n>-r1`.
