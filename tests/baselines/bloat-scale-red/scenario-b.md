# Scenario (b) — policy chunk (RED)

Sandbox: `bloat-scale-sandbox/b` — `docs/superpowers/plans/p{1,2,3}.md`
declared policy scope via `.github/doc-sync/audit-scope.json`, plus a
README in its own sweep chunk; real `manifest.json` present. Dispatch:
`dispatch-b.txt` (real `--emit-prompt` output for policy chunk
`p-04e855a882`; hands the dir and the complete files list verbatim, never
mentions a manifest).

## Runner output (verbatim)

ACTION LOG
1. Read — …/detecting-doc-bloat/SKILL.md — invoke the skill; get headless-executor and policy-chunk rules.
2. Read — …/detecting-doc-bloat/output-contract.md — load the v2 record field rules and chunk-result seam shape.
3. Read — …/references/planning-artifacts.md — load the policy-chunk verdict rules (one record, sample 2–3 files, files verbatim).
4. Bash — ls -R …/bloat-scale-sandbox/b — inventory the job directory (found manifest.json, docs/superpowers/plans/, chunks/ not yet present).
5. Read — …/b/manifest.json — confirm chunk p-04e855a882 is kind policy, dir docs/superpowers, and its verbatim file list matches the dispatch.
6. Read — …/b/docs/superpowers/plans/p1.md — sample file 1 for the evidence field.
7. Read — …/b/docs/superpowers/plans/p2.md — sample file 2 for the evidence field (2-of-3 sampling per the reference; p3.md deliberately not opened).
8. Write — …/b/chunks/p-04e855a882.json — write the chunk result with the single POLICY record.
9. Bash — python3 …/validate-bloat-output.py --chunk chunks/p-04e855a882.json --manifest manifest.json — seam-validate the result (OK: 1 record(s) valid).

RESULT: one POLICY record, doc `docs/superpowers`, files exactly the three
dispatched paths in order, single-class evidence sampling p1/p2 with
file:line quotes. (Full JSON in the runner transcript; contract-clean per
the seam validator.)

## Grader verdict (fresh stakeless grader, verbatim)

Q1: FAIL — Action-log line 4 (`ls -R` over the job directory) is tree
enumeration and line 5 (Read of `manifest.json`) is a manifest hunt; the
dispatch handed the policy dir and full files list verbatim and never
mentioned a manifest, so both reads are wasted turns outside the correct
shape. Everything else matched.

Q2: MISDIRECTS — the SKILL.md headless paragraph teaches a manifest
handoff, not slice-from-the-prompt: "**Headless (chunk executor):** you
were handed a manifest and a chunk id. Read the manifest slice you are
given, judge exactly those docs with the reference rules, write the chunk
result, stop." and "A policy chunk means one `POLICY` record, files copied
from the manifest verbatim." Reinforced by the frontmatter ("a
chunk-executor invocation handed a manifest slice") and the red flag ("a
`files` list that isn't the manifest's verbatim").

Grader's key lines: "The runner's own log shows the misdirection working:
line 1 says it got 'headless-executor and policy-chunk rules' from
SKILL.md, then line 5 rationalizes the manifest read as confirming 'its
verbatim file list matches the dispatch' — a cross-check the skill text
demands ('copied from the manifest verbatim') but the new dispatch design
makes unnecessary and, when the manifest is absent, impossible." "Line 4's
`ls -R` was the search that located the manifest … enumeration in service
of the manifest hunt; on a real repo this floods context." Skill-text
mark: FAIL — incorrect behavior (lines 4–5) occurred because of the
current wording.
