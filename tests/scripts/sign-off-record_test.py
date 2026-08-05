#!/usr/bin/env python3
"""Holds the #203 sign-off record's numeric claims to the artifacts they describe.

Issue #203's deliverable is an evidence record, and the same defect recurred in
every one of its three review rounds: **a number in prose drifted from the
artifact under it.** The race-test count (six vs seven), the pinned-suite count
(fourteen, then eighteen, both wrong), and the engine-test count (1348 vs 1349)
each shipped wrong and each was caught by a human reader rather than by the
gate. Nothing in the release gate compared prose against artifact, so every one
of those was invisible to a green run.

This is that comparison. It is deliberately narrow: it checks the claims that
can be *derived* from something authoritative, and it says nothing about prose
that cannot be. Specifically:

1. The pinned-suite count is derived from `release-manifest.py`'s own
   `GATE_MANIFEST`, never from a number typed twice.
2. Every suite that criterion names exists on disk.
3. Every engine-test count stated anywhere in the record agrees with every
   other. This cannot be checked against a real run here — discovering and
   running 1349 tests inside a script suite would make the gate quadratic — so
   it is an internal-consistency check, which is precisely the failure that
   occurred: `gate-results.md` disagreed with itself.
4. The race-test audit's prose totals match the rows of its own table.
5. **No gate-shaped number reaches the record's prose except a derived one.**
   Checks 1-4 each pin a *phrasing*, and a phrasing they do not know is a
   phrasing they do not check: a seventh instance of this record's own defect
   class shipped in #229 as "(inside the 28)", three lines above two counts
   round 4 had corrected, because that is a third way of saying the
   script-suite total and neither pattern matches it. Check 5 inverts the
   default — in any paragraph that mentions the suites, a number is a failure
   *unless* it is a value derived here or one of a short list of documented
   non-counts. An unknown phrasing now fails closed instead of passing
   silently.

A wiring suite in the manner of `doc-contract_test.py`. Checks 1-4 inherit that
suite's documented ceiling: they catch *the claims they name* drifting, not new
false claims appearing. Check 5 is the deliberate exception — it is written
against the class rather than the instances — and its own limits are stated on
`NoUncheckedGateCountReachesTheProse` rather than pretended away.

Run: python3 tests/scripts/sign-off-record_test.py
"""

import importlib.util
import os
import re
import unittest

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
RECORD = os.path.join(ROOT, "tests", "baselines", "issue-203-sign-off-gate")
MANIFEST = os.path.join(ROOT, ".github", "scripts", "release-manifest.py")
DECISIONS = os.path.join(ROOT, "docs", "decisions.md")
CRITERION = "issue #168 sign-off regressions"

# Prose spells these out; the artifacts count in digits.
WORDS = {
    1: "one", 2: "two", 3: "three", 4: "four", 5: "five", 6: "six",
    7: "seven", 8: "eight", 9: "nine", 10: "ten", 11: "eleven",
    12: "twelve", 13: "thirteen", 14: "fourteen", 15: "fifteen",
    16: "sixteen", 17: "seventeen", 18: "eighteen", 19: "nineteen",
    20: "twenty",
}


def read(path):
    with open(path, encoding="utf-8") as handle:
        return handle.read()


# A quotation must never be edited to satisfy a consistency check — the
# reviewers ran before #203 changed anything, so they say 1344 engine tests and
# 28/28 suites, correctly and permanently. Editing that would be falsifying
# evidence, the precise opposite of why it is retained.
#
# But the exemption is *the quoted blocks*, not the files holding them. Those
# files also carry ~66 lines of authored analysis — including the corrected
# provenance narrative — and an earlier file-level exemption left that prose
# unguarded: a planted "the criterion now names eighteen suites, and the engine
# suite ran 9999 tests" inside an authored header passed the whole gate. The
# hole was created by the exemption itself, not by the "new claims" ceiling
# this suite already acknowledges.
#
# So the boundary is explicit rather than inferred. `mark_quotes` wrapped each
# quotation in these markers by locating it via its exact text re-extracted
# from the session transcript, refusing unless it matched verbatim exactly
# once — the markers sit outside the quote and change not one character of it.
# Inferring the boundary from the surrounding `---` rules would have been
# wrong: several reviewers' own reports contain `---` lines.
BEGIN_VERBATIM = "<!-- BEGIN VERBATIM -->"
END_VERBATIM = "<!-- END VERBATIM -->"

# The second kind of not-an-assertion, found the hard way: `gate-results.md`
# carries a drift-history table that *quotes the wrong numbers on purpose* —
# "28/28 suites passed", "eighteen suites pinned" — as the record of what this
# ticket got wrong. Every one of those is a false claim by construction, and a
# guard that reads them as live assertions demands the history be falsified to
# go green. That is the same error as editing a reviewer's quotation, in a
# different costume.
#
# It is a separate marker rather than the same one because the two exemptions
# rest on different grounds and a reader should be able to tell them apart: a
# VERBATIM block is someone else's words, a QUOTED-CLAIMS block is this
# record's own record of its errors.
BEGIN_QUOTED_CLAIMS = "<!-- BEGIN QUOTED-CLAIMS -->"
END_QUOTED_CLAIMS = "<!-- END QUOTED-CLAIMS -->"

MARKERS = ((BEGIN_VERBATIM, END_VERBATIM),
           (BEGIN_QUOTED_CLAIMS, END_QUOTED_CLAIMS))
OPENERS = {begin for begin, _ in MARKERS}
CLOSERS = {end for _, end in MARKERS}


def authored(text):
    """`text` with every quoted block removed, leaving only asserted prose.

    Two block kinds are stripped: reviewer quotations (VERBATIM) and this
    record's own quotations of its past mistakes (QUOTED-CLAIMS). Neither is a
    claim the record makes, so neither may be held to the artifacts.

    An unterminated marker drops the rest of the file, which is the safe
    direction: it can only hide asserted prose from a check, never expose a
    quotation to one. `TheQuotationBoundaryIsWellFormed` is what stops that
    from happening silently.
    """
    kept, quoting = [], False
    for line in text.splitlines():
        marker = line.strip()
        if marker in OPENERS:
            quoting = True
        elif marker in CLOSERS:
            quoting = False
        elif not quoting:
            kept.append(line)
    return "\n".join(kept)


def record_files():
    """Every record file. Quotations are stripped per-file by `authored`."""
    return sorted(os.path.join(RECORD, name) for name in os.listdir(RECORD)
                  if name.endswith(".md"))


def _load(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def gate_manifest():
    return _load(MANIFEST, "release_manifest").GATE_MANIFEST


def script_suites():
    """Every suite `run-script-suites.py` runs, from its own glob."""
    runner = _load(
        os.path.join(ROOT, ".github", "scripts", "run-script-suites.py"),
        "run_script_suites")
    return runner.discover(os.path.join(ROOT, "tests", "scripts"))


def wired_suites():
    """Every suite `release-manifest.py` accounts for, from its own audit."""
    return _load(MANIFEST, "release_manifest").audit(ROOT).gate


QUOTE_BEARING = ("reviewer-output-verbatim.md",
                 "reviewer-leaf-output-verbatim.md")


class TheRecordExists(unittest.TestCase):
    """If the record is gone or renamed, every check below would vacuously pass."""

    def test_the_sign_off_record_is_present(self):
        self.assertTrue(os.path.isdir(RECORD), f"no record at {RECORD}")
        present = set(os.listdir(RECORD))
        for expected in ("gate-results.md", "independent-reviews.md",
                         "race-test-audit.md") + QUOTE_BEARING:
            self.assertIn(expected, present)


class TheQuotationBoundaryIsWellFormed(unittest.TestCase):
    """The markers must balance, or `authored` silently drops real prose.

    This is the check that keeps the block-level exemption honest: without it,
    a stray or deleted `END VERBATIM` would quietly restore the file-level
    hole this suite exists to close, and every other test here would still
    pass.
    """

    @staticmethod
    def _marker_lines(text, marker):
        """Lines that *are* the marker, matching how `authored` reads them.

        Counting substrings instead would count this record's own prose
        discussing the markers — which is what happened, and is the same
        mention-versus-use confusion the fences exist to resolve.
        """
        return sum(1 for line in text.splitlines() if line.strip() == marker)

    def test_markers_balance_in_every_record_file(self):
        # Every file, not just the quote-bearing ones: gate-results.md carries
        # the QUOTED-CLAIMS fences, and an unbalanced marker there would hide
        # the rest of the record's real claims from every check below.
        for path in record_files():
            text = read(path)
            name = os.path.basename(path)
            for begin, end in MARKERS:
                opened = self._marker_lines(text, begin)
                closed = self._marker_lines(text, end)
                self.assertEqual(
                    opened, closed,
                    f"{name} has {opened} '{begin}' and {closed} '{end}' "
                    f"lines — unbalanced, so asserted prose is being hidden "
                    f"from every check in this suite")

    def test_the_quote_bearing_files_still_carry_their_markers(self):
        for name in QUOTE_BEARING:
            text = read(os.path.join(RECORD, name))
            self.assertGreater(
                self._marker_lines(text, BEGIN_VERBATIM), 0,
                f"{name} carries no quotation markers; either it stopped "
                f"holding quotations or the boundary was removed")

    def test_the_drift_history_is_fenced_and_the_fences_stay_few(self):
        # The history quotes false numbers on purpose; unfenced, this suite
        # would demand it be falsified to go green — which is how the fence
        # came to exist, the guard having flagged the table minutes after it
        # was written. The upper bound is the point: a fence marks text as
        # quoted rather than asserted, so a record that kept growing them
        # would be routing its live claims around the guard.
        text = read(os.path.join(RECORD, "gate-results.md"))
        fences = self._marker_lines(text, BEGIN_QUOTED_CLAIMS)
        self.assertGreaterEqual(
            fences, 1, "the drift-history table must stay fenced")
        self.assertLessEqual(
            fences, 3,
            f"gate-results.md carries {fences} quoted-claim fences; each one "
            f"is prose this suite cannot check, so they stay few and "
            f"deliberate rather than becoming a way around it")

    def test_authored_prose_survives_the_strip(self):
        # If the markers ever swallowed a whole file, its authored analysis
        # would silently stop being guarded.
        for name in QUOTE_BEARING:
            kept = authored(read(os.path.join(RECORD, name))).strip()
            self.assertTrue(
                kept, f"{name} has no authored prose left after stripping "
                      f"quotations — the boundary is wrong")

    def test_quotations_are_actually_excluded(self):
        # The other direction: prove the strip removes something. A no-op
        # `authored` would expose quotations to checks that must never edit
        # them.
        for name in QUOTE_BEARING:
            text = read(os.path.join(RECORD, name))
            self.assertLess(len(authored(text)), len(text),
                            f"{name}: nothing was stripped")


class ThePinnedSuiteCountIsDerived(unittest.TestCase):
    def setUp(self):
        self.suites = gate_manifest()[CRITERION]

    def test_every_pinned_suite_exists(self):
        for suite in self.suites:
            self.assertTrue(
                os.path.exists(os.path.join(ROOT, suite)),
                f"{CRITERION} pins {suite}, which is not on disk")

    def test_no_suite_is_pinned_twice(self):
        self.assertEqual(len(self.suites), len(set(self.suites)),
                         "a suite is pinned twice, inflating the stated count")

    def test_the_prose_count_matches_the_manifest(self):
        # The exact drift that shipped twice: prose said fourteen, then
        # eighteen, while the manifest held a different number both times.
        expected = WORDS[len(self.suites)]
        wrong = {w for n, w in WORDS.items() if n != len(self.suites)}
        pattern = re.compile(
            r"pinning the (\w+) suites|naming the\s+(\w+) suites|"
            r"criterion now names (\w+) suites", re.IGNORECASE)

        for path in record_files() + [DECISIONS]:
            for match in pattern.finditer(
                    authored(read(path)).replace("\n", " ")):
                stated = next(g for g in match.groups() if g)
                self.assertNotIn(
                    stated.lower(), wrong,
                    f"{os.path.relpath(path, ROOT)} says '{stated} suites'; "
                    f"{CRITERION} pins {len(self.suites)} ({expected})")
                self.assertEqual(stated.lower(), expected)


class TheGateSizeCountsAreDerived(unittest.TestCase):
    """The script-suite and wired-suite totals, from the tools themselves.

    Round 4's finding, and the sharpest instance of this record's own defect
    class: the commit that added *this suite* made it the 29th script suite
    and the 61st wired suite, invalidating four "28/28" and "60 suites" claims
    in a record whose contract is "every gate component, its command, and its
    result". Extracting the previous commit and running the gate there showed
    those numbers were correct when written — the anti-drift commit introduced
    the fifth instance of the drift.

    The earlier checks could not have caught it: they match a spelled-out
    suite count, a four-digit engine count, and the race totals, and `28/28`
    and `60 suites` match none of those. Correcting the strings alone would
    have recurred on the next suite added, so both numbers are derived here —
    from `run-script-suites.py`'s own glob and `release-manifest.py`'s own
    audit, never from a number typed twice.
    """

    def setUp(self):
        self.scripts = script_suites()
        self.wired = wired_suites()

    def test_every_stated_script_suite_total_matches_the_glob(self):
        # `28/28`, `29/29` — the runner reports passed/total, so a correct
        # record states the suite count on both sides.
        total = len(self.scripts)
        for path in record_files():
            for match in re.finditer(r"(\d+)/(\d+) suite", authored(read(path))):
                self.assertEqual(
                    (int(match.group(1)), int(match.group(2))),
                    (total, total),
                    f"{os.path.relpath(path, ROOT)} states "
                    f"'{match.group(0)}' but tests/scripts holds {total} "
                    f"suites — re-running the documented command contradicts "
                    f"the record")

    def test_every_stated_wired_suite_total_matches_the_manifest_guard(self):
        total = len(self.wired)
        for path in record_files():
            for match in re.finditer(r"(\d+) suites? wired", authored(read(path))):
                self.assertEqual(
                    int(match.group(1)), total,
                    f"{os.path.relpath(path, ROOT)} states "
                    f"'{match.group(0)}' but release-manifest.py wires "
                    f"{total}")

    def test_the_guard_suite_is_itself_pinned_to_a_criterion(self):
        # Round 4's third finding: this suite was silently deletable — the
        # manifest guard stayed green without it. The suite that keeps the
        # record honest is exactly the one whose removal must be reported.
        pinned = {path for paths in gate_manifest().values() for path in paths}
        self.assertIn("tests/scripts/sign-off-record_test.py", pinned)


class NoUncheckedGateCountReachesTheProse(unittest.TestCase):
    """Every gate-shaped number in suite prose is a derived one — or a failure.

    The seventh instance of this record's defect class, and the first to ship:
    #229 merged `(inside the 28)` in the gate-results table three lines above
    two totals round 4 had just corrected. Every check above stayed green,
    because each of them matches a phrasing — `N/N suite`,
    `N suites wired`, `pinning the <word> suites` — and "inside the 28" is a
    third way of saying the script-suite total that matches none of them. The
    guard derived the instances it had seen, not the class, so a fourth
    phrasing would have been the eighth instance. Two reviewers swept for the
    phrasings already known to have drifted and missed it for the same reason.

    Adding "the 28" to a pattern list would repeat that error one step out. So
    this check inverts the default instead. In any paragraph that mentions the
    suites at all, a gate-shaped number is a *failure* unless it is one of:

    * a value derived here — the script-suite total, the wired-suite total, or
      the pinned-suite count. This is the property that makes renumbering
      pointless: correcting `28` to `29` does not satisfy this check, deriving
      it does, and the next suite added invalidates a stale `29` in any
      phrasing at all, including one nobody has written yet.
    * a shape that cannot be a suite count: a number followed by its own unit
      (`43 tests`, `66 lines`), a reference rather than a tally
      (`User Story 40`), or a run that is part of an identifier, issue number,
      version, date, or line reference (`#168`, `0.46.10`, `python3`,
      `applier_test.py:1089`).
    * a literal in `UNCHECKED_TALLIES` — the closed, capped list below.

    Its limits, stated rather than implied:

    * **Digits only.** A spelled-out total ("twenty-nine script suites")
      escapes; `ThePinnedSuiteCountIsDerived` covers the one spelled phrasing
      the record actually uses, and nothing covers a new one.
    * **One-digit and four-digit runs are out of range** — a plausible
      gate-suite total in this tree is two or three digits, and the bound is
      what keeps "Round 4" and `1349` from being read as suite counts. The
      engine counts have their own check; a one-digit count of anything has
      none.
    * **A wrong number that happens to equal another derived total passes.**
      Writing `61` where `29` was meant is not caught.
    * **It cannot tell a live count from a historical one.** "made it the 29th
      script suite" stays true forever and still fails here the moment a suite
      is added, so the record states its own history count-free instead. That
      is a real cost, and the trade it buys is that no stale count survives by
      being phrased in a way nobody anticipated.
    * **The record only.** `docs/decisions.md` quotes this history too, with
      no fence mechanism to mark quotation from assertion, so it is out of
      scope here and stays covered only by the phrasing checks above.
    * It says nothing about non-numeric drift. The provenance error this
      record also carries would still pass.
    """

    # A paragraph mentioning any of these is talking about the suites, so a
    # number in it is presumed to be a count of them. Deliberately broad: the
    # defect row named no count word at all, only the suite file it describes.
    ANCHOR = re.compile(r"suites?\b|tests/scripts|run-script-suites", re.I)

    # Two to three digits, not glued to an identifier, `#`, `.`, `:` or `-` on
    # the left, and not continued by more digits or by a `.`/`:` group on the
    # right — so `#168`, `0.46.10`, `2026-08-05`, `python3`, `US40`,
    # `14:38:35` and `applier_test.py:1089` are references, not tallies. The
    # right-hand test is deliberately narrow: an earlier draft rejected any
    # trailing `.` and so let a sentence-final count ("there are 28.") walk
    # straight through, which is the same fail-open shape as the defect.
    NUMBER = re.compile(r"(?<![\w.#:-])(\d{2,3})(?!\d)(?![.:]\d)")

    # A number carrying its own unit is a count of that unit, not of suites.
    # Only the units the record actually uses — every entry is a hole, so an
    # unused one is a hole for nothing.
    OWN_UNIT = re.compile(r"\A\s*(tests?|lines?)\b", re.I)

    # ...and a number that names something is a reference, like `#168`.
    NAMES_A_THING = re.compile(r"user stor(y|ies)\s+\Z", re.I)

    # The closed list of gate-shaped numbers this suite cannot derive. Each is
    # a per-suite test tally, not a gate total, and each is therefore an
    # unchecked claim — the same kind this record exists to be honest about.
    # It is capped for the same reason the quoted-claim fences are: a list that
    # grew freely would be a way around the check rather than a stated limit.
    UNCHECKED_TALLIES = (
        "`apply-recovery_test.py` 14/14",
        "`verify-apply-bytes_test.py` 31/31",
    )

    def setUp(self):
        self.derived = {
            "script suites in tests/scripts": len(script_suites()),
            "suites wired in release-manifest.py": len(wired_suites()),
            f"suites pinned to {CRITERION}": len(gate_manifest()[CRITERION]),
        }

    @staticmethod
    def _paragraphs(text):
        """Blank-line-separated blocks, so a wrapped sentence stays whole.

        Anchoring per line would miss a count whose subject sits on the line
        above it, which is one edit away in prose this heavily wrapped.
        """
        for block in re.split(r"\n\s*\n", text):
            if block.strip():
                yield block

    def _mask_registered(self, block):
        for tally in self.UNCHECKED_TALLIES:
            block = block.replace(tally, " " * len(tally))
        return block

    def test_every_gate_shaped_number_in_suite_prose_is_derived(self):
        allowed = set(self.derived.values())
        for path in record_files():
            for block in self._paragraphs(authored(read(path))):
                if not self.ANCHOR.search(block):
                    continue
                scanned = self._mask_registered(block)
                for match in self.NUMBER.finditer(scanned):
                    if int(match.group(1)) in allowed:
                        continue
                    after = scanned[match.end():match.end() + 20]
                    before = scanned[max(0, match.start() - 20):match.start()]
                    if (self.OWN_UNIT.match(after)
                            or self.NAMES_A_THING.search(before)):
                        continue
                    line = block.splitlines()[
                        scanned[:match.start()].count("\n")]
                    self.fail(
                        f"{os.path.relpath(path, ROOT)} states '"
                        f"{match.group(1)}' in prose about the suites:\n"
                        f"    {line.strip()}\n"
                        f"Derived totals are "
                        + ", ".join(f"{v} {k}" for k, v in
                                    sorted(self.derived.items()))
                        + ".\nA count here must either match a derived total "
                        f"or not be a count at all. Renumbering it recurs on "
                        f"the next suite added — reword the claim count-free, "
                        f"the way the record does elsewhere.")

    def test_the_unchecked_tally_registry_has_no_stale_entries(self):
        # A registered literal that no longer appears would be an exemption
        # nothing needs, quietly widening what the check skips.
        prose = "\n".join(authored(read(path)) for path in record_files())
        for tally in self.UNCHECKED_TALLIES:
            self.assertEqual(
                prose.count(tally), 1,
                f"UNCHECKED_TALLIES registers {tally!r}, which appears "
                f"{prose.count(tally)} times in the record — an entry is "
                f"stale, or a number is being exempted more than once")

    def test_the_unchecked_tally_registry_stays_small(self):
        self.assertLessEqual(
            len(self.UNCHECKED_TALLIES), 3,
            "the registry is a list of numbers nothing checks; growing it is "
            "how this check would stop being one")


class TheEngineTestCountIsInternallyConsistent(unittest.TestCase):
    """Every stated engine-test count agrees with every other.

    Not checked against a live run — see this module's docstring. The failure
    this catches is the one that happened: one file, and even one file's own
    table versus its own code block, disagreeing.
    """

    COUNT = re.compile(r"(\d{4}) tests|# (\d{4}), OK|\*\*(\d{4})\*\* engine")

    def test_all_stated_engine_counts_agree(self):
        seen = {}
        for path in record_files() + [DECISIONS]:
            for match in self.COUNT.finditer(authored(read(path))):
                value = next(g for g in match.groups() if g)
                seen.setdefault(value, []).append(
                    os.path.relpath(path, ROOT))
        if not seen:
            self.skipTest("no engine-test count stated in the record")
        self.assertEqual(
            len(seen), 1,
            "the record states more than one engine-test count: "
            + "; ".join(f"{v} in {sorted(set(f))}" for v, f in seen.items()))


class TheRaceAuditTotalsMatchItsTable(unittest.TestCase):
    """The six-versus-seven drift, checked against the table it summarizes."""

    PATH = os.path.join(RECORD, "race-test-audit.md")

    def setUp(self):
        self.text = authored(read(self.PATH))

    def test_the_prose_totals_match_the_row_dispositions(self):
        rows = [line for line in self.text.splitlines()
                if line.startswith("|") and "Fixed" in line or
                (line.startswith("|") and "Accepted" in line)]
        fixed = sum(1 for r in rows if "Fixed:" in r or "| Fixed" in r)
        accepted = sum(1 for r in rows if "**Accepted." in r or
                       "| Accepted" in r)
        if not rows:
            self.skipTest("no disposition table found to compare against")

        match = re.search(r"\*\*(\w+) were fixed in #203; (\w+) were accepted",
                          self.text)
        self.assertIsNotNone(
            match, "the race audit states no fixed/accepted totals")
        stated_fixed, stated_accepted = match.group(1), match.group(2)

        self.assertEqual(
            stated_fixed.lower(), WORDS[fixed],
            f"prose says '{stated_fixed} were fixed' but the table shows "
            f"{fixed} fixed rows")
        # The accepted side is one row naming two tests, which is exactly the
        # miscount that produced 'six': the prose counts tests, the table
        # counts rows. Assert the prose says so rather than asserting equality.
        self.assertIn("counts tests", self.text,
                      "the audit must state that its totals count tests "
                      "rather than table rows — that ambiguity is what "
                      "produced the original miscount")
        self.assertEqual(stated_accepted.lower(), WORDS[2])


if __name__ == "__main__":
    unittest.main(verbosity=2)
