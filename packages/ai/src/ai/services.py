from __future__ import annotations

import json
from collections.abc import AsyncIterator

from llm_core import (
    LLMProvider,
    LLMResponse,
    generate,
    generate_stream,
    generate_structured,
)

from ai.dtos import (
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
    return await generate_structured(messages, DecomposeResult, provider=provider)  # type: ignore[return-value]


async def extract_metadata(
    raw_text: str,
    *,
    provider: LLMProvider | None = None,
) -> MetadataResult:
    context = {"raw_text": raw_text}
    messages = render(METADATA_EXTRACTION, context)
    return await generate_structured(messages, MetadataResult, provider=provider)  # type: ignore[return-value]


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
    return await generate_structured(messages, EntityResult, provider=provider)  # type: ignore[return-value]


async def summarize_document(
    raw_text: str,
    *,
    provider: LLMProvider | None = None,
) -> SummarizeResult:
    context = {"raw_text": raw_text}
    messages = render(DOCUMENT_SUMMARIZATION, context)
    response: LLMResponse = await generate(messages, provider=provider)
    return SummarizeResult(summary=response.message.content)


async def synthesize_answer(
    request: SynthesizeRequest,
    *,
    provider: LLMProvider | None = None,
) -> AsyncIterator[str]:
    formatted_chunks = "".join(
        f"[Mål {chunk.case_number}] {chunk.chunk_text}\n" for chunk in request.chunks
    )
    context = {
        "question": request.question,
        "chunks": formatted_chunks,
        "conversation_history": json.dumps(
            request.conversation_history or [], ensure_ascii=False
        ),
    }
    messages = render(ANSWER_SYNTHESIS, context)
    async for token in generate_stream(messages, provider=provider):
        yield token
