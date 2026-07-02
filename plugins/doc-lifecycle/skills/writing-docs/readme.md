# Writing a README

Reader: a newcomer deciding whether to use this and getting it running. Human rendering —
orient first, then enable. Every command and output is a verifiable claim (see SKILL.md).

## Coverage checklist (Diátaxis lenses — a checklist, NOT a page layout)

- [ ] **Orient** (explanation): what is this, what problem it solves, in 1–2 sentences.
- [ ] **Get it running** (how-to): install + minimal usage, with **real** output.
- [ ] **Look things up** (reference): flags/config/exit codes — or a pointer to where they live.
- [ ] **Learn** (tutorial): only if onboarding is non-trivial; otherwise skip.

Small repos do NOT get four sections. Use the lenses to check coverage, then write the
smallest README that covers them.

## Structure

```
# name
one-sentence what-and-why

## Requirements        (only non-obvious ones: runtime version, services)
## Install             (only verified steps; no aspirational package names)
## Usage               (real command + real output)
## Configuration       (if any: shape + default location + override)
## Exit codes / output (if a CLI: the actual contract)
## Development         (build/test commands, verified)
## License
```

## One verified example

Good — output was produced by running the command:

```sh
npm run build      # required first: the CLI measures dist/bundle.js
node bin/cli.js
# OK   dist/bundle.js  0.1kb / 5.0kb   ← real output; sizes are gzip-dependent
```

## Failure modes (observed in baselines)

- **Fabricated example output.** A baseline README showed `3.2kb` / `actual:3277`; real
  values were `0.1kb` / `145`. Run it or omit it.
- **Aspirational install.** `npm install <pkg>` / `npx <pkg>` for an unpublished package.
  Cut or mark as not-yet-published.
- **Marketing prose.** "blazing-fast", "powerful", "zero-config" — unverifiable; cut.
- **Missing the gotcha.** The build-before-run requirement is invisible unless you run it;
  it's exactly what the reader needs.
