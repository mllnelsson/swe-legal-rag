from __future__ import annotations

import dataclasses
import datetime
import re

_SWEDISH_MONTHS: dict[str, int] = {
    "januari": 1,
    "februari": 2,
    "mars": 3,
    "april": 4,
    "maj": 5,
    "juni": 6,
    "juli": 7,
    "augusti": 8,
    "september": 9,
    "oktober": 10,
    "november": 11,
    "december": 12,
    "jan": 1,
    "feb": 2,
    "mar": 3,
    "apr": 4,
    "jun": 6,
    "jul": 7,
    "aug": 8,
    "sep": 9,
    "okt": 10,
    "nov": 11,
    "dec": 12,
}

_CASE_NUMBER_PATTERNS: list[str] = [
    r"(?:Dnr|dnr)\s+([\d]{4}-[\d]+)",
    r"Diarienummer\s+([\d]{4}-[\d]+)",
    r"ÖN\s+([\d]{4}-[\d]+)",
    r"(?:Beslut\s+)?([\d]{4}-[\d]{3,})",
]

_OUTCOME_KEYWORDS: list[str] = [
    r"bifaller\s+överklagandet",
    r"avslår\s+överklagandet",
    r"avvisar\s+överklagandet",
]

_CATEGORY_PATTERNS: list[str] = [
    r"Ärende:\s*(.+?)(?:\n|$)",
    r"Ämne:\s*(.+?)(?:\n|$)",
    r"Kategori:\s*(.+?)(?:\n|$)",
]


@dataclasses.dataclass
class MetadataResult:
    case_number: str | None = None
    decision_date: datetime.date | None = None
    decision_outcome: str | None = None
    category: str | None = None


def extract_case_number(text: str) -> str | None:
    for pattern in _CASE_NUMBER_PATTERNS:
        m = re.search(pattern, text, re.IGNORECASE)
        if m:
            return m.group(1).strip()
    return None


def extract_decision_date(text: str) -> datetime.date | None:
    m = re.search(r"\b(\d{4}-\d{2}-\d{2})\b", text)
    if m:
        try:
            return datetime.date.fromisoformat(m.group(1))
        except ValueError:
            pass

    textual = (
        r"(?:den\s+)?(\d{1,2})\s+"
        r"(januari|februari|mars|april|maj|juni|juli|augusti|september|oktober|november|december)"
        r"\s+(\d{4})"
    )
    m = re.search(textual, text, re.IGNORECASE)
    if m:
        month = _SWEDISH_MONTHS.get(m.group(2).lower())
        if month:
            try:
                return datetime.date(int(m.group(3)), month, int(m.group(1)))
            except ValueError:
                pass

    abbreviated = r"(\d{1,2})\s+(jan|feb|mar|apr|maj|jun|jul|aug|sep|okt|nov|dec)\.?\s+(\d{4})"
    m = re.search(abbreviated, text, re.IGNORECASE)
    if m:
        month = _SWEDISH_MONTHS.get(m.group(2).lower())
        if month:
            try:
                return datetime.date(int(m.group(3)), month, int(m.group(1)))
            except ValueError:
                pass

    return None


def extract_decision_outcome(text: str) -> str | None:
    search_text = text[-2000:] if len(text) > 2000 else text
    for keyword in _OUTCOME_KEYWORDS:
        m = re.search(r"[^.!?\n]*" + keyword + r"[^.!?\n]*[.!?]?", search_text, re.IGNORECASE)
        if m:
            return m.group(0).strip()
    return None


def extract_category(text: str) -> str | None:
    for pattern in _CATEGORY_PATTERNS:
        m = re.search(pattern, text, re.IGNORECASE)
        if m:
            return m.group(1).strip()
    return None


def extract_metadata_rule_based(text: str) -> MetadataResult:
    return MetadataResult(
        case_number=extract_case_number(text),
        decision_date=extract_decision_date(text),
        decision_outcome=extract_decision_outcome(text),
        category=extract_category(text),
    )


def is_complete(result: MetadataResult) -> bool:
    return (
        result.case_number is not None
        and result.decision_date is not None
        and result.decision_outcome is not None
        and result.category is not None
    )
