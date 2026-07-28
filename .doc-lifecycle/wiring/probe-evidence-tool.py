#!/usr/bin/env python3
"""The audit lane's declared-tool probe — Tier-2 evidence without a wider grant.

A drift verdict may cite `evidence.command` instead of `evidence.source`
(aj604/toolshed#115), but only for a tool the run *declared*: the report's
`evidence_boundary.commands` names the bare executables, and the engine refuses
a citation outside it (`drift-evidence-outside-boundary`). Something has to let
the model job actually reach those tools, and the obvious route — adding `gh`
to the model step's `--allowedTools` — is not available: those patterns are
prefix-matched, so `Bash(gh *)` grants `gh api` and `gh pr list` alongside
`gh <sub> --help`, i.e. GitHub API surface declared for a job that is
deliberately token-free.

This script is the narrow route instead (aj604/toolshed#118). It runs under the
model job's *existing* `Bash(python3 *)` allowance, so no tool grant widens at
all, and what it can reach is enumerable in two directions:

  * **Which programs** — only those named in `.doc-lifecycle/evidence-tools.json`,
    a consumer-owned file this repo's wiring never overwrites. Empty (or absent)
    means the lane stays tool-free, which is the default.
  * **How** — only as a `--help`/`--version` read. Every token between the tool
    and that final flag must be a bare subcommand word, so there is no path to
    `gh api`, no flag carrying a value, and nothing for a shell to interpret
    (the tool is exec'd directly, never through a shell).

The same config feeds `--evidence-command`, so the boundary the report declares
and the tools this script will run are one list, not two that can drift apart:
`declared --flags` renders the engine arguments the audit step passes.

Usage:
    probe-evidence-tool.py declared [--config PATH] [--flags]
    probe-evidence-tool.py run [--config PATH] TOOL [SUBCOMMAND...] --help|--version

`run` prints the citation a reader re-runs — the tool's own command line, never
this wrapper — followed by the tool's output.

Exit status:
    0  the probe ran and its output is above the fold
    1  the environment could not answer (no config that parses, tool not
       installed, tool rejected the probe, probe timed out)
    2  refused (the tool is not declared, or the invocation is not a
       --help/--version read)

Every non-zero exit names its reason on stderr with a typed code, so an
unattended run's log says which of the two it was.
"""

import argparse
import json
import os
import pathlib
import re
import shutil
import subprocess
import sys

# The consumer's declaration, owned by whoever installed the lane. Same status
# as audit-scope.json and drift-waivers.json: seeded when absent, never
# overwritten by an upgrade (see scheduling-doc-sync/scripts/apply-upgrade.py).
DEFAULT_CONFIG = os.path.join(".doc-lifecycle", "evidence-tools.json")

# What the engine accepts in `evidence_boundary.commands`
# (doclifecycle/report.py's EXECUTABLE_NAME). Checked here too, so a config
# typo is named at the config rather than surfacing as a report-shape refusal
# several steps later.
EXECUTABLE_NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._+-]*$")

# A subcommand word, and nothing else: no leading dash (so no flags, hence no
# flag values), no separator, no whitespace, nothing a shell would read.
SUBCOMMAND_WORD = re.compile(r"^[a-z0-9][a-z0-9-]*$")

# The only two things this script will ask a program to do. Both are reads of
# the program's own interface — the Tier-2 question the audit lane needs
# settled ("does this command support that flag?") — and neither reaches a
# network, a repository, or an account.
PROBES = ("--help", "--version")

# Nothing credential-shaped is handed to a probed program. The model job holds
# no token at all (`tests/scripts/workflow-permissions_test.py` asserts it), so
# this is belt-and-braces rather than the boundary — but "with no credential in
# its environment" is part of what makes the reachable surface enumerable.
CREDENTIAL_MARKERS = ("TOKEN", "SECRET", "PASSWORD", "PASSWD", "KEY",
                      "CREDENTIAL", "COOKIE", "SESSION")

TIMEOUT_SECONDS = 60


class Refused(Exception):
    """The invocation is outside what this script will run. Exit 2."""


class Unanswerable(Exception):
    """The environment could not answer the probe. Exit 1."""


def probe_env(base):
    """The environment a probed tool runs in: no credential-shaped variable."""
    return {name: value for name, value in base.items()
            if not any(marker in name.upper() for marker in CREDENTIAL_MARKERS)}


def declared_tools(config_path):
    """The executables this install declared, in the order it declared them."""
    path = pathlib.Path(config_path)
    if not path.is_file():
        # A consumer who declared nothing gets the tool-free lane, which is the
        # default and not an error: the audit step renders no
        # --evidence-command, the report's boundary declares no command, and a
        # verdict citing one is refused by the engine.
        return []
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as e:
        raise Unanswerable(f"could not read {path} (evidence-tools.json): {e}")
    if not isinstance(raw, dict) or not isinstance(raw.get("tools", []), list):
        raise Unanswerable(
            f'{path} must be an object with a "tools" list of bare executable '
            f"names")
    tools = raw.get("tools", [])
    for value in tools:
        if not isinstance(value, str) or not EXECUTABLE_NAME.fullmatch(value):
            raise Unanswerable(
                f"{path} declares {value!r}, which is not a bare executable "
                f"name matching {EXECUTABLE_NAME.pattern} — the boundary names "
                f"programs, never command lines")
    return tools


def citation_for(argv, tools):
    """The command line a reader re-runs, or a refusal saying why there is none."""
    if len(argv) < 2:
        raise Refused(
            "not-a-probe-invocation: a probe is a tool, any subcommand words, "
            f"and one of {list(PROBES)} — got {argv}")
    tool, words, probe = argv[0], argv[1:-1], argv[-1]
    if tool not in tools:
        raise Refused(
            f"tool-not-declared: {tool!r} is not in this install's declared "
            f"evidence tools ({tools}) — declare it in evidence-tools.json, "
            f"which is also what the report's evidence boundary publishes")
    if probe not in PROBES:
        raise Refused(
            f"not-a-probe-invocation: {probe!r} is not one of {list(PROBES)} — "
            f"this script reads a program's own interface and runs nothing else")
    for word in words:
        if not SUBCOMMAND_WORD.fullmatch(word):
            raise Refused(
                f"not-a-probe-invocation: {word!r} is not a subcommand word "
                f"({SUBCOMMAND_WORD.pattern}) — a probe carries no flags, no "
                f"values, and no path")
    return " ".join(argv)


def probe(argv, tools):
    """Run one declared probe. Returns (citation, output)."""
    citation = citation_for(argv, tools)
    binary = shutil.which(argv[0])
    if binary is None:
        raise Unanswerable(
            f"tool-not-installed: {argv[0]!r} is declared but not on PATH here "
            f"— nothing this run could have cited it for")
    try:
        # shell=False and an argv list: the words above were checked to be
        # shell-free anyway, and this way there is no shell to check against.
        result = subprocess.run(
            [binary, *argv[1:]], capture_output=True, text=True,
            timeout=TIMEOUT_SECONDS, env=probe_env(os.environ),
            stdin=subprocess.DEVNULL)
    except subprocess.TimeoutExpired:
        raise Unanswerable(
            f"probe-timed-out: {citation!r} did not answer within "
            f"{TIMEOUT_SECONDS}s")
    output = result.stdout + result.stderr
    if result.returncode != 0:
        raise Unanswerable(
            f"probe-failed: {citation!r} exited {result.returncode} — it "
            f"settled nothing, so there is no citation to make\n{output}")
    return citation, output


def main():
    parser = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="mode", required=True)

    listing = sub.add_parser(
        "declared", help="print the executables this install declared")
    listing.add_argument("--config", default=DEFAULT_CONFIG)
    listing.add_argument(
        "--flags", action="store_true",
        help="render them as drift-audit --evidence-command arguments")

    # Parsed by hand rather than by argparse: the probe's own `--help` belongs
    # to the tool being probed, and argparse would answer it here instead.
    runner = sub.add_parser(
        "run", add_help=False,
        help="run one declared tool as a --help/--version read")
    runner.add_argument("--config", default=DEFAULT_CONFIG)
    runner.add_argument("argv", nargs=argparse.REMAINDER)

    args = parser.parse_args()
    try:
        tools = declared_tools(args.config)
        if args.mode == "declared":
            if args.flags:
                print(" ".join(f"--evidence-command {t}" for t in tools))
            else:
                for tool in tools:
                    print(tool)
            return 0
        citation, output = probe(args.argv, tools)
        print(f"citation: {citation}")
        print(output)
        return 0
    except Refused as e:
        print(f"refused: {e}", file=sys.stderr)
        return 2
    except Unanswerable as e:
        print(f"error: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
