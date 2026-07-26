# doc-lifecycle

The documentation-lifecycle plugin: detects drift and bloat in repo documentation, routes human approval, and applies approved fixes. This glossary is the ubiquitous language for its re-architecture (issue #57).

## Language

### Components

**Audit engine**:
The read-only component that examines documentation against the repo and produces a report. Never mutates anything.
_Avoid_: detector (that's a policy, not the component), scanner

**Applier**:
The deterministic, capability-limited component that executes an edit plan authorized by an approval set. The only component that writes.
_Avoid_: fixer, executor

**Scheduler adapter**:
The automation wrapper (currently GitHub Actions) that sequences audit → approval → apply on a cadence. Owns no lifecycle rules; calls the same contracts interactive use does.
_Avoid_: the workflow, the automation (as if it owned behavior)

**Authoring skills**:
The interactive skill family (bootstrapping-docs, writing-docs, growing-docs) that helps a person create and grow docs. Shares the document model's vocabulary, not the engine's code.

**Assertion unit**:
A deterministically segmented structural unit of a living document (sentence, list item, table row — fixed parser). Its identity is a content digest of the unit; findings may group several units. Segmentation never involves a model.
_Avoid_: claim (legacy "every line is a claim"), line

**Assertion class**:
The model-assigned classification of an assertion unit — factual (needs evidence), normative (needs owner/source), rationale, or non-assertive prose (no obligation). Recorded in the report as reviewable data; determines the unit's evidence obligation, never its identity.
_Avoid_: claim type

### Contracts (artifacts, not components)

**Report**:
An immutable statement of what was examined and what was found, pinned to the repository state and audit inputs that produced it. Proof of examination, not authority to change anything.
_Avoid_: findings list, output, results

**Document inventory**:
The registry's verdict on a repository: every document under the declared roots with its kind, set, and content digest, plus a finding for each document no rule claims. Derived, deterministic, and digested — the inventory digest is part of every report's lineage. Says what exists, never whether it is accurate.
_Avoid_: file list, corpus (as if it were the inventory), doc index

**Result state**:
The single named outcome a run resolves to — clean, findings, partial, stale, or invalid/unsafe. Only clean means the declared scope was examined successfully under the named mode and rules. A run that cannot be trusted reports invalid and carries no partial output.
_Avoid_: status (unqualified), error, failure

**Problem**:
One typed reason a run is invalid: a code, a message that says how to recover, and where it was found. Reported exhaustively — a run names every problem it found, not the first.
_Avoid_: error message, warning (a problem never degrades to advisory)

**Approval set**:
An immutable artifact binding selected record digests from one report, plus its lineage, to an allowed mutation scope. The sole authority the applier accepts. Never tracked in the repo: its digest and summary travel in the change it authorizes (commit, PR body), and it expires with that change's validity.
_Avoid_: approval layer, dispatch list, approved records (informal)

**Semantic approval**:
A person selecting record digests from one report — the act that mints an approval set. Authorizes planning and application, not the final diff.
_Avoid_: approval (unqualified), dispatch

**Auto-apply policy**:
A standing, consumer-configured declaration of which finding classes may have approval sets minted without a human — mechanical remedies only (default: drift STALE with exact preimage and evidence; narrative as-of/anchor refresh; never bloat, create, or retire). Recorded as the minter in the approval set's lineage; PR review is the designated semantic review for what it mints.
_Avoid_: auto-fix, autonomous mode

**Change approval**:
A person accepting the actual produced diff — merging the draft PR, or committing the staged interactive change. The only approval that lands anything.
_Avoid_: merge (as if it approved the model's judgment)

### Substrate

**Document model**:
The shared typed vocabulary for what documentation is (kinds, sets, assertions) that all components and the authoring skills build on.

**Document kind**:
The truth obligation a document carries. Exactly three: living (must be currently true, assertions carry evidence), narrative (must be honestly dated; as-of/anchors valid, never line-verified), planning (temporary; carries lifecycle state; ends in distillation or retirement). Every document has exactly one kind.
_Avoid_: document type, category, policy collection (as a kind)

**Document set**:
A grouping of documents sharing conventions — naming, metadata template, retirement rules (e.g., docs/adr/). Orthogonal to kind: a set's members each have their own kind. At most one set per document.
_Avoid_: collection, policy collection

**Registry**:
The validated manifest mapping paths and globs to document kind and set within declared documentation roots. Closed-world: a document under a root matching no rule is an audit finding, and an unparseable registry invalidates the whole audit. Owns classification; content-coupled facts (as-of, anchors, lifecycle state) stay in the file. Its digest is part of every report's lineage.
_Avoid_: scope file, doc-scope (legacy), manifest (unqualified)

**Deterministic scope**:
An enumerable inclusion rule declaring exactly which files a bulk operation may touch — typically a document set. Sampling may prioritize review but never authorizes mutation. Belongs to audit configuration and the approval set, not the document model's taxonomy.
_Avoid_: policy collection, sample scope
