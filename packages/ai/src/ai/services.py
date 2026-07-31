from __future__ import annotations

import json
from collections.abc import AsyncIterator

from llm_core import (
    LLMProvider,
    LLMResponse,
    generate,
    generate_stream,
    generate_structured,
    trace_context,
)

from shared.enums import ChunkSection

from ai.dtos import (
    ChunkContext,
    DecomposeResult,
    EntityResult,
    MetadataResult,
    SummarizeResult,
    SynthesizeRequest,
)
from ai.prompts import (
    ANSWER_SYNTHESIS,
    DOCUMENT_SUMMARIZATION,
    ENTITY_EXTRACTION,
    METADATA_EXTRACTION,
    QUERY_DECOMPOSITION,
    render,
)

# Each traced call is tagged with what it is (`source`) and which prompt drove
# it. Who asked for it — an interaction or a document — comes from the trace
# context the caller has already set further out.
#
# The prompt name would otherwise be lost: `render()` returns a plain message
# list, so nothing downstream can tell which template produced it.
_SOURCE_DECOMPOSE = "ai.decompose_query"
_SOURCE_METADATA = "ai.extract_metadata"
_SOURCE_ENTITIES = "ai.extract_entities"
_SOURCE_SUMMARIZE = "ai.summarize_document"
_SOURCE_SYNTHESIZE = "ai.synthesize_answer"


async def decompose_query(
    question: str,
    conversation_history: list[dict] | None = None,
    *,
    provider: LLMProvider | None = None,
) -> DecomposeResult:
    context = {
        "question": question,
        "conversation_history": json.dumps(
            conversation_history or [], ensure_ascii=False
        ),
    }
    messages = render(QUERY_DECOMPOSITION, context)
    with trace_context(source=_SOURCE_DECOMPOSE, prompt=QUERY_DECOMPOSITION.name):
        return await generate_structured(messages, DecomposeResult, provider=provider)


async def extract_metadata(
    raw_text: str,
    *,
    provider: LLMProvider | None = None,
) -> MetadataResult:
    context = {"raw_text": raw_text}
    messages = render(METADATA_EXTRACTION, context)
    with trace_context(source=_SOURCE_METADATA, prompt=METADATA_EXTRACTION.name):
        return await generate_structured(messages, MetadataResult, provider=provider)


async def extract_entities(
    raw_text: str,
    case_number: str | None = None,
    *,
    provider: LLMProvider | None = None,
) -> EntityResult:
    context = {
        "raw_text": raw_text,
        "case_number": case_number or "unknown",
    }
    messages = render(ENTITY_EXTRACTION, context)
    with trace_context(source=_SOURCE_ENTITIES, prompt=ENTITY_EXTRACTION.name):
        return await generate_structured(messages, EntityResult, provider=provider)


async def summarize_document(
    raw_text: str,
    *,
    provider: LLMProvider | None = None,
) -> SummarizeResult:
    context = {"raw_text": raw_text}
    messages = render(DOCUMENT_SUMMARIZATION, context)
    with trace_context(source=_SOURCE_SUMMARIZE, prompt=DOCUMENT_SUMMARIZATION.name):
        response: LLMResponse = await generate(messages, provider=provider)
    return SummarizeResult(summary=response.message.content)


def _chunk_label(chunk: ChunkContext) -> str:
    """Tag each excerpt with whose words it holds.

    An appendix excerpt is the appealed decision — often the very reasoning
    Överklagandenämnden went on to overturn — so the model has to be told, or it
    will present it as the nämnd's own.
    """
    if chunk.section is ChunkSection.APPENDIX:
        label = chunk.appendix_label or "bilaga"
        return f"Mål {chunk.case_number} - {label}, det överklagade beslutet"
    return f"Mål {chunk.case_number}"


async def synthesize_answer(
    request: SynthesizeRequest,
    *,
    provider: LLMProvider | None = None,
) -> AsyncIterator[str]:
    formatted_chunks = "".join(
        f"[{_chunk_label(chunk)}] {chunk.chunk_text}\n" for chunk in request.chunks
    )
    context = {
        "question": request.question,
        "chunks": formatted_chunks,
        "conversation_history": json.dumps(
            request.conversation_history or [], ensure_ascii=False
        ),
    }
    messages = render(ANSWER_SYNTHESIS, context)
    with trace_context(source=_SOURCE_SYNTHESIZE, prompt=ANSWER_SYNTHESIS.name):
        async for token in generate_stream(messages, provider=provider):
            yield token
