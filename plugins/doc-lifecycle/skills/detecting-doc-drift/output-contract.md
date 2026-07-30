# Output contract — worked example

Reference for `detecting-doc-drift`; the field set, enum rules, and validator step live in
SKILL.md — this file is the worked example only.

`verdicts.json` for a two-document run against a sample repo. `CLAUDE.md` was segmented and
judged; `docs/runbook.md` was not reached, so it is declared `failed` with a reason rather than
left out.

```json
{
  "schema_version": 1,
  "documents": [
    {
      "path": "CLAUDE.md",
      "status": "ok",
      "verdicts": [
        {
          "unit": 12,
          "assertion_class": "factual",
          "obligation": "evidence",
          "verdict": "STALE",
          "kind": "command",
          "tier": 1,
          "evidence": {
            "source": "Makefile",
            "line": 9,
            "observed": "the target is `clean:`; no `reset` target is defined"
          },
          "fix": "Reset state = `make clean`"
        },
        {
          "unit": 18,
          "assertion_class": "factual",
          "obligation": "evidence",
          "verdict": "VERIFIED",
          "kind": "behavior",
          "tier": 2,
          "evidence": {
            "command": "worker --version",
            "observed": "prints 3.2.0, the version the line documents"
          }
        },
        {
          "unit": 19,
          "assertion_class": "non-assertive"
        },
        {
          "unit": 20,
          "assertion_class": "normative",
          "obligation": "governing-source",
          "verdict": "VERIFIED",
          "kind": "behavior",
          "tier": 2,
          "evidence": {
            "source": "CONTRIBUTING.md",
            "line": 31,
            "observed": "the governing review rule still requires two approvals"
          }
        },
        {
          "unit": 21,
          "assertion_class": "rationale",
          "obligation": "coherence",
          "verdict": "UNVERIFIABLE",
          "kind": "behavior",
          "tier": 3,
          "evidence": {
            "observed": "no current decision or implementation source explains the stated tradeoff"
          }
        }
      ]
    },
    {
      "path": "docs/runbook.md",
      "status": "failed",
      "reason": "segment exited 1: the file was deleted between plan and audit"
    }
  ]
}
```

What each entry demonstrates:

- **Unit 12** — a STALE `command` claim citing a file. `source` and `line` locate what was
  read, `observed` states the fact in one line, and `fix` is the unit's complete replacement
  text, not an instruction describing one.
- **Unit 18** — a VERIFIED `behavior` claim citing a **command** rather than a file. There is
  no `line`: a tool's output is not a file position. There is no `fix` — only STALE carries
  one. The command is a single read-only line, with no chaining or redirection.
- **Unit 19** — a `non-assertive` unit. It is classified (leaving a capable unit out is refused)
  but takes no `obligation`, `verdict`, `kind`, `tier`, or `evidence`: it asserts nothing the code could
  contradict, so a verdict would record a claim nobody made.
- **Unit 20** — a normative assertion discharging its `governing-source` obligation against the
  current rule. `owner-judgment` is the other valid normative obligation.
- **Unit 21** — a rationale assertion whose required `coherence` judgment is UNVERIFIABLE because
  no current evidence settles the explanation. Classification does not let it go unjudged.
- **`docs/runbook.md`** — a `failed` entry. It carries a one-line `reason` and no `verdicts`,
  which is how the run declares a document it did not examine.

Validate before the audit — see SKILL.md step 5 for the command and the full rules.

`unit` is the `ordinal` that `segment` printed for that unit, and it is how the engine places a
drift edit — no `file:line` location appears anywhere in this artifact.
