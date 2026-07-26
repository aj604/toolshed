"""The `python3 -m doclifecycle` commands.

Deliberately thin: a command parses argv, calls one library function, prints its
`to_dict()` payload, and maps the result state to an exit code. No command holds
logic of its own, so an interactive import and a CI invocation cannot disagree.

Exit codes: 0 the run completed (findings are data, not a gate), 1 the run is
invalid, 2 a usage error.
"""

import argparse
import json
import sys

from .inventory import DEFAULT_REGISTRY_PATH, build_inventory
from .results import STATUS_INVALID


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
    inventory.add_argument(
        "--repo", default=".", help="repository root (default: the current directory)"
    )
    inventory.add_argument(
        "--registry",
        default=DEFAULT_REGISTRY_PATH,
        help=f"registry path, repo-relative (default: {DEFAULT_REGISTRY_PATH})",
    )
    inventory.set_defaults(run=lambda args: build_inventory(args.repo, args.registry))
    return parser


def main(argv=None):
    args = _parser().parse_args(argv)
    result = args.run(args)
    # ensure_ascii=False so a CI log shows the message a human wrote; digests are
    # taken over digest.canonical(), not over this rendering.
    print(json.dumps(result.to_dict(), indent=2, ensure_ascii=False))
    if result.status == STATUS_INVALID:
        # Say why on the run surface too: a CI log or terminal reader must not
        # have to parse the payload to learn what went wrong.
        for problem in result.problems:
            where = f" [{problem.location}]" if problem.location else ""
            print(f"{problem.code}: {problem.message}{where}", file=sys.stderr)
        return 1
    return 0
