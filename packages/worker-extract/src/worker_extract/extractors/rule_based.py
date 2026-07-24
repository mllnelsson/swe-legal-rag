from __future__ import annotations

import re

from worker_extract.models import (
    EntityRelevance,
    EntityType,
    ExtractedEntity,
    ExtractedReference,
    ExtractionResult,
)

_CASE_REF_RE = re.compile(
    r"\b(ÖN\s+(?:dnr\s+)?\d{4}[-–]\d{3,})\b",
    re.IGNORECASE,
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

# Entities in the latter portion of the document are considered primary
_PRIMARY_THRESHOLD = 0.6


def _extract_sentence(text: str, pos: int) -> str:
    sentence_start = max(0, text.rfind(".", 0, pos) + 1)
    sentence_end = text.find(".", pos)
    if sentence_end == -1:
        sentence_end = len(text)
    return text[sentence_start : sentence_end + 1].strip()


def _relevance(text_len: int, pos: int) -> EntityRelevance:
    return (
        EntityRelevance.PRIMARY
        if pos / max(text_len, 1) >= _PRIMARY_THRESHOLD
        else EntityRelevance.MENTIONED
    )


def extract_references(text: str) -> list[ExtractedReference]:
    refs: list[ExtractedReference] = []
    seen: set[str] = set()
    for m in _CASE_REF_RE.finditer(text):
        case_number = m.group(1).strip()
        if case_number in seen:
            continue
        seen.add(case_number)
        refs.append(
            ExtractedReference(
                case_number=case_number,
                reference_context=_extract_sentence(text, m.start()),
            )
        )
    return refs


def _extract_regulations(text: str) -> list[tuple[str, int]]:
    results: list[tuple[str, int]] = []
    seen: set[str] = set()
    for pattern in _REGULATION_PATTERNS:
        for m in pattern.finditer(text):
            name = m.group(0).lower().strip()
            if name not in seen:
                seen.add(name)
                results.append((name, m.start()))
    return results


def _extract_parishes(text: str) -> list[tuple[str, int]]:
    results: list[tuple[str, int]] = []
    seen: set[str] = set()
    for pattern in _PARISH_PATTERNS:
        for m in pattern.finditer(text):
            name = m.group(0).lower().strip()
            if name not in seen:
                seen.add(name)
                results.append((name, m.start()))
    return results


def _extract_roles(text: str) -> list[tuple[str, int]]:
    results: list[tuple[str, int]] = []
    seen: set[str] = set()
    text_lower = text.lower()
    for role in _KNOWN_ROLES:
        # Allow common Swedish inflection suffixes (-n, -s, -t, -m, -r, -ns, -ts, -en)
        pattern = re.compile(r"\b" + re.escape(role) + r"(?:en|et|s|ns|ts|n|t|r)?\b")
        m = pattern.search(text_lower)
        if m and role not in seen:
            seen.add(role)
            results.append((role, m.start()))
    return results


def _extract_legal_concepts(text: str) -> list[tuple[str, int]]:
    results: list[tuple[str, int]] = []
    seen: set[str] = set()
    text_lower = text.lower()
    for concept in _KNOWN_LEGAL_CONCEPTS:
        # Allow common Swedish inflection suffixes
        pattern = re.compile(r"\b" + re.escape(concept) + r"(?:en|et|s|ns|ts|n|t|r)?\b")
        m = pattern.search(text_lower)
        if m and concept not in seen:
            seen.add(concept)
            results.append((concept, m.start()))
    return results


def extract_entities_rule_based(text: str) -> list[ExtractedEntity]:
    text_len = len(text)
    entities: list[ExtractedEntity] = []

    for name, pos in _extract_regulations(text):
        entities.append(
            ExtractedEntity(
                name=name,
                type=EntityType.REGULATION,
                relevance=_relevance(text_len, pos),
            )
        )

    for name, pos in _extract_parishes(text):
        entities.append(
            ExtractedEntity(
                name=name, type=EntityType.PARISH, relevance=_relevance(text_len, pos)
            )
        )

    for name, pos in _extract_roles(text):
        entities.append(
            ExtractedEntity(
                name=name, type=EntityType.ROLE, relevance=_relevance(text_len, pos)
            )
        )

    for name, pos in _extract_legal_concepts(text):
        entities.append(
            ExtractedEntity(
                name=name,
                type=EntityType.LEGAL_CONCEPT,
                relevance=_relevance(text_len, pos),
            )
        )

    return entities


def extract_rule_based(text: str) -> ExtractionResult:
    # TODO: Make sure there is no self references.
    entities = extract_entities_rule_based(text)
    references = extract_references(text)
    breakpoint()
    return ExtractionResult(
        entities=entities,
        references=references,
    )


class RuleBasedStrategy:
    async def extract(
        self, document_text: str, case_number: str | None = None
    ) -> ExtractionResult:
        return extract_rule_based(document_text)
