#!/usr/bin/env python3
"""Run surface for the scheduler adapter's apply lane (doc-apply.yml, #72).

The workflow sequences the engine's own commands — `validate-report`,
`mint-approval`, `render-approval`, `apply-plan` — and this script owns
everything the *run* says and hands to `git`: the typed refusals, the staged
path list, and the PR title, PR body, and commit message that carry the
approval set's digest and summary into the change it authorizes. It is a
separate script for the same reason `render-audit-summary.py` is: logic in
workflow YAML is untestable, and this is the half of the lane a reviewer reads
before performing change approval.

It re-derives nothing. Every fact it prints comes from an artifact the engine
already validated — a report, an approval set, or an `ApplyResult` — and the
only judgments it makes are refusals: an artifact the lane cannot proceed from
is named, rendered, and exited on. In particular it never decides that an
apply is safe; `apply-plan` decides that, and this script refuses anything
that is not its `clean` verdict.

Usage:
    render-apply-summary.py verify-report --report FILE --expected-digest HEX
    render-apply-summary.py gate --stage NAME --payload FILE --exit-code N
    render-apply-summary.py policy-eligibility --eligibility FILE --out FILE
    render-apply-summary.py run-id --run-id STR --out FILE
    render-apply-summary.py record-args --records STR --out FILE
    render-apply-summary.py config-digest --report FILE --out FILE  # FILE: audit-config-digest output
    render-apply-summary.py approval-digest --approval FILE --out FILE
    render-apply-summary.py branch-name --approval FILE --out FILE
    render-apply-summary.py staged-paths --result FILE --approval FILE --out FILE
    render-apply-summary.py verify-staged --paths FILE --staged FILE --unstaged FILE
    render-apply-summary.py pr-title --result FILE --approval FILE --out FILE
    render-apply-summary.py pr-body --result FILE --approval FILE --report FILE
                                    [--approval-summary FILE] --out FILE
    render-apply-summary.py commit-message --result FILE --approval FILE
                                    [--trailers FILE] --out FILE
    render-apply-summary.py remote-branch --listing FILE --exit-code N
                                    --branch NAME --approval FILE --out FILE
    render-apply-summary.py existing-pull-request --listing FILE --approval FILE
                                    --branch NAME --base NAME --out FILE
    render-apply-summary.py recovery --state NAME --branch NAME --approval FILE
                                    [--commit OID] [--pull-request N]

The last three are the recovery half (aj604/toolshed#198): a run whose push
landed while its pull request did not leaves the approval stranded, and the
branch a re-run derives is the same one, because `branch-name` derives it from
the approval digest. So the remote is read before anything is pushed, an
already-open pull request for this approval is idempotent success rather than a
duplicate-creation failure, and every terminal outcome — branch created, branch
reused, pull request already open, or a typed conflict — says so on the run
surface. A deterministic name is never authority to overwrite what stands
there: nothing here force-pushes, and a conflict refuses.

Exit status: 0 the subcommand produced its artifact; 1 a typed refusal, which
is rendered to $GITHUB_STEP_SUMMARY (stdout when unset) and always states what
this run did and did not create — before the push, that no branch and no pull
request exist, because the lane's jobs are ordered so that a refusal stops it
before any write; at the recovery steps, that this run published nothing and
left what it found untouched; 2 a usage error, caught by
argparse before any subcommand body runs. A refusal never writes its output
file: a half-written path list is one a later step would stage.
"""

import argparse
import json
import os
import re
import sys
import unicodedata

SHA256 = re.compile(r"^[0-9a-f]{64}$")
RUN_ID = re.compile(r"^[0-9]+$")
DRIVE_LETTER = re.compile(r"^[A-Za-z]:")
# The report states an approval set can be minted from, per the engine's
# `approval-report-not-approvable`. `mint-approval` re-checks this and owns the
# verdict; naming it here only turns a dispatch against the wrong report into a
# refusal that says so, before a fresh audit has been run to compare against.
APPROVABLE_REPORT_STATES = ("findings", "partial")


# -- untrusted text ----------------------------------------------------------

def code_span(value):
    """One Markdown code span holding `value`, with no way out of it.

    Modelled on `doclifecycle/render.py`'s `_code()`, and here for the same
    reason: record ids, codes, and paths are content a model wrote about
    repository documents, and a PR body is what a human reads before performing
    change approval. Two ways out of a span, both shut — a backtick run as long
    as the fence (so the fence is fitted one longer than the longest run
    inside), and a line break (so control characters, U+2028 and U+2029
    included, are escaped rather than emitted).
    """
    text = value if isinstance(value, str) else json.dumps(
        value, sort_keys=True, separators=(",", ":"))
    out = []
    for ch in text:
        if ch in (" ", " ") or unicodedata.category(ch) in (
                "Cc", "Cf", "Cs", "Co", "Cn"):
            out.append(f"\\u{ord(ch):04x}")
        else:
            out.append(ch)
    text = "".join(out)
    longest, run = 0, 0
    for ch in text:
        run = run + 1 if ch == "`" else 0
        longest = max(longest, run)
    fence = "`" * (longest + 1)
    pad = " " if text.startswith("`") or text.endswith("`") or not text else ""
    return f"{fence}{pad}{text}{pad}{fence}"


# -- the run surface ---------------------------------------------------------

def write_surface(text):
    path = os.environ.get("GITHUB_STEP_SUMMARY")
    if path:
        with open(path, "a", encoding="utf-8") as fh:
            fh.write(text)
    else:
        sys.stdout.write(text)


NOTHING_CREATED = (
    "**No branch and no pull request were created.** Re-run the audit, "
    "then dispatch this lane again with a report digest that describes "
    "the repository as it is now.")

# What a recovery refusal has to say instead (aj604/toolshed#198): by then a
# branch or a pull request may well exist — an earlier attempt's, or somebody
# else's — and telling a reader nothing was created would be false. What is
# true is that *this run* published nothing and left what it found alone.
NOTHING_TOUCHED = (
    "**This run pushed nothing and opened no pull request, and it changed "
    "nothing that was already there.** A branch or pull request it did not "
    "recognise is left exactly as it stands: inspect it, delete it if it is "
    "stale, and dispatch this lane again.")


def refuse(stage, code, message, details=(), closing=NOTHING_CREATED):
    """Render one typed refusal and return the lane's exit status.

    Every refusal names the stage it happened at, the typed code, and what a
    reader must do about it — and states what did or did not get created,
    because the absence of a PR is otherwise indistinguishable from a run still
    going.
    """
    lines = [
        f"## Doc apply: REFUSED at {stage}",
        "",
        f"- `{code}`: {message}",
    ]
    lines += [f"  - {d}" for d in details]
    lines += ["", closing, ""]
    write_surface("\n".join(lines))
    return 1


def read_json(path):
    """(payload, None) or (None, reason)."""
    try:
        with open(path, encoding="utf-8") as fh:
            return json.load(fh), None
    except OSError as exc:
        return None, f"cannot read {path}: {exc.strerror}"
    except (ValueError, UnicodeDecodeError) as exc:
        return None, f"{path} is not readable JSON: {exc}"


def write_file(path, text, mode="w"):
    with open(path, mode, encoding="utf-8") as fh:
        fh.write(text)


# -- subcommands -------------------------------------------------------------

def verify_report(args):
    """Bind the downloaded report artifact to the dispatched report digest."""
    payload, reason = read_json(args.report)
    if payload is None:
        return refuse("dispatch", "apply-report-unreadable", reason)
    declared = payload.get("digest")
    if declared != args.expected_digest:
        return refuse(
            "dispatch", "apply-report-digest-mismatch",
            "the report artifact is not the report this dispatch approved "
            "records from",
            [f"dispatched: {code_span(args.expected_digest)}",
             f"artifact: {code_span(declared)}"])
    state = payload.get("status")
    if state not in APPROVABLE_REPORT_STATES:
        return refuse(
            "dispatch", "apply-report-not-approvable",
            f"a {code_span(state)} report authorizes nothing — only "
            f"{' or '.join(code_span(s) for s in APPROVABLE_REPORT_STATES)} "
            f"carries records an approval set can be minted from")
    return 0


def _reason_lines(payload):
    """Every stale reason or problem the engine named, as detail lines."""
    details = []
    for reason in payload.get("stale_reasons", []) or []:
        details.append(
            f"{code_span(reason.get('code'))}: {code_span(reason.get('message'))} "
            f"(reported {code_span(reason.get('reported'))}, now "
            f"{code_span(reason.get('current'))})")
    for problem in payload.get("problems", []) or []:
        where = (f" at {code_span(problem.get('location'))}"
                 if problem.get("location") else "")
        details.append(
            f"{code_span(problem.get('code'))}: {code_span(problem.get('message'))}"
            f"{where}")
    return details


def gate(args):
    """Turn one engine exit code into a pass or a typed refusal.

    The exit code is the verdict — `stale` (3) and `invalid` (1) are the
    engine's own, and a payload that declares otherwise never talks the lane
    past them. A stage may name further codes it accepts: `partial` (4) is a
    legitimate typed report an approval set can be minted from, and its
    coverage gaps travel into the pull-request body rather than stopping the
    lane. Accepting one is stated on the run surface, never silent.
    """
    payload, reason = read_json(args.payload)
    accepted = set(args.accept_exit_code or ()) | {0}
    if args.exit_code not in accepted:
        details = _reason_lines(payload) if payload else []
        if not details and reason:
            details = [reason]
        return refuse(
            args.stage, "apply-stage-failed",
            f"the engine refused at {code_span(args.stage)} "
            f"(exit {args.exit_code})", details)
    if args.exit_code != 0:
        state = payload.get("status") if payload else None
        write_surface(
            f"\n**{args.stage}:** accepted exit {args.exit_code} — the engine "
            f"returned {code_span(state)}, a state this stage proceeds from.\n")
    if payload is None:
        return refuse(
            args.stage, "apply-stage-produced-nothing",
            f"{code_span(args.stage)} reported success but left no artifact "
            f"to carry forward — {reason}")
    return 0


def run_id(args):
    """The dispatched report run id, shape-checked before it names a run.

    The raw input reaches two consumers that read it differently: a
    `gh api repos/.../actions/runs/<id>` path, where a `/`-bearing value walks
    to another run's path, and `download-artifact`'s `run-id`, which `parseInt`s
    it — so `1/../../repos/other/repo/actions/runs/999` is one run to the API
    and the integer `1` to the download, and the lane could bind one run while
    the artifact comes from another. A run is named by decimal digits and
    nothing else; validated here, both consumers read the one value this wrote.
    """
    if not RUN_ID.fullmatch(args.run_id):
        return refuse(
            "dispatch", "apply-run-id-not-numeric",
            f"{code_span(args.run_id)} is not a run id — a run is named by its "
            f"decimal id, never by a path a command could walk to another run")
    # Appended: the caller points this at $GITHUB_OUTPUT, which accumulates
    # every output a step declares.
    write_file(args.out, f"report_run_id={args.run_id}\n", mode="a")
    return 0


def record_args(args):
    """The dispatched record subset, as inert argv for `mint-approval`.

    The named subset *is* the semantic approval, so it is the one input a human
    supplies to this lane — and the one place a dispatch string reaches a
    command line. Each token must be a record digest and nothing else: a
    validated sha256 cannot be read as a flag, a path, or a shell word.
    """
    tokens = [t for t in re.split(r"[\s,]+", args.records) if t]
    if not tokens:
        return refuse(
            "dispatch", "apply-empty-selection",
            "no record digests were dispatched — the named subset is the "
            "approval, so an empty one approves nothing")
    for token in tokens:
        if not SHA256.match(token):
            return refuse(
                "dispatch", "apply-record-not-a-digest",
                f"{code_span(token)} is not a record digest — a selection "
                f"names records by their sha256 digest, never by id, path, or "
                f"anything a command line could read as a flag")
    if len(set(tokens)) != len(tokens):
        return refuse(
            "dispatch", "apply-duplicate-selection",
            "a record digest was dispatched more than once")
    write_file(args.out, "".join(f"--record\n{t}\n" for t in tokens))
    return 0


def config_digest(args):
    """The current audit-configuration digest, read off the engine's own
    `audit-config-digest` command (aj604/toolshed#175 — never a fresh full
    audit's lineage: a lane that ran that audit under a different declared
    evidence boundary than the report it is checking against would derive an
    incomparable digest, structurally, no matter how current the repository
    is).

    Supplied to `validate-report`/`mint-approval`, configuration drift is
    compared; omitted, it is never compared and a config-stale report would be
    laundered clean by the weaker check. So an unavailable digest refuses
    rather than silently dropping the flag.
    """
    payload, reason = read_json(args.report)
    if payload is None:
        return refuse("revalidation", "apply-config-digest-unavailable", reason)
    digest = payload.get("audit_config_digest")
    if not isinstance(digest, str) or not SHA256.match(digest):
        return refuse(
            "revalidation", "apply-config-digest-unavailable",
            "the current audit configuration digest could not be read from "
            "the engine's audit-config-digest command, so configuration "
            "drift cannot be compared — refusing rather than checking less "
            "than the lane claims to")
    write_file(args.out, digest)
    return 0


def policy_eligibility(args):
    """Render the policy's per-record decisions and gate downstream jobs.

    The engine owns every eligibility judgment. It has no public read-back
    validator for this ephemeral command result, so this is a fail-closed
    adapter envelope check: it confirms only the fields the scheduler must
    render and that the eligible summary agrees with the decision envelopes.
    It does not know any finding code, policy class, or eligibility rule. The
    one scheduler decision it publishes is whether there is a subset worth
    handing to `policy-mint`, which derives that subset again itself.
    """
    payload, reason = read_json(args.eligibility)
    if payload is None:
        return refuse(
            "policy eligibility", "apply-policy-eligibility-invalid", reason)

    policy = payload.get("policy")
    decisions = payload.get("decisions")
    eligible = payload.get("eligible")
    report_digest = payload.get("report_digest")
    malformed = (
        payload.get("status") != "ok"
        or not isinstance(policy, dict)
        or not isinstance(policy.get("id"), str)
        or not policy.get("id").strip()
        or not isinstance(decisions, list)
        or not isinstance(eligible, list)
        or not isinstance(report_digest, str)
        or not SHA256.fullmatch(report_digest)
        or len(set(eligible)) != len(eligible)
        or any(not isinstance(d, str) or not SHA256.fullmatch(d)
               for d in eligible)
    )

    admitted = []
    if not malformed:
        for decision in decisions:
            if not isinstance(decision, dict):
                malformed = True
                break
            digest = decision.get("digest")
            eligible_class = decision.get("eligible_class")
            refusal_payload = decision.get("refusal")
            if (
                not isinstance(digest, str)
                or not SHA256.fullmatch(digest)
                or not isinstance(decision.get("id"), str)
                or not isinstance(decision.get("code"), str)
                or ((eligible_class is None) == (refusal_payload is None))
                or (eligible_class is not None
                    and not isinstance(eligible_class, str))
                or (refusal_payload is not None
                    and not isinstance(refusal_payload, dict))
            ):
                malformed = True
                break
            if eligible_class is not None:
                admitted.append(digest)

    if malformed or admitted != eligible:
        return refuse(
            "policy eligibility", "apply-policy-eligibility-invalid",
            "the engine's eligibility artifact is malformed or its eligible "
            "summary disagrees with the per-record decisions — refusing "
            "rather than guessing which records the policy admitted")

    surface = [
        "## Doc apply: policy eligibility",
        "",
        f"- Policy: {code_span(policy.get('id'))}",
        f"- Report: {code_span(report_digest)}",
        f"- Eligible records: {len(eligible)}",
        "",
        "### Decisions",
        "",
    ]
    for decision in decisions:
        if decision.get("eligible_class") is not None:
            outcome = (
                f"eligible as {code_span(decision.get('eligible_class'))}")
        else:
            refusal_payload = decision.get("refusal") or {}
            outcome = (
                f"refused by {code_span(refusal_payload.get('code'))}: "
                f"{code_span(refusal_payload.get('message'))}")
        surface.append(
            f"- {code_span(decision.get('id'))} "
            f"{code_span(decision.get('code'))}: {outcome}")

    if not eligible:
        surface += [
            "",
            "**No branch and no pull request were created.** The standing "
            "policy admitted no record from this report; a human may still "
            "select records through the manual apply lane.",
        ]
    surface.append("")
    write_surface("\n".join(surface))
    write_file(args.out, f"eligible={'true' if eligible else 'false'}\n",
               mode="a")
    return 0


def _validated_digest(stage, app, field="digest",
                      closing=NOTHING_CREATED):
    """`(digest, None)` when `app[field]` is a sha256 digest, else
    `(None, exit_status)` — the one shape check every surface that lets a digest
    reach a ref, a title, or a commit message needs. A digest is content an
    artifact declared; a corrupt one that only gets sliced (`digest[:12]`) or
    interpolated raw could carry a newline into `gh pr create --title` or a
    forged trailer into a commit message. So it is verified here, not assumed,
    exactly as `branch-name` verifies the ref it derives.
    """
    digest = app.get(field)
    if isinstance(digest, str) and SHA256.match(digest):
        return digest, None
    return None, refuse(
        stage, "apply-approval-digest-invalid",
        f"the approval set declares no sha256 {field} ({code_span(digest)})",
        closing=closing)


def approval_digest(args):
    """The minted approval digest, as a `$GITHUB_OUTPUT` line.

    It travels between jobs so the credentialed job can bind the approval-set
    artifact it downloaded to the one the revalidation job actually minted
    (`apply-plan --expected-digest`).
    """
    payload, reason = read_json(args.approval)
    if payload is None:
        return refuse("minting", "apply-approval-digest-invalid", reason)
    digest, bad = _validated_digest("minting", payload)
    if bad is not None:
        return bad
    # Appended: the caller points this at $GITHUB_OUTPUT, which accumulates
    # every output a step declares.
    write_file(args.out, f"approval_digest={digest}\n", mode="a")
    return 0


def _derived_branch(digest):
    """The one place the branch this approval lands on is spelled.

    Derived, so the branch itself is provenance and no dispatch input reaches a
    ref a credentialed job writes to — and re-derivable, which is what lets
    every recovery step below check that the branch it is about to name is this
    approval's own and not some other ref that happens to be passed in.
    """
    return f"doc-lifecycle/apply-{digest[:12]}"


def branch_name(args):
    """The branch the change lands on: derived, never dispatched."""
    payload, reason = read_json(args.approval)
    if payload is None:
        return refuse("apply", "apply-approval-digest-invalid", reason)
    digest, bad = _validated_digest("apply", payload)
    if bad is not None:
        return bad
    write_file(args.out, f"{_derived_branch(digest)}\n")
    return 0


def _unsafe_path_reason(path):
    """Why `path` must not reach `git add`, or None.

    The applier already routed every one of these through
    `paths.authorize_path`, so this is a second, independent reading of the
    same string at the boundary where it stops being data and becomes an
    argument. It is deliberately not the full authorization check — that has
    one owner — only the shapes that are dangerous *here*.
    """
    if not isinstance(path, str) or not path:
        return "not a path"
    for ch in path:
        category = unicodedata.category(ch)
        if category in ("Cc", "Cf", "Cs", "Co", "Cn"):
            return "holds a control character"
        # Zl/Zp are U+2028/U+2029: not C*, but `code_span` and `paths.py`
        # both reject them, so this second reading refuses them too rather
        # than passing a line/paragraph separator a stricter check already bars.
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


def staged_paths(args):
    """The exact path list the credentialed job stages, or nothing at all.

    The applier's `changed_paths` is the whole write set of a run whose
    whole-diff confinement check already passed, so it is what `git add` gets —
    never a pathspec, never `-A`. Everything below refuses instead of
    narrowing: a result that is not `clean`, a path the approval set's allowed
    mutation scope does not cover, and a path git would read as anything but a
    file name.
    """
    res, reason = read_json(args.result)
    if res is None:
        return refuse("apply", "apply-result-unreadable", reason)
    app, reason = read_json(args.approval)
    if app is None:
        return refuse("apply", "apply-approval-unreadable", reason)

    if res.get("status") != "clean":
        return refuse(
            "apply", "apply-result-not-clean",
            f"the applier returned {code_span(res.get('status'))} — only a "
            f"clean apply, whose complete working-tree diff was inside the "
            f"approved mutation scope, may be staged",
            _reason_lines(res))
    if res.get("already_applied"):
        return refuse(
            "apply", "apply-already-landed",
            "the approved changes are already in the base — the plan's "
            "postimages were re-derived onto the committed baseline and match "
            "it byte for byte, so there is nothing to open a pull request for")

    paths = res.get("changed_paths") or []
    if not paths:
        return refuse(
            "apply", "apply-nothing-changed",
            "the apply wrote nothing, so there is no diff to review")

    # Exhaustively, as the engine reports its own problems: a reader fixing one
    # path at a time learns nothing about the second.
    scope = set((app.get("scope") or {}).get("paths") or [])
    unsafe = [(p, why) for p, why in
              ((p, _unsafe_path_reason(p)) for p in paths) if why]
    if unsafe:
        return refuse(
            "apply", "apply-path-unsafe",
            "the apply result names path(s) this lane refuses to hand to git",
            [f"{code_span(p)} {why}" for p, why in unsafe])
    outside = [p for p in paths if p not in scope]
    if outside:
        return refuse(
            "apply", "apply-path-outside-approved-scope",
            "the apply result names path(s) the approval set's allowed "
            "mutation scope does not cover",
            [code_span(p) for p in outside]
            + ["approved scope: "
               + (", ".join(code_span(p) for p in sorted(scope)) or "none")])

    write_file(args.out, "".join(f"{p}\0" for p in paths))
    return 0


def _nul_paths(path):
    """The NUL-separated path list git wrote (or this script did), as a list."""
    try:
        with open(path, encoding="utf-8") as fh:
            raw = fh.read()
    except (OSError, UnicodeDecodeError) as exc:
        return None, f"cannot read {path}: {exc}"
    return [p for p in raw.split("\0") if p], None


def verify_staged(args):
    """What git staged must equal what the verified apply result emitted.

    `staged-paths` decides what to stage; this checks what actually got staged,
    from git's own plumbing rather than from the same list read twice — a
    pathspec that expanded further, a hook, or anything else that touched the
    tree between the apply and the commit shows up here as a refusal instead of
    riding into a diff a reviewer is told is confined.
    """
    approved, reason = _nul_paths(args.paths)
    if approved is None:
        return refuse("apply", "apply-staging-unreadable", reason)
    staged, reason = _nul_paths(args.staged)
    if staged is None:
        return refuse("apply", "apply-staging-unreadable", reason)
    unstaged, reason = _nul_paths(args.unstaged)
    if unstaged is None:
        return refuse("apply", "apply-staging-unreadable", reason)

    extra = sorted(set(staged) - set(approved))
    if extra:
        return refuse(
            "apply", "apply-staging-not-confined",
            "git staged path(s) the apply result did not emit",
            [code_span(p) for p in extra])
    missing = sorted(set(approved) - set(staged))
    if missing:
        return refuse(
            "apply", "apply-staging-incomplete",
            "the apply result emitted path(s) git did not stage — the commit "
            "would not be the change this run certified",
            [code_span(p) for p in missing])
    if unstaged:
        return refuse(
            "apply", "apply-worktree-not-clean",
            "the working tree holds change(s) outside the staged set",
            [code_span(p) for p in sorted(set(unstaged))])
    return 0


def _counts(app):
    return len(app.get("records") or []), len(app.get("skipped") or [])


def pr_title(args):
    """One line, from validated artifacts only — no dispatched text."""
    res, reason = read_json(args.result)
    if res is None:
        return refuse("apply", "apply-result-unreadable", reason)
    app, reason = read_json(args.approval)
    if app is None:
        return refuse("apply", "apply-approval-unreadable", reason)
    approved, _ = _counts(app)
    digest, bad = _validated_digest("apply", app)
    if bad is not None:
        return bad
    written = len(res.get("changed_paths") or [])
    write_file(args.out, (
        f"docs: apply {approved} approved record(s) to {written} file(s) "
        f"[approval {digest[:12]}]\n"))
    return 0


def _semantic_review(app, approved, skipped):
    """Who performed the semantic approval this apply rests on.

    Two minters, and the difference is the whole point of saying it here. A
    human dispatch *is* the semantic approval, performed before the lane ran.
    A standing auto-apply policy mints without anybody selecting anything, so
    the semantic review has not happened yet — reviewing this pull request is
    it, and a reviewer who cannot tell the two apart would perform the wrong
    one. The policy's id is consumer-written content, so it goes through
    `code_span` like every other interpolated value.
    """
    minter = app.get("minter") or {}
    counts = f"{approved} approved record(s) applied, {skipped} skipped."
    if minter.get("kind") != "policy":
        return counts + (
            " The named record subset dispatched to this lane **is** the "
            "semantic approval; merging this pull request is change approval "
            "of the actual diff.")
    return counts + (
        " **No human selected these records.** The standing auto-apply policy "
        f"{code_span(minter.get('id'))} minted the approval set, for finding "
        "classes it is configured to treat as mechanical remedies. **Reviewing "
        "this pull request is the semantic review** for what the policy "
        "minted, as well as change approval of the actual diff.")


def _record_line(entry):
    # Every field below is content a model wrote; none of it may restructure
    # the page a reviewer reads before performing change approval.
    return (f"- {code_span(entry.get('id'))} "
            f"{code_span(entry.get('code', '—'))} "
            f"{code_span(entry.get('path', '—'))} "
            f"— digest {code_span(entry.get('digest'))}")


def pr_body(args):
    """The PR body: the whole provenance of one apply, in one page.

    Change approval is a person merging this PR, so the page has to carry
    everything that approval rests on — which approval set authorized it, which
    report that came from, what was deliberately skipped, what the audit never
    examined, and that the diff was confined to the approved scope.
    """
    res, reason = read_json(args.result)
    if res is None:
        return refuse("apply", "apply-result-unreadable", reason)
    app, reason = read_json(args.approval)
    if app is None:
        return refuse("apply", "apply-approval-unreadable", reason)
    rep, reason = read_json(args.report)
    if rep is None:
        return refuse("apply", "apply-report-unreadable", reason)

    approved, skipped = _counts(app)
    lineage = app.get("lineage") or rep.get("lineage") or {}
    changed = res.get("changed_paths") or []

    lines = [
        "## Documentation apply",
        "",
        _semantic_review(app, approved, skipped),
        "",
        "### Authority",
        "",
        f"- Approval digest: {code_span(app.get('digest'))}",
        f"- Approval state when minted: {code_span(app.get('status'))}",
        f"- Minter: {code_span((app.get('minter') or {}).get('kind'))} "
        f"{code_span((app.get('minter') or {}).get('id'))}",
        f"- Report digest: {code_span(app.get('report_digest'))}",
        f"- Report state: {code_span(rep.get('status'))}",
        f"- Plan digest: {code_span(res.get('plan_digest'))}",
        "",
        "### Lineage",
        "",
        f"- Repository: {code_span(lineage.get('repository'))}",
        f"- Base commit: {code_span(lineage.get('base_commit'))}",
        f"- Audit mode: {code_span(lineage.get('audit_mode'))}",
        f"- Registry digest: {code_span(lineage.get('registry_digest'))}",
        f"- Inventory digest: {code_span(lineage.get('inventory_digest'))}",
        f"- Audit configuration digest: "
        f"{code_span(lineage.get('audit_config_digest'))}",
        f"- Ruleset version: {code_span(lineage.get('ruleset_version'))}",
        f"- Plugin version: {code_span(lineage.get('plugin_version'))}",
        "",
        "### Confinement",
        "",
        f"- Result: {code_span(res.get('status'))} — the complete working-tree "
        "diff was inside the approval set's allowed mutation scope, and every "
        "declared postimage was checked before a byte landed.",
        f"- Paths written ({len(changed)}): "
        + (", ".join(code_span(p) for p in changed) or "none"),
        "- Nothing outside this list was staged: the credentialed job stages "
        "exactly the paths this result emitted.",
        "",
        "### Approved records",
        "",
    ]
    lines += ([_record_line(e) for e in app.get("records") or []]
              or ["None — the approval set selected nothing."])

    lines += ["", "### Skipped records", ""]
    if app.get("skipped"):
        lines += [_record_line(e) for e in app["skipped"]]
        lines += ["",
                  "Skipped records stay in the report; a later dispatch may "
                  "approve them, and the preimage check refuses honestly if "
                  "this change moved the text they describe."]
    else:
        lines.append("None — every record in the report was approved.")

    lines += ["", "### Coverage gaps", ""]
    if rep.get("incomplete"):
        lines += [f"- {code_span(e.get('scope'))}: {code_span(e.get('reason'))}"
                  for e in rep["incomplete"]]
        lines.append("")
        lines.append(
            "A missing finding proves nothing for the scopes above — the "
            "audit did not examine them.")
    else:
        lines.append(
            "No coverage gaps: the audit examined every scope it declared.")

    if args.approval_summary:
        try:
            with open(args.approval_summary, encoding="utf-8") as fh:
                summary = fh.read()
        except (OSError, UnicodeDecodeError) as exc:
            return refuse("apply", "apply-approval-summary-unreadable",
                          f"cannot read {args.approval_summary}: {exc}")
        lines += ["", "---", "",
                  "<!-- rendered by `doclifecycle render-approval` -->", "",
                  summary.rstrip("\n")]

    write_file(args.out, "\n".join(lines) + "\n")
    return 0


def commit_message(args):
    """The commit message: subject, what landed, and the approval trailers."""
    res, reason = read_json(args.result)
    if res is None:
        return refuse("apply", "apply-result-unreadable", reason)
    app, reason = read_json(args.approval)
    if app is None:
        return refuse("apply", "apply-approval-unreadable", reason)

    approved, skipped = _counts(app)
    digest, bad = _validated_digest("apply", app)
    if bad is not None:
        return bad
    # The report digest is interpolated raw into the message body below (not a
    # code span — this is a commit message, not Markdown), so it is shape-checked
    # the same way, lest a newline in it forge a trailer git would parse.
    report_digest, bad = _validated_digest("apply", app, "report_digest")
    if bad is not None:
        return bad
    changed = res.get("changed_paths") or []
    lines = [
        f"docs: apply {approved} approved record(s) [approval {digest[:12]}]",
        "",
        f"{approved} approved, {skipped} skipped, from report "
        f"{report_digest}.",
        "",
        "Paths written:",
    ]
    lines += [f"- {p}" for p in changed]
    lines += ["",
              "The approval set is an untracked artifact; its digest and "
              "summary travel here and in the pull request body.",
              ""]

    trailers = None
    if args.trailers:
        try:
            with open(args.trailers, encoding="utf-8") as fh:
                trailers = fh.read()
        except (OSError, UnicodeDecodeError) as exc:
            return refuse("apply", "apply-trailers-unreadable",
                          f"cannot read {args.trailers}: {exc}")
        if not trailers.strip():
            # Never fall back here. The engine's block carries
            # `Doc-Lifecycle-Approval-State`, which is what tells a block
            # copied from a stale approval set from a live one; a hand-built
            # pair of trailers would land the change looking authorized
            # without it.
            return refuse(
                "apply", "apply-trailers-empty",
                f"{code_span(args.trailers)} is empty — `render-approval "
                f"--trailers` printed nothing, which it does only for an "
                f"approval set it refused")
    if not trailers:
        # The engine renders these; without its file the digest still travels,
        # because it is the only part of an approval set that reaches the
        # repository at all.
        trailers = (f"Doc-Lifecycle-Approval: {digest}\n"
                    f"Doc-Lifecycle-Report: {report_digest}\n")
    write_file(args.out, "\n".join(lines) + trailers)
    return 0


# -- recovery (aj604/toolshed#198) -------------------------------------------

# A git object id, sha-1 or sha-256, spelled as `verify-apply-bytes.py` spells
# it — this script hands one to that one, and to `git push`.
OBJECT_ID = re.compile(r"[0-9a-f]{40}([0-9a-f]{24})?")
# `<object id><tab><ref>`, which is all `git ls-remote` writes. A line shaped
# any other way is a remote this lane did not understand, never an empty one.
REMOTE_REF = re.compile(r"^([0-9a-f]{40}(?:[0-9a-f]{24})?)\t(\S+)$")
# `git ls-remote --exit-code`'s "no matching refs": the *typed* absence, told
# apart from a remote that could not be read at all.
NO_MATCHING_REFS = 2
PULL_REQUEST_NUMBER = re.compile(r"^[0-9]+$")

RECOVERY_STATES = {
    "branch-created": (
        "branch created",
        "The verified commit was pushed to a branch that did not exist "
        "before. Nothing was overwritten.",
    ),
    "branch-reused": (
        "branch reused",
        "The derived branch already carried this approval's own verified "
        "result — an earlier attempt pushed it and did not get as far as the "
        "pull request. Its commit was re-checked against this run's certified "
        "postimages and its approval trailer before anything below was done "
        "with it; nothing was pushed and nothing was overwritten.",
    ),
    "pull-request-already-open": (
        "pull request already open",
        "A pull request for this approval is already open on this branch, so "
        "this run had nothing left to create. Review and merge that pull "
        "request: merging it is the change approval that lands the diff.",
    ),
}


def _bound_branch(stage, approval_path, branch):
    """`(the approval set's digest, None)` when `branch` is the one this
    approval derives, else `(None, exit status)`.

    Every recovery step puts the branch name on a command line — `ls-remote`, a
    fetch refspec, `gh pr list --head`, and the push itself. The name has one
    author (`branch-name`), so re-deriving it here is what keeps a recovery
    step from acting on some other ref: the only branch a run may read, reuse,
    or push is the one its own approval digest names.
    """
    app, reason = read_json(approval_path)
    if app is None:
        return None, refuse(stage, "apply-approval-unreadable", reason,
                            closing=NOTHING_TOUCHED)
    digest, bad = _validated_digest(stage, app, closing=NOTHING_TOUCHED)
    if bad is not None:
        return None, bad
    if branch != _derived_branch(digest):
        return None, refuse(
            stage, "apply-branch-not-derived",
            f"this run is working on {code_span(branch)}, which is not the "
            f"branch this approval set derives "
            f"({code_span(_derived_branch(digest))})",
            closing=NOTHING_TOUCHED)
    return digest, None


def remote_branch(args):
    """What the remote holds at the derived branch, if anything.

    The recovery question, asked before anything is pushed, and it has three
    answers that must stay three: a listing (the branch stands — an earlier
    attempt got that far, and what it holds decides whether this run may reuse
    it), `--exit-code` 2 (no such ref, so this is a first run), and any other
    status (the remote could not be read, which is *not* the same as empty and
    must never be read as one — that reading would push onto an unexamined
    ref). Writes the commit the branch points at, or an empty file.
    """
    _, bad = _bound_branch("recovery", args.approval, args.branch)
    if bad is not None:
        return bad
    if args.exit_code not in (0, NO_MATCHING_REFS):
        return refuse(
            "recovery", "apply-remote-unreadable",
            f"the remote could not be listed (exit {args.exit_code}), so "
            f"whether {code_span(args.branch)} already exists is unanswerable "
            f"— refusing rather than treating an unreadable remote as an "
            f"empty one", closing=NOTHING_TOUCHED)
    try:
        with open(args.listing, encoding="utf-8") as fh:
            listing = fh.read()
    except (OSError, UnicodeDecodeError) as exc:
        return refuse("recovery", "apply-remote-unreadable",
                      f"cannot read {args.listing}: {exc}",
                      closing=NOTHING_TOUCHED)

    entries = [line for line in listing.splitlines() if line.strip()]
    if args.exit_code == NO_MATCHING_REFS or not entries:
        write_file(args.out, "")
        return 0
    matched = [REMOTE_REF.match(entry) for entry in entries]
    if len(entries) != 1 or matched[0] is None \
            or matched[0].group(2) != f"refs/heads/{args.branch}":
        return refuse(
            "recovery", "apply-remote-branch-unreadable",
            f"the remote's listing for {code_span(args.branch)} is not one "
            f"branch and one commit id, so what stands there is not a "
            f"question with one answer",
            [code_span(entry) for entry in entries],
            closing=NOTHING_TOUCHED)
    write_file(args.out, f"{matched[0].group(1)}\n")
    return 0


def existing_pull_request(args):
    """The pull request already open for this approval, if there is one.

    What makes a re-run idempotent rather than a duplicate-creation failure:
    an open pull request whose head is this approval's branch and whose body
    carries this approval's digest is this run's own outcome, reached by an
    earlier attempt. Anything else open on that head is a conflict — another
    approval's review door, or one aimed at a base this run is not applying
    onto — and is refused rather than added to, because the alternative is
    two open pull requests claiming one branch.
    """
    digest, bad = _bound_branch("recovery", args.approval, args.branch)
    if bad is not None:
        return bad
    payload, reason = read_json(args.listing)
    if payload is None:
        return refuse("recovery", "apply-pull-request-listing-unreadable",
                      reason, closing=NOTHING_TOUCHED)
    if not isinstance(payload, list) or any(
            not isinstance(entry, dict) for entry in payload):
        return refuse(
            "recovery", "apply-pull-request-listing-unreadable",
            "the open pull requests were not listed as a list of pull "
            "requests, so whether one is already open for this approval is "
            "unanswerable", closing=NOTHING_TOUCHED)
    if not payload:
        write_file(args.out, "")
        return 0

    off_branch = [entry for entry in payload
                  if entry.get("headRefName") != args.branch]
    if off_branch:
        return refuse(
            "recovery", "apply-pull-request-listing-unreadable",
            f"the listing carries pull request(s) whose head is not "
            f"{code_span(args.branch)}, so it does not answer the question it "
            f"was asked",
            [code_span(entry.get("headRefName")) for entry in off_branch],
            closing=NOTHING_TOUCHED)
    if len(payload) > 1:
        return refuse(
            "recovery", "apply-pull-request-conflict",
            f"{len(payload)} pull requests are open on "
            f"{code_span(args.branch)} — this lane opens one review door per "
            f"approval, and which of these is it is not something this run may "
            f"decide",
            [f"#{code_span(entry.get('number'))}" for entry in payload],
            closing=NOTHING_TOUCHED)

    entry = payload[0]
    number = entry.get("number")
    if not PULL_REQUEST_NUMBER.fullmatch(str(number)):
        return refuse(
            "recovery", "apply-pull-request-listing-unreadable",
            f"the open pull request is numbered {code_span(number)}, which is "
            f"not a pull request number", closing=NOTHING_TOUCHED)
    body = entry.get("body")
    if not isinstance(body, str) or digest not in body:
        return refuse(
            "recovery", "apply-pull-request-conflict",
            f"a pull request is already open on {code_span(args.branch)} whose "
            f"body does not carry this approval's digest, so it is some other "
            f"change's review door and this run must not add to it",
            [f"open: #{number}", f"this approval: {code_span(digest)}"],
            closing=NOTHING_TOUCHED)
    if entry.get("baseRefName") != args.base:
        return refuse(
            "recovery", "apply-pull-request-conflict",
            f"the pull request already open on {code_span(args.branch)} is "
            f"aimed at {code_span(entry.get('baseRefName'))}, and this run "
            f"applied onto {code_span(args.base)} — merging it would land this "
            f"approval somewhere it was not approved for",
            [f"open: #{number}"], closing=NOTHING_TOUCHED)
    write_file(args.out, f"{number}\n")
    return 0


def recovery(args):
    """One terminal recovery outcome, stated on the run surface.

    Four outcomes exist and a reader must be able to tell them apart: the
    branch was created, the branch was reused, a pull request was already
    open, or something conflicted. The conflicts are the typed refusals above
    and in `verify-apply-bytes.py`; the other three are here, because a run
    that quietly did nothing looks exactly like a run that quietly overwrote
    something.
    """
    digest, bad = _bound_branch("recovery", args.approval, args.branch)
    if bad is not None:
        return bad
    heading, meaning = RECOVERY_STATES[args.state]

    lines = [f"## Doc apply: {heading}", "",
             f"- Approval digest: {code_span(digest)}",
             f"- Branch: {code_span(args.branch)}"]
    if args.state == "pull-request-already-open":
        if not PULL_REQUEST_NUMBER.fullmatch(args.pull_request or ""):
            return refuse(
                "recovery", "apply-recovery-state-incomplete",
                f"{code_span(args.state)} names no pull request "
                f"({code_span(args.pull_request)}), so the outcome it claims "
                f"points at nothing a reviewer can open",
                closing=NOTHING_TOUCHED)
        lines.append(f"- Pull request: #{args.pull_request}")
    else:
        if not OBJECT_ID.fullmatch(args.commit or ""):
            return refuse(
                "recovery", "apply-recovery-state-incomplete",
                f"{code_span(args.state)} names no commit "
                f"({code_span(args.commit)}), so what the branch carries is "
                f"not stated", closing=NOTHING_TOUCHED)
        lines.append(f"- Commit: {code_span(args.commit)}")
    lines += ["", meaning, ""]
    write_surface("\n".join(lines))
    return 0


# -- argv --------------------------------------------------------------------

def _parser():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="mode", required=True)

    verify = sub.add_parser("verify-report")
    verify.add_argument("--report", required=True)
    verify.add_argument("--expected-digest", required=True)
    verify.set_defaults(run=verify_report)

    gate_cmd = sub.add_parser("gate")
    gate_cmd.add_argument("--stage", required=True)
    gate_cmd.add_argument("--payload", required=True)
    gate_cmd.add_argument("--exit-code", required=True, type=int)
    gate_cmd.add_argument(
        "--accept-exit-code", action="append", type=int, default=None,
        help="a further engine exit code this stage proceeds from (repeatable)")
    gate_cmd.set_defaults(run=gate)

    runid = sub.add_parser("run-id")
    runid.add_argument("--run-id", required=True)
    runid.add_argument("--out", required=True)
    runid.set_defaults(run=run_id)

    records = sub.add_parser("record-args")
    records.add_argument("--records", required=True)
    records.add_argument("--out", required=True)
    records.set_defaults(run=record_args)

    config = sub.add_parser("config-digest")
    config.add_argument("--report", required=True)
    config.add_argument("--out", required=True)
    config.set_defaults(run=config_digest)

    policy = sub.add_parser("policy-eligibility")
    policy.add_argument("--eligibility", required=True)
    policy.add_argument("--out", required=True)
    policy.set_defaults(run=policy_eligibility)

    approval = sub.add_parser("approval-digest")
    approval.add_argument("--approval", required=True)
    approval.add_argument("--out", required=True)
    approval.set_defaults(run=approval_digest)

    branch = sub.add_parser("branch-name")
    branch.add_argument("--approval", required=True)
    branch.add_argument("--out", required=True)
    branch.set_defaults(run=branch_name)

    staged = sub.add_parser("staged-paths")
    staged.add_argument("--result", required=True)
    staged.add_argument("--approval", required=True)
    staged.add_argument("--out", required=True)
    staged.set_defaults(run=staged_paths)

    verify_staging = sub.add_parser("verify-staged")
    verify_staging.add_argument("--paths", required=True)
    verify_staging.add_argument("--staged", required=True)
    verify_staging.add_argument("--unstaged", required=True)
    verify_staging.set_defaults(run=verify_staged)

    title = sub.add_parser("pr-title")
    title.add_argument("--result", required=True)
    title.add_argument("--approval", required=True)
    title.add_argument("--out", required=True)
    title.set_defaults(run=pr_title)

    body = sub.add_parser("pr-body")
    body.add_argument("--result", required=True)
    body.add_argument("--approval", required=True)
    body.add_argument("--report", required=True)
    body.add_argument("--approval-summary", default=None)
    body.add_argument("--out", required=True)
    body.set_defaults(run=pr_body)

    commit = sub.add_parser("commit-message")
    commit.add_argument("--result", required=True)
    commit.add_argument("--approval", required=True)
    commit.add_argument("--trailers", default=None)
    commit.add_argument("--out", required=True)
    commit.set_defaults(run=commit_message)

    remote = sub.add_parser("remote-branch")
    remote.add_argument("--listing", required=True)
    remote.add_argument("--exit-code", required=True, type=int)
    remote.add_argument("--branch", required=True)
    remote.add_argument("--approval", required=True)
    remote.add_argument("--out", required=True)
    remote.set_defaults(run=remote_branch)

    open_pr = sub.add_parser("existing-pull-request")
    open_pr.add_argument("--listing", required=True)
    open_pr.add_argument("--approval", required=True)
    open_pr.add_argument("--branch", required=True)
    open_pr.add_argument("--base", required=True)
    open_pr.add_argument("--out", required=True)
    open_pr.set_defaults(run=existing_pull_request)

    state = sub.add_parser("recovery")
    state.add_argument("--state", required=True, choices=sorted(RECOVERY_STATES))
    state.add_argument("--branch", required=True)
    state.add_argument("--approval", required=True)
    state.add_argument("--commit", default=None)
    state.add_argument("--pull-request", default=None)
    state.set_defaults(run=recovery)

    return parser


def main():
    args = _parser().parse_args()
    return args.run(args)


if __name__ == "__main__":
    sys.exit(main())
