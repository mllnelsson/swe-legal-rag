from __future__ import annotations

import dataclasses
import datetime
import re
from collections.abc import Callable

from shared.segmentation import (
    DocumentSegments,
    TrailerField,
    normalize_case_number,
    normalize_decision_number,
    parse_trailer_fields,
    split_document,
)
from shared.source_headline import parse_source_headline

# Both identifiers sit on their own labelled line in the trailer, which
# `parse_trailer_fields` reads directly. These patterns are the body fallback for
# decisions whose trailer the anchors did not find; match the line, then let
# shared.segmentation canonicalise whatever spelling it holds.
_CASE_NUMBER_LINE_RE = re.compile(r"^[ \t]*Ärendenummer:(.*)$", re.MULTILINE)
_DECISION_NUMBER_LINE_RE = re.compile(r"^[ \t]*Beslut:(.*)$", re.MULTILINE)

_OUTCOME_KEYWORDS: list[str] = [
    r"bifaller\s+överklagandet",
    r"avslår\s+överklagandet",
    r"avvisar\s+överklagandet",
]

# The decision outcome ("avslår", "bifaller", ...) sits near the end of a ruling,
# so only the tail of the text is scanned.
SUMMARY_TAIL_CHARS = 2000

# The category is the third line of the decision header, under "Svenska kyrkans
# överklagandenämnd" and the "Meddelat <date>" line.
_CATEGORY_HEADER = "Svenska kyrkans överklagandenämnd"
_CATEGORY_OFFSET = 2
_HEADER_SEARCH_LINES = 10


@dataclasses.dataclass
class MetadataResult:
    case_number: str | None = None
    decision_number: str | None = None
    decision_date: datetime.date | None = None
    decision_outcome: str | None = None
    category: str | None = None


def extract_case_number(segments: DocumentSegments) -> str | None:
    """Read the ärendenummer, canonicalised to ``YYYY-NNNN``."""
    return _from_trailer_or_body(
        segments,
        TrailerField.CASE_NUMBER,
        _CASE_NUMBER_LINE_RE,
        normalize_case_number,
    )


def extract_decision_number(
    segments: DocumentSegments, source_headline: str | None = None
) -> str | None:
    """Read the beslutsnummer ("1/2026"), corroborated by the crawler headline.

    The document's own trailer wins: the PDF is the authoritative artefact and
    `source_headline` is a listing field the crawler copied. They agree across the
    whole corpus, so the ordering only matters if they ever diverge — and then the
    decision itself is the one to believe.
    """
    from_document = _from_trailer_or_body(
        segments,
        TrailerField.DECISION_NUMBER,
        _DECISION_NUMBER_LINE_RE,
        normalize_decision_number,
    )
    if from_document is not None:
        return from_document

    parsed = parse_source_headline(source_headline)
    return parsed.decision_number if parsed is not None else None


def _from_trailer_or_body(
    segments: DocumentSegments,
    field: TrailerField,
    body_pattern: re.Pattern[str],
    normalize: Callable[[str], str | None],
) -> str | None:
    """Prefer the trailer, fall back to the body — but never the appendices.

    The trailer is where both identifiers belong, and looking there first means a
    header that happens to repeat one cannot win. Reading it through
    `parse_trailer_fields` rather than a second copy of the label regex is what
    makes this independent of the order the decision lists its trailer fields in.

    The body is a fallback for decisions that lay the header out differently.
    Appendices are excluded outright: an appended lower-instance decision carries
    its own diarienummer, and mistaking that for this decision's would misfile the
    whole document.
    """
    value = parse_trailer_fields(segments.trailer).get(field)
    if value is not None and (found := normalize(value)) is not None:
        return found

    match = body_pattern.search(segments.body)
    if match is not None:
        return normalize(match.group(1))
    return None


def extract_decision_date(segments: DocumentSegments) -> datetime.date | None:
    match = re.search(r"Meddelat (\d{4}-\d{2}-\d{2})", segments.body[:2000])
    if match is None:
        return None
    try:
        return datetime.datetime.strptime(match.group(1), "%Y-%m-%d").date()
    except ValueError:
        return None


def extract_decision_outcome(segments: DocumentSegments) -> str | None:
    """Prefer the holding verbatim; fall back to keyword matching in the body."""
    if segments.holding is not None:
        return " ".join(segments.holding.split())

    tail = segments.body[-SUMMARY_TAIL_CHARS:]
    for keyword in _OUTCOME_KEYWORDS:
        match = re.search(
            r"[^.!?\n]*" + keyword + r"[^.!?\n]*[.!?]?", tail, re.IGNORECASE
        )
        if match:
            return match.group(0).strip()
    return None


def extract_category(
    segments: DocumentSegments, source_headline: str | None = None
) -> str | None:
    """Read the category off the header line, falling back to the headline title.

    The header wins where both exist. The two agree for almost every decision, and
    where they differ the PDF is the richer of the two — "Avskrivning m.m." against
    the listing's bare "Avskrivning".
    """
    lines = segments.body.splitlines()[:_HEADER_SEARCH_LINES]
    for index, line in enumerate(lines[:-_CATEGORY_OFFSET]):
        if _CATEGORY_HEADER in line:
            category = lines[index + _CATEGORY_OFFSET].strip()
            if category:
                return category

    parsed = parse_source_headline(source_headline)
    return parsed.title if parsed is not None else None


def extract_metadata_rule_based(
    text: str, source_headline: str | None = None
) -> MetadataResult:
    segments = split_document(text)
    return MetadataResult(
        case_number=extract_case_number(segments),
        decision_number=extract_decision_number(segments, source_headline),
        decision_date=extract_decision_date(segments),
        decision_outcome=extract_decision_outcome(segments),
        category=extract_category(segments, source_headline),
    )


def is_complete(result: MetadataResult) -> bool:
    """Whether the LLM fallback can be skipped.

    ``decision_number`` is deliberately excluded: it is a nice-to-have for
    reference resolution, not something worth paying for an LLM call over.
    """
    return (
        result.case_number is not None
        and result.decision_date is not None
        and result.decision_outcome is not None
        and result.category is not None
    )
