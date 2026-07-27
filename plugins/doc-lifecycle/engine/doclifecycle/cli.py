"""The `python3 -m doclifecycle` commands.

Deliberately thin: a command parses argv, calls one library function, prints its
`to_dict()` payload, and maps the result state to an exit code. No command holds
logic of its own, so an interactive import and a CI invocation cannot disagree.

Exit codes name the result state, so a workflow can gate without parsing JSON:
0 the run completed and its scope was examined (`ok`, `clean`, `findings` —
findings are data, not a gate); 1 invalid; 2 a usage error; 3 stale; 4 partial.
`inventory` reaches only 0, 1, and 2, as it always has; 3 and 4 belong to the
report states.
"""

import argparse
import json
import sys

from .bloat import (
    DEFAULT_MAX_DOCUMENTS,
    DEFAULT_MAX_UNITS,
    plan_repository_chunks,
)
from .context import build_context_index
from .inventory import DEFAULT_REGISTRY_PATH, build_inventory
from .render import render_report
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


def _positive(value):
    number = int(value)
    if number < 1:
        raise argparse.ArgumentTypeError(f"must be a positive integer, not {value}")
    return number


def _parser():
    parser = argparse.ArgumentParser(
        prog="python3 -m doclifecycle",
        description="doc-lifecycle engine commands.",
    )
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
        run=lambda args: build_inventory(args.repo, args.registry), render=False
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
        render=False,
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
        run=lambda args: build_context_index(args.repo, args.registry), render=False
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
        render=False,
    )

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
    validate.set_defaults(render=False)

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
    render.set_defaults(render=True)

    return parser


def _explain(result):
    """State the outcome and its reason on the run surface.

    A CI log or terminal reader must not have to parse the payload to learn why
    a run is invalid, stale, or partial.
    """
    if isinstance(result, Invalid):
        for problem in result.problems:
            where = f" [{problem.location}]" if problem.location else ""
            print(f"{problem.code}: {problem.message}{where}", file=sys.stderr)
    elif isinstance(result, Report):
        for reason in result.stale_reasons:
            print(f"{reason.code}: {reason.message}", file=sys.stderr)
        if result.status == STATE_PARTIAL:
            for entry in result.incomplete:
                print(
                    f"not-examined: {entry.scope} — {entry.reason}",
                    file=sys.stderr,
                )


def main(argv=None):
    args = _parser().parse_args(argv)
    result = args.run(args)
    if args.render:
        # Rendering takes validated typed objects only, so an invalid result
        # prints nothing: there is no rendered form of a report that failed.
        if result.status != STATE_INVALID:
            print(render_report(result))
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
