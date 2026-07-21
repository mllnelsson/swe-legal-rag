from __future__ import annotations

import dataclasses
import datetime
import re

_CASE_NUMBER_PATTERNS: list[str] = [
    r"Ärendenummer: ÖN\s+(\d{4}-\d+)",
]

_OUTCOME_KEYWORDS: list[str] = [
    r"bifaller\s+överklagandet",
    r"avslår\s+överklagandet",
    r"avvisar\s+överklagandet",
]

# The decision outcome ("avslår", "bifaller", ...) sits near the end of a ruling,
# so only the tail of the text is scanned.
SUMMARY_TAIL_CHARS = 2000


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
    m = re.search(r"Meddelat (\d{4}-\d{2}-\d{2})", text[:2000])
    if m:
        try:
            return datetime.datetime.strptime(m.group(1), "%Y-%m-%d").date()
        except ValueError:
            pass
    return None


def extract_decision_outcome(text: str) -> str | None:
    m = re.search(r"^Bilaga\s+(?:\d+|[A-ZÅÄÖ])\b", text, re.MULTILINE)
    pre_apendix_text = text[: m.start()] if m else text
    m = re.search(r"^Överklagandenämndens beslut:\s*", pre_apendix_text, re.MULTILINE)
    # Include all the text between the two anchors
    if m:
        after_descison = pre_apendix_text[m.end() :]
        end_anchor = re.search(r"^Sökord: ", after_descison, re.MULTILINE)
        if end_anchor:
            return (
                after_descison[: end_anchor.start()]
                .strip()
                .replace("\r\n", " ")
                .replace("\n", " ")
            )
    search_text = (
        pre_apendix_text[-SUMMARY_TAIL_CHARS:]
        if len(pre_apendix_text) > SUMMARY_TAIL_CHARS
        else pre_apendix_text
    )
    for keyword in _OUTCOME_KEYWORDS:
        m = re.search(
            r"[^.!?\n]*" + keyword + r"[^.!?\n]*[.!?]?", search_text, re.IGNORECASE
        )
        if m:
            return m.group(0).strip()
    return None


def extract_category(text: str) -> str | None:
    # Utilize the descison sampling has the category as the third line
    first_lines = text.splitlines()[:10]
    for i, line in enumerate(first_lines[:-3]):
        if "Svenska kyrkans överklagandenämnd" in line:
            return first_lines[i + 2]
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
