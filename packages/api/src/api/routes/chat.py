from __future__ import annotations

import json
import logging
import uuid
from collections.abc import AsyncIterator

from ai import trace_context
from fastapi import APIRouter, Depends, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from api.config import (
    RetrievalSettings,
    SessionSettings,
    get_retrieval_settings,
    get_session_settings,
)
from api.dependencies import get_db
from api.services.answerer import DoneEvent, SourcesEvent, TokenEvent, answer_query
from api.services.session_service import get_or_create_session, history_for_llm

logger = logging.getLogger(__name__)
router = APIRouter()

# DEPRECATED — this endpoint and the four services behind it (answerer,
# query_planner, retriever, session_service) are the agent half of the API and
# are slated to move out of the api package. See /api/chat-endpoint.md. Nothing
# consumes it yet, so the marker is about ownership, not a compatibility
# window: the api package is meant to be a deterministic retrieval tool set,
# and this is the only LLM-driven, stateful, streaming surface left in it.
# Deprecated rather than deleted because it is working, tested code that the
# agent will want intact when it lands.

# Upper bound on a single user message; keeps prompts and payloads bounded.
MAX_MESSAGE_CHARS = 4000

# Fallback attribution for anything the chat path calls that does not name
# itself; inner calls override it.
_SOURCE = "api.chat"


class ChatRequest(BaseModel):
    session_id: uuid.UUID | None = None
    message: str = Field(min_length=1, max_length=MAX_MESSAGE_CHARS)


def _format_sse(event: str, data: dict) -> str:
    return f"event: {event}\ndata: {json.dumps(data)}\n\n"


@router.post("/api/chat", deprecated=True)
async def chat_endpoint(
    body: ChatRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
    retrieval_settings: RetrievalSettings = Depends(get_retrieval_settings),
    session_settings: SessionSettings = Depends(get_session_settings),
) -> StreamingResponse:
    embedding_provider = request.app.state.embedding_provider
    structured_llm_provider = request.app.state.structured_llm_provider
    chat_llm_provider = request.app.state.chat_llm_provider
    storage = getattr(request.app.state, "storage", None)

    chat_session = await get_or_create_session(body.session_id, db)
    history = history_for_llm(chat_session, session_settings.session_max_history_turns)

    async def generate() -> AsyncIterator[str]:
        # The trace context is set here, inside the generator, rather than
        # around the handler body: Starlette drives this generator *after*
        # chat_endpoint has returned, so a context entered out there would
        # already have exited before the first token. Set inside, it spans
        # every nested call — decomposition, embedding, reranking, and the
        # streaming synthesis — so one interaction id ties together everything
        # this question cost.
        interaction_id = str(uuid.uuid4())
        logger.info(
            "Chat interaction %s for session %s", interaction_id, chat_session.id
        )

        with trace_context(
            interaction_id=interaction_id,
            session_id=str(chat_session.id),
            source=_SOURCE,
        ):
            done_emitted = False
            try:
                async for event in answer_query(
                    body.message,
                    history,
                    db,
                    embedding_provider=embedding_provider,
                    settings=retrieval_settings,
                    storage=storage,
                    structured_llm_provider=structured_llm_provider,
                    chat_llm_provider=chat_llm_provider,
                    chat_session_id=chat_session.id,
                ):
                    match event:
                        case TokenEvent():
                            yield _format_sse("token", {"text": event.text})
                        case SourcesEvent():
                            yield _format_sse(
                                "sources",
                                {"sources": [s.model_dump() for s in event.sources]},
                            )
                        case DoneEvent():
                            done_emitted = True
                            yield _format_sse(
                                "done", {"session_id": str(chat_session.id)}
                            )
            except Exception:
                if not done_emitted:
                    logger.exception(
                        "Error during query for session %s", chat_session.id
                    )
                    yield _format_sse(
                        "error",
                        {"message": "An error occurred while processing your request."},
                    )
                else:
                    logger.exception(
                        "Error persisting turn for session %s", chat_session.id
                    )

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )
