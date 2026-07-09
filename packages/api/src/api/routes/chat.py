from __future__ import annotations

import json
import logging
import uuid
from collections.abc import AsyncGenerator, AsyncIterator

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
from api.services.answerer import DoneEvent, SourcesEvent, TokenEvent, answer_query
from api.services.session_service import get_or_create_session, history_for_llm
from shared.db import get_async_session

logger = logging.getLogger(__name__)
router = APIRouter()


class ChatRequest(BaseModel):
    session_id: uuid.UUID | None = None
    message: str = Field(min_length=1, max_length=4000)


def format_sse(event: str, data: dict) -> str:
    return f"event: {event}\ndata: {json.dumps(data)}\n\n"


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    async with get_async_session() as session:
        yield session


@router.post("/api/chat")
async def chat_endpoint(
    body: ChatRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
    retrieval_settings: RetrievalSettings = Depends(get_retrieval_settings),
    session_settings: SessionSettings = Depends(get_session_settings),
) -> StreamingResponse:
    embedding_provider = request.app.state.embedding_provider
    storage = getattr(request.app.state, "storage", None)

    chat_session = await get_or_create_session(body.session_id, db)
    history = history_for_llm(chat_session, session_settings.session_max_history_turns)

    async def generate() -> AsyncIterator[str]:
        done_emitted = False
        try:
            async for event in answer_query(
                body.message,
                history,
                db,
                embedding_provider=embedding_provider,
                settings=retrieval_settings,
                storage=storage,
                chat_session_id=chat_session.id,
            ):
                if isinstance(event, TokenEvent):
                    yield format_sse("token", {"text": event.text})
                elif isinstance(event, SourcesEvent):
                    yield format_sse(
                        "sources", {"sources": [s.model_dump() for s in event.sources]}
                    )
                elif isinstance(event, DoneEvent):
                    done_emitted = True
                    yield format_sse("done", {"session_id": str(chat_session.id)})
        except Exception:
            if not done_emitted:
                logger.exception("Error during query for session %s", chat_session.id)
                yield format_sse(
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
