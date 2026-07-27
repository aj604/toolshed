#!/usr/bin/env python3
"""Harness for the shadow-mode parity gate's cycle (aj604/toolshed#76).

Not plugin content and not a test — the recorded scaffolding that made one
shadow cycle reproducible. `doc-audit.yml` does the same three things in CI
(plan the scope, hand each document to a model, fold the answers into one
verdicts file); here they are separated so the cycle can be run locally,
recorded, and re-run.

    shadow-cycle.py digest --repo .
        A sha256 over every file in the worktree except .git/ and whatever the
        repository's own ignore rules exclude, as sorted "mode path sha256"
        lines. The before/after evidence for the gate's G1b criterion: the new
        lane must leave the tree byte-identical.

        The ignore rules are not a convenience. CPython writes
        `engine/doclifecycle/__pycache__/*.pyc` the moment anything imports the
        engine, and a `.pyc` embeds its source's mtime — so `git checkout` of an
        unchanged source file re-keys 16 files that no process wrote to the
        repository. Counting those measured the instrument, not the lane.

    shadow-cycle.py slices --repo . --registry <path> --out <dir>
        One task file per declared living document, each carrying that
        document's deterministic segmentation, for a model worker to answer.
        Also writes segments.json, the whole-run segmentation the comparison
        reads. Everything lands in --out, which must be outside the repository.

    shadow-cycle.py merge --slices <dir> --repair <dir> --out <path>
        Fold both rounds' answers into the one verdicts file
        `drift-audit --verdicts` consumes. Later rounds win per unit — that is
        what a repair round means. Answers naming a digest the document does
        not contain, and second answers for a unit already covered, are
        dropped: neither carries information, and the engine refuses the whole
        document over either.
"""

import argparse
import hashlib
import json
import os
import subprocess
import sys

ENGINE = os.path.join("plugins", "doc-lifecycle", "engine", "doc-lifecycle.py")


def engine(repo, *argv):
    result = subprocess.run(
        [sys.executable, os.path.join(repo, ENGINE), *argv],
        capture_output=True, text=True, cwd=repo,
    )
    if result.returncode not in (0,):
        sys.exit(f"engine {argv[0]} exited {result.returncode}: {result.stderr}")
    return json.loads(result.stdout)


def ignored(repo):
    """The paths the repository's own ignore rules exclude, as a prefix set."""
    result = subprocess.run(
        ["git", "ls-files", "--others", "--ignored", "--exclude-standard",
         "--directory"],
        capture_output=True, text=True, cwd=repo,
    )
    return tuple(line.rstrip("/") for line in result.stdout.splitlines() if line)


def digest(repo):
    skip = ignored(repo)
    entries = []
    for root, dirnames, filenames in os.walk(repo):
        dirnames[:] = sorted(
            d for d in dirnames
            if d != ".git"
            and os.path.relpath(os.path.join(root, d), repo) not in skip
        )
        for name in sorted(filenames):
            path = os.path.join(root, name)
            relative = os.path.relpath(path, repo)
            if relative in skip:
                continue
            info = os.lstat(path)
            if os.path.islink(path):
                body = os.readlink(path).encode()
            else:
                with open(path, "rb") as fh:
                    body = fh.read()
            entries.append(
                f"{info.st_mode:o} {relative} {hashlib.sha256(body).hexdigest()}"
            )
    listing = "\n".join(entries)
    return hashlib.sha256(listing.encode()).hexdigest(), len(entries)


def slices(repo, registry, out):
    plan = engine(repo, "drift-plan", "--repo", ".", "--registry", registry,
                  "--mode", "full")
    os.makedirs(out, exist_ok=True)
    documents = []
    for document in plan["documents"]:
        if document["obligation"] != "assertions":
            continue
        segmentation = engine(repo, "segment", "--repo", ".",
                              "--registry", registry,
                              "--path", document["path"])
        documents.append({"path": document["path"],
                          "units": segmentation["units"]})
        name = document["path"].replace("/", "__") + ".json"
        with open(os.path.join(out, name), "w", encoding="utf-8") as fh:
            json.dump({"path": document["path"],
                       "units": segmentation["units"]}, fh, indent=2)
    with open(os.path.join(out, "segments.json"), "w", encoding="utf-8") as fh:
        json.dump({"documents": documents}, fh, indent=2)
    print(f"{len(documents)} living documents, "
          f"{sum(len(d['units']) for d in documents)} units")


def _answers(directory):
    out = {}
    if not directory or not os.path.isdir(directory):
        return out
    for name in sorted(os.listdir(directory)):
        if not name.endswith(".answer.json"):
            continue
        with open(os.path.join(directory, name), encoding="utf-8") as fh:
            answer = json.load(fh)
        out.setdefault(answer["path"], []).extend(answer.get("verdicts", []))
    return out


def merge(slices_dir, repair_dir, out):
    with open(os.path.join(slices_dir, "segments.json"), encoding="utf-8") as fh:
        segments = {d["path"]: d["units"] for d in json.load(fh)["documents"]}
    rounds = [_answers(slices_dir), _answers(repair_dir)]

    documents, dropped, kept = [], 0, 0
    for path in sorted(rounds[0]):
        known = {u["digest"] for u in segments[path]}
        by_unit = {}
        for round_answers in rounds:
            for answer in round_answers.get(path, []):
                unit = answer.get("unit")
                if unit not in known:
                    dropped += 1
                    continue
                by_unit[unit] = answer
        verdicts = [by_unit[u] for u in sorted(by_unit)]
        kept += len(verdicts)
        documents.append({"path": path, "status": "ok", "verdicts": verdicts})

    with open(out, "w", encoding="utf-8") as fh:
        json.dump({"documents": documents}, fh, indent=2, ensure_ascii=False)
    print(f"{len(documents)} documents, {kept} answers, {dropped} dropped")


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)

    tree = commands.add_parser("digest")
    tree.add_argument("--repo", default=".")

    plan = commands.add_parser("slices")
    plan.add_argument("--repo", default=".")
    plan.add_argument("--registry", required=True)
    plan.add_argument("--out", required=True)

    fold = commands.add_parser("merge")
    fold.add_argument("--slices", required=True)
    fold.add_argument("--repair", default=None)
    fold.add_argument("--out", required=True)

    args = parser.parse_args(argv)
    if args.command == "digest":
        value, count = digest(os.path.abspath(args.repo))
        print(f"{value}  ({count} files)")
    elif args.command == "slices":
        slices(os.path.abspath(args.repo), args.registry,
               os.path.abspath(args.out))
    else:
        merge(args.slices, args.repair, args.out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
