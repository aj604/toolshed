#!/usr/bin/env python3
"""Harness for the shadow-mode parity gate's cycle (aj604/toolshed#76).

Not plugin content and not a test — the recorded scaffolding that made one
shadow cycle reproducible. `doc-audit.yml` does the same three things in CI
(plan the scope, hand each document to a model, fold the answers into one
verdicts file); here they are separated so the cycle can be run locally,
recorded, and re-run.

    shadow-cycle.py digest --repo .
        A sha256 over every file in the worktree except .git/, as
        sorted "mode path sha256" lines. The before/after evidence for the
        gate's G1b criterion: the new lane must leave the tree byte-identical.

    shadow-cycle.py slices --repo . --registry <path> --out <dir>
        One task file per declared living document, each carrying that
        document's deterministic segmentation, for a model worker to answer.
        Also writes segments.json, the whole-run segmentation the comparison
        reads. Everything lands in --out, which must be outside the repository.

    shadow-cycle.py merge --slices <dir> --out <path>
        Fold the workers' answers into the one verdicts file
        `drift-audit --verdicts` consumes.
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


def digest(repo):
    entries = []
    for root, dirnames, filenames in os.walk(repo):
        dirnames[:] = sorted(d for d in dirnames if d != ".git")
        for name in sorted(filenames):
            path = os.path.join(root, name)
            relative = os.path.relpath(path, repo)
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


def merge(slices_dir, out):
    documents = []
    for name in sorted(os.listdir(slices_dir)):
        if not name.endswith(".answer.json"):
            continue
        with open(os.path.join(slices_dir, name), encoding="utf-8") as fh:
            documents.append(json.load(fh))
    with open(out, "w", encoding="utf-8") as fh:
        json.dump({"documents": documents}, fh, indent=2)
    print(f"{len(documents)} documents, "
          f"{sum(len(d.get('verdicts', [])) for d in documents)} answers")


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
    fold.add_argument("--out", required=True)

    args = parser.parse_args(argv)
    if args.command == "digest":
        value, count = digest(os.path.abspath(args.repo))
        print(f"{value}  ({count} files)")
    elif args.command == "slices":
        slices(os.path.abspath(args.repo), args.registry,
               os.path.abspath(args.out))
    else:
        merge(args.slices, args.out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
