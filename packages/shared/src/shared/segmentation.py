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
    Bilaga A
    <the prior instance's own document, verbatim>

Everything here is pure: no I/O, no logging, no configuration. Callers decide what
to do with the segments — see the extract, metadata and chunk workers.
"""

from __future__ import annotations

import re

from pydantic import BaseModel, ConfigDict

__all__ = [
    "Appendix",
    "DocumentSegments",
    "normalize_case_number",
    "normalize_decision_number",
    "parse_keywords",
    "split_document",
]


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


# A line that is *only* an appendix label. Deliberately end-anchored: prose like
# "Bilaga 1 innehåller ..." and "markerade med rött i bilagan" must not split the
# document. Labels seen in the corpus are a single letter or a small number.
_APPENDIX_LABEL_RE = re.compile(
    r"^[ \t]*(Bilaga[ \t]+(?:\d{1,2}|[A-ZÅÄÖ]))[ \t]*$",
    re.MULTILINE,
)

# The trailer opens with "Sökord:"; "Ärendenummer:" is the fallback for decisions
# that omit it. Both are line-initial, unlike their in-prose mentions.
_TRAILER_START_PATTERNS = (
    re.compile(r"^[ \t]*Sökord:", re.MULTILINE),
    re.compile(r"^[ \t]*Ärendenummer:", re.MULTILINE),
)

_HOLDING_RE = re.compile(r"^[ \t]*Överklagandenämndens beslut:[ \t]*", re.MULTILINE)

# The typographic rule separating the trailer from the first appendix — a run of
# ellipsis characters, sometimes plain dots. Matched as a whole line so a sentence
# ending in a full stop survives.
_RULE_LINE_RE = re.compile(r"^[ \t]*[….]{2,}[ \t]*$")

_CASE_NUMBER_RE = re.compile(
    r"(?:ÖN\s*)?(?:dnr\s*)?(\d{4})\s*[-–]\s*(\d+)",
    re.IGNORECASE,
)

_DECISION_NUMBER_RE = re.compile(r"(\d{1,3})\s*/\s*(\d{4})")

# The `Sökord:` value. Deliberately not end-of-line anchored: a long value wraps
# onto following lines, so it runs until the next trailer label or the end of the
# trailer. `Ärendenummer` and `Beslut` are the only labels that follow it.
_KEYWORDS_VALUE_RE = re.compile(
    r"^[ \t]*Sökord:(.*?)(?=^[ \t]*(?:Ärendenummer|Beslut):|\Z)",
    re.MULTILINE | re.DOTALL,
)

# A decision classified under several keywords separates them with either.
_KEYWORD_SEPARATOR_RE = re.compile(r"[,;]")


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
        trailer = _strip_ellipsis_rule(text[trailer_start:appendix_start])

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
    """
    match = _CASE_NUMBER_RE.search(raw)
    if match is None:
        return None
    return f"{match.group(1)}-{match.group(2)}"


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


def parse_keywords(trailer: str | None) -> list[str]:
    """Read the subject keywords off the trailer's ``Sökord:`` line.

    These are Överklagandenämnden's own classification of the case — the one piece
    of subject metadata the corpus vouches for, where every other entity type is
    inferred from prose. Returned in document order with duplicates collapsed.

    Never raises: a missing trailer, a trailer carrying only ``Ärendenummer:``, and
    an empty value all come back as an empty list.
    """
    if trailer is None:
        return []

    match = _KEYWORDS_VALUE_RE.search(trailer)
    if match is None:
        return []

    keywords: list[str] = []
    seen: set[str] = set()
    for part in _KEYWORD_SEPARATOR_RE.split(match.group(1)):
        # A wrapped value arrives with newlines inside it, and the corpus ends the
        # line with a full stop that is sentence punctuation, not part of the
        # keyword — `_strip_ellipsis_rule` is what lets that stop survive this far.
        keyword = " ".join(part.split()).rstrip(".").strip()
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
        Appendix(label=match.group(1).strip(), text=raw_text[start:end].strip())
        for match, start, end in zip(labels, starts, ends, strict=True)
    ]
    return labels[0].start(), appendices


def _find_trailer_start(raw_text: str, appendix_start: int) -> int | None:
    """Locate the trailer, ignoring any match that sits inside an appendix.

    An appended lower-instance decision can carry a trailer of its own; only the
    nämnd's counts.
    """
    for pattern in _TRAILER_START_PATTERNS:
        match = pattern.search(raw_text, 0, appendix_start)
        if match is not None:
            return match.start()
    return None


def _find_holding(body: str) -> str | None:
    match = _HOLDING_RE.search(body)
    if match is None:
        return None
    return body[match.end() :].strip() or None


def _strip_ellipsis_rule(trailer: str) -> str:
    kept = [line for line in trailer.splitlines() if not _RULE_LINE_RE.match(line)]
    return "\n".join(kept).strip()
