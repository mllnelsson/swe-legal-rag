from __future__ import annotations

import json
import logging
import uuid
from collections.abc import AsyncIterator

from agents import ChatAgentRequest, run_chat_agent
from agents.chat import (
    DoneEvent,
    ErrorEvent,
    SourceReference,
    SourcesEvent,
    SqlEvent,
    TokenEvent,
    ToolCallEvent,
    ToolResultEvent,
)
from ai import interaction_scope
from fastapi import APIRouter, Depends, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from api.config import (
    SearchSettings,
    SessionSettings,
    get_search_settings,
    get_session_settings,
)
from api.correlation import INTERACTION_ID_HEADER, resolve_interaction_id
from api.dependencies import get_db
from api.services.chat_toolset import build_chat_toolset
from api.services.session_service import (
    append_turn,
    get_or_create_session,
    history_for_llm,
)

logger = logging.getLogger(__name__)
router = APIRouter()

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


def _pdf_url(document_id: uuid.UUID) -> str:
    """Where the client can fetch the decision itself.

    The API path rather than a storage URL: the local backend's `get_url`
    returns a filesystem path no browser can open, and proxying keeps one URL
    shape across local and GCS.
    """
    return f"/api/documents/{document_id}/pdf"


def _source_payload(source: SourceReference) -> dict:
    payload = source.model_dump(mode="json")
    payload["pdf_url"] = _pdf_url(source.document_id)
    return payload


@router.post("/api/chat")
async def chat_endpoint(
    body: ChatRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
    search_settings: SearchSettings = Depends(get_search_settings),
    session_settings: SessionSettings = Depends(get_session_settings),
) -> StreamingResponse:
    toolset = build_chat_toolset(
        db,
        embedding_provider=request.app.state.embedding_provider,
        search_settings=search_settings,
        sql_llm_provider=request.app.state.sql_llm_provider,
    )
    chat_llm_provider = request.app.state.chat_llm_provider
    read_llm_provider = request.app.state.read_llm_provider

    chat_session = await get_or_create_session(body.session_id, db)
    history = history_for_llm(chat_session, session_settings.session_max_history_turns)

    # Resolved out here, not in the generator: the response headers are built
    # before Starlette starts draining it, so an id minted inside could never
    # reach them.
    interaction_id = resolve_interaction_id(request.headers.get(INTERACTION_ID_HEADER))
    logger.info("Chat interaction %s for session %s", interaction_id, chat_session.id)

    async def generate() -> AsyncIterator[str]:
        # The trace context, unlike the id itself, is entered here inside the
        # generator: Starlette drives this generator *after* chat_endpoint has
        # returned, so a context entered out there would already have exited
        # before the first token. Set inside, it spans every nested call — the
        # orchestrator's iterations, the SQL sub-agent, the reader, the embedding
        # and the streaming synthesis. Both agents inherit this id rather than
        # minting their own, which is what makes the whole turn one sum.
        answer_parts: list[str] = []
        done_emitted = False

        with interaction_scope(
            interaction_id,
            session_id=str(chat_session.id),
            source=_SOURCE,
        ):
            try:
                async for event in run_chat_agent(
                    ChatAgentRequest(question=body.message, history=history),
                    toolset,
                    llm_provider=chat_llm_provider,
                    reader_provider=read_llm_provider,
                ):
                    match event:
                        case ToolCallEvent():
                            yield _format_sse(
                                "tool_call", event.model_dump(mode="json")
                            )
                        case ToolResultEvent():
                            yield _format_sse(
                                "tool_result", event.model_dump(mode="json")
                            )
                        case SqlEvent():
                            yield _format_sse("sql", event.model_dump(mode="json"))
                        case TokenEvent():
                            # Accumulated as it streams, never buffered: the
                            # client sees each token as it arrives and the whole
                            # answer is still available to persist afterwards.
                            answer_parts.append(event.text)
                            yield _format_sse("token", {"text": event.text})
                        case SourcesEvent():
                            yield _format_sse(
                                "sources",
                                {
                                    "sources": [
                                        _source_payload(s) for s in event.sources
                                    ]
                                },
                            )
                        case DoneEvent():
                            done_emitted = True
                            yield _format_sse(
                                "done", {"session_id": str(chat_session.id)}
                            )
                        case ErrorEvent():
                            # Terminal. The agent has already logged the cause;
                            # the failed turn is not persisted.
                            yield _format_sse("error", {"message": event.message})
            except Exception:
                if not done_emitted:
                    logger.exception(
                        "Error during query for session %s", chat_session.id
                    )
                    yield _format_sse(
                        "error",
                        {"message": "An error occurred while processing your request."},
                    )
                    return
                logger.exception(
                    "Error persisting turn for session %s", chat_session.id
                )
                return

        if done_emitted:
            try:
                await append_turn(
                    chat_session.id,
                    body.message,
                    "".join(answer_parts),
                    db,
                    interaction_id=interaction_id,
                )
            except Exception:
                # The answer already reached the client; failing to remember it
                # is worth logging, not worth an error frame after `done`.
                logger.exception(
                    "Error persisting turn for session %s", chat_session.id
                )

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
            # Sent before the stream opens, so it survives a turn that ends in an
            # `error` frame — which is the turn someone reports.
            INTERACTION_ID_HEADER: interaction_id,
        },
    )
