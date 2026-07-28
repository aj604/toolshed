"""The `python3 -m doclifecycle` commands.

Deliberately thin: a command parses argv, calls one library function, prints its
`to_dict()` payload, and maps the result state to an exit code. No command holds
logic of its own, so an interactive import and a CI invocation cannot disagree.
Two commands print something other than that payload — `render-report` prints
Markdown, and `migration-draft --registry-only` prints the registry file's bytes
so the door's output can be redirected straight to the path a human reviews —
and in both cases the alternative rendering is of the same library result.

Exit codes name the result state, so a workflow can gate without parsing JSON:
0 the run completed and its scope was examined (`ok`, `clean`, `findings` —
findings are data, not a gate); 1 invalid; 2 a usage error; 3 stale; 4 partial.
`inventory` reaches only 0, 1, and 2, as it always has; 3 and 4 belong to the
report states.
"""

import argparse
import json
import sys

from .applier import apply_edit_plan, load_approval_payload, load_edit_plan
from .approval import (
    MINTER_HUMAN,
    MINTER_KINDS,
    Minter,
    load_approval_set,
    mint_approval_set,
    write_approval_set,
)
from .bloat import (
    DEFAULT_MAX_DOCUMENTS,
    DEFAULT_MAX_UNITS,
    plan_repository_chunks,
)
from .context import build_context_index
from .drift import (
    DEFAULT_EVIDENCE,
    MODE_FULL,
    MODES,
    audit_drift,
    load_verdicts,
    plan_drift_audit,
)
from .inventory import DEFAULT_REGISTRY_PATH, build_inventory
from .migrate import (
    INSTALLED_VERSION_PATH,
    WAIVERS_PATH,
    draft_registry,
    dry_run_migration,
)
from .policy import (
    DEFAULT_POLICY_PATH,
    load_auto_apply_policy,
    mint_policy_approval_set,
    policy_eligibility,
)
from .reconcile import reconcile
from .render import approval_trailers, render_approval_set, render_report
from .report import Report, load_report
from .segment import segment_document
from .results import (
    STATE_CLEAN,
    STATE_FINDINGS,
    STATE_INVALID,
    STATE_PARTIAL,
    STATE_STALE,
    STATUS_OK,
    Invalid,
)

EXIT_CODES = {
    STATUS_OK: 0,
    STATE_CLEAN: 0,
    STATE_FINDINGS: 0,
    STATE_INVALID: 1,
    STATE_STALE: 3,
    STATE_PARTIAL: 4,
}


def _add_report_arguments(command):
    command.add_argument(
        "--report", required=True, help="path to the report JSON to check"
    )
    command.add_argument(
        "--repo",
        default=None,
        help=(
            "repository the report claims to describe; supply it to check "
            "freshness (without it the check is structural only and can never "
            "return stale)"
        ),
    )
    command.add_argument(
        "--registry",
        default=DEFAULT_REGISTRY_PATH,
        help=f"registry path, repo-relative (default: {DEFAULT_REGISTRY_PATH})",
    )
    command.add_argument(
        "--audit-config-digest",
        default=None,
        help=(
            "the consumer's current audit-configuration digest; supply it to "
            "include configuration drift in the freshness check"
        ),
    )
    command.set_defaults(run=lambda args: load_report(
        args.report,
        repo_root=args.repo,
        registry_path=args.registry,
        audit_config_digest=args.audit_config_digest,
    ))


def _add_approval_arguments(command):
    """`--approval`, plus the optional things it can be checked against."""
    command.add_argument(
        "--approval", required=True, help="path to the approval-set JSON"
    )
    command.add_argument(
        "--report", default=None,
        help=(
            "the report the approval set was minted from; supply it to check "
            "the selection against the records it names"
        ),
    )
    command.add_argument(
        "--repo", default=None,
        help=(
            "the repository the approval set authorizes changes to; supply it "
            "to check freshness (without it the check is structural only and "
            "can never return stale)"
        ),
    )
    command.add_argument(
        "--registry", default=DEFAULT_REGISTRY_PATH,
        help=f"registry path, repo-relative (default: {DEFAULT_REGISTRY_PATH})",
    )
    command.add_argument(
        "--audit-config-digest", default=None,
        help="the consumer's current audit-configuration digest",
    )
    command.add_argument(
        "--expected-digest", default=None,
        help=(
            "the Doc-Lifecycle-Approval trailer of the change being applied; "
            "supply it to bind this file to the approval that authorized the "
            "change, since the trailer is the only part that lands in the "
            "repository"
        ),
    )
    command.set_defaults(run=_validate_approval)


def _validate_approval(args):
    """Load the approval set, and the report it is checked against if named."""
    report = None
    if args.report is not None:
        report = load_report(
            args.report, repo_root=args.repo, registry_path=args.registry,
            audit_config_digest=args.audit_config_digest,
        )
        if isinstance(report, Invalid):
            return report
    return load_approval_set(
        args.approval, report=report, repo_root=args.repo,
        registry_path=args.registry,
        audit_config_digest=args.audit_config_digest,
        expected_digest=args.expected_digest,
    )


def _apply_plan(args):
    """Load the artifacts as data and hand them to the one write path."""
    plan = load_edit_plan(args.plan)
    if isinstance(plan, Invalid):
        return plan
    approval = load_approval_payload(args.approval)
    if isinstance(approval, Invalid):
        return approval
    report = None
    if args.report is not None:
        report = load_report(
            args.report, repo_root=args.repo, registry_path=args.registry,
            audit_config_digest=args.audit_config_digest,
        )
        if isinstance(report, Invalid):
            return report
    return apply_edit_plan(
        args.repo, plan, approval, report=report,
        registry_path=args.registry,
        audit_config_digest=args.audit_config_digest,
        expected_digest=args.expected_digest,
    )


def _reconcile_report(args):
    report = load_report(
        args.report, repo_root=args.repo, registry_path=args.registry,
        audit_config_digest=args.audit_config_digest,
    )
    if isinstance(report, Invalid):
        return report
    # Reconciliation is a property of the records, so it is answered for any
    # report that validates. Whether the report is still fresh enough to act on
    # is `validate-report`'s question, and minting's gate.
    return reconcile(report)


def _mint_approval(args):
    report = load_report(
        args.report, repo_root=args.repo, registry_path=args.registry,
        audit_config_digest=args.audit_config_digest,
    )
    if isinstance(report, Invalid):
        return report
    approval = mint_approval_set(
        report, args.record, repo_root=args.repo,
        minter=Minter(kind=args.minter_kind, id=args.minter),
        registry_path=args.registry,
    )
    if isinstance(approval, Invalid) or args.out is None:
        return approval
    written = write_approval_set(approval, args.out)
    return written if isinstance(written, Invalid) else approval


def _policy_inputs(args):
    """`(report, policy)`, or the `Invalid` whichever of them refused first.

    Two artifacts and either can refuse, so the refusal is returned as itself
    rather than as a flag: a caller that has to ask which of a pair is `None`
    is one that can forget to.
    """
    report = load_report(
        args.report, repo_root=args.repo, registry_path=args.registry,
        audit_config_digest=args.audit_config_digest,
    )
    if isinstance(report, Invalid):
        return report
    policy = load_auto_apply_policy(args.repo, args.policy)
    if isinstance(policy, Invalid):
        return policy
    return report, policy


def _policy_eligibility(args):
    inputs = _policy_inputs(args)
    if isinstance(inputs, Invalid):
        return inputs
    report, policy = inputs
    return policy_eligibility(policy, report)


def _policy_mint(args):
    inputs = _policy_inputs(args)
    if isinstance(inputs, Invalid):
        return inputs
    report, policy = inputs
    approval = mint_policy_approval_set(
        report, policy, repo_root=args.repo, registry_path=args.registry,
    )
    if isinstance(approval, Invalid) or args.out is None:
        return approval
    written = write_approval_set(approval, args.out)
    return written if isinstance(written, Invalid) else approval


def _render_report(result, args):
    return render_report(result)


def _render_approval(result, args):
    return approval_trailers(result) if args.trailers else render_approval_set(result)


def _add_corpus_arguments(command):
    """`--repo`/`--registry`, for the commands that read the whole corpus."""
    command.add_argument(
        "--repo", default=".", help="repository root (default: the current directory)"
    )
    command.add_argument(
        "--registry",
        default=DEFAULT_REGISTRY_PATH,
        help=f"registry path, repo-relative (default: {DEFAULT_REGISTRY_PATH})",
    )


def _add_policy_arguments(command):
    """The report, the repository, and where the auto-apply policy lives."""
    command.add_argument(
        "--report", required=True,
        help="path to the report JSON the policy decides about",
    )
    command.add_argument(
        "--repo", required=True,
        help="the repository the report describes, and the policy's home",
    )
    command.add_argument(
        "--policy", default=DEFAULT_POLICY_PATH,
        help=(
            f"auto-apply policy path, repo-relative (default: "
            f"{DEFAULT_POLICY_PATH})"
        ),
    )
    command.add_argument(
        "--registry", default=DEFAULT_REGISTRY_PATH,
        help=f"registry path, repo-relative (default: {DEFAULT_REGISTRY_PATH})",
    )
    command.add_argument(
        "--audit-config-digest", default=None,
        help="the consumer's current audit-configuration digest",
    )


def _add_drift_scope_arguments(command):
    """The corpus pair, plus how much of it a drift run declares."""
    _add_corpus_arguments(command)
    command.add_argument(
        "--mode", default=MODE_FULL, choices=list(MODES),
        help=f"how much of the inventory to declare (default: {MODE_FULL})",
    )
    command.add_argument(
        "--since", default=None,
        help="the commit a diff-scoped audit derives its scope from",
    )


def _positive(value):
    number = int(value)
    if number < 1:
        raise argparse.ArgumentTypeError(f"must be a positive integer, not {value}")
    return number


def _drift_audit(args):
    """The audit command's one call, plus reading the verdicts file it names."""
    verdicts = None
    if args.verdicts is not None:
        verdicts = load_verdicts(args.verdicts)
        if isinstance(verdicts, Invalid):
            return verdicts
    # `append` cannot have a non-empty default without appending to it, so the
    # engine's default boundary is applied here instead of in argparse.
    sources = tuple(args.evidence) if args.evidence else DEFAULT_EVIDENCE
    return audit_drift(
        args.repo, mode=args.mode, since=args.since, verdicts=verdicts,
        waivers=args.waivers, evidence_sources=sources,
        evidence_excluded=tuple(args.exclude_evidence or ()),
        evidence_commands=tuple(args.evidence_command or ()),
        registry_path=args.registry,
    )


def _parser():
    parser = argparse.ArgumentParser(
        prog="python3 -m doclifecycle",
        description="doc-lifecycle engine commands.",
    )
    # Every command answers this, so `main` never has to ask whether it was
    # defined: only `migration-draft` offers the flag that turns it on.
    parser.set_defaults(registry_only=False)
    commands = parser.add_subparsers(dest="command", required=True)

    inventory = commands.add_parser(
        "inventory",
        help="classify every document under the registry's declared roots",
        description=(
            "Emit the document inventory as JSON: every registered document with "
            "its kind and set, plus closed-world findings for documents under a "
            "declared root that no rule claims. Exits 1 if the registry is "
            "invalid, which invalidates the whole run."
        ),
    )
    _add_corpus_arguments(inventory)
    inventory.set_defaults(
        run=lambda args: build_inventory(args.repo, args.registry), render=None
    )

    segment = commands.add_parser(
        "segment",
        help="split one registered document into assertion units",
        description=(
            "Emit a document's assertion units as JSON: one unit per sentence, "
            "list item, or table row, each with the content digest that is its "
            "identity, and a flag saying whether its structure can carry a "
            "claim at all. A fixed parser with no model in the loop, so the "
            "same bytes always produce the same units. Exits 1 if the registry "
            "is invalid or the path is not a document in the inventory."
        ),
    )
    _add_corpus_arguments(segment)
    segment.add_argument(
        "--path", required=True,
        help="the document to segment, repository-relative; must be inventoried",
    )
    segment.set_defaults(
        run=lambda args: segment_document(args.repo, args.path, args.registry),
        render=None,
    )

    context = commands.add_parser(
        "context-index",
        help="index every document in the repository, and where each unit occurs",
        description=(
            "Emit the repository-wide context index as JSON: every inventoried "
            "document with its units, every distinct unit, and every place each "
            "unit occurs. This is the global view a bloat chunk worker queries "
            "instead of guessing about duplication or ownership from its own "
            "slice. Read-only and model-free. Exits 1 if the registry is invalid."
        ),
    )
    _add_corpus_arguments(context)
    context.set_defaults(
        run=lambda args: build_context_index(args.repo, args.registry), render=None
    )

    plan = commands.add_parser(
        "bloat-plan",
        help="partition the corpus into bounded bloat-audit chunks",
        description=(
            "Emit the chunk plan as JSON: every indexed document assigned to "
            "exactly one bounded chunk, each with a content-addressed id, so an "
            "unchanged chunk keeps its id across re-plans and an edited document "
            "re-keys only the chunk holding it. Exits 1 if the registry is "
            "invalid."
        ),
    )
    _add_corpus_arguments(plan)
    plan.add_argument(
        "--max-documents", type=_positive, default=DEFAULT_MAX_DOCUMENTS,
        help=f"documents per chunk (default: {DEFAULT_MAX_DOCUMENTS})",
    )
    plan.add_argument(
        "--max-units", type=_positive, default=DEFAULT_MAX_UNITS,
        help=f"assertion units per chunk (default: {DEFAULT_MAX_UNITS})",
    )
    plan.set_defaults(
        run=lambda args: plan_repository_chunks(
            args.repo, args.registry,
            max_documents=args.max_documents, max_units=args.max_units,
        ),
        render=None,
    )

    drift_plan = commands.add_parser(
        "drift-plan",
        help="declare which documents a drift audit would examine",
        description=(
            "Emit the drift audit's scope as JSON: every living and narrative "
            "document the audit declares, with the obligation its kind owes, "
            "and every document it deliberately leaves out with the reason. "
            "Deterministic — no model is involved — so a report's declared "
            "scope can be re-derived rather than trusted. A diff-scoped run "
            "(--mode incremental --since <commit>) declares only the documents "
            "the range changed or that name a path it changed."
        ),
    )
    _add_drift_scope_arguments(drift_plan)
    drift_plan.set_defaults(
        run=lambda args: plan_drift_audit(
            args.repo, mode=args.mode, since=args.since,
            registry_path=args.registry,
        ),
        render=None,
    )

    audit = commands.add_parser(
        "drift-audit",
        help="audit documentation against the code, and report what it examined",
        description=(
            "Emit a validated drift report as JSON. Living documents are judged "
            "from the verdicts a lane returns (--verdicts); narrative documents "
            "are checked here, deterministically, for a valid and honestly "
            "dated as-of anchor. A document that was not validly examined is "
            "named in the report's unexamined scopes, so the result is partial "
            "rather than clean. The audit writes nothing to the repository."
        ),
    )
    _add_drift_scope_arguments(audit)
    audit.add_argument(
        "--verdicts", default=None,
        help=(
            "path to the verdicts a lane returned for the declared living "
            "documents; without it none of them were examined"
        ),
    )
    audit.add_argument(
        "--waivers", default=None,
        help=(
            "repo-relative waivers file; accepted claims are annotated in the "
            "report, never removed from it"
        ),
    )
    audit.add_argument(
        "--evidence", action="append", default=None, metavar="GLOB",
        help="a source glob the run was permitted to consult (repeatable)",
    )
    audit.add_argument(
        "--exclude-evidence", action="append", default=None, metavar="GLOB",
        help="a source glob the run was not permitted to consult (repeatable)",
    )
    audit.add_argument(
        "--evidence-command", action="append", default=None, metavar="NAME",
        help=(
            "a local tool a verdict may be settled by running, named as a bare "
            "executable (repeatable). Empty by default: a run that declares no "
            "tool cannot cite one. The engine never runs it — the citation is "
            "for whoever checks the verdict"
        ),
    )
    audit.set_defaults(run=_drift_audit, render=None)

    validate = commands.add_parser(
        "validate-report",
        help="check a report against the contract, and optionally a repository",
        description=(
            "Validate a report's lineage, schema version, and result state, and "
            "emit the validated payload as JSON. With --repo, also check the "
            "lineage against the repository's current state. The verdict is one "
            "of clean, findings, partial, stale, or invalid, and is the exit "
            "code as well as the payload's status."
        ),
    )
    _add_report_arguments(validate)
    validate.set_defaults(render=None)

    draft = commands.add_parser(
        "migration-draft",
        help="infer a reviewable draft registry from a legacy install",
        description=(
            "Emit a draft registry inferred from the consumer's existing audit "
            "scope, waivers, scope record, narrative markers, and directory "
            "conventions — as glob rules, one per directory with per-file "
            "overrides only where a directory is not uniform, so the adoption "
            "review is a short diff rather than a per-file slog. Every rule "
            "carries the evidence it came from. --registry-only prints just the "
            "registry file's bytes, to redirect into the path being reviewed. "
            "Writes nothing. Exits 1 if the legacy state cannot be read or no "
            "documentation root can be inferred."
        ),
    )
    _add_corpus_arguments(draft)
    draft.add_argument(
        "--root", action="append", default=None, metavar="PATH",
        help=(
            "a documentation root, repeatable; declaring any replaces inference "
            "entirely"
        ),
    )
    draft.add_argument(
        "--registry-only", action="store_true",
        help="print the drafted registry file instead of the draft payload",
    )
    draft.set_defaults(
        run=lambda args: draft_registry(
            args.repo, roots=args.root, registry_path=args.registry,
        ),
        render=None,
    )

    dry_run = commands.add_parser(
        "migration-dry-run",
        help="state what adopting the landed registry would cost",
        description=(
            "Emit the migration dry run as JSON: the versions the migration "
            "spans, the audit obligation each document kind takes on, which "
            "legacy waivers re-key cleanly onto assertion-unit identity and "
            "which need re-waiving, which old artifacts are not carried across "
            "and how to regenerate them, and which consumer files are preserved "
            "untouched. Writes nothing. Exits 1 when the migration is blocked — "
            "including when any document under a declared root is unclassified, "
            "which is named rather than bucketed."
        ),
    )
    _add_corpus_arguments(dry_run)
    dry_run.add_argument(
        "--waivers", default=WAIVERS_PATH,
        help=f"repo-relative legacy waivers file (default: {WAIVERS_PATH})",
    )
    dry_run.add_argument(
        "--installed-version", default=INSTALLED_VERSION_PATH,
        help=(
            f"repo-relative version lockfile the migration reads its from-version "
            f"out of (default: {INSTALLED_VERSION_PATH})"
        ),
    )
    dry_run.set_defaults(
        run=lambda args: dry_run_migration(
            args.repo, registry_path=args.registry, waivers=args.waivers,
            installed_version=args.installed_version,
        ),
        render=None,
    )

    render = commands.add_parser(
        "render-report",
        help="render a validated report as Markdown",
        description=(
            "Validate a report and print it as Markdown. An invalid report "
            "renders nothing at all — malformed content must not reach a PR "
            "body or a CI summary. The exit code is the verdict, as for "
            "validate-report."
        ),
    )
    _add_report_arguments(render)
    render.set_defaults(render=_render_report)

    reconcile_command = commands.add_parser(
        "reconcile-report",
        help="group a report's records by what they would change",
        description=(
            "Emit the reconciliation as JSON: every record in the report "
            "assigned to exactly one group, with the relations that put it "
            "there and the selection rule the group carries. An `atomic` group "
            "is approved whole or not at all; an `exclusive` group holds "
            "records that contradict and may not be approved at all. "
            "Deterministic and model-free. Exits 1 if the report is invalid."
        ),
    )
    _add_report_arguments(reconcile_command)
    reconcile_command.set_defaults(run=_reconcile_report, render=None)

    mint = commands.add_parser(
        "mint-approval",
        help="mint an approval set from selected record digests",
        description=(
            "Emit an approval set as JSON: the selected record digests, the "
            "report lineage they came from, and the enumerated allowed "
            "mutation scope, bound under one digest. The selection must "
            "respect the report's reconciliation groups, every target must "
            "authorize as documentation inside a declared root, and every "
            "target's text must still be what the record was written about. "
            "With --out the artifact is also written to a file — never inside "
            "the repository's tracked or trackable state."
        ),
    )
    mint.add_argument(
        "--report", required=True, help="path to the report JSON to select from"
    )
    mint.add_argument(
        "--repo", required=True,
        help="the repository the approval authorizes changes to",
    )
    mint.add_argument(
        "--record", action="append", required=True, metavar="DIGEST",
        help="a record digest to approve (repeatable)",
    )
    mint.add_argument(
        "--minter", required=True,
        help="who is approving: a person, or the name of an auto-apply policy",
    )
    mint.add_argument(
        "--minter-kind", default=MINTER_HUMAN, choices=list(MINTER_KINDS),
        help=f"what kind of minter that is (default: {MINTER_HUMAN})",
    )
    mint.add_argument(
        "--registry", default=DEFAULT_REGISTRY_PATH,
        help=f"registry path, repo-relative (default: {DEFAULT_REGISTRY_PATH})",
    )
    mint.add_argument(
        "--audit-config-digest", default=None,
        help="the consumer's current audit-configuration digest",
    )
    mint.add_argument(
        "--out", default=None,
        help=(
            "also write the approval set here; refused for any path git would "
            "track, since an approval set is never repository state"
        ),
    )
    mint.set_defaults(run=_mint_approval, render=None)

    validate_approval = commands.add_parser(
        "validate-approval",
        help="check an approval set against its report and the repository",
        description=(
            "Validate an approval set and emit it as JSON. With --report, "
            "check the selection against the records it names; with --repo, "
            "check it against the repository — base commit, rules, "
            "configuration, allowed scope, and every selected record's target "
            "text. The verdict is clean, stale, or invalid, and is the exit "
            "code as well as the payload's status."
        ),
    )
    _add_approval_arguments(validate_approval)
    validate_approval.set_defaults(render=None)

    apply_plan = commands.add_parser(
        "apply-plan",
        help="execute an edit plan under its approval set — the one write path",
        description=(
            "Validate the approval set against its report and the repository, "
            "validate the edit plan against the approval set, verify every "
            "exact preimage, apply the operations in deterministic order, and "
            "check the complete working-tree diff against the approval set's "
            "allowed mutation scope. Any problem leaves the tree "
            "byte-identical; a stale approval refuses and names every field "
            "that moved. Reapplying the same approval set is a no-op. Nothing "
            "is staged or committed — change approval is a person's."
        ),
    )
    apply_plan.add_argument(
        "--plan", required=True, help="path to the edit-plan JSON to execute"
    )
    apply_plan.add_argument(
        "--approval", required=True,
        help="path to the approval-set JSON that authorizes it",
    )
    apply_plan.add_argument(
        "--repo", default=".",
        help="repository root (default: the current directory)",
    )
    apply_plan.add_argument(
        "--report", required=True,
        help=(
            "the report the approval set was minted from — required, so the "
            "selection is checked against the records it names rather than "
            "against public repository state anyone could re-derive"
        ),
    )
    apply_plan.add_argument(
        "--registry", default=DEFAULT_REGISTRY_PATH,
        help=f"registry path, repo-relative (default: {DEFAULT_REGISTRY_PATH})",
    )
    apply_plan.add_argument(
        "--audit-config-digest", default=None,
        help="the consumer's current audit-configuration digest",
    )
    apply_plan.add_argument(
        "--expected-digest", default=None,
        help=(
            "the Doc-Lifecycle-Approval trailer of the change being applied; "
            "supply it to bind the approval file to the change that claims it"
        ),
    )
    apply_plan.set_defaults(run=_apply_plan, render=None)

    render_approval = commands.add_parser(
        "render-approval",
        help="render an approval set as the summary that travels with a change",
        description=(
            "Validate an approval set and print it as Markdown for a PR body, "
            "or as git trailers for a commit message (--trailers). An invalid "
            "approval set renders nothing at all. The exit code is the "
            "verdict, as for validate-approval."
        ),
    )
    _add_approval_arguments(render_approval)
    render_approval.add_argument(
        "--trailers", action="store_true",
        help="print git trailers for a commit message instead of Markdown",
    )
    render_approval.set_defaults(render=_render_approval)

    eligibility = commands.add_parser(
        "policy-eligibility",
        help="decide which of a report's records an auto-apply policy admits",
        description=(
            "Emit one decision per record: the eligibility class that admitted "
            "it, or the typed reason it was refused. Read-only, and `ok` even "
            "when nothing is eligible — a report of bloat findings is a run "
            "whose answer is 'a person decides all of these'. An absent policy "
            "file is a refusal, never a permissive default."
        ),
    )
    _add_policy_arguments(eligibility)
    eligibility.set_defaults(run=_policy_eligibility, render=None)

    policy_mint = commands.add_parser(
        "policy-mint",
        help="mint an approval set for everything the policy rules eligible",
        description=(
            "Mint an approval set whose selection is derived from the policy's "
            "own decisions — there is no flag that names a record — through "
            "the same mint_approval_set a human dispatch uses, with the policy "
            "named as the minter. Refuses policy-nothing-eligible, naming "
            "every record's reason, when the policy admits nothing."
        ),
    )
    _add_policy_arguments(policy_mint)
    policy_mint.add_argument(
        "--out", default=None,
        help=(
            "also write the approval set here; refused for any path git would "
            "track, as mint-approval's --out is"
        ),
    )
    policy_mint.set_defaults(run=_policy_mint, render=None)

    return parser


def _explain(result):
    """State the outcome and its reason on the run surface.

    A CI log or terminal reader must not have to parse the payload to learn why
    a run is invalid, stale, or partial.

    A location is quoted, exactly as the messages quote what they echo: it can
    be a field name off an artifact this engine did not write, and a raw one
    carrying newlines would let that artifact write its own lines onto the run
    surface — where a forged "clean" is read as a verdict.
    """
    if isinstance(result, Invalid):
        for problem in result.problems:
            where = f" [{problem.location!r}]" if problem.location else ""
            print(f"{problem.code}: {problem.message}{where}", file=sys.stderr)
    else:
        # Every artifact that can go stale says which field moved — a report
        # and an approval set alike, since both reach a reader as an exit code
        # first and a payload second.
        for reason in getattr(result, "stale_reasons", ()):
            print(f"{reason.code}: {reason.message}", file=sys.stderr)
        if isinstance(result, Report) and result.status == STATE_PARTIAL:
            for entry in result.incomplete:
                print(
                    f"not-examined: {entry.scope} — {entry.reason}",
                    file=sys.stderr,
                )


def main(argv=None):
    args = _parser().parse_args(argv)
    result = args.run(args)
    if args.registry_only:
        # The registry file's exact bytes, so the door's output can be
        # redirected to the path the human reviews. An invalid draft prints
        # nothing, for the same reason an invalid report renders nothing.
        if result.status != STATE_INVALID:
            print(result.registry_text, end="")
    elif args.render:
        # Rendering takes validated typed objects only, so an invalid result
        # prints nothing: there is no rendered form of a report that failed.
        if result.status != STATE_INVALID:
            print(args.render(result, args))
    else:
        # ensure_ascii=False so a CI log shows the message a human wrote;
        # digests are taken over digest.canonical(), not over this rendering.
        # allow_nan=False so the engine can never emit something no strict JSON
        # parser will read — validation rejects non-finite numbers, and this
        # makes any gap in that a loud failure rather than corrupt output.
        print(json.dumps(
            result.to_dict(), indent=2, ensure_ascii=False, allow_nan=False
        ))
    _explain(result)
    return EXIT_CODES[result.status]
