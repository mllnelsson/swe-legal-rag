from __future__ import annotations

import uuid
from collections.abc import AsyncIterator
from typing import Literal

from pydantic import BaseModel

import ai
from ai.dtos import ChunkContext, SynthesizeRequest
from api.config import RetrievalSettings
from api.services.query_planner import plan_query
from api.services.retriever import RetrievedChunk, retrieve
from api.services.session_service import append_turn
from shared.repositories.session import SessionRepository
from shared.storage.base import StorageBackend

EXCERPT_MAX_LEN = 200
_PDF_KEY = "documents/{document_id}/original.pdf"


class TokenEvent(BaseModel):
    type: Literal["token"] = "token"
    text: str


class SourcesEvent(BaseModel):
    type: Literal["sources"] = "sources"
    sources: list[SourceReference]


class DoneEvent(BaseModel):
    type: Literal["done"] = "done"


AnswerEvent = TokenEvent | SourcesEvent | DoneEvent


class SourceReference(BaseModel):
    case_number: str | None
    decision_date: str | None
    decision_outcome: str | None
    category: str | None
    excerpt: str
    pdf_url: str | None


def _pdf_url(document_id: uuid.UUID, storage: StorageBackend | None) -> str | None:
    if storage is None:
        return None
    key = _PDF_KEY.format(document_id=document_id)
    try:
        return storage.get_url(key)
    except Exception:
        return None


def _build_sources(
    chunks: list[RetrievedChunk],
    storage: StorageBackend | None,
) -> list[SourceReference]:
    seen: set[uuid.UUID] = set()
    sources: list[SourceReference] = []
    for chunk in chunks:
        if chunk.document_id in seen:
            continue
        seen.add(chunk.document_id)
        sources.append(
            SourceReference(
                case_number=chunk.case_number,
                decision_date=str(chunk.decision_date) if chunk.decision_date else None,
                decision_outcome=chunk.decision_outcome,
                category=chunk.category,
                excerpt=chunk.chunk_text[:EXCERPT_MAX_LEN],
                pdf_url=_pdf_url(chunk.document_id, storage),
            )
        )
    return sources


async def answer_query(
    question: str,
    history: list[dict],
    session,
    *,
    embedding_provider,
    settings: RetrievalSettings,
    storage: StorageBackend | None = None,
    llm_provider=None,
    chat_session_id: uuid.UUID | None = None,
    session_repo: SessionRepository | None = None,
) -> AsyncIterator[AnswerEvent]:
    the_plan = await plan_query(question, history, llm_provider=llm_provider)
    chunks = await retrieve(
        the_plan,
        session,
        embedding_provider=embedding_provider,
        settings=settings,
    )

    chunk_contexts = [
        ChunkContext(
            chunk_text=chunk.chunk_text,
            case_number=chunk.case_number or "",
            decision_date=str(chunk.decision_date) if chunk.decision_date else None,
            decision_outcome=chunk.decision_outcome,
            score=1.0,
        )
        for chunk in chunks
    ]

    request = SynthesizeRequest(
        question=question,
        chunks=chunk_contexts,
        conversation_history=history,
    )

    accumulated: list[str] = []
    async for token in ai.synthesize_answer(request, provider=llm_provider):
        accumulated.append(token)
        yield TokenEvent(text=token)

    yield SourcesEvent(sources=_build_sources(chunks, storage))
    yield DoneEvent()

    if chat_session_id is not None and session_repo is not None:
        await append_turn(chat_session_id, question, "".join(accumulated), session_repo)
