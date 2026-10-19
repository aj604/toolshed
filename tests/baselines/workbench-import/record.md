# Workbench skill import — 2026-10-18

Initial scope: import the existing local `enhance`, `incremental-enhancement-lanes`, and
`pm-status` skills, and convert the local `commit-to-pr` command into a bundled
skill. This checks packaging and the adaptations required for other consumers;
it does not re-establish the original workflows' effectiveness end to end.

Final scope: `pm-status` and its helper, eval catalog, and helper test were removed
at the user's request because they have not tested that skill yet. The retained
responses and initial validation below describe the earlier import; they are
historical evidence, not a claim that PM status still ships. Workbench retains
its existing seven custom role agents; no personal agent definitions were added.

## Evidence

- `RED.md`: the pre-import subagent's response, retained verbatim. Its consumer
  environment excludes personal skills and commands. It walked improvement
  shipping, open lane stacks, status reporting, and another contributor's branch
  naming against the proposed local payloads and existing plugin.
- `GREEN-initial.md`: a fresh consumer rehearsal's response, retained verbatim.
  The same dependency/resource scenarios resolve after import. The additional
  dirty-worktree scenario found an inherited hook instruction that could stage
  unrelated edits; the shipping skill now scopes re-staging to intended paths or
  hunks and permits unrelated dirt.
- `REFACTOR.md`: a fresh agent's pressure-rehearsal response, retained verbatim.
  The scenario combined a default branch named `develop`, unrelated tracked
  edits, a formatting hook, pressure for blanket staging, and pressure to merge
  lane rounds. It named the scoped-staging and open-stack rules. Its caveat is
  part of the result: explicit user overrides outrank skill defaults. This is a
  reasoning rehearsal, not an executed shipping workflow or an absolute
  no-override guarantee.
- `helper-green.txt`: actual subprocess output from the offline helper suite.
  Before import its three tests failed because the packaged scripts were absent.
  The first post-import run found a test assertion comparing macOS `/var` and
  `/private/var` aliases; resolving both paths corrected that assertion. No helper
  implementation changed.
- `incremental-enhancement-lanes/evals.json`: imported development scenarios with
  the checkout path made relative. This eval catalog was not run against a live
  repository during this import. The initially copied PM eval catalog was removed.

The Python helpers are byte-identical to the local sources. The executed helper
suite uses temporary git repositories, a local bare remote, an isolated home, and
a stubbed GitHub CLI for lane reconstruction. It covers a pushed round with no
PR, a broken stack base, and PM status/mark continuity between worktrees without
GitHub. No real transcripts or GitHub writes are involved.

The new helper suite increases CI discovery totals. The authored current totals
in `issue-203-sign-off-gate/gate-results.md` were updated accordingly; its frozen
reviewer quotations and quoted historical claims were preserved.

## Validation

- `claude plugin validate .` and `claude plugin validate plugins/workbench`:
  validation passed.
- The skill-creator `quick_validate.py` passes for all four imported skills using
  `/usr/bin/python3`. The initial default `python3` invocation could not import
  `yaml`; the system interpreter already provides it, so no dependency was added.
- `python3 .github/scripts/release-manifest.py`: all discovered suites wired,
  every gate criterion covered.
- `python3 -m unittest discover -s tests/engine -p '*_test.py'`: 1431 tests, OK.
- `python3 .github/scripts/run-script-suites.py`: 30/30 suites passed after
  updating the authored discovery totals. The initial run failed only
  `sign-off-record_test.py` on those totals; an explanatory paragraph also
  changed its measured paragraph reach, so that note was kept here instead.
- `git diff --check`: clean.

After removing PM status, the remaining helper tests passed (two tests), both
plugin/marketplace validations passed, the release manifest guard passed, and
`git diff --check` remained clean. Engine code was unchanged by the removal.
