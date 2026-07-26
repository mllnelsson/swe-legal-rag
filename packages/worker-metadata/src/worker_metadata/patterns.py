from __future__ import annotations

import dataclasses
import datetime
import re
from collections.abc import Callable

from shared.segmentation import (
    DocumentSegments,
    normalize_case_number,
    normalize_decision_number,
    split_document,
)

# Both identifiers sit on their own labelled line in the trailer. Match the line,
# then let shared.segmentation canonicalise whatever spelling it holds.
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
    return _from_trailer_or_body(segments, _CASE_NUMBER_LINE_RE, normalize_case_number)


def extract_decision_number(segments: DocumentSegments) -> str | None:
    """Read the beslutsnummer ("1/2026")."""
    return _from_trailer_or_body(
        segments, _DECISION_NUMBER_LINE_RE, normalize_decision_number
    )


def _from_trailer_or_body(
    segments: DocumentSegments,
    pattern: re.Pattern[str],
    normalize: Callable[[str], str | None],
) -> str | None:
    """Prefer the trailer, fall back to the body — but never the appendices.

    The trailer is where both identifiers belong, and looking there first means a
    header that happens to repeat one cannot win. The body is a fallback for
    decisions that lay the header out differently. Appendices are excluded outright:
    an appended lower-instance decision carries its own diarienummer, and mistaking
    that for this decision's would misfile the whole document.
    """
    for text in (segments.trailer, segments.body):
        if text is None:
            continue
        match = pattern.search(text)
        if match is not None:
            found = normalize(match.group(1))
            if found is not None:
                return found
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


def extract_category(segments: DocumentSegments) -> str | None:
    lines = segments.body.splitlines()[:_HEADER_SEARCH_LINES]
    for index, line in enumerate(lines[:-_CATEGORY_OFFSET]):
        if _CATEGORY_HEADER in line:
            return lines[index + _CATEGORY_OFFSET].strip() or None
    return None


def extract_metadata_rule_based(text: str) -> MetadataResult:
    segments = split_document(text)
    return MetadataResult(
        case_number=extract_case_number(segments),
        decision_number=extract_decision_number(segments),
        decision_date=extract_decision_date(segments),
        decision_outcome=extract_decision_outcome(segments),
        category=extract_category(segments),
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
