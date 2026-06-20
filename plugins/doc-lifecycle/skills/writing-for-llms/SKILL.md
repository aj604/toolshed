---
name: writing-for-llms
description: Use when documentation needs to be optimized for AI/agent consumption — converting human or marketing docs into dense agent-facing form, or authoring agent-facing docs from a repo or from findings, especially when token bloat or context rot is a concern.
---

# Writing for LLMs

Agent-facing docs must be **dense and honest**: maximum signal per token, with no specific asserted that the input or the code doesn't back.

## Dispatch the agent

For any real LLM-doc work, dispatch the **llm-doc-writer** agent. It runs in its own context — keeping the source doc and the repo exploration out of yours — and owns the method (densify, verify-or-mark, anchor). Don't re-derive that method here; the agent holds it.

Pass it:
- **What to write from:** a source doc path, raw content, or a topic + findings.
- **The repo path, if one exists** — this puts it in *verify* mode (checks every claim against code, runs safe commands, anchors to `file:line`). Omit it for *densify-only* mode (trusts the input, marks what it can't trace).
- **The output path** to write to.

## The contract (what to require of the output)

- **Run-or-omit:** every command, flag, number, API, and example output is backed, marked `> UNVERIFIED`, or cut. No invented specifics, no token-count theater, no `-revised` orphan files.
- **Anchored** to `file:line` or `command → output` when a repo is present, so the result is drift-checkable by `detecting-doc-drift`.

A one-line tweak not worth a dispatch? Apply the same contract inline.
