RED packaging result: **fails before import**. No workflow execution, writes, GitHub/network calls, or private-session access occurred.

Located findings:

- **Required shipping dependency absent.** `enhance/SKILL.md:223` requires invoking `commit-to-pr`; it exists only at `~/.claude/commands/commit-to-pr.md`, outside the installed plugin. Import it as `skills/commit-to-pr/SKILL.md` and resolve the bundled skill explicitly.
- **Status commands retain a personal installation path.** `pm-status/SKILL.md:42,180` invoke `~/.claude/skills/pm-status/scripts/gather.py`. Even copying the full source directory into workbench leaves those commands pointing outside the installation. Use the plugin resource path for both gather and mark.
- **Shipping assigns Avery’s branch namespace to other contributors.** `commit-to-pr.md:47–63` mandates `ajones/<slug>` and includes matching create/rename commands. A different contributor following the default-branch scenario creates an Avery-namespaced branch. Use repository convention or a neutral branch slug.
- **Lane portability assumes `main`.** `incremental-enhancement-lanes/SKILL.md:167`, `references/lane-briefs.md:31,67`, and `references/stacking.md:58` use `main` as the actual initial base/rebase target. On a repo whose default is `develop`, following those instructions selects an absent or wrong base. Resolve the default branch once and propagate it through briefs/recipes.
- **Copy entire resource directories.** Lane execution needs `references/lane-briefs.md`; recovery/status needs `scripts/lanes.py`; stack maintenance needs `references/stacking.md`. Status needs `scripts/gather.py`. Those files exist in the local source and currently do not exist in workbench.

Dependency assessment: `enhance → commit-to-pr` is the required cross-skill edge. `/code-review` and `/security-review` in commit-to-pr are optional suggestions. PM’s Claude desktop session tools are optional because the documented fallback is local transcripts; they are not an external skill requirement. Lanes carry their own reviewer briefs.

Exact packaging probe:

```bash
python3 - <<'PY'
from pathlib import Path
root=Path('plugins/workbench')
for rel in ['skills/enhance/SKILL.md','skills/commit-to-pr/SKILL.md','skills/incremental-enhancement-lanes/SKILL.md','skills/incremental-enhancement-lanes/references/lane-briefs.md','skills/incremental-enhancement-lanes/references/stacking.md','skills/incremental-enhancement-lanes/scripts/lanes.py','skills/pm-status/SKILL.md','skills/pm-status/scripts/gather.py']:
 print(f'{rel}: {"present" if (root/rel).is_file() else "MISSING"}')
PY
```

Actual output:

```text
skills/enhance/SKILL.md: MISSING
skills/commit-to-pr/SKILL.md: MISSING
skills/incremental-enhancement-lanes/SKILL.md: MISSING
skills/incremental-enhancement-lanes/references/lane-briefs.md: MISSING
skills/incremental-enhancement-lanes/references/stacking.md: MISSING
skills/incremental-enhancement-lanes/scripts/lanes.py: MISSING
skills/pm-status/SKILL.md: MISSING
skills/pm-status/scripts/gather.py: MISSING
```

Source evidence was read with `nl -ba` for the six Markdown files and PM helper; `rg --files` inventoried source/plugin resources, and `rg -n` located dependency/path/namespace references. No helper was run, avoiding fetches, marking, and transcript reads.
