#!/usr/bin/env python3
"""The apply lanes' byte verification at the two git boundaries (#191).

The applier certifies a **postimage manifest**: every path one apply run wrote,
with the sha256 of the bytes it read back off disk — `null` for a document it
retired (`doclifecycle/applier.py`, "Final-byte certification"). That
certification ends at the working tree, and two trust boundaries lie beyond it
that the engine cannot see, because git owns both:

  * **the index.** `git add` does not have to store the bytes it was pointed
    at. A `clean` filter or an end-of-line attribute rewrites content on the
    way in, and anything that mutates an approved path between the apply and
    the staging lands in the index unread — path confinement
    (`render-apply-summary.py verify-staged`) sees the same path list either
    way, because the path *is* one the plan writes. Only the bytes betray it.
  * **the commit tree.** A `pre-commit` hook may rewrite a target and re-stage
    it after the index was verified, so the tree that would be pushed is not
    the index anybody checked.

So each boundary is re-read from git's own object store and compared with the
manifest, and the commit this script certifies is the one the lane pushes: it
writes the verified commit id out, and the push names that id rather than
`HEAD`, which anything running in between could have moved.

Path confinement and byte binding stay separate checks here, exactly as they
are in the applier, and both must hold: `--result`'s `changed_paths` must be
covered by the manifest, the commit's whole diff against its parent must lie
inside it, and every manifest entry must match byte for byte — or be absent,
which is what a retired document's `null` certifies and what a deletion has to
mean at an index and a tree alike.

Both apply lanes run this script, with the same arguments, at the same two
points: `doc-apply.yml` (a human selected the records) and
`doc-policy-apply.yml` (a standing policy did). Selection and trigger are the
only intended differences between them, and
`tests/scripts/apply-lane-parity_test.py` is what holds that true.

A third boundary is the same question asked of a commit this run did not make:
`reuse` (#198). An apply whose push landed while its pull request did not
leaves the derived branch standing, and a re-run of that dispatch aims at the
same ref, because the name is derived from the approval digest. Reusing it is
only safe if it is provably this run's own result, so the existing commit goes
through the certification a fresh one passes — the same manifest, the same
confinement, the same tree comparison — plus the approval trailer it carries
and the parent it sits on. Anything else is a typed conflict, never a force
push.

That boundary has a fourth check, and it is what makes the other three answer
about the branch rather than about some commit on it: `--commit` is an id the
lane read from `ls-remote` in an *earlier* step, and the branch can move
between the two. A fast-forward is the dangerous case — the fetch necessarily
brings the old tip along as an ancestor of the new one, so every check above
would pass on a commit the branch no longer holds, and the lane would open a
pull request over the tip that nothing verified. So the fetched ref is resolved
here and required to be exactly `--commit`; a branch that moved is
`apply-branch-moved`, not a reuse.

Usage:
    verify-apply-bytes.py index  --result FILE [--repo DIR]
    verify-apply-bytes.py commit --result FILE [--repo DIR] --out FILE
    verify-apply-bytes.py reuse  --result FILE [--repo DIR] --commit OID
                                 --ref REF --verified FILE --approval FILE

Exit status: 0 the boundary holds; 1 a typed refusal, rendered to
$GITHUB_STEP_SUMMARY (stdout when unset); 2 a usage error, caught by argparse
before any subcommand body runs. A refusal never writes `--out`: a commit id no
check certified is one a later step would push.
"""

import argparse
import json
import os
import re
import subprocess
import sys
import unicodedata
from hashlib import sha256

SHA256 = re.compile(r"^[0-9a-f]{64}$")
# A git object id, sha-1 or sha-256 — what a listing hands back and what
# `cat-file --batch` is fed. Nothing else becomes a name this script reads.
OBJECT_ID = re.compile(r"^[0-9a-f]{40}([0-9a-f]{24})?$")
DRIVE_LETTER = re.compile(r"^[A-Za-z]:")
# A fully qualified ref this script may resolve. The lane fetches the derived
# branch into one it names itself, so nothing here has to parse a revision
# expression — and a name shaped like an option never becomes an argument.
REF_NAME = re.compile(r"refs/[A-Za-z0-9._][A-Za-z0-9._/-]*")

# The modes a document may be stored under. A `120000` entry is a symlink,
# whose blob content is the path it points at — bytes that would digest as some
# other document's — and `160000` is a submodule. Neither is something the
# applier writes, so neither is something this lane certifies.
REGULAR_MODES = ("100644", "100755")

# git, invoked exactly as `doclifecycle/repository.py` invokes it: the
# repository named on the command line and no other, and no environment
# variable left that could redirect it at another tree.
REDIRECTING_VARS = (
    "GIT_DIR",
    "GIT_WORK_TREE",
    "GIT_INDEX_FILE",
    "GIT_COMMON_DIR",
    "GIT_OBJECT_DIRECTORY",
    "GIT_ALTERNATE_OBJECT_DIRECTORIES",
    "GIT_CEILING_DIRECTORIES",
    "GIT_NAMESPACE",
)

# A local object-store read is milliseconds. Anything near this is a hung git,
# and hanging a credentialed job is a worse answer than a typed refusal.
TIMEOUT_SECONDS = 30

STAGE_INDEX = "staging"
STAGE_COMMIT = "commit"
STAGE_REUSE = "branch reuse"

# The trailer `render-approval --trailers` puts at the head of its block, and
# the one fact that binds a commit somebody else's run made to this run's
# authority. Read as a whole line, so a mention of it in prose is not one.
APPROVAL_TRAILER = "Doc-Lifecycle-Approval:"


# -- the run surface ---------------------------------------------------------

def write_surface(text):
    path = os.environ.get("GITHUB_STEP_SUMMARY")
    if path:
        with open(path, "a", encoding="utf-8") as fh:
            fh.write(text)
    else:
        sys.stdout.write(text)


def quoted(value):
    """One JSON string, for a value this script did not shape-check.

    Everything else it prints — a repository-relative path, a sha256, a git
    mode — is refused before it is rendered, so a plain code span around one
    cannot be escaped from. git's own stderr is the exception: it is a line
    from another program, and `json.dumps` escapes every control character in
    it rather than letting one restructure the page a reviewer reads.
    """
    return json.dumps(value if isinstance(value, str) else str(value))


def refuse(stage, code, message, details=()):
    """Render one typed refusal and return the lane's exit status.

    Worded for where this runs: by the staging boundary a local branch exists,
    so the honest claim is not "no branch" but that nothing left this runner.
    """
    lines = [
        f"## Doc apply: REFUSED at {stage}",
        "",
        f"- `{code}`: {message}",
    ]
    lines += [f"  - {d}" for d in details]
    lines += [
        "",
        "**Nothing was pushed and no pull request was created.** This run "
        "could not certify that what git holds is what the applier verified, "
        "so it will not publish it as approved. Inspect the checkout, then "
        "re-run the audit and mint afresh.",
        "",
    ]
    write_surface("\n".join(lines))
    return 1


# -- git ---------------------------------------------------------------------

def git(repo, *args, stdin=None):
    """Read-only git in `repo`. Returns (stdout bytes, None) or (None, detail).

    Bytes throughout, never text: a stored blob is compared byte for byte, and
    decoding it — or letting git translate its line endings — would make the
    comparison answer about a rendering rather than about the object. No shell,
    a fixed argv, and a timeout, for the reasons `repository.py` gives.
    """
    env = {k: v for k, v in os.environ.items() if k not in REDIRECTING_VARS}
    try:
        result = subprocess.run(
            ["git", "-C", repo, *args],
            input=stdin, capture_output=True, env=env, timeout=TIMEOUT_SECONDS,
        )
    except OSError as exc:
        return None, f"git is not available ({exc.strerror})"
    except subprocess.TimeoutExpired:
        return None, f"git {args[0]} did not finish in {TIMEOUT_SECONDS}s"
    if result.returncode != 0:
        detail = result.stderr.decode("utf-8", "replace").strip().splitlines()
        return None, (detail[0] if detail else f"git {args[0]} failed")
    return result.stdout, None


def _nul_fields(out):
    """A `-z` listing's entries, the trailing empty one dropped."""
    return [entry for entry in out.split(b"\0") if entry]


def _listing(stage, repo, args, what):
    """({path: (mode, object id)}, None) for one git listing, or (None, status).

    `ls-files --stage` writes `mode oid stage`, `ls-tree -r` writes
    `mode type oid`, and both put the path after a tab — so the mode is the
    first field and the object id is the one field shaped like one. Read that
    way, neither format needs its own parser and neither can be read as the
    other's.

    A path git cannot hand back as valid UTF-8 is not one the applier wrote,
    and is refused rather than replaced: a lossy decode would compare a
    different name than the one git holds. A path listed twice is an unmerged
    index, whose entries are several competing versions of one document — not
    something a lane that commits one reviewed change may pick between.
    """
    out, detail = git(repo, *args)
    if detail is not None:
        return None, refuse(
            stage, "apply-git-listing-unavailable",
            f"git could not list the {what}, so what it holds cannot be "
            f"compared with what the applier certified",
            [quoted(detail)])
    entries = {}
    for entry in _nul_fields(out):
        info, tab, name = entry.partition(b"\t")
        if not tab:
            return None, refuse(
                stage, "apply-git-listing-unreadable",
                f"git's {what} listing carries an entry with no path in it",
                [quoted(entry.decode("utf-8", "replace"))])
        try:
            path = name.decode("utf-8")
        except UnicodeDecodeError:
            return None, refuse(
                stage, "apply-git-listing-unreadable",
                f"git's {what} listing names a path that is not valid UTF-8, "
                f"so it cannot be compared with a certified one",
                [quoted(name.decode("utf-8", "replace"))])
        if path in entries:
            return None, refuse(
                stage, "apply-git-listing-unreadable",
                f"git's {what} listing carries `{path}` more than once, so "
                f"which bytes it holds there is not a question with one answer")
        fields = [field.decode("ascii", "replace") for field in info.split()]
        oids = [field for field in fields if OBJECT_ID.match(field)]
        entries[path] = (fields[0] if fields else "",
                         oids[0] if oids else "")
    return entries, None


def _blobs(stage, repo, oids, what):
    """({object id: bytes}, None) for every id in `oids`, or (None, status).

    Object ids, never `:path` or `<commit>:path`: the ids come from the listing
    already read, so nothing this script hands git has to be parsed as a
    revision. They travel on stdin rather than in argv for the same reason —
    there is no position there an id could be read from as an option.
    """
    wanted = sorted(set(oids))
    if not wanted:
        return {}, None
    for oid in wanted:
        if not OBJECT_ID.match(oid):
            return None, refuse(
                stage, "apply-git-listing-unreadable",
                f"git's {what} listing names {quoted(oid)} where an object id "
                f"belongs")
    out, detail = git(repo, "cat-file", "--batch",
                      stdin="".join(f"{oid}\n" for oid in wanted).encode())
    if detail is not None:
        return None, refuse(
            stage, "apply-git-listing-unavailable",
            f"git could not read the {what}'s stored content, so it cannot be "
            f"compared with what the applier certified",
            [quoted(detail)])

    blobs, cursor = {}, 0
    for oid in wanted:
        end = out.find(b"\n", cursor)
        if end < 0:
            return None, refuse(
                stage, "apply-git-object-unreadable",
                f"git's batch read of the {what} ended mid-header")
        header = out[cursor:end].decode("utf-8", "replace").split()
        cursor = end + 1
        if len(header) != 3 or header[1] != "blob":
            return None, refuse(
                stage, "apply-git-object-unreadable",
                f"git reports {quoted(header[0] if header else '')} as "
                f"{quoted(' '.join(header[1:]))} — a document is stored as a "
                f"blob, and nothing else is content this lane may certify")
        size = int(header[2]) if header[2].isdigit() else -1
        if size < 0 or cursor + size > len(out):
            return None, refuse(
                stage, "apply-git-object-unreadable",
                f"git's batch read of the {what} declares a length its output "
                f"does not carry")
        blobs[oid] = out[cursor:cursor + size]
        cursor += size + 1
    return blobs, None


# -- the certified manifest --------------------------------------------------

def read_json(path):
    """(payload, None) or (None, reason)."""
    try:
        with open(path, encoding="utf-8") as fh:
            return json.load(fh), None
    except OSError as exc:
        return None, f"cannot read {path}: {exc.strerror}"
    except (ValueError, UnicodeDecodeError) as exc:
        return None, f"{path} is not readable JSON: {exc}"


def _unsafe_path_reason(path):
    """Why `path` must not be compared as a repository document, or None.

    A third reading of a string `paths.authorize_path` and
    `render-apply-summary.py`'s `_unsafe_path_reason` have each already read,
    at the boundary where it stops being data and starts naming a git object.
    Deliberately not the full authorization check — that has one owner — only
    the shapes that are dangerous *here*: a path that is not canonically and
    printably spelled cannot be matched against a listing git wrote, and a
    mismatch that silently reads as "absent" would certify a deletion nobody
    approved.
    """
    if not isinstance(path, str) or not path:
        return "not a path"
    for ch in path:
        category = unicodedata.category(ch)
        if category in ("Cc", "Cf", "Cs", "Co", "Cn"):
            return "holds a control character"
        if category in ("Zl", "Zp"):
            return "holds a line or paragraph separator"
    if path.startswith("-"):
        return "starts with a dash, which git reads as an option"
    if path.startswith("/") or path.startswith("~") or DRIVE_LETTER.match(path):
        return "is not repository-relative"
    if "\\" in path:
        return "uses a backslash separator"
    if any(part in ("", ".", "..") for part in path.split("/")):
        return "is not canonically spelled"
    return None


def manifest(stage, result_path):
    """(the applier's verified postimage manifest, None), or (None, status).

    The manifest is the *engine's* certification and the only authority this
    script compares against: `{path: sha256 of the bytes read back}`, `None`
    for a document the run retired. A result that carries none certifies
    nothing, so there is nothing here to check bytes against — which is a
    refusal, never a boundary quietly skipped.
    """
    res, reason = read_json(result_path)
    if res is None:
        return None, refuse(stage, "apply-result-unreadable", reason)
    if res.get("status") != "clean":
        return None, refuse(
            stage, "apply-result-not-clean",
            f"the applier returned `{res.get('status')}` — only a clean apply "
            f"certifies postimages, and only certified bytes may be committed")

    postimages = res.get("postimages")
    if not isinstance(postimages, dict) or not postimages:
        return None, refuse(
            stage, "apply-postimages-absent",
            "the apply result carries no verified postimage manifest — the "
            "applier certifies one for every clean run, so this result came "
            "from an engine that cannot certify what it wrote, and this lane "
            "will not publish bytes nothing verified")

    bad = []
    for path, digest in sorted(postimages.items()):
        why = _unsafe_path_reason(path)
        if why is not None:
            bad.append(f"`{path if isinstance(path, str) else quoted(path)}` {why}")
        elif not (digest is None or (isinstance(digest, str)
                                     and SHA256.match(digest))):
            bad.append(f"`{path}` carries {quoted(digest)} where a sha256 or "
                       f"null belongs")
    if bad:
        return None, refuse(
            stage, "apply-postimages-malformed",
            "the verified postimage manifest is not a map of repository "
            "documents to the sha256 of their bytes", bad)

    # Path confinement, the half that is not about bytes: everything the run
    # reported changing must be something it also certified. A path in the
    # staged set with no manifest entry has no certified bytes to be compared
    # against, so it would ride into the commit unchecked. A `changed_paths`
    # that is not a list is not a path set at all, and reading one out of it
    # would answer this question about something else.
    changed = res.get("changed_paths") or []
    if not isinstance(changed, list) or any(
            not isinstance(p, str) for p in changed):
        return None, refuse(
            stage, "apply-result-unreadable",
            "the apply result does not name the paths it changed as a list of "
            "documents, so what it wrote cannot be compared with what it "
            "certified")
    uncertified = sorted(set(changed) - set(postimages))
    if uncertified:
        return None, refuse(
            stage, "apply-changed-path-uncertified",
            "the apply result reports changing path(s) its postimage manifest "
            "does not certify, so their bytes rest on nothing",
            [f"`{p}`" for p in uncertified])
    return postimages, None


# -- the comparison ----------------------------------------------------------

def compare(stage, repo, entries, postimages, what):
    """Every manifest entry against one git listing. Returns an exit status.

    Exhaustively, as the engine reports its own problems: a reader fixing one
    path at a time learns nothing about the second. Present-and-different,
    present-when-it-should-be-absent, and absent-when-it-should-be-present are
    three distinct answers and each gets its own line.
    """
    absent, present = [], {}
    for path, digest in sorted(postimages.items()):
        entry = entries.get(path)
        if digest is None:
            # A retired document. Its certified final state is its absence,
            # and an index or a tree that still carries it would commit the
            # document the approval retired.
            if entry is not None:
                absent.append(
                    f"`{path}` was retired by this apply and the {what} still "
                    f"carries it")
            continue
        if entry is None:
            absent.append(
                f"`{path}` was written by this apply and the {what} does not "
                f"carry it")
            continue
        mode, oid = entry
        if mode not in REGULAR_MODES:
            absent.append(
                f"`{path}` is stored with mode `{mode}` — a document is a "
                f"regular file, and a symlink or submodule entry is not "
                f"content the applier wrote")
            continue
        present[path] = (oid, digest)

    blobs, bad = _blobs(stage, repo, [oid for oid, _ in present.values()], what)
    if bad is not None:
        return bad

    mismatched = []
    for path, (oid, digest) in sorted(present.items()):
        stored = blobs.get(oid)
        if stored is None or sha256(stored).hexdigest() != digest:
            mismatched.append(
                f"`{path}`: the applier certified `{digest}`, and the {what} "
                f"holds `"
                + (sha256(stored).hexdigest() if stored is not None else "?")
                + "`")

    if absent or mismatched:
        return refuse(
            stage, "apply-bytes-not-certified",
            f"the {what} is not what the applier certified — git holds "
            f"different bytes than the apply result verified on disk, so "
            f"something rewrote an approved document (a `clean`/`smudge` "
            f"filter, an end-of-line attribute, a hook, or another writer) "
            f"after the engine read it back",
            absent + mismatched)
    return 0


# -- subcommands -------------------------------------------------------------

def verify_index(args):
    """The staged index, against the certified manifest.

    Run after `render-apply-summary.py verify-staged` has settled which *paths*
    got staged, and before the commit. Every manifest entry is checked, not
    only the staged ones: a path the plan wrote to the bytes it already had
    produces no diff and so is never staged, and the index must still carry the
    certified content for the commit to be the approved change.
    """
    postimages, bad = manifest(STAGE_INDEX, args.result)
    if bad is not None:
        return bad
    entries, bad = _listing(
        STAGE_INDEX, args.repo, ("ls-files", "--stage", "-z"), "index")
    if bad is not None:
        return bad
    return compare(STAGE_INDEX, args.repo, entries, postimages, "index")


def _parents(stage, repo, commit, whose):
    """(the commit's parents, None), or (None, status).

    `commit` reaches this read where an option would, so it is the `OBJECT_ID`
    gate every caller applies first — not a `--` separator, which only says
    where pathspecs start — that makes it a revision rather than a flag. The
    same reasoning `repository.changed_paths` states about a diff baseline.
    """
    lineage, detail = git(repo, "rev-list", "--parents", "-n", "1", commit)
    if detail is not None:
        return None, refuse(
            stage, "apply-commit-unreadable",
            f"{whose} parentage cannot be read, so what it changed cannot be "
            f"established", [quoted(detail)])
    return lineage.decode("ascii", "replace").split()[1:], None


def certify(stage, repo, commit, postimages, what):
    """One commit against the certified manifest. Returns (parent, status).

    Parentage, whole-diff confinement, and byte binding, in that order — the
    three checks that together say this commit is the change the applier
    verified and nothing else. Shared by the commit this run just made and, at
    `reuse`, by one an earlier attempt left on the remote: two commits asking
    the same question deserve one answer, not a second and weaker notion of
    what a certified tree is.
    """
    parents, bad = _parents(stage, repo, commit, f"the {what}'s")
    if bad is not None:
        return None, bad
    if len(parents) != 1:
        # The diff below is against the one parent this lane's commit has.
        # A merge (or a root commit) is a different shape of change, and this
        # lane never makes one.
        return None, refuse(
            stage, "apply-commit-not-linear",
            f"the {what} has {len(parents)} parent(s) — this lane commits one "
            f"reviewed change onto the base it checked out, and anything else "
            f"is a change nobody approved the shape of")

    # Path confinement at the commit boundary, the counterpart to
    # `verify-staged` at the index: the *whole* diff this commit carries must
    # lie inside what the applier certified. Byte binding below cannot answer
    # this — a path outside the manifest has no certified bytes at all.
    diff, detail = git(repo, "diff-tree", "-r", "--no-commit-id",
                       "--name-only", "-z", "--no-renames", commit, "--")
    if detail is not None:
        return None, refuse(
            stage, "apply-commit-unreadable",
            f"the {what}'s own diff cannot be read, so whether it is confined "
            f"to the approved paths is unanswerable", [quoted(detail)])
    changed = sorted(
        entry.decode("utf-8", "replace") for entry in _nul_fields(diff))
    outside = [p for p in changed if p not in postimages]
    if outside:
        return None, refuse(
            stage, "apply-commit-not-confined",
            f"the {what} changes path(s) the applier never certified — the "
            f"tree that would be pushed is not the change this run verified",
            [f"`{p}`" for p in outside])

    entries, bad = _listing(
        stage, repo, ("ls-tree", "-r", "-z", "--full-tree", commit, "--"),
        f"{what} tree")
    if bad is not None:
        return None, bad
    status = compare(stage, repo, entries, postimages, f"{what} tree")
    if status != 0:
        return None, status
    return parents[0], 0


def verify_commit(args):
    """The commit tree, against the certified manifest — then name that commit.

    The last check before anything leaves the runner, and the reason it exists
    is that the index it re-reads is not the one `index` verified: `git commit`
    runs hooks, and a `pre-commit` that rewrote and re-staged a target would
    have moved the tree in between. What this writes to `--out` is the commit
    id it verified, and the push names that id — so the commit that lands is
    provably the tree that passed, not whatever `HEAD` points at by then.
    """
    postimages, bad = manifest(STAGE_COMMIT, args.result)
    if bad is not None:
        return bad

    out, detail = git(args.repo, "rev-parse", "--verify", "--end-of-options",
                      "HEAD^{commit}")
    if detail is not None:
        return refuse(
            STAGE_COMMIT, "apply-commit-unreadable",
            "the commit this run just made cannot be resolved, so there is no "
            "tree to verify and nothing safe to push", [quoted(detail)])
    commit = out.decode("ascii", "replace").strip()
    if not OBJECT_ID.match(commit):
        return refuse(
            STAGE_COMMIT, "apply-commit-unreadable",
            f"git resolved HEAD to {quoted(commit)}, which is not a commit id")

    _, status = certify(STAGE_COMMIT, args.repo, commit, postimages, "commit")
    if status != 0:
        return status

    # Written only now: a commit id this file carries is one the push names,
    # so it must never exist for a tree no check certified.
    with open(args.out, "w", encoding="utf-8") as fh:
        fh.write(f"{commit}\n")
    write_surface(
        f"\n**Commit tree verified:** `{commit}` holds exactly the "
        f"{len(postimages)} certified postimage(s); it is the commit this run "
        f"pushes.\n")
    return 0


def read_text(path):
    """(the file's text, None) or (None, reason)."""
    try:
        with open(path, encoding="utf-8") as fh:
            return fh.read(), None
    except OSError as exc:
        return None, f"cannot read {path}: {exc.strerror}"
    except UnicodeDecodeError as exc:
        return None, f"{path} is not readable text: {exc}"


def _commit_id(source, value):
    """(a commit id, None) or (None, status) — for an id this script is handed.

    `reuse` reads two ids it did not resolve itself: the one the remote listing
    named and the one the tree verification wrote. Both become revisions on a
    git command line, so both are shape-checked here rather than trusted.
    """
    commit = (value or "").strip()
    if not OBJECT_ID.match(commit):
        return None, refuse(
            STAGE_REUSE, "apply-commit-unreadable",
            f"{source} is {quoted(commit)}, which is not a commit id")
    return commit, None


def _branch_tip(repo, ref, commit):
    """Whether `ref` still resolves to `commit`. Returns an exit status.

    The check the other three rest on. `commit` came from an `ls-remote` the
    lane ran in an earlier step; this ref is what the fetch in *this* step
    actually brought back, so resolving it is the only way to learn that the
    branch is still where it was. Nothing below would notice on its own: a
    fast-forward makes the old tip an ancestor of the new one, so it stays
    readable, its tree stays certified, and its trailer stays right — while
    the branch a pull request would be opened over carries something else
    entirely.
    """
    if not REF_NAME.fullmatch(ref):
        return refuse(
            STAGE_REUSE, "apply-branch-unreadable",
            f"{quoted(ref)} is not a fully qualified ref name, so what the "
            f"fetch brought back cannot be resolved")
    out, detail = git(repo, "rev-parse", "--verify", "--end-of-options",
                      f"{ref}^{{commit}}")
    if detail is not None:
        return refuse(
            STAGE_REUSE, "apply-branch-unreadable",
            f"`{ref}` does not resolve to a commit, so this run cannot "
            f"establish what the derived branch holds now", [quoted(detail)])
    tip = out.decode("ascii", "replace").strip()
    if tip != commit:
        return refuse(
            STAGE_REUSE, "apply-branch-moved",
            "the derived branch moved between this run reading it and "
            "fetching it, so the commit checked below is not the one the "
            "branch holds — reusing it would open a pull request over a tip "
            "nothing verified",
            [f"read: `{commit}`", f"now: `{tip}`",
             "re-run this lane once the branch has settled"])
    return 0


def _approval_bound(repo, commit, digest):
    """Whether `commit`'s message carries this run's approval trailer.

    Half of what makes an existing branch reusable, and the half a tree
    comparison cannot answer: two applies of different approval sets could
    write the same bytes, and the derived branch name carries only the
    digest's first twelve characters. The trailer carries all of it, and
    `render-approval --trailers` is what put it there.
    """
    out, detail = git(repo, "show", "-s", "--format=%B", "--end-of-options",
                      commit)
    if detail is not None:
        return refuse(
            STAGE_REUSE, "apply-commit-unreadable",
            "the existing branch's commit message cannot be read, so what "
            "authorized it is unanswerable", [quoted(detail)])
    trailers = [line.strip()
                for line in out.decode("utf-8", "replace").splitlines()
                if line.strip().startswith(APPROVAL_TRAILER)]
    if not trailers:
        return refuse(
            STAGE_REUSE, "apply-branch-approval-conflict",
            f"the branch this approval derives already exists on the remote, "
            f"and the commit it points at carries no `{APPROVAL_TRAILER}` "
            f"trailer — this lane did not write it, and a derived name is no "
            f"authority to overwrite a ref this run does not own",
            ["inspect that branch, delete it if it is stale, and re-run"])
    if f"{APPROVAL_TRAILER} {digest}" not in trailers:
        return refuse(
            STAGE_REUSE, "apply-branch-approval-conflict",
            "the branch this approval derives already exists on the remote "
            "carrying a different approval set, so reusing it would publish "
            "one approval's branch as another's",
            [f"this run: `{digest}`"]
            + [f"the branch: `{t[len(APPROVAL_TRAILER):].strip()}`"
               for t in trailers])
    return 0


def verify_reuse(args):
    """An existing derived branch, against the result this run just verified.

    The recovery boundary (#198). The branch name is derived from the approval
    digest, so a re-run of a dispatch whose push landed and whose pull request
    did not aims at a ref that already exists — and a deterministic name is not
    authority to overwrite it. Reuse is allowed only when the commit standing
    there is this run's own result, which is two questions: does it carry this
    approval's trailer, and is its tree the one the applier certified. The
    second is answered by the same certification the fresh commit passed,
    against the same manifest, plus the parent — the same postimages on another
    base are a different diff against the base under review.
    """
    postimages, bad = manifest(STAGE_REUSE, args.result)
    if bad is not None:
        return bad

    app, reason = read_json(args.approval)
    if app is None:
        return refuse(STAGE_REUSE, "apply-approval-unreadable", reason)
    digest = app.get("digest")
    if not (isinstance(digest, str) and SHA256.match(digest)):
        return refuse(
            STAGE_REUSE, "apply-approval-digest-invalid",
            f"the approval set declares no sha256 digest ({quoted(digest)}), "
            f"so there is nothing to bind an existing branch to")

    existing, bad = _commit_id("the remote's branch tip", args.commit)
    if bad is not None:
        return bad
    text, reason = read_text(args.verified)
    if text is None:
        return refuse(STAGE_REUSE, "apply-commit-unreadable", reason)
    verified, bad = _commit_id("the commit this run verified", text)
    if bad is not None:
        return bad

    # First, because everything below is about `existing` and this is what
    # makes `existing` the branch rather than a commit somewhere on it.
    status = _branch_tip(args.repo, args.ref, existing)
    if status != 0:
        return status

    status = _approval_bound(args.repo, existing, digest)
    if status != 0:
        return status

    parent, status = certify(
        STAGE_REUSE, args.repo, existing, postimages, "existing branch")
    if status != 0:
        return status
    ours, bad = _parents(STAGE_REUSE, args.repo, verified,
                         "this run's own commit's")
    if bad is not None:
        return bad
    if ours != [parent]:
        return refuse(
            STAGE_REUSE, "apply-branch-lineage-conflict",
            "the existing branch holds this approval's postimages on a "
            "different base than this run applied onto, so what it changes "
            "against the base under review is not what this run verified",
            [f"this run applied onto `{ours[0] if ours else 'nothing'}`",
             f"the branch sits on `{parent}`"])

    write_surface(
        f"\n**Existing branch verified:** `{existing}` carries this approval's "
        f"trailer and holds exactly the {len(postimages)} certified "
        f"postimage(s) on the same base; it is this run's own result, reached "
        f"by an earlier attempt.\n")
    return 0


# -- argv --------------------------------------------------------------------

def _parser():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="mode", required=True)

    index = sub.add_parser("index")
    index.add_argument("--result", required=True)
    index.add_argument("--repo", default=".")
    index.set_defaults(run=verify_index)

    commit = sub.add_parser("commit")
    commit.add_argument("--result", required=True)
    commit.add_argument("--repo", default=".")
    commit.add_argument("--out", required=True)
    commit.set_defaults(run=verify_commit)

    reuse = sub.add_parser("reuse")
    reuse.add_argument("--result", required=True)
    reuse.add_argument("--repo", default=".")
    reuse.add_argument("--commit", required=True)
    reuse.add_argument("--ref", required=True)
    reuse.add_argument("--verified", required=True)
    reuse.add_argument("--approval", required=True)
    reuse.set_defaults(run=verify_reuse)

    return parser


def main():
    args = _parser().parse_args()
    return args.run(args)


if __name__ == "__main__":
    sys.exit(main())
