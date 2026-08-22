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
    DecisionReading,
    DecomposeResult,
    EntityResult,
    MetadataResult,
    PassageNote,
    QueryExpansionResult,
    SummarizeResult,
    SynthesizeRequest,
    TabularEvidence,
)
from ai.prompts import (
    ANSWER_SYNTHESIS,
    DOCUMENT_SUMMARIZATION,
    ENTITY_EXTRACTION,
    METADATA_EXTRACTION,
    QUERY_DECOMPOSITION,
    QUERY_EXPANSION,
    render,
)

# Each traced call is tagged with what it is (`source`) and which prompt drove
# it. Who asked for it — an interaction or a document — comes from the trace
# context the caller has already set further out.
#
# The prompt name would otherwise be lost: `render()` returns a plain message
# list, so nothing downstream can tell which template produced it.
_SOURCE_DECOMPOSE = "ai.decompose_query"
_SOURCE_EXPAND = "ai.expand_query"
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


async def expand_query(
    question: str,
    *,
    max_variants: int,
    provider: LLMProvider | None = None,
) -> QueryExpansionResult:
    """Alternative phrasings of a search question.

    Stateless by design — no conversation history, no filters, no rewritten
    "best" query. It answers only "what else could this have been called", which
    is what keeps it a search-tool concern rather than a planner's.
    """
    context = {"question": question, "max_variants": max_variants}
    messages = render(QUERY_EXPANSION, context)
    with trace_context(source=_SOURCE_EXPAND, prompt=QUERY_EXPANSION.name):
        return await generate_structured(
            messages, QueryExpansionResult, provider=provider
        )


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


# Rendered where a section of the evidence bundle is empty. A visible marker
# beats a blank: it tells the model the section exists and holds nothing, so an
# absent count reads as "not established" rather than "not mentioned".
_NOTHING = "(inget)"


def _chunk_label(chunk: ChunkContext) -> str:
    """Tag each excerpt with its handle and whose words it holds.

    The handle leads because the model marks its claims with it; the
    attribution follows because an appendix excerpt is the appealed decision —
    often the very reasoning Överklagandenämnden went on to overturn — and the
    model has to be told, or it will present it as the nämnd's own.
    """
    if chunk.section is ChunkSection.APPENDIX:
        label = chunk.appendix_label or "bilaga"
        return (
            f"{chunk.handle} · Mål {chunk.case_number} - {label}, "
            "det överklagade beslutet"
        )
    return f"{chunk.handle} · Mål {chunk.case_number}"


def _format_chunks(chunks: list[ChunkContext]) -> str:
    if not chunks:
        return _NOTHING
    return "".join(f"[{_chunk_label(chunk)}] {chunk.chunk_text}\n" for chunk in chunks)


def _format_annotations(notes: list[PassageNote]) -> str:
    """The guidance, one line per passage, handle first.

    Rendered as a list rather than prose so its status is visible: these are
    labels on the evidence, not sentences the writer may lift.
    """
    if not notes:
        return _NOTHING
    lines = []
    for note in notes:
        caution = f" — obs: {note.caution}" if note.caution else ""
        lines.append(f"{note.handle}: {note.carries}{caution}")
    return "\n".join(lines)


def _format_gaps(gaps: list[str]) -> str:
    if not gaps:
        return _NOTHING
    return "\n".join(f"- {gap}" for gap in gaps)


def _format_readings(readings: list[DecisionReading]) -> str:
    if not readings:
        return _NOTHING
    return "\n".join(
        f"[Mål {reading.case_number}] {reading.extract}" for reading in readings
    )


def _format_tabular(tabular: TabularEvidence | None) -> str:
    """The rows, and the query that produced them.

    The query is rendered alongside because the model is told that counts may
    only come from here — showing it what was actually asked is what makes that
    instruction checkable rather than a matter of trust.
    """
    if tabular is None:
        return _NOTHING

    header = " | ".join(tabular.columns)
    body = "\n".join(
        " | ".join("" if value is None else str(value) for value in row)
        for row in tabular.rows
    )
    parts = [f"Fråga: {tabular.sql}", f"Rader: {tabular.row_count}", header, body]
    if tabular.truncated:
        parts.append("(resultatet är avkortat)")
    if tabular.assumptions:
        parts.append("Tolkningsval: " + "; ".join(tabular.assumptions))
    return "\n".join(parts)


async def synthesize_answer(
    request: SynthesizeRequest,
    *,
    provider: LLMProvider | None = None,
) -> AsyncIterator[str]:
    context = {
        "question": request.question,
        "chunks": _format_chunks(request.chunks),
        "readings": _format_readings(request.readings),
        "tabular": _format_tabular(request.tabular),
        "annotations": _format_annotations(request.annotations),
        "gaps": _format_gaps(request.gaps),
        "conversation_history": json.dumps(
            request.conversation_history or [], ensure_ascii=False
        ),
    }
    messages = render(ANSWER_SYNTHESIS, context)
    with trace_context(source=_SOURCE_SYNTHESIZE, prompt=ANSWER_SYNTHESIS.name):
        async for token in generate_stream(messages, provider=provider):
            yield token
