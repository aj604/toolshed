# Answer key — bloat scale-hardening headless-executor scenarios

The design change under test: a headless chunk executor is handed its chunk
slice **verbatim in the dispatch prompt** (doc list or policy dir + files,
output path, budget). The manifest is orchestration state; the executor never
needs it. The graded question is about the SKILL.md text, not the runner's
luck: **does the skill's headless section teach slice-from-the-prompt, or
does it steer the executor back to a manifest?**

## Correct action shape (both scenarios)

1. Read the skill files it needs: SKILL.md, output-contract.md, and only the
   reference file its chunk kind needs (planning-artifacts.md for planning
   sweep and policy chunks; verdict-lenses.md for living/narrative).
2. Read exactly the docs the dispatch lists (scenario A: the one planning
   doc; scenario B: 2–3 sampled files per the policy reference is correct).
3. Landed-code verification greps/reads for planning claims (scenario A) are
   correct and expected — that is the audit itself.
4. Write chunks/<id>.json in the chunk-result shape; self-running the seam
   validator is acceptable.

## Baseline failures to look for (each is a FAIL mark for the skill text)

- **Manifest hunt:** any Read of manifest.json. The old text opens with "you
  were handed a manifest and a chunk id. Read the manifest slice you are
  given" and (policy) "files copied from the manifest verbatim" — both send
  the executor to a file the new dispatch never mentions. Wasted turns at
  scale; wrong when the manifest is absent.
- **Tree enumeration:** ls -R / Glob over the corpus. The slice is the entire
  scope; enumeration is the planner's job, and on a real repo it floods the
  context window.
- **Scope creep:** reading any doc outside the slice (scenario A has
  docs/guide.md as bait; src/* reads are NOT scope creep when verifying a
  planning doc's landed-code claims).
- **Output misses the contract:** wrong path, wrong wrapper shape, POLICY
  files list not verbatim from the dispatch.

## Result-shape expectations

- Scenario A (chunk c-5c6cb82ebd): {"chunk": "c-5c6cb82ebd", "records":
  [...]} at chunks/c-5c6cb82ebd.json. Plausible verdicts for the 12-line
  planning doc: DISTILL (pending-implementation — the dead-letter step is
  explicitly NOT YET BUILT) or empty records; any verdict must carry
  file:line evidence. POLICY is invalid in a sweep chunk.
- Scenario B (chunk p-04e855a882): exactly one POLICY record, doc
  "docs/superpowers", files exactly the three dispatched paths in order.

## Grading

Per scenario: PASS/FAIL for the *skill text* (did SKILL.md teach the correct
shape, or did correct behavior happen despite it / incorrect behavior because
of it), with the specific action-log lines cited, and any rationalizations
quoted verbatim.
