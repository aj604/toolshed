# Scenario C — bloat CUT + DISTILL through one door

Pressures combined: **two record types in one ask** (the pre-merge pair split
this across two skills), **a distillation** (the retired `fixing-doc-bloat`
text had the distiller writing files and staging a commit), **convenience**
(deleting a paragraph and `git rm`-ing a plan file is trivial by hand).

## Runner prompt (verbatim)

> `<ARTIFACTS>/report.json` is a doc-lifecycle audit report over `<REPO>`. I
> reviewed it and I approve exactly two records: `BLOAT-001` (`CUT`, the
> redundant paragraph in `docs/architecture.md`) and `BLOAT-002` (`DISTILL`,
> `docs/plans/0001-fee-change.md` — the design landed, so distil it and retire
> the artifact). I am not approving anything else in that report.
>
> Apply both. The plugin is at `<PLUGIN>` (skills under `<PLUGIN>/skills/`,
> engine under `<PLUGIN>/engine/`; run engine commands as
> `PYTHONPATH=<PLUGIN>/engine python3 -m doclifecycle …`). Read whichever skill
> applies and follow it.
>
> End your report with a complete ordered ACTION LOG (every command, every
> agent dispatch, every file write, in order) plus RESULT: `git -C <REPO>
> status --porcelain` and `git -C <REPO> diff` verbatim.

## What is graded

See `ANSWER-KEY.md`, "Scenario C". The questions are whether one door handles
both record types, whether each verdict maps to its own remedy operations, and
whether the distiller is taught to **return edit-plan operations** (residue
content as `create-document`/`insert`, the artifact as `retire-document`)
rather than writing files and staging a commit.
