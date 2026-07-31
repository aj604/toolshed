#!/usr/bin/env python3
"""Trusted prompt, extraction, validation, and retry seam for doc-bloat-audit.

The scheduled model has no command or file-mutation tools. ``prepare`` renders
the complete coordinator work order before the model runs. ``collect`` consumes
the pinned claude-code-action's documented ``structured_output``, validates
each returned chunk with the detecting-doc-bloat public seam, and optionally
renders the one retry work order. Invalid or missing chunks never become files,
so deterministic completion assembly records them as partial truth.
"""

import argparse
import json
import os
import subprocess
import sys
import tempfile


ACTION_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": ["schema_version", "chunks"],
    "properties": {
        "schema_version": {"type": "integer", "enum": [1]},
        "chunks": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": ["id", "result_json"],
                "properties": {
                    "id": {"type": "string"},
                    "result_json": {"type": "string"},
                },
            },
        },
    },
}


def die(message):
    print(message, file=sys.stderr)
    raise SystemExit(2)


def load_json(path, label):
    try:
        with open(path, encoding="utf-8") as stream:
            return json.load(stream)
    except (OSError, json.JSONDecodeError, UnicodeDecodeError) as exc:
        die(f"error: cannot read {label} {path}: {exc}")


def manifest_state(path):
    payload = load_json(path, "manifest")
    if not isinstance(payload, dict):
        die("error: manifest must be an object")
    chunks = payload.get("chunks")
    pending = payload.get("pending")
    if not isinstance(chunks, list) or not isinstance(pending, list):
        die("error: manifest must carry chunks and pending arrays")
    ids = [chunk.get("id") for chunk in chunks if isinstance(chunk, dict)]
    if (len(ids) != len(chunks) or any(not isinstance(cid, str) for cid in ids)
            or len(ids) != len(set(ids))):
        die("error: manifest chunk ids must be unique strings")
    if (any(not isinstance(cid, str) for cid in pending)
            or len(pending) != len(set(pending))
            or not set(pending).issubset(ids)):
        die("error: manifest pending ids must be unique known chunk ids")
    return payload, pending


def planner_output(planner, root, manifest, option, chunk_id):
    result = subprocess.run(
        [sys.executable, planner, "--root", root, "--manifest", manifest,
         option, chunk_id],
        capture_output=True, text=True,
    )
    if result.returncode != 0:
        detail = result.stderr.strip() or result.stdout.strip()
        die(f"error: planner could not render {option} for {chunk_id}: "
            f"{detail or 'unknown failure'}")
    return result.stdout


def coordinator_prompt(manifest, planner, root, prompts_dir, chunk_ids,
                       retry=False):
    work = []
    os.makedirs(prompts_dir, exist_ok=True)
    for chunk_id in chunk_ids:
        task_prompt = planner_output(
            planner, root, manifest, "--emit-readonly-prompt", chunk_id,
        ).rstrip()
        turns_text = planner_output(
            planner, root, manifest, "--emit-turns", chunk_id,
        ).strip()
        try:
            turns = int(turns_text)
        except ValueError:
            die(f"error: planner returned a non-integer turn budget for "
                f"{chunk_id}: {turns_text!r}")
        if turns < 1:
            die(f"error: planner returned a non-positive turn budget for "
                f"{chunk_id}: {turns}")
        prompt_path = os.path.abspath(os.path.join(
            prompts_dir, chunk_id + ".md",
        ))
        write_text(prompt_path, task_prompt + "\n")
        work.append(
            f'<task id="{chunk_id}" max_turns="{turns}" '
            f'prompt_path="{prompt_path}">\n'
            f"max_turns: {turns}\n</task>"
        )

    retry_line = (
        "This is the single fresh retry for every task below; do not retry a "
        "second time."
        if retry else
        "This is the first attempt for every task below."
    )
    return f"""\
You are the read-only coordinator for a scheduled documentation-bloat audit.
Use only Task, Read, Grep, and Glob. Do not inspect or judge repository
documents yourself, and never author, repair, or infer a worker result.
{retry_line}

Dispatch one fresh Task for every <task> below. Read its prompt_path immediately
before dispatch and pass that file's contents verbatim as the Task prompt. Set
that Task's max_turns to the element's max_turns value. Chunks are independent:
read and dispatch them in parallel waves of several, not serially. Each Task's
final response is one JSON chunk-result object.

After all Tasks return, respond only through the required structured-output
schema: schema_version must be 1 and chunks must contain one
{{"id": <task id>, "result_json": <the Task's exact response encoded as a
JSON string>}} entry per successful Task. Omit a Task that failed to return an
object. Never repair or reinterpret a response; the trusted post-model
collector parses and validates every seam.

{os.linesep.join(work)}
"""


def write_text(path, contents):
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    with open(path, "w", encoding="utf-8") as stream:
        stream.write(contents)


def append_output(path, key, value):
    if not path:
        return
    with open(path, "a", encoding="utf-8") as stream:
        stream.write(f"{key}={value}\n")


def prepare(args):
    _manifest, pending = manifest_state(args.manifest)
    write_text(
        args.out,
        coordinator_prompt(
            args.manifest, args.planner, args.root, args.prompts_dir, pending,
        ),
    )
    append_output(
        args.github_output, "schema",
        json.dumps(ACTION_SCHEMA, separators=(",", ":"), sort_keys=True),
    )
    print(f"prepared {len(pending)} read-only task(s)")


def valid_chunk(path, manifest, validator):
    if not os.path.isfile(path):
        return False
    result = subprocess.run(
        [sys.executable, validator, "--chunk", path, "--manifest", manifest],
        capture_output=True, text=True,
    )
    return result.returncode == 0


def outstanding_ids(manifest, pending, results_dir, validator):
    return [
        chunk_id for chunk_id in pending
        if not valid_chunk(
            os.path.join(results_dir, chunk_id + ".json"), manifest, validator,
        )
    ]


def parse_structured_output(raw, expected):
    """Return id -> candidate, or no candidates when the action seam is bad."""
    try:
        payload = json.loads(raw)
    except (TypeError, json.JSONDecodeError):
        print("warning: model structured_output was absent or malformed",
              file=sys.stderr)
        return {}
    if (not isinstance(payload, dict)
            or set(payload) != {"schema_version", "chunks"}
            or payload.get("schema_version") != 1
            or not isinstance(payload.get("chunks"), list)):
        print("warning: model structured_output failed its envelope contract",
              file=sys.stderr)
        return {}

    candidates = {}
    for item in payload["chunks"]:
        if (not isinstance(item, dict) or set(item) != {"id", "result_json"}
                or not isinstance(item.get("id"), str)
                or not isinstance(item.get("result_json"), str)
                or item["id"] not in expected or item["id"] in candidates):
            print("warning: model structured_output carried an unknown, duplicate, "
                  "or malformed chunk entry", file=sys.stderr)
            return {}
        try:
            result = json.loads(item["result_json"])
        except json.JSONDecodeError:
            print(f"warning: model returned malformed JSON for {item['id']}",
                  file=sys.stderr)
            continue
        if not isinstance(result, dict):
            print(f"warning: model returned a non-object for {item['id']}",
                  file=sys.stderr)
            continue
        candidates[item["id"]] = result
    return candidates


def accept_candidates(candidates, manifest, results_dir, validator):
    os.makedirs(results_dir, exist_ok=True)
    accepted = []
    for chunk_id, candidate in candidates.items():
        fd, temporary = tempfile.mkstemp(
            prefix=f".{chunk_id}.", suffix=".json", dir=results_dir,
        )
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as stream:
                json.dump(candidate, stream, indent=2, sort_keys=True)
                stream.write("\n")
            if not valid_chunk(temporary, manifest, validator):
                print(f"warning: rejected invalid chunk result {chunk_id}",
                      file=sys.stderr)
                continue
            os.replace(temporary, os.path.join(results_dir, chunk_id + ".json"))
            temporary = None
            accepted.append(chunk_id)
        finally:
            if temporary:
                try:
                    os.unlink(temporary)
                except FileNotFoundError:
                    pass
    return accepted


def collect(args):
    _manifest, pending = manifest_state(args.manifest)
    before = outstanding_ids(
        args.manifest, pending, args.results_dir, args.validator,
    )
    raw = os.environ.get(args.structured_output_env, "")
    candidates = parse_structured_output(raw, set(before))
    accepted = accept_candidates(
        candidates, args.manifest, args.results_dir, args.validator,
    )
    remaining = outstanding_ids(
        args.manifest, pending, args.results_dir, args.validator,
    )

    retry = bool(remaining and args.retry_prompt)
    append_output(args.github_output, "retry", str(retry).lower())
    append_output(args.github_output, "remaining", str(len(remaining)))
    if retry:
        if not args.planner or not args.prompts_dir:
            die("error: --retry-prompt requires --planner and --prompts-dir")
        write_text(
            args.retry_prompt,
            coordinator_prompt(
                args.manifest, args.planner, args.root, args.prompts_dir,
                remaining, retry=True,
            ),
        )
    print(f"accepted {len(accepted)} chunk(s); {len(remaining)} remain incomplete")


def build_parser():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)

    prep = commands.add_parser("prepare")
    prep.add_argument("--manifest", required=True)
    prep.add_argument("--planner", required=True)
    prep.add_argument("--root", required=True)
    prep.add_argument("--out", required=True)
    prep.add_argument("--prompts-dir", required=True)
    prep.add_argument("--github-output")

    take = commands.add_parser("collect")
    take.add_argument("--manifest", required=True)
    take.add_argument("--results-dir", required=True)
    take.add_argument("--validator", required=True)
    take.add_argument(
        "--structured-output-env", default="MODEL_STRUCTURED_OUTPUT",
    )
    take.add_argument("--github-output")
    take.add_argument("--retry-prompt")
    take.add_argument("--planner")
    take.add_argument("--prompts-dir")
    take.add_argument("--root", default=os.getcwd())
    return parser


def main():
    args = build_parser().parse_args()
    if args.command == "prepare":
        prepare(args)
    else:
        collect(args)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
