"""Split a decision's ``raw_text`` into the nämnd's own text and its appendices.

Överklagandenämnden publishes one PDF per ärende, and that PDF physically contains
the decision that was appealed — pasted in after the nämnd's own trailer under a
``Bilaga X`` label. Flattened into ``documents.raw_text`` the two are
indistinguishable, which is how lower-instance reasoning ends up being retrieved,
summarised and cited as if the nämnd had written it.

The layout is regular enough to segment with anchors alone::

    Svenska kyrkans överklagandenämnd
    Meddelat 2026-01-07
    Utlämnande av handlingar            <- category
    53 kap. 3-11 §§ kyrkoordningen      <- lagrum (optional)
    YRKANDE M.M.
    ...background, submissions, reasoning...
    Överklagandenämndens beslut: ...    <- holding
    Sökord: Utlämnande av handlingar.   -.
    Ärendenummer: ÖN 2025-0017           |- trailer
    Beslut: 1/2026                      -'
    ...............                     <- ellipsis rule
    BILAGA A                            <- label, usually upper case
    <the prior instance's own document, verbatim>

Everything here is pure: no I/O, no logging, no configuration. Callers decide what
to do with the segments — see the extract, metadata and chunk workers.
"""

from __future__ import annotations

import re
from enum import StrEnum, auto

from pydantic import BaseModel, ConfigDict

__all__ = [
    "Appendix",
    "DocumentSegments",
    "SegmentationGap",
    "TrailerField",
    "find_segmentation_gaps",
    "normalize_case_number",
    "normalize_cited_decision_number",
    "normalize_decision_number",
    "parse_keywords",
    "parse_trailer_fields",
    "split_document",
]


class SegmentationGap(StrEnum):
    """Structure every decision in the corpus has, that this one did not.

    Not an error: `split_document` never raises, and a decision genuinely laid
    out differently is a thing that happens. A gap is a signal to whoever reads
    the logs that an anchor stopped matching — every defect this module has had
    produced `None` or a plausible wrong value with no signal at all.
    """

    NO_TRAILER = auto()
    NO_HOLDING = auto()
    NO_APPENDIX = auto()
    NO_KEYWORDS = auto()


class TrailerField(StrEnum):
    """The labels the nämnd's trailer uses, spelled as they appear in the PDF."""

    KEYWORDS = "Sökord"
    CASE_NUMBER = "Ärendenummer"
    DECISION_NUMBER = "Beslut"


class Appendix(BaseModel):
    """One ``Bilaga X`` block: the label line and everything under it."""

    model_config = ConfigDict(frozen=True)

    label: str
    text: str


class DocumentSegments(BaseModel):
    """A decision cut into the parts that mean different things.

    ``body`` is the nämnd's own document with the trailer removed. ``holding`` is
    the sub-slice of ``body`` after ``Överklagandenämndens beslut:`` — what the
    nämnd actually decided. ``trailer`` holds the document's *own* identifiers, so
    excluding it is what stops a decision citing itself.
    """

    model_config = ConfigDict(frozen=True)

    body: str
    holding: str | None = None
    trailer: str | None = None
    appendices: list[Appendix] = []


# The one spelling `Appendix.label` and `chunks.appendix_label` use. The corpus
# writes the word both ways — "BILAGA A" in 22 of 25 decisions, "Bilaga A" in the
# rest — so the emitted label is built rather than echoed from the source.
_APPENDIX_LABEL_PREFIX = "Bilaga"

# A line that is *only* an appendix label. Deliberately end-anchored: prose like
# "Bilaga 1 innehåller ..." and "markerade med rött i bilagan" must not split the
# document. Labels seen in the corpus are a single letter or a small number.
#
# Case-insensitive on the word alone, not via re.IGNORECASE on the whole pattern,
# which would widen the identifier to lowercase too — a stray "bilaga a" in prose
# is not a label.
_APPENDIX_LABEL_RE = re.compile(
    r"^[ \t]*(?i:bilaga)[ \t]+(?P<identifier>\d{1,2}|[A-ZÅÄÖ])[ \t]*$",
    re.MULTILINE,
)

# The trailer opens with "Sökord:"; "Ärendenummer:" is the fallback for decisions
# that omit it. Both are line-initial, unlike their in-prose mentions. The corpus
# does not fix their order, so the *earliest* of them starts the trailer — see
# `_find_trailer_start`. "Beslut:" is deliberately not an anchor: it is never the
# first trailer line in the corpus, and an appended protocol uses it as a heading.
_TRAILER_START_PATTERNS = (
    re.compile(r"^[ \t]*Sökord:", re.MULTILINE),
    re.compile(r"^[ \t]*Ärendenummer:", re.MULTILINE),
)

# The holding opens either "Överklagandenämndens beslut: <the decision>" or with the
# same words as a bare heading on their own line. Only those two: the colon and the
# end of the line are what separate the anchor from the in-prose citation
# "Överklagandenämndens beslut 8/01", which names a *different* decision and must
# never be read as the start of this one's holding.
_HOLDING_RE = re.compile(
    r"^[ \t]*Överklagandenämndens beslut(?::[ \t]*|[ \t]*$)", re.MULTILINE
)

# The typographic rule separating the trailer from the first appendix — a run of
# ellipsis characters, dots, or dashes; the corpus draws it every one of those
# ways. Matched as a whole line so a sentence ending in a full stop survives, and
# applied to the trailer slice only.
_RULE_LINE_RE = re.compile(r"^[ \t]*[….\-–—_]{2,}[ \t]*$")

# Ärendenummer: "ÖN 2026-0014", "ÖN 2026-04", "2026-0005" — the ÖN and Dnr markers
# are both optional because the corpus omits them on some trailer lines.
#
# The separator is a slash as often as a hyphen. The registry wrote "ÖN 2021/2"
# throughout 2020 and 2021 and sporadically after, and the two are spellings of one
# identifier space rather than two registries: decisions 29/2020 and 30/2020 carry
# "ÖN 2020-37" and "ÖN 2020-36", and 1/2021 — the final decision in the same matter,
# of which those two were the interim rulings — lists "ÖN 2020/36, ÖN 2020/37, ÖN
# 2020/39". Accepting both is what lets `normalize_case_number` give them one name.
#
# Two guards stop a year being read as an ärendenummer, which matters because the
# body fallback runs this over free prose:
#
#   * a sequence that is itself a year of this era is a period, not a sequence, so
#     the mandate period "2026-2029" is rejected while case 1234 of "2020-1234" is
#     kept;
#   * a following date component disqualifies the match, so "Meddelat 2026-04-08"
#     does not read as case 4 of 2026.
#
# Nothing anchors the left edge, deliberately: two trailers in the corpus read
# "ÖN 32020/33" and "ÖN 32020/35", a stray digit the PDF glued to the front, and
# scanning past it recovers the ärendenummer the surrounding sequence confirms.
_CASE_NUMBER_RE = re.compile(
    r"(?:ÖN\s*)?(?:dnr\s*)?(\d{4})\s*[-–/]\s*(?!(?:19|20)\d{2}\b)(\d{1,4})\b(?![-–/]\s*\d)",
    re.IGNORECASE,
)

# Beslutsnummer: "13/2026", and the one corpus decision that writes "23-2026".
# Both halves are length-bounded and word-anchored so the hyphen form cannot
# swallow an ärendenummer ("2026-0014"), a date ("2025-10-07") or a mandate period
# ("2026-2029").
_DECISION_NUMBER_RE = re.compile(r"\b(\d{1,3})[ \t]*[/-][ \t]*(\d{4})\b")

# The same beslutsnummer with the halves the other way round — "2022/15" for
# decision 15/2022. Deliberately *not* part of `_DECISION_NUMBER_RE`: year-first
# is the shape an ärendenummer also has, so only a caller who already knows it is
# reading a beslutsnummer may apply it. See `normalize_cited_decision_number`.
_YEAR_FIRST_DECISION_RE = re.compile(
    r"\b((?:19|20)\d{2})[ \t]*[/–-][ \t]*(\d{1,3})\b(?![-–/]\s*\d)"
)

# One labelled trailer line. Built from the enum so a label cannot be added to
# `TrailerField` without the parser recognising it.
_TRAILER_FIELD_RE = re.compile(
    r"^[ \t]*(?P<label>"
    + "|".join(field.value for field in TrailerField)
    + r")[ \t]*:(?P<value>.*)$"
)

# A decision classified under several keywords separates them with a full stop —
# every `Sökord:` line in the corpus does, and most end with one. `,` and `;` are
# kept as the conventional spelling.
#
# A stop only separates before whitespace and a capital, or at the end of the
# value; the end-of-value case is what drops the line's terminating stop, leaving
# an empty final part the caller discards. The lookbehind spots the
# letter-after-a-stop that ends a Swedish abbreviation, so "m.m." and "bl.a." are
# neither split apart nor truncated to "m.m".
_KEYWORD_SEPARATOR_RE = re.compile(r"[,;]|(?<!\.[A-ZÅÄÖa-zåäö])\.(?=\s+[A-ZÅÄÖ]|\s*$)")


def split_document(raw_text: str) -> DocumentSegments:
    """Cut ``raw_text`` into body, holding, trailer and appendices.

    Never raises and never returns nothing: a decision with no recognisable
    trailer or appendix comes back as a single ``body``.
    """
    # Source PDFs mix CRLF and LF. Every anchor below is line-anchored, and a
    # stray CR before the newline would defeat the end-of-line assertions, so
    # settle on LF once here rather than tolerating \r in five regexes.
    text = raw_text.replace("\r\n", "\n").replace("\r", "\n")

    appendix_start, appendices = _split_appendices(text)
    trailer_start = _find_trailer_start(text, appendix_start)

    body_end = trailer_start if trailer_start is not None else appendix_start
    body = text[:body_end].strip()

    trailer = None
    if trailer_start is not None:
        trailer = _strip_rule_lines(text[trailer_start:appendix_start])

    return DocumentSegments(
        body=body,
        holding=_find_holding(body),
        trailer=trailer or None,
        appendices=appendices,
    )


def normalize_case_number(raw: str) -> str | None:
    """Reduce any ärendenummer spelling to the canonical ``YYYY-NNNN``.

    ``worker-metadata`` stores ``2025-0017`` while the extractor's regex yields
    ``ÖN 2025-0017``; without one canonical form the self-reference guard never
    fires and no cross-reference ever resolves.

    The sequence is zero-padded to four digits for the same reason. The registry
    writes it both ways — ``ÖN 2026-04`` alongside ``ÖN 2026-0014`` — and stored
    unpadded, a citation written the long way could never resolve to it and the
    document could not recognise a self-citation written the long way either.
    Padding assumes the registrar never issues ``2026-04`` and ``2026-0004`` as
    *distinct* ärenden in one year, which is the same assumption the unpadded form
    already made in reverse. A sequence longer than four digits is left alone.
    """
    match = _CASE_NUMBER_RE.search(raw)
    if match is None:
        return None
    return f"{match.group(1)}-{int(match.group(2)):04d}"


def normalize_decision_number(raw: str) -> str | None:
    """Reduce any beslutsnummer spelling to the canonical ``N/YYYY``.

    Beslutsnummer (``1/2026``) is a different identifier space from ärendenummer
    (``2025-0017``) — a decision carries both, and references in the corpus use
    either.
    """
    match = _DECISION_NUMBER_RE.search(raw)
    if match is None:
        return None
    return f"{int(match.group(1))}/{match.group(2)}"


def normalize_cited_decision_number(raw: str) -> str | None:
    """Like :func:`normalize_decision_number`, but also reads the year-first form.

    Decisions cite each other with the halves in either order — "beslut 13/2025"
    and "Överklagandenämndens beslut 2022/15" are both beslutsnummer, the second
    written the way the registry writes its own listing headlines ("Beslut
    2022-15"; see :mod:`shared.source_headline`).

    Two citations in the 2020-2026 corpus settle that this is the beslutsnummer
    space and not the ärendenummer one, because both readings name a real
    document and only one names the right document:

    * 25/2026, refusing a *begäran om utlämnande*, cites "beslut 2010/06 och
      2022/15". Decision 15/2022 is "Utlämnande av handling"; ärende 2022-0015
      belongs to a verkställighetsförbud ruling.
    * 23/2022, on beredningens kvalitet *i ett beslutsprövningsärende*, cites
      "beslut 2020/24". Decision 24/2020 is "Beslutsprövning".

    Reading the year-first form as an ärendenummer instead would also turn each
    decision's own title line ("Beslut 2020/02") into an outbound citation,
    where reading it as a beslutsnummer makes it the self-reference it is.

    Kept separate from :func:`normalize_decision_number` because the two
    identifier spaces have to stay distinguishable by shape everywhere else —
    ``ÖN 2020-36`` is ärende ``2020-0036``, not decision ``36/2020``. Only a
    caller that has already seen the word "beslut" may resolve the ambiguity
    this way.
    """
    canonical = normalize_decision_number(raw)
    if canonical is not None:
        return canonical

    match = _YEAR_FIRST_DECISION_RE.search(raw)
    if match is None:
        return None
    return f"{int(match.group(2))}/{match.group(1)}"


def find_segmentation_gaps(segments: DocumentSegments) -> list[SegmentationGap]:
    """Anchors that did not fire. Empty means the document matched the template.

    Pure, like everything else here — callers at the worker edge decide whether a
    gap is worth logging.
    """
    gaps = []
    if segments.trailer is None:
        gaps.append(SegmentationGap.NO_TRAILER)
    if segments.holding is None:
        gaps.append(SegmentationGap.NO_HOLDING)
    if not segments.appendices:
        gaps.append(SegmentationGap.NO_APPENDIX)
    if not parse_keywords(segments.trailer):
        gaps.append(SegmentationGap.NO_KEYWORDS)
    return gaps


def parse_trailer_fields(trailer: str | None) -> dict[TrailerField, str]:
    """Read the trailer's labelled lines as label -> value.

    Line-oriented rather than one regex per field. The corpus does not fix the
    field order, so any pattern that ends a value by naming the labels that may
    follow it is wrong for some ordering — and when the guess is wrong the value
    runs to the end of the document and swallows the appendix.

    A value the PDF wrapped onto the following line is folded back into its field;
    a blank line or a typographic rule ends it. Never raises: a missing or
    label-less trailer comes back empty.
    """
    if trailer is None:
        return {}

    fields: dict[TrailerField, str] = {}
    current: TrailerField | None = None
    for line in trailer.splitlines():
        match = _TRAILER_FIELD_RE.match(line)
        if match is not None:
            current = TrailerField(match.group("label"))
            fields[current] = match.group("value").strip()
        elif current is not None and _is_continuation_line(line):
            fields[current] = f"{fields[current]} {line.strip()}".strip()
        else:
            current = None
    return fields


def parse_keywords(trailer: str | None) -> list[str]:
    """Read the subject keywords off the trailer's ``Sökord:`` line.

    These are Överklagandenämnden's own classification of the case — the one piece
    of subject metadata the corpus vouches for, where every other entity type is
    inferred from prose. Returned in document order with duplicates collapsed.

    Never raises: a missing trailer, a trailer carrying only ``Ärendenummer:``, and
    an empty value all come back as an empty list.
    """
    value = parse_trailer_fields(trailer).get(TrailerField.KEYWORDS)
    if value is None:
        return []

    keywords: list[str] = []
    seen: set[str] = set()
    for part in _KEYWORD_SEPARATOR_RE.split(value):
        # A wrapped value arrives with newlines inside it, and the line's own
        # terminating stop leaves an empty trailing part.
        keyword = " ".join(part.split())
        if not keyword or keyword.casefold() in seen:
            continue
        seen.add(keyword.casefold())
        keywords.append(keyword)
    return keywords


def _split_appendices(raw_text: str) -> tuple[int, list[Appendix]]:
    """Return where the appendices begin and the appendices themselves.

    The offset is ``len(raw_text)`` when there are none, so callers can slice with
    it unconditionally.
    """
    labels = list(_APPENDIX_LABEL_RE.finditer(raw_text))
    if not labels:
        return len(raw_text), []

    # Each appendix runs from the end of its label line to the start of the next
    # label, or to the end of the document for the last one.
    starts = [match.end() for match in labels]
    ends = [match.start() for match in labels[1:]] + [len(raw_text)]

    appendices = [
        Appendix(
            label=f"{_APPENDIX_LABEL_PREFIX} {match.group('identifier')}",
            text=raw_text[start:end].strip(),
        )
        for match, start, end in zip(labels, starts, ends, strict=True)
    ]
    return labels[0].start(), appendices


def _find_trailer_start(raw_text: str, appendix_start: int) -> int | None:
    """Locate the trailer, ignoring any match that sits inside an appendix.

    The *earliest* label wins rather than the first pattern tried. The corpus
    orders the trailer `Sökord > Ärendenummer > Beslut` in almost every decision
    but not all, and anchoring on `Sökord:` in a decision that puts it last cut the
    trailer at its final line — leaving the document's own identifiers in `body`,
    where they defeat the self-citation guard.

    An appended lower-instance decision can carry a trailer of its own; only the
    nämnd's counts.
    """
    starts = [
        match.start()
        for pattern in _TRAILER_START_PATTERNS
        if (match := pattern.search(raw_text, 0, appendix_start)) is not None
    ]
    return min(starts, default=None)


def _find_holding(body: str) -> str | None:
    match = _HOLDING_RE.search(body)
    if match is None:
        return None
    return body[match.end() :].strip() or None


def _strip_rule_lines(trailer: str) -> str:
    kept = [line for line in trailer.splitlines() if not _RULE_LINE_RE.match(line)]
    return "\n".join(kept).strip()


def _is_continuation_line(line: str) -> bool:
    """Whether ``line`` continues the trailer field above it."""
    return bool(line.strip()) and _RULE_LINE_RE.match(line) is None
