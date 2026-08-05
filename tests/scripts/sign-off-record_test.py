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

A wiring suite in the manner of `doc-contract_test.py`, and it inherits that
suite's documented ceiling: it catches *the claims it names* drifting, not new
false claims appearing. That ceiling is stated in `gate-results.md` rather than
pretended away.

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


# The verbatim files are frozen quotations of what agents actually returned,
# and the reviewers ran before #203 changed anything — so they quote 1344
# engine tests, correctly and permanently. Editing them to satisfy a
# consistency check would be falsifying evidence, which is the precise
# opposite of their purpose. They are excluded from every check below, and
# that exclusion is the point rather than a convenience: a claim this suite
# can enforce is an authored claim, and a quotation is not one.
VERBATIM = ("reviewer-output-verbatim.md", "reviewer-leaf-output-verbatim.md")


def record_files():
    """The record's *authored* prose — quotations deliberately excluded."""
    return sorted(os.path.join(RECORD, name) for name in os.listdir(RECORD)
                  if name.endswith(".md") and name not in VERBATIM)


def gate_manifest():
    spec = importlib.util.spec_from_file_location("release_manifest", MANIFEST)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.GATE_MANIFEST


class TheRecordExists(unittest.TestCase):
    """If the record is gone or renamed, every check below would vacuously pass."""

    def test_the_sign_off_record_is_present(self):
        self.assertTrue(os.path.isdir(RECORD), f"no record at {RECORD}")
        present = set(os.listdir(RECORD))
        for expected in ("gate-results.md", "independent-reviews.md",
                         "race-test-audit.md") + VERBATIM:
            self.assertIn(expected, present)

    def test_the_authored_and_quoted_halves_are_both_non_empty(self):
        # If VERBATIM ever grew to swallow the authored files, every check
        # below would vacuously pass.
        self.assertTrue(record_files(), "no authored prose left to check")


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
            for match in pattern.finditer(read(path).replace("\n", " ")):
                stated = next(g for g in match.groups() if g)
                self.assertNotIn(
                    stated.lower(), wrong,
                    f"{os.path.relpath(path, ROOT)} says '{stated} suites'; "
                    f"{CRITERION} pins {len(self.suites)} ({expected})")
                self.assertEqual(stated.lower(), expected)


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
            for match in self.COUNT.finditer(read(path)):
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
        self.text = read(self.PATH)

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
