from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest
from shared.enums import ChunkSection

from ai.dtos import (
    ChunkContext,
    DecomposeResult,
    EntityResult,
    ExtractedEntity,
    ExtractedReference,
    MetadataResult,
    SummarizeResult,
    SynthesizeRequest,
)
from ai.services import (
    decompose_query,
    extract_entities,
    extract_metadata,
    summarize_document,
    synthesize_answer,
)
from llm_core import LLMResponse, Message, Role, StreamChunk
from shared.enums import EntityRelevance, EntityType


def _response(content: str) -> LLMResponse:
    return LLMResponse(message=Message(role=Role.assistant, content=content))


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
    with patch(
        "ai.services.generate_structured", new=AsyncMock(return_value=expected)
    ) as mock:
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
        entities=[
            ExtractedEntity(
                name="överklaganderätt",
                type=EntityType.LEGAL_CONCEPT,
                relevance=EntityRelevance.PRIMARY,
            )
        ],
        references=[
            ExtractedReference(
                case_number="2022-0100",
                reference_context="Se ärende 2022-0100 för liknande avgörande.",
            )
        ],
    )
    with patch("ai.services.generate_structured", new=AsyncMock(return_value=expected)):
        result = await extract_entities("Dokumenttext...")
    assert len(result.entities) == 1
    assert result.entities[0].name == "överklaganderätt"
    assert len(result.references) == 1
    assert result.references[0].case_number == "2022-0100"


@pytest.mark.asyncio
async def test_extract_entities_with_case_number() -> None:
    expected = EntityResult(entities=[], references=[])
    with patch(
        "ai.services.generate_structured", new=AsyncMock(return_value=expected)
    ) as mock:
        await extract_entities("Dokumenttext...", case_number="2023-0042")
    messages = mock.call_args[0][0]
    assert "2023-0042" in messages[1].content


@pytest.mark.asyncio
async def test_summarize_document() -> None:
    mock_response = LLMResponse(
        message=Message(
            role=Role.assistant, content="En kortfattad sammanfattning av ärendet."
        ),
        raw=None,
    )
    with patch("ai.services.generate", new=AsyncMock(return_value=mock_response)):
        result = await summarize_document("Dokumenttext...")
    assert isinstance(result, SummarizeResult)
    assert result.summary == "En kortfattad sammanfattning av ärendet."


@pytest.mark.asyncio
async def test_synthesize_answer_streams_tokens() -> None:
    expected_tokens = ["Enligt ", "beslut ", "12/2023..."]

    async def mock_generate_stream(*args: object, **kwargs: object):  # type: ignore[return]
        for token in expected_tokens:
            yield token

    request = SynthesizeRequest(
        question="Vad gäller för överklaganden?",
        chunks=[
            ChunkContext(
                case_number="12/2023",
                chunk_text="Nämnden beslutar att bifalla överklagandet.",
                score=0.95,
            )
        ],
    )

    with patch("ai.services.generate_stream", mock_generate_stream):
        tokens: list[str] = []
        async for token in synthesize_answer(request):
            tokens.append(token)

    assert tokens == expected_tokens


@pytest.mark.asyncio
async def test_synthesize_answer_uses_answer_synthesis_template() -> None:
    captured_messages: list[Message] = []

    async def mock_generate_stream(messages: list[Message], **kwargs: object):  # type: ignore[return]
        captured_messages.extend(messages)
        yield "token"

    request = SynthesizeRequest(
        question="Vad händer om man missar en deadline?",
        chunks=[
            ChunkContext(
                case_number="7/2022", chunk_text="Överklagandet avvisas.", score=0.8
            )
        ],
    )

    with patch("ai.services.generate_stream", mock_generate_stream):
        async for _ in synthesize_answer(request):
            pass

    assert any("7/2022" in m.content for m in captured_messages)
    assert any("Vad händer" in m.content for m in captured_messages)


async def test_synthesize_answer_marks_appendix_excerpts() -> None:
    """An appendix excerpt is the appealed decision, not the nämnd's holding.

    The label is the only thing standing between the model and presenting the
    overturned reasoning as the ruling.
    """
    captured_messages: list[Message] = []

    async def mock_generate_stream(messages: list[Message], **kwargs: object):  # type: ignore[return]
        captured_messages.extend(messages)
        yield "token"

    request = SynthesizeRequest(
        question="Vad beslutade stiftet?",
        chunks=[
            ChunkContext(
                case_number="1/2026",
                chunk_text="Stiftet avslår begäran.",
                score=0.8,
                section=ChunkSection.APPENDIX,
                appendix_label="Bilaga A",
            ),
            ChunkContext(
                case_number="1/2026",
                chunk_text="Nämnden undanröjer beslutet.",
                score=0.8,
            ),
        ],
    )

    with patch("ai.services.generate_stream", mock_generate_stream):
        async for _ in synthesize_answer(request):
            pass

    prompt = "\n".join(m.content for m in captured_messages)
    assert "Bilaga A, det överklagade beslutet" in prompt
    # The body excerpt keeps the plain label.
    assert "[Mål 1/2026]" in prompt


class TestTraceAttribution:
    """Each service call tags its trace with what it is and which prompt drove it."""

    @pytest.fixture
    def recorder(self):
        from llm_core import set_trace_recorder

        class Recording:
            def __init__(self):
                self.records = []

            def record(self, record):
                self.records.append(record)

        recorder = Recording()
        set_trace_recorder(recorder)
        yield recorder
        set_trace_recorder(None)

    async def test_decompose_query_is_attributed(self, recorder) -> None:
        provider = AsyncMock()
        provider.generate = AsyncMock(
            return_value=_response(
                '{"categories": [], "entity_refs": [], "semantic_query": "kyrka"}'
            )
        )

        await decompose_query("Vad gäller?", provider=provider)

        (record,) = recorder.records
        assert record.context["source"] == "ai.decompose_query"
        assert record.context["prompt"] == "QUERY_DECOMPOSITION"

    async def test_extract_metadata_is_attributed(self, recorder) -> None:
        provider = AsyncMock()
        provider.generate = AsyncMock(return_value=_response("{}"))

        await extract_metadata("beslut", provider=provider)

        (record,) = recorder.records
        assert record.context["source"] == "ai.extract_metadata"
        assert record.context["prompt"] == "METADATA_EXTRACTION"

    async def test_extract_entities_is_attributed(self, recorder) -> None:
        provider = AsyncMock()
        provider.generate = AsyncMock(
            return_value=_response('{"entities": [], "references": []}')
        )

        await extract_entities("beslut", provider=provider)

        (record,) = recorder.records
        assert record.context["source"] == "ai.extract_entities"
        assert record.context["prompt"] == "ENTITY_EXTRACTION"

    async def test_summarize_document_is_attributed(self, recorder) -> None:
        provider = AsyncMock()
        provider.generate = AsyncMock(return_value=_response("sammanfattning"))

        await summarize_document("beslut", provider=provider)

        (record,) = recorder.records
        assert record.context["source"] == "ai.summarize_document"
        assert record.context["prompt"] == "DOCUMENT_SUMMARIZATION"

    async def test_synthesize_answer_is_attributed(self, recorder) -> None:
        async def _stream(*args, **kwargs):
            for text in ["Sva", "r"]:
                yield StreamChunk(text=text)

        provider = AsyncMock()
        provider.generate_stream = AsyncMock(side_effect=_stream)

        request = SynthesizeRequest(question="Vad gäller?", chunks=[])
        assert [token async for token in synthesize_answer(request, provider=provider)]

        (record,) = recorder.records
        assert record.context["source"] == "ai.synthesize_answer"
        assert record.context["prompt"] == "ANSWER_SYNTHESIS"
        assert record.response_text == "Svar"

    async def test_outer_correlation_survives_into_the_record(self, recorder) -> None:
        """The caller's interaction id must reach the innermost trace."""
        from llm_core import trace_context

        provider = AsyncMock()
        provider.generate = AsyncMock(return_value=_response("{}"))

        with trace_context(interaction_id="abc"):
            await extract_metadata("beslut", provider=provider)

        (record,) = recorder.records
        assert record.context["interaction_id"] == "abc"
        assert record.context["source"] == "ai.extract_metadata"
