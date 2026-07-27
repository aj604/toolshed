"""The segmenter: a document's assertion units, and their identity.

Segmentation splits a document into **assertion units** — the smallest pieces
an audit can reach a verdict about (a sentence, a list item, a table row). It
is a fixed structural parser and nothing else: no model is in the loop, no
network or subprocess is touched, and the same bytes always produce the same
units and the same digests. That is the point. Finding digests, cache keys, and
approval binding all rest on unit identity, so identity must be reproducible
by anyone holding the bytes, years later, without asking a model anything.

Two properties follow from that, and both are deliberate:

*Identity is content, not position.* A unit's digest covers its structural kind
and its normalized text — not its line number, not its document. Re-wrapping a
paragraph, renumbering a list, or repadding a table column therefore preserves
identity, and the same sentence in two documents is one identity, which is
exactly what a duplication audit wants. Position travels alongside the digest
(`line`, `end_line`, `ordinal`) for a reader to follow, and never inside it.

*Capability is structural, judgment is not.* Some kinds cannot carry a claim at
all: a heading names a section, a code block is an example, an HTML comment is
not prose. Those units are marked `assertion_capable = False` — non-assertive
capable — so nothing downstream can record a factual claim against them and
then "verify" it. What a *capable* unit actually asserts is the model's call
(factual / normative / rationale / non-assertive), recorded as reviewable data
by `finding.py` and never folded into identity here.

`segment_text` is the pure parser; `segment_document` reads one registered
document out of a repository and is the same parser behind an inventory lookup.
"""

import os
import re
from dataclasses import dataclass
from typing import Optional, Tuple

from . import ARTIFACT_SCHEMA_VERSION
from .digest import sha256_bytes, sha256_canonical
from .inventory import DEFAULT_REGISTRY_PATH, build_inventory
from .results import STATUS_OK, Invalid, Problem

# The structural kinds a unit may have. Closed: a reader can enumerate what a
# document can be made of, and a new kind is a deliberate, versioned change.
FRONT_MATTER = "front_matter"
HEADING = "heading"
SENTENCE = "sentence"
LIST_ITEM = "list_item"
BLOCK_QUOTE = "block_quote"
TABLE_HEADER = "table_header"
TABLE_ROW = "table_row"
CODE_BLOCK = "code_block"
HTML_BLOCK = "html_block"

UNIT_KINDS = (
    FRONT_MATTER, HEADING, SENTENCE, LIST_ITEM, BLOCK_QUOTE,
    TABLE_HEADER, TABLE_ROW, CODE_BLOCK, HTML_BLOCK,
)

# The kinds that can carry an assertion at all. Everything else is
# non-assertive capable: structure, metadata, or an example — never a claim,
# so never a claim to verify.
ASSERTION_CAPABLE_KINDS = (SENTENCE, LIST_ITEM, BLOCK_QUOTE, TABLE_ROW)

# Kinds whose text is kept exactly as written. Prose identity ignores how it
# was wrapped; code and metadata do not, because their whitespace is content.
VERBATIM_KINDS = (CODE_BLOCK, FRONT_MATTER)

_ATX = re.compile(r"^ {0,3}(#{1,6})(?:\s+(?P<text>.*?))?\s*$")
_TRAILING_HASHES = re.compile(r"\s+#+\s*$")
_SETEXT = re.compile(r"^ {0,3}(=+|-+)\s*$")
_THEMATIC = re.compile(r"^ {0,3}(?:(?:\*\s*){3,}|(?:-\s*){3,}|(?:_\s*){3,})$")
_FENCE = re.compile(r"^ {0,3}(?P<fence>`{3,}|~{3,})")
_LIST = re.compile(
    r"^(?P<indent> *)(?P<marker>[-*+]|\d{1,9}[.)])(?P<gap> +)(?P<text>.*)$"
)
_QUOTE = re.compile(r"^ {0,3}> ?(?P<text>.*)$")
_HTML = re.compile(r"^ {0,3}(?:<!--|</?[A-Za-z][A-Za-z0-9-]*(?:[ />]|$))")
_INDENTED = re.compile(r"^(?: {4}|\t)")
_FRONT_FENCE = re.compile(r"^(-{3,})\s*$")
_FRONT_END = re.compile(r"^(-{3,}|\.{3,})\s*$")

# Terminators that can end a sentence, and what may legally follow one.
_TERMINATORS = ".!?"
_CLOSERS = "\"')]}»”’"
_OPENERS = "`\"'([{*_“‘«"

# Words whose trailing period is part of the word. Without this list a fixed
# splitter cuts "e.g. Redis" in half and invents a claim that was never made.
_ABBREVIATIONS = frozenset("""
e.g. i.e. etc. cf. vs. viz. al. ca. approx. est. resp. incl. excl.
dr. mr. mrs. ms. prof. sr. jr. st. mt. no. nos. vol. ch. sec. fig. eq. ref.
inc. ltd. co. corp. dept. univ. jan. feb. mar. apr. jun. jul. aug. sep. sept.
oct. nov. dec. mon. tue. wed. thu. fri. sat. sun. min. max. avg. approx
""".split())
_INITIAL = re.compile(r"^[A-Za-z]\.$")


@dataclass(frozen=True)
class AssertionUnit:
    """One deterministically segmented piece of a document.

    `digest` is the identity every downstream contract binds to; `ordinal`,
    `line`, and `end_line` locate it for a human and are not part of that
    identity.
    """

    ordinal: int
    kind: str
    text: str
    line: int
    end_line: int
    assertion_capable: bool
    digest: str

    def to_dict(self):
        return {
            "ordinal": self.ordinal,
            "kind": self.kind,
            "text": self.text,
            "line": self.line,
            "end_line": self.end_line,
            "assertion_capable": self.assertion_capable,
            "digest": self.digest,
        }


@dataclass(frozen=True)
class Segmentation:
    """A document's units, in document order, with the digests over them."""

    status: str
    units: Tuple[AssertionUnit, ...]
    document_digest: str
    digest: str
    path: Optional[str] = None
    kind: Optional[str] = None

    def to_dict(self):
        return {
            "status": self.status,
            "schema_version": ARTIFACT_SCHEMA_VERSION,
            "path": self.path,
            "kind": self.kind,
            "document_digest": self.document_digest,
            "digest": self.digest,
            "units": [unit.to_dict() for unit in self.units],
        }


def unit_digest(kind, text):
    """A unit's identity: its structural kind and its normalized text.

    Canonical JSON, like every other digest the engine takes, so the same two
    fields always hash the same way regardless of how they were assembled.
    Deliberately excludes the document, the position, the artifact schema
    version, and anything a model said: identity must survive a document being
    reorganized, an engine release, and a re-classification.
    """
    return sha256_canonical({"kind": kind, "text": text})


def _flow(numbered):
    """Join `(line number, text)` pairs into one whitespace-normalized string.

    Returns `(text, origins)` where `origins[i]` is the source line of
    `text[i]` — so a sentence carved out of a wrapped paragraph can still say
    which lines it came from.
    """
    chars, origins = [], []
    for lineno, raw in numbered:
        # The line break itself is whitespace, and `split("\n")` already ate
        # it: without this a hard-wrapped sentence reads as one run-on word.
        if chars and chars[-1] != " ":
            chars.append(" ")
            origins.append(lineno)
        for char in raw:
            if char.isspace():
                if chars and chars[-1] != " ":
                    chars.append(" ")
                    origins.append(lineno)
            else:
                chars.append(char)
                origins.append(lineno)
    while chars and chars[-1] == " ":
        chars.pop()
        origins.pop()
    return "".join(chars), origins


def _is_table_delimiter(line):
    stripped = line.strip()
    return (
        "|" in stripped
        and "-" in stripped
        and set(stripped) <= set("|-: ")
    )


def _table_row_text(line):
    """A row's cells, trimmed and rejoined — padding is layout, not content."""
    stripped = line.strip()
    if stripped.startswith("|"):
        stripped = stripped[1:]
    if stripped.endswith("|") and not stripped.endswith("\\|"):
        stripped = stripped[:-1]
    return " | ".join(cell.strip() for cell in stripped.split("|"))


def _sentence_bounds(text):
    """Offsets one past each sentence end, by fixed rules.

    The rules, in full: a terminator run (`.`, `!`, `?`) plus any closing
    quotes or brackets ends a sentence when it is followed by whitespace or the
    end of the text, the word it closes is not a known abbreviation or an
    initial, and the next visible character opens a sentence (a capital, a
    digit, or an opening delimiter). Terminators inside an inline code span are
    invisible to it. Everything else is one sentence.
    """
    bounds, in_code, i, length = [], False, 0, len(text)
    while i < length:
        char = text[i]
        if char == "`":
            in_code = not in_code
            i += 1
            continue
        if in_code or char not in _TERMINATORS:
            i += 1
            continue
        end = i
        while end < length and text[end] in _TERMINATORS:
            end += 1
        while end < length and text[end] in _CLOSERS:
            end += 1
        word = text[:end].split(" ")[-1].lower()
        if word in _ABBREVIATIONS or _INITIAL.match(word):
            i = end
            continue
        if end >= length:
            bounds.append(length)
            break
        if text[end] != " ":
            i = end
            continue
        following = end
        while following < length and text[following] == " ":
            following += 1
        if following >= length:
            bounds.append(length)
            break
        nxt = text[following]
        if nxt.isupper() or nxt.isdigit() or nxt in _OPENERS:
            bounds.append(end)
        i = end
    if not bounds or bounds[-1] != length:
        bounds.append(length)
    return bounds


class _Segmenter:
    """One pass over one document's lines. Holds no state between documents."""

    def __init__(self, text):
        self.lines = text.replace("\r\n", "\n").replace("\r", "\n").split("\n")
        self.units = []
        self.i = 0

    # -- emitting ---------------------------------------------------------

    def emit(self, kind, text, line, end_line):
        if not text:
            return                      # nothing to assert about, nothing to key
        self.units.append(AssertionUnit(
            ordinal=len(self.units),
            kind=kind,
            text=text,
            line=line,
            end_line=end_line,
            assertion_capable=kind in ASSERTION_CAPABLE_KINDS,
            digest=unit_digest(kind, text),
        ))

    def emit_flowed(self, kind, numbered):
        text, origins = _flow(numbered)
        if origins:
            self.emit(kind, text, origins[0], origins[-1])

    def emit_sentences(self, numbered, kind=SENTENCE):
        text, origins = _flow(numbered)
        start = 0
        for bound in _sentence_bounds(text):
            piece = text[start:bound].strip()
            if piece:
                offset = text.index(piece, start)
                self.emit(
                    kind, piece, origins[offset], origins[offset + len(piece) - 1],
                )
            start = bound

    def starts_block(self, line):
        """Whether `line` begins a block, and so ends whatever precedes it."""
        return bool(
            _ATX.match(line) or _FENCE.match(line) or _THEMATIC.match(line)
            or _QUOTE.match(line) or _LIST.match(line) or _HTML.match(line)
        )

    # -- block dispatch ---------------------------------------------------

    def run(self):
        self.front_matter()
        while self.i < len(self.lines):
            line = self.lines[self.i]
            if not line.strip():
                self.i += 1
            elif _FENCE.match(line):
                self.fenced_code()
            elif _ATX.match(line):
                self.heading()
            elif _THEMATIC.match(line):
                self.i += 1             # punctuation, not content
            elif _HTML.match(line):
                self.html_block()
            elif _QUOTE.match(line):
                self.block_quote()
            elif _LIST.match(line):
                self.list_item()
            elif self.starts_table():
                self.table()
            elif _INDENTED.match(line):
                self.indented_code()
            else:
                self.paragraph()
        return tuple(self.units)

    def starts_table(self, offset=0):
        i = self.i + offset
        return (
            "|" in self.lines[i]
            and not _is_table_delimiter(self.lines[i])
            and i + 1 < len(self.lines)
            and _is_table_delimiter(self.lines[i + 1])
        )

    # -- blocks -----------------------------------------------------------

    def front_matter(self):
        """A metadata fence at the very top. Verbatim: its whitespace is data."""
        if not self.lines or not _FRONT_FENCE.match(self.lines[0]):
            return
        for end in range(1, len(self.lines)):
            if _FRONT_END.match(self.lines[end]):
                body = self.lines[1:end]
                self.emit(FRONT_MATTER, "\n".join(body).strip("\n"), 2, max(end, 2))
                self.i = end + 1
                return
        # No closing fence: it was never front matter. Leave it to the parser,
        # which reads the opening line as a thematic break.

    def fenced_code(self):
        opener = _FENCE.match(self.lines[self.i]).group("fence")
        start = self.i
        self.i += 1
        body = []
        while self.i < len(self.lines):
            line = self.lines[self.i]
            stripped = line.strip()
            if stripped.startswith(opener[0] * len(opener)) and set(stripped) == {
                opener[0]
            }:
                self.i += 1
                break
            body.append(line)
            self.i += 1
        self.emit(CODE_BLOCK, "\n".join(body).strip("\n"), start + 2,
                  max(start + 1 + len(body), start + 2))

    def indented_code(self):
        start = self.i
        body = []
        while self.i < len(self.lines):
            line = self.lines[self.i]
            if not line.strip():
                # A blank line inside an indented block only continues it if
                # more indented content follows.
                ahead = self.i + 1
                while ahead < len(self.lines) and not self.lines[ahead].strip():
                    ahead += 1
                if ahead >= len(self.lines) or not _INDENTED.match(self.lines[ahead]):
                    break
                body.append("")
                self.i += 1
                continue
            if not _INDENTED.match(line):
                break
            body.append(line[4:] if line.startswith("    ") else line[1:])
            self.i += 1
        self.emit(CODE_BLOCK, "\n".join(body).strip("\n"), start + 1, self.i)

    def heading(self):
        match = _ATX.match(self.lines[self.i])
        text = _TRAILING_HASHES.sub("", match.group("text") or "").strip()
        self.emit_flowed(HEADING, [(self.i + 1, text)])
        self.i += 1

    def html_block(self):
        start = self.i
        comment = self.lines[self.i].lstrip().startswith("<!--")
        body = []
        while self.i < len(self.lines):
            line = self.lines[self.i]
            if not comment and not line.strip():
                break
            body.append((self.i + 1, line))
            self.i += 1
            if comment and "-->" in line:
                break
        self.emit_flowed(HTML_BLOCK, body)
        if self.i == start:             # defensive: always make progress
            self.i += 1

    def block_quote(self):
        body = []
        while self.i < len(self.lines):
            match = _QUOTE.match(self.lines[self.i])
            if match is None:
                break
            body.append((self.i + 1, match.group("text")))
            self.i += 1
        self.emit_sentences(body, kind=BLOCK_QUOTE)

    def list_item(self):
        """One item, its wrapped lines folded in — indented or not.

        A following line continues the item unless it starts a block of its
        own, so an item wrapped without indentation is still one unit and
        re-wrapping it does not re-key it.
        """
        body = [(self.i + 1, _LIST.match(self.lines[self.i]).group("text"))]
        self.i += 1
        while self.i < len(self.lines):
            line = self.lines[self.i]
            if not line.strip() or self.starts_block(line) or self.starts_table():
                break
            body.append((self.i + 1, line))
            self.i += 1
        self.emit_flowed(LIST_ITEM, body)

    def table(self):
        self.emit_flowed(
            TABLE_HEADER, [(self.i + 1, _table_row_text(self.lines[self.i]))]
        )
        self.i += 2                     # the delimiter row is syntax, not content
        while self.i < len(self.lines):
            line = self.lines[self.i]
            if not line.strip() or "|" not in line:
                break
            self.emit_flowed(TABLE_ROW, [(self.i + 1, _table_row_text(line))])
            self.i += 1

    def paragraph(self):
        body = []
        while self.i < len(self.lines):
            line = self.lines[self.i]
            if not line.strip():
                break
            if body and _SETEXT.match(line):
                self.emit_flowed(HEADING, body)
                self.i += 1
                return
            if body and (self.starts_block(line) or self.starts_table()):
                break
            body.append((self.i + 1, line))
            self.i += 1
        self.emit_sentences(body)


def _segmentation_digest(units):
    """The identity of a whole segmentation: which units, in which order.

    Order is part of it — moving a sentence keeps that sentence's identity but
    produces a different document — while the file's bytes are not, so a
    re-wrap that changes no unit changes no segmentation.
    """
    return sha256_canonical({
        "schema_version": ARTIFACT_SCHEMA_VERSION,
        "units": [unit.digest for unit in units],
    })


def segment_text(text, path=None, kind=None):
    """Segment a document's text into assertion units. Pure and model-free.

    `path` and `kind` are recorded for a reader; neither affects any digest.
    """
    units = _Segmenter(text).run()
    return Segmentation(
        status=STATUS_OK,
        units=units,
        document_digest=sha256_bytes(text.encode("utf-8")),
        digest=_segmentation_digest(units),
        path=path,
        kind=kind,
    )


def segment_document(repo_root, path, registry_path=DEFAULT_REGISTRY_PATH):
    """Segment one registered document. Returns a `Segmentation` or `Invalid`.

    The registry decides what a document is, so segmentation goes through the
    inventory rather than opening whatever path it was handed: an unregistered,
    excluded, or symlinked path is refused here, once, instead of every caller
    re-deriving the rule. An invalid registry invalidates the run, as it does
    everywhere else.
    """
    inventory = build_inventory(repo_root, registry_path)
    if isinstance(inventory, Invalid):
        return inventory

    document = next((d for d in inventory.documents if d.path == path), None)
    if document is None:
        return Invalid((Problem(
            code="document-not-inventoried",
            message=(
                f"{path} is not a document in this repository's inventory — it "
                f"is outside the declared roots, excluded, unregistered, or not "
                f"a regular file. Classify it in the registry rather than "
                f"segmenting a path the registry does not claim."
            ),
            location=path,
        ),))

    try:
        with open(os.path.join(repo_root, path), "rb") as fh:
            raw = fh.read()
        text = raw.decode("utf-8")
    except OSError as exc:
        return Invalid((Problem(
            code="document-unreadable",
            message=f"cannot read {path}: {exc.strerror}",
            location=path,
        ),))
    except UnicodeDecodeError as exc:
        return Invalid((Problem(
            code="document-unreadable",
            message=(
                f"{path} is not valid UTF-8 ({exc.reason} at byte {exc.start}) — "
                f"re-encode it; a document the engine cannot decode cannot be "
                f"segmented, and guessing an encoding would make identity "
                f"depend on the guess"
            ),
            location=path,
        ),))

    return segment_text(text, path=path, kind=document.kind)
