from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from ai.dtos import (
    DecomposeResult,
    EntityResult,
    ExtractedEntity,
    ExtractedReference,
    MetadataResult,
    SummarizeResult,
)
from ai.services import (
    decompose_query,
    extract_entities,
    extract_metadata,
    summarize_document,
)
from llm_core import LLMResponse, Message, Role


@pytest.mark.asyncio
async def test_decompose_query() -> None:
    expected = DecomposeResult(
        filters=None,
        categories=["tjänstetillsättning"],
        entity_refs=["Skattkärrens församling"],
        semantic_query="överklagande tjänstetillsättning",
    )
    with patch("ai.services.generate_structured", new=AsyncMock(return_value=expected)):
        result = await decompose_query("Vad gäller för tjänstetillsättning?")
    assert result == expected


@pytest.mark.asyncio
async def test_decompose_query_with_history() -> None:
    expected = DecomposeResult(
        filters=None,
        categories=[],
        entity_refs=[],
        semantic_query="överklagande",
    )
    history = [{"role": "user", "content": "Tidigare fråga"}]
    with patch("ai.services.generate_structured", new=AsyncMock(return_value=expected)) as mock:
        await decompose_query("Fråga", conversation_history=history)
    messages = mock.call_args[0][0]
    assert "Tidigare fråga" in messages[1].content


@pytest.mark.asyncio
async def test_extract_metadata() -> None:
    expected = MetadataResult(
        case_number="2023-0042",
        decision_date="2023-01-15",
        decision_outcome="bifaller överklagandet",
        category="Kyrkogårdsförvaltning",
    )
    with patch("ai.services.generate_structured", new=AsyncMock(return_value=expected)):
        result = await extract_metadata("Dokumenttext...")
    assert result.case_number == "2023-0042"
    assert result.decision_date == "2023-01-15"
    assert result.decision_outcome == "bifaller överklagandet"
    assert result.category == "Kyrkogårdsförvaltning"


@pytest.mark.asyncio
async def test_extract_entities() -> None:
    expected = EntityResult(
        entities=[ExtractedEntity(name="överklaganderätt", type="legal_concept", relevance="primary")],
        references=[ExtractedReference(target_case_number="2022-0100", reference_type="följer")],
    )
    with patch("ai.services.generate_structured", new=AsyncMock(return_value=expected)):
        result = await extract_entities("Dokumenttext...")
    assert len(result.entities) == 1
    assert result.entities[0].name == "överklaganderätt"
    assert len(result.references) == 1
    assert result.references[0].target_case_number == "2022-0100"


@pytest.mark.asyncio
async def test_extract_entities_with_case_number() -> None:
    expected = EntityResult(entities=[], references=[])
    with patch("ai.services.generate_structured", new=AsyncMock(return_value=expected)) as mock:
        await extract_entities("Dokumenttext...", case_number="2023-0042")
    messages = mock.call_args[0][0]
    assert "2023-0042" in messages[1].content


@pytest.mark.asyncio
async def test_summarize_document() -> None:
    mock_response = LLMResponse(
        message=Message(role=Role.assistant, content="En kortfattad sammanfattning av ärendet."),
        raw=None,
    )
    with patch("ai.services.generate", new=AsyncMock(return_value=mock_response)):
        result = await summarize_document("Dokumenttext...")
    assert isinstance(result, SummarizeResult)
    assert result.summary == "En kortfattad sammanfattning av ärendet."
