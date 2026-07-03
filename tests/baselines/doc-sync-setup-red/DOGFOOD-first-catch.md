# Dogfood — the first production catch (2026-07-02)

Closes the record set for `scheduling-doc-sync` (RED → GREEN → E2E → production). The
pipeline was installed on toolshed itself (`bd91cb6`, marker seeded at `cead264`) and
manually dispatched for its inaugural run:
[run 28617674431](https://github.com/aj604/toolshed/actions/runs/28617674431) →
[PR #5](https://github.com/aj604/toolshed/pull/5), merged as `0b72777`.

## What it caught — two stale claims in this repo's own docs

| Location | Stale claim | Why it was stale |
|----------|-------------|------------------|
| `CLAUDE.md:9` | "`tests/fixtures/` are the only other runnable code." | The install commit itself added runnable `.github/doc-sync/*.py` + the workflow — the claim was falsified by the very commit being scanned. |
| `detecting-doc-drift/SKILL.md:25` | auto-trigger layer "designed but not yet built" | False since `scheduling-doc-sync` shipped that same day. |

Both fixes were drafted by detection with `file:line` evidence, applied verbatim by the
fixer, and landed via the evidence PR. The diff touched exactly the two doc lines plus the
sync marker.

## Why this closes the loop

The second catch is the notable one: that "not yet built" line survived every human gate
this branch ran — the Task-6 doc sync (scoped to four named files; see the task brief in
the plan), the final whole-branch review, and the manual merge-conflict reconciliation
sweep — because it sat in a *different skill's* SKILL.md. The nightly found it on its
first pass. The failure mode the suite was built for (drift hiding where nobody is
looking) is the one its own automation caught, in its own repo, on day one.
