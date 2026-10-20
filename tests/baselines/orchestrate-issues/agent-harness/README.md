# Agent harness: evals 14-17

These evals run the workbench role agents directly, with
`claude -p --plugin-dir <plugin> --agent workbench:<role>`. An arm is a
plugin tree, for example `git archive <ref> plugins/workbench | tar -x
--strip-components=2 -C <dir>`.

- **Real run (eval 17):** `./run-impl.sh <plugin-dir> <out-dir>`, then
  `./grade-real.py <out-dir>`. The run builds the substrate
  (`substrate-notify/base` committed on `main`, `uncommitted/` as the
  stopped agent's work on the issue branch), a local bare remote, and the
  `bin/gh` stub, which logs calls and fakes PR #31. The README puts the
  full suite at ~15 minutes, but it really takes ~150 s. The grader reads
  top-level tool_use events from `outputs/stream.jsonl` and writes
  `grading.json`. A run costs about $1 and takes 4-7 minutes.
- **Rehearsals (evals 14-16):** `./run-rehearsal.py <plugin-dir> <out-dir>
  [ids]`. All tools are disallowed, and the agent answers with the tool
  calls it would make. Grade each `response.md` with a fresh grader that
  holds the assertions from `../evals.json` and not the arm labels.
