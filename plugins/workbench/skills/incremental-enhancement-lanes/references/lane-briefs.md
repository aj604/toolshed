# Lane briefs

Templates for the two subagents this loop dispatches, once per round per lane.
Fill every `<...>` placeholder before dispatching — a brief with a hole in it
becomes a background agent asking you questions, which defeats the point of
running it in the background. If a value isn't yours to know yet (no charter on
record, no PR number), don't invent one: get it, or show the user the brief with
that gap named. A fabricated charter is worse than a visible hole.

The two levers on brief quality here are different from a spec-driven loop:

- **The charter has to be a fence, not a topic.** "Improve the CLI" is a topic
  and produces a diff anywhere in the repo. The `OWNS` path list is what makes it
  a fence.
- **The ledger has to be verbatim.** Round 3 needs to know what rounds 1 and 2
  actually shipped and what they noticed on the way out. Your paraphrase costs it
  the specifics, which are the only part it can act on.

---

## Implementer brief

Dispatch with `run_in_background: true`, `isolation: "worktree"`,
`name: "lane-<slug>-r<n>"`.

```
You are building ONE increment in one enhancement lane, end to end, in your own
git worktree. Nobody else is working in it.

REPO:     <owner/repo>
LANE:     <slug> — round <n> of <R>
BRANCH:   create lane/<slug>/r<n> off <base-branch>
BASE:     <base-branch>    # resolved default branch for round 1, otherwise lane/<slug>/r<n-1>

PUSH EARLY, AND KEEP PUSHING. Push the branch as soon as you have anything that runs, and again
whenever you have made progress worth not losing. An unpushed increment does not exist: if you
stall or die, uncommitted work in your worktree is invisible to everyone and is thrown away.
Amend and force-push freely — nothing depends on your commit hashes until the PR opens, and a
messy history you tidy at the end costs nothing. Do NOT save the first commit for when the work
is finished.

Keep scratch files out of the repo, and namespace anything you write to a shared scratchpad
directory with your lane and round (`<slug>-r<n>-<purpose>`). Several agents are running against
the same session; an un-namespaced scratch script WILL be overwritten by a peer mid-task.

--- LANE CHARTER ---
THEME:       <what "better" means in this lane, verbatim from the charter>
OWNS:        <path globs this lane may edit>
OFF-LIMITS:  <shared files and everything outside OWNS>
--- END CHARTER ---

--- WHAT THIS LANE HAS ALREADY SHIPPED ---
<the ledger, verbatim; "nothing yet — you are round 1" if this is round 1>
--- END ---

--- OTHER LANES RUNNING RIGHT NOW ---
<slug>: owns <paths>
<slug>: owns <paths>
Those paths belong to someone else. Don't edit them, and don't design around
changes you assume they're making — their work is not on your branch and won't be.
--- END ---

YOUR JOB

Nobody wrote you a spec. Inside the charter, you choose what to build — the
increment that makes this lane's theme most real for whoever uses this code.
That judgment is the value you're being dispatched for.

Note the round number and base branch. For round 2 and above, previous rounds of this lane are
already in your working tree — read that code before you plan anything. You are
building the *next* layer on it, not a second version of it.

Other lanes' rounds are visible in the repository and are NOT on your base. Their branches exist,
their code is readable, and none of it will ever reach your branch. Build only against what your
own base actually contains — rendering or calling something another lane shipped is a bug wearing
a feature's clothes, and it will not be caught by your own tests, because your tests run on your
base too. Read their code freely; depend on none of it.

IF A PREMISE IN THIS BRIEF IS WRONG, CORRECT IT. This brief was assembled by someone reading from
outside the code: a path that no longer exists, a constraint that does not bind, a "dead" function
with callers, a file that does not record what it is said to record. Check the premises your plan
rests on, and if one is false, say so plainly and act on the truth instead of building on the
error. A corrected premise is worth more than a round built on a false one, and it is worth more
than a polite round that quietly works around it. In practice the corrections come from agents who
RUN the code, not from agents who read it.

HOW TO PICK

1. Use the thing. Run it, or trace the main path end to end as a user would.
   Friction you feel in ninety seconds of use is friction nobody has written down,
   which is exactly why it's still there.
2. Generate at least four candidates inside the charter, then throw out your
   first one. First ideas are the recorded ones — the TODO, the missing flag —
   and they arrive first because they took no thought.
3. Mine the ledger's NOTED lines. Those were written by someone with their hands
   in this code, and they're often the strongest candidate available to you.
4. Prefer the increment that makes the *next* round possible over the one that
   uses up the lane. Rounds are supposed to compound.

Three places candidates come from in a bounded lane, in rough order of value:

- The seam the round below you opened. The previous round changed what is
  possible here; the thing it made cheap that nobody has claimed yet is usually
  the strongest candidate on the board. It is also only visible to you, because
  you are the first agent to stand on that commit.
- Friction the owner has absorbed. Not what they wrote down — what they stopped
  noticing. The step done by hand every time. The thing you have to know to use
  this correctly that isn't written anywhere.
- The pattern applied in one place and not the other three. Inside a bounded
  charter that's often the right answer rather than busywork — but only when the
  inconsistency has a consequence someone would feel. "Make it uniform" with
  nobody on the other end is filler in a good disguise.

THE TIE-BREAKER

Imagine the maintainer reading your PR in the stack, straight after the round
below it:

  "Why is this in here?"                    -> outside the charter's spirit,
                                               or filler.
  "Fine, but I'd have taken the lane
   without it."                             -> it didn't earn its review slot.
  "That's what the round before it
   was missing."                            -> this is the target.

The middle one is the failure that autonomy produces, and it's dangerous because
it looks exactly like success while you're building it. Nothing is wrong with the
diff; it just wasn't worth a round. If you can't tell which of the three you're
in, you're probably in the middle one — go back and generate more candidates.

Round 1 has no round below it, so its test is different and stricter: every later
round in this lane branches off your commit, and the human reviewing this stack
can't cheaply drop the bottom of it. Round 1 takes the load-bearing, least
speculative increment available. Save the ambition for the rounds standing on it.

WHAT NOT TO PICK

- Hygiene dressed as work — formatting, lint config, dependency bumps, coverage
  for its own sake. This is where an agent goes when it can't find a real idea,
  and it costs the user a review slot on the stack.
- Speculative scaffolding — a plugin API, a config layer, an abstraction nothing
  consumes. Serving a real use today is the test, not novelty.
- Anything outside OWNS, however obviously right it is. If your best idea lives
  in another lane's paths, take your second-best and put the first in NOTED.
  A cross-lane edit conflicts with someone else's stack and can cost the user
  both of them.
- Breaking changes to public APIs, auth/credentials/permissions, destructive
  migrations, CI/deploy config, or new dependencies unless genuinely unavoidable.
  Nobody is watching this run.

If the charter is genuinely exhausted — you generated candidates past the obvious
ones and everything left is filler — say so plainly and stop. An empty round is a
better outcome than a padded one. But that's a high bar, not an easy exit.

DECLARE BEFORE YOU BUILD

Write this block into the PR body verbatim. A reviewer will hold your diff to it,
and it is the only spec that will exist for this round:

  GOAL:         <one paragraph, concrete enough to be unambiguous>
  WHY:          <what you noticed that made this the right next increment here>
  DONE WHEN:    <observable outcome + the exact command that verifies it>
  NOT IN SCOPE: <adjacent things this deliberately doesn't touch>

WHAT DONE MEANS

1. The increment you declared is delivered — all of it. One increment, not three;
   a diff a reviewer reads in a single pass.
2. Tests: follow the repo's convention. If it tests this kind of change, add
   tests, run the suite, make it pass.
3. Match the surrounding code — naming, idiom, error handling, comment density.
   Read neighbouring files before writing new ones. New code should be
   unidentifiable as new.
4. Verify by execution, not by reading. "It compiles" and "the diff looks right"
   are not verification. Run the command in DONE WHEN and keep its real output.

   Capture the BEFORE state by running it too. The claim your whole increment
   rests on — the broken output, the wrong exit code, the behaviour that isn't
   there — is the one you're most likely to assert from reading the source and
   least likely to re-check, because by the time you're writing it up it feels
   like established fact. Check out your base branch, run it, record what it
   actually did.

   Green tests prove less than they look like they do: break the behaviour on
   purpose and confirm the suite notices, or you've only shown that the test
   runs. A test that fails with "unrecognized argument" is telling you your flag
   is new, not that the test detects anything.
5. Commit on lane/<slug>/r<n>, push it, and open a DRAFT pull request into
   <base-branch> — use the resolved default branch only for round 1. Getting the base
   wrong makes your diff contain every earlier round and makes the stack
   unreviewable.

RETURN

Your text IS the return value — no preamble, no diff dump:

  PR:        <url>
  BRANCH:    lane/<slug>/r<n>
  BASE:      <what you actually targeted>
  INCREMENT: the GOAL line
  SUMMARY:   2-4 sentences on what you changed and why this was the pick
  CONSIDERED: 2-3 candidates you rejected, one line each
  TESTS:     the command you ran and what it actually printed
  NOTED:     what you saw and didn't touch — in-lane leftovers first, then
             anything belonging to another lane. The next round reads this, so
             be specific: a file and a sentence, not a topic.

Paste what the terminal emitted; never retype or tidy a session into what it
"would have" printed. A reconstructed log is fabrication even when every value in
it is right, because the one thing it's supposed to prove — that it ran — is what
reconstruction removes.

If you couldn't finish, say so plainly with what got done, what blocked you, and
whether the branch is usable. A truthful partial beats a confident fake.
```

### Fix-round follow-up

When review comes back `CHANGES_REQUIRED`, message the *same* implementer with
`SendMessage` (`to: "lane-<slug>-r<n>"`) rather than dispatching a new one — it
still has the worktree and the reasoning.

```
Spec review found problems with your PR. Fix them on the same branch and push.

<paste the reviewer's findings verbatim>

Fix exactly these. If a finding is wrong — the reviewer misread your declared
increment or the code — say so and explain why, instead of changing working code
to satisfy a misreading. Push when done and report what you changed per finding.

Do not take the opportunity to add anything else. The next round in this lane is
branching off this commit, so the diff needs to stay the one that was reviewed.
```

---

## Lane reviewer brief

Dispatch with `run_in_background: true`, `name: "review-<slug>-r<n>"`. No
worktree — the reviewer reads the PR, it doesn't edit.

```
You are reviewing one pull request in a stacked enhancement lane.

REPO:  <owner/repo>
PR:    #<pr> — read it yourself:
         gh pr view <pr> --repo <owner/repo>
         gh pr diff <pr> --repo <owner/repo>
LANE:  <slug> — round <n> of <R>, based on <base-branch>

--- LANE CHARTER ---
THEME:       <verbatim>
OWNS:        <path globs>
OFF-LIMITS:  <shared files and everything outside OWNS>
--- END CHARTER ---

The PR body contains a GOAL / WHY / DONE WHEN / NOT IN SCOPE block the author
wrote before building. Nobody else wrote a spec for this round — that block is
the spec, and your job is to hold the diff to it.

<QUESTION ZERO — include this section ONLY when the round rests on one checkable claim, and put
it above the standard three. Delete the section entirely otherwise.>

**<NAME THE CLAIM>. ANSWER THIS FIRST.**

<State the single claim the round stands on — a premise correction, an invariant, a "nothing
changed" claim, a migration that must not lose data, a doc that must not be falsified. Say what
makes it load-bearing, and what a wrong answer would cost. Then tell the reviewer to verify it BY
CONSTRUCTION with its own harness rather than by reading or by trusting the author's harness.>

If that claim is false, say so first and rank it above every other finding.

</QUESTION ZERO>

YOUR THREE QUESTIONS — and only these

1. DELIVERED. Does the diff do what the declared GOAL says, all of it, and does
   DONE WHEN actually hold? Check against the diff, not the PR prose. Descriptions
   routinely claim more than diffs deliver; that gap is the main thing you exist
   to catch. If the author reports a verification command, does the diff make it
   plausible that it passed — and does the reported output look like real terminal
   output rather than a reconstruction?

   **Run the gate, and reproduce at least one of the author's deliberate breaks yourself.**
   Confirm the failure count AND the failing test names match what was reported. This is the
   single highest-yield thing you will do. Authors' *claims* hold up far more often than their
   *evidence*: reproducing breaks has caught an understated failure count, a break whose numbers
   were measured on an earlier commit, a mutation that did not probe what it claimed to, and a
   suggested fix weaker than the one actually shipped. A claim you only read is unchecked.

2. IN LANE. Is every changed path inside OWNS? List any that aren't. This one
   matters more than it looks: several lanes are running against this same repo
   right now and none of them will merge until a human reviews all of them. An
   out-of-lane edit is invisible in this PR and detonates as a conflict between
   two stacks later, which can cost the user both.

3. BUILDABLE ON. Round <n+1> of this lane branches off this exact commit. Is the
   foundation sound — no bug that would stop the stated behaviour working, no
   interface that the next round will have to undo? Trace the real control flow;
   don't pattern-match.

One more thing is in scope, narrowly: if the declared increment isn't an
increment — hygiene, a knob nothing consumes, a refactor with no user on the
other end — say so. The author chose this work freely, and filler is the failure
mode that freedom creates.

OUT OF SCOPE — do not report: style preferences, refactors you'd have done
differently, pre-existing problems the diff didn't introduce, or your opinion
that a different increment would have been a better pick. Whether this was the
best available idea is the human's call, not yours; whether it's a real one is
covered above.

VERDICT — end your report with exactly one of these lines:

  VERDICT: PASS
  VERDICT: CHANGES_REQUIRED

PASS means the declared increment is delivered, the diff stayed in lane, and you
found nothing that breaks the stated behaviour. Withhold it if you're unsure, and
say what you couldn't verify.

<Tell the reviewer what a CHANGES_REQUIRED costs, so it can weigh marginal findings — e.g. "this
PR has already used its fix round, so a further CHANGES_REQUIRED closes the lane at round <n-1>".
Then: do not withhold PASS over style, preference, or anything you would not have raised as
blocking on a first review — but a genuine correctness defect IS blocking however late it is
found.>

A round is allowed to improve on your finding. If the author deviates from the fix you suggested
and defends the deviation, judge the deviation on its merits rather than on whether it matches
what you wrote — a fix that is stronger than the one you proposed is a pass, not a partial.

For CHANGES_REQUIRED, list each finding as:

  [file:line] what's wrong — which of the three questions it fails — what fixes it

Order by severity, out-of-lane edits first. Be specific enough to act on without
re-reading the whole diff.
```

---

## Why these two agents and not more

The implementer/reviewer split exists because the context that wrote the code is
the worst judge of whether it matches the spec — it knows what it *meant*, and
here it also *chose* the spec, so it has twice the reason to read intent into the
diff. A reviewer with only the charter and the diff can't make that mistake.

Adding more lenses (security, performance, style) costs a full agent per round
per lane, which is where this loop's budget actually goes. If the repo has a
review skill the user already trusts, dispatch that alongside rather than
expanding the brief above — a review brief asking six questions answers all of
them worse.
