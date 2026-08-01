"""Regex extraction of entities and cross-references from a segmented decision.

Two rules shape everything here, both consequences of decision PDFs carrying the
appealed decision as an appendix (see :mod:`shared.segmentation`):

* **References come from the body only.** A reference found in an appendix is the
  *lower instance* citing something, not Överklagandenämnden. The trailer is
  excluded too — it holds the document's own identifiers, so scanning it made every
  decision cite itself.
* **Only the holding confers primacy.** Relevance used to be positional (latter 60 %
  of the text), which an appendix inverts: the tail of the document *is* the appealed
  decision, so its entities were the ones being promoted.
"""

from __future__ import annotations

import re

from ai.dtos import EntityResult, ExtractedEntity, ExtractedReference
from shared.enums import EntityRelevance, EntityType
from shared.segmentation import (
    DocumentSegments,
    normalize_case_number,
    normalize_decision_number,
)
from worker_extract.entities import deduplicate_entities

# "ÖN 2025-0017" / "ÖN dnr 2025-0017" — the ärendenummer space.
_CASE_REF_RE = re.compile(r"\bÖN\s+(?:dnr\s+)?\d{4}[-–]\d{3,}\b", re.IGNORECASE)

# "beslut 13/2025" — the beslutsnummer space. Requires the leading word so bare
# fractions and dates in prose are not mistaken for citations.
_DECISION_REF_RE = re.compile(
    r"\bbeslut(?:et)?\s+(\d{1,3}\s*/\s*\d{4})\b", re.IGNORECASE
)

_REGULATION_PATTERNS = [
    re.compile(r"kyrkoordningen\s+\d+\s*kap\.?\s*\d+\s*§(?:\s*\d+)?", re.IGNORECASE),
    re.compile(r"kyrkoordningen\s+kapitel\s+\d+(?:\s*§\s*\d+)?", re.IGNORECASE),
    re.compile(r"\bKO\s+\d+:\d+\b", re.IGNORECASE),
]

_PARISH_PATTERNS = [
    re.compile(r"\b([A-ZÅÄÖ][a-zåäö]+(?:\s+[A-Za-zÅÄÖåäö]+){0,3})\s+församling\b"),
    re.compile(r"\b([A-ZÅÄÖ][a-zåäö]+(?:\s+[A-Za-zÅÄÖåäö]+){0,3})\s+stift\b"),
    re.compile(r"\bförsamlingen\s+i\s+([A-ZÅÄÖ][a-zåäö]+)\b"),
]

_KNOWN_ROLES = frozenset(
    {
        "kyrkoherde",
        "kyrkoråd",
        "kyrkofullmäktige",
        "biskop",
        "domkapitel",
        "kontraktsprost",
        "domprost",
        "stiftsstyrelse",
        "präst",
    }
)

_KNOWN_LEGAL_CONCEPTS = frozenset(
    {
        "överklagande",
        "behörighet",
        "jäv",
        "verkställighet",
        "tjänstetillsättning",
        "överklaganderätt",
        "tjänsteförseelse",
        "disciplinärende",
    }
)

# Swedish definite/genitive suffixes the keyword lookups tolerate.
_INFLECTION_SUFFIX = r"(?:en|et|s|ns|ts|n|t|r)?"


def extract_references(segments: DocumentSegments) -> list[ExtractedReference]:
    """Find citations to other decisions, in either identifier space.

    Both spellings are canonicalised so `reference_service` can resolve them
    against `documents.case_number` / `documents.decision_number`. The two formats
    are disjoint, so the canonical string alone says which column to try.
    """
    references: list[ExtractedReference] = []
    seen: set[str] = set()

    matchers = (
        (_CASE_REF_RE, normalize_case_number),
        (_DECISION_REF_RE, normalize_decision_number),
    )
    for pattern, normalize in matchers:
        for match in pattern.finditer(segments.body):
            case_number = normalize(match.group(0))
            if case_number is None or case_number in seen:
                continue
            seen.add(case_number)
            references.append(
                ExtractedReference(
                    case_number=case_number,
                    reference_context=_extract_sentence(segments.body, match.start()),
                )
            )
    return references


def extract_entities_rule_based(segments: DocumentSegments) -> list[ExtractedEntity]:
    """Extract entities from the body and every appendix.

    The holding is scanned first at PRIMARY; because it is a slice of the body,
    every holding entity is also found at MENTIONED and de-duplication resolves the
    pair in PRIMARY's favour. Appendix entities stay MENTIONED unconditionally —
    they belong to the appealed decision, not to this one.
    """
    entities = _entities_in(segments.holding or "", EntityRelevance.PRIMARY)
    entities += _entities_in(segments.body, EntityRelevance.MENTIONED)
    for appendix in segments.appendices:
        entities += _entities_in(appendix.text, EntityRelevance.MENTIONED)
    return deduplicate_entities(entities)


def extract_rule_based(segments: DocumentSegments) -> EntityResult:
    return EntityResult(
        entities=extract_entities_rule_based(segments),
        references=extract_references(segments),
    )


async def extract_rule_based_strategy(
    segments: DocumentSegments, case_number: str | None = None
) -> EntityResult:
    """`extract_rule_based` in `ExtractionStrategy` shape.

    Async and accepting `case_number` only to satisfy the common signature.
    Rule-based extraction does no I/O and does not need the case number:
    excluding the trailer already removes the document's own identifiers.
    """
    return extract_rule_based(segments)


def _entities_in(text: str, relevance: EntityRelevance) -> list[ExtractedEntity]:
    if not text:
        return []
    found = (
        [
            (name, EntityType.REGULATION)
            for name in _match_patterns(text, _REGULATION_PATTERNS)
        ]
        + [
            (name, EntityType.PARISH)
            for name in _match_patterns(text, _PARISH_PATTERNS)
        ]
        + [(name, EntityType.ROLE) for name in _match_keywords(text, _KNOWN_ROLES)]
        + [
            (name, EntityType.LEGAL_CONCEPT)
            for name in _match_keywords(text, _KNOWN_LEGAL_CONCEPTS)
        ]
    )
    return [
        ExtractedEntity(name=name, type=entity_type, relevance=relevance)
        for name, entity_type in found
    ]


def _match_patterns(text: str, patterns: list[re.Pattern[str]]) -> list[str]:
    names: list[str] = []
    seen: set[str] = set()
    for pattern in patterns:
        for match in pattern.finditer(text):
            name = match.group(0).lower().strip()
            if name not in seen:
                seen.add(name)
                names.append(name)
    return names


def _match_keywords(text: str, keywords: frozenset[str]) -> list[str]:
    # Sorted so extraction output is stable run to run: frozenset iteration order
    # depends on per-process string hash seeding.
    lowered = text.lower()
    return [
        keyword
        for keyword in sorted(keywords)
        if re.search(r"\b" + re.escape(keyword) + _INFLECTION_SUFFIX + r"\b", lowered)
    ]


def _extract_sentence(text: str, pos: int) -> str:
    sentence_start = max(0, text.rfind(".", 0, pos) + 1)
    sentence_end = text.find(".", pos)
    if sentence_end == -1:
        sentence_end = len(text)
    return text[sentence_start : sentence_end + 1].strip()
