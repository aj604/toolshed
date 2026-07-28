#!/usr/bin/env python3
"""Harness for the shadow-mode parity gate's cycle (aj604/toolshed#76).

Not plugin content and not a test — the recorded scaffolding that made one
shadow cycle reproducible. `doc-audit.yml` does the same three things in CI
(plan the scope, hand each document to a model, fold the answers into one
verdicts file); here they are separated so the cycle can be run locally,
recorded, and re-run.

    shadow-cycle.py digest --repo .
        A sha256 over the repository's content *as the repository defines it* —
        the tracked files plus the untracked ones its ignore rules do not
        exclude — as sorted "mode path sha256" lines, together with
        `git status --porcelain`. Emitted as JSON. The before/after evidence
        for the gate's G1b criterion: the new lane must leave the tree
        byte-identical.

        Asking git what the content is settles `.git/` for free: it is never
        listed, so it is never hashed, and a directory that churns on every
        read cannot make the instrument measure itself.

        One exclusion is made here rather than by git, and it is the one
        re-registered for the 2026-07-27 cycle (aj604/toolshed#117) after the
        first cycle failed G1b on its instrument rather than on the lane:
        `.pyc` files and anything under a `__pycache__` directory, dropped
        unconditionally rather than by trusting a consumer's `.gitignore` to
        list them. CPython writes them the moment anything imports the engine,
        and a `.pyc` embeds its source's mtime, so `git checkout` of an
        *unchanged* source file re-keys them without any process writing to
        the repository. Counting those measured the instrument, not the lane.

        `porcelain_clean` is the other half of the criterion, reported rather
        than assumed: a digest taken over a tree somebody is editing proves
        nothing about what the cycle did. It is `git status --porcelain`
        verbatim, so in a repository whose ignore rules do *not* exclude
        `__pycache__` the two halves can disagree — the digest holds and the
        porcelain goes dirty over byproducts. That is the honest report of
        two different questions, not a bug: this repository's `.gitignore`
        does list them, and a consumer's that does not has a real untracked
        file the criterion should not hide.

    shadow-cycle.py slices --repo . --registry <path> --out <dir>
        One task file per declared living document, each carrying that
        document's deterministic segmentation, for a model worker to answer.
        Also writes segments.json, the whole-run segmentation the comparison
        reads. Everything lands in --out, which must be outside the repository.

    shadow-cycle.py merge --slices <dir> --repair <dir> --out <path>
        Fold both rounds' answers into the one verdicts file
        `drift-audit --verdicts` consumes. Later rounds win per unit — that is
        what a repair round means. Answers naming a unit the document does not
        contain, and second answers for a unit already covered, are dropped:
        neither carries information, and the engine refuses the whole document
        over either.

        A worker answers by a unit's small integer *ordinal*, the identity
        aj604/toolshed#116 introduced after this gate measured a 2.9%
        transcription error rate on 64-character digests. Both spellings are
        resolved to the digest here, so a repair round keyed by ordinal
        overrides a round-1 answer keyed by digest for the same unit — two
        spellings that did not land on one key would make a repair round a
        silent no-op.
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


def git(repo, *argv):
    result = subprocess.run(["git", *argv], capture_output=True, text=True,
                            cwd=repo)
    if result.returncode != 0:
        sys.exit(f"git {argv[0]} exited {result.returncode}: {result.stderr}")
    return result.stdout


def _byproduct(relative):
    """A CPython import byproduct, excluded whatever the ignore rules say."""
    parts = relative.split(os.sep)
    return relative.endswith(".pyc") or "__pycache__" in parts


def content_paths(repo):
    """The repository's content as the repository defines it, sorted.

    Tracked plus untracked-but-not-ignored, which is the same set
    `git status` reasons about — one enumeration, asked of git, rather than a
    walk that re-derives the ignore rules and can drift from them.
    """
    listed = set()
    for argv in (("ls-files", "-z"),
                 ("ls-files", "--others", "--exclude-standard", "-z")):
        listed.update(p for p in git(repo, *argv).split("\0") if p)
    return sorted(
        p for p in listed
        if not _byproduct(p.replace("/", os.sep))
    )


def digest(repo):
    entries = []
    for relative in content_paths(repo):
        path = os.path.join(repo, relative.replace("/", os.sep))
        if not os.path.lexists(path):
            # Tracked and deleted. Porcelain reports it too; recorded here so
            # the digest moves as well, rather than a deletion reading as "no
            # change" because the file simply stopped being enumerated.
            entries.append(f"- {relative} deleted")
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
    porcelain = git(repo, "status", "--porcelain").strip()
    return {
        "digest": hashlib.sha256(listing.encode()).hexdigest(),
        "files": len(entries),
        "porcelain_clean": porcelain == "",
        "porcelain": porcelain,
    }


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
        # `.get`, not `[...]`: a segments file recorded before #116 added the
        # ordinal has none to resolve against, and re-running a recorded cycle
        # is what this module is for. Such a file simply has no ordinal
        # answers to fold, and an integer against it drops like any other unit
        # the document does not contain.
        by_ordinal = {
            u["ordinal"]: u["digest"] for u in segments[path] if "ordinal" in u
        }
        by_unit = {}
        for round_answers in rounds:
            for answer in round_answers.get(path, []):
                unit = answer.get("unit")
                if isinstance(unit, int) and not isinstance(unit, bool):
                    unit = by_ordinal.get(unit)
                if unit not in known:
                    dropped += 1
                    continue
                by_unit[unit] = dict(answer, unit=unit)
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
        print(json.dumps(digest(os.path.abspath(args.repo)), indent=2))
    elif args.command == "slices":
        slices(os.path.abspath(args.repo), args.registry,
               os.path.abspath(args.out))
    else:
        merge(args.slices, args.repair, args.out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
