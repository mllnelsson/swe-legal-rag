from __future__ import annotations

import json
import logging
import time
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
    chat_context_carry,
)
from ai import interaction_scope
from fastapi import APIRouter, Depends, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from api.access_log import note, preview
from api.config import (
    DevSettings,
    SearchSettings,
    SessionSettings,
    get_dev_settings,
    get_search_settings,
    get_session_settings,
)
from api.correlation import INTERACTION_ID_HEADER, interaction_id_of
from api.dependencies import get_db
from api.dev.chat_scripts import SCRIPTS, replay, select_script
from api.services.chat_toolset import build_chat_toolset
from api.services.context_store import PostgresContextStore
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

# What a client shows when the route itself fails rather than the agent. Swedish
# for the same reason the agent's message is: it reaches the person who asked.
_ROUTE_FAILURE_MESSAGE = "Ett fel uppstod när frågan besvarades."


class ChatRequest(BaseModel):
    session_id: uuid.UUID | None = None
    message: str = Field(min_length=1, max_length=MAX_MESSAGE_CHARS)


# The answer, the sources and the error message are all Swedish. Escaping them
# to \uXXXX triples the size of every token frame for no reader's benefit — SSE
# is UTF-8 by definition.
def _format_sse(event: str, data: dict) -> str:
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


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
    dev_settings: DevSettings = Depends(get_dev_settings),
) -> StreamingResponse:
    chat_session = await get_or_create_session(body.session_id, db)
    # Committed here rather than left to the request's teardown. The turn that
    # follows runs for up to a minute, and the `done` frame hands this id to the
    # client, which immediately claims it as a URL and refetches the session
    # list. Both of those would race a row that is still only flushed: a reload
    # in that window reads a 404 for a conversation the client has just been
    # told the name of.
    await db.commit()
    history = history_for_llm(chat_session, session_settings.session_max_history_turns)

    # Resolved out here, not in the generator: the response headers are built
    # before Starlette starts draining it, so an id minted inside could never
    # reach them. `api.access_log` has already resolved it for this request, so
    # asking again would split one turn across two ids.
    interaction_id = interaction_id_of(request)

    # Started before the agent is built, not inside the generator: `run_chat_agent`
    # is a coroutine function, so the work begins when Starlette drains the
    # stream, but the reader's question was asked here.
    started_at = time.perf_counter()
    logger.info(
        "chat started session=%s msg_chars=%d history=%d",
        chat_session.id,
        len(body.message),
        len(history),
    )
    logger.debug("chat question q=%s", preview(body.message))

    # A development switch, off by default. When on, the events are canned and
    # nothing else about the request changes — same SSE framing, same session
    # row, same persisted turn. The toolset and the LLM providers are the
    # expensive half of this request and are provably unused here, so building
    # them would only be a way to fail. See `api.dev.chat_scripts`.
    scripted = select_script(dev_settings.chat_script, body.message)
    if scripted is None:
        agent_events = run_chat_agent(
            ChatAgentRequest(
                question=body.message,
                history=history,
                # Keys the carry-over blob to this conversation, so a follow-up's
                # planner sees what earlier turns established.
                conversation_id=str(chat_session.id),
            ),
            build_chat_toolset(
                db,
                embedding_provider=request.app.state.embedding_provider,
                search_settings=search_settings,
                sql_llm_provider=request.app.state.sql_llm_provider,
            ),
            llm_provider=request.app.state.chat_llm_provider,
            reader_provider=request.app.state.read_llm_provider,
            executor_provider=request.app.state.orchestrate_llm_provider,
            # The blob lives in `sessions.context`, written in the same
            # transaction as the turn's history — see `PostgresContextStore`.
            context_store=PostgresContextStore(db),
            derive_context=chat_context_carry,
        )
    else:
        # A server answering from a script while someone believes it is
        # answering from the corpus is the one real hazard here, so it is said
        # loudly and on every request rather than once at startup.
        logger.warning(
            "chat is SCRIPTED (%s) — no model was called",
            scripted,
        )
        agent_events = replay(SCRIPTS[scripted])

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
        persisted = False
        tool_calls = 0
        sql_events = 0
        source_count = 0
        first_token_at: float | None = None

        def _summarise() -> None:
            """Hand the turn's counts to the access line, on every exit path.

            There is no `chat completed` line of its own: `api.access` fires at
            the true end of the stream and renders these fields, so a second
            summary would be the duplicate started/finished pair the worker
            envelope rule forbids — see /pipeline/worker-patterns.md.
            `answer_chars` and not `tokens` because no token count reaches this
            route; the billed totals are in the trace records
            (/observability.md).
            """
            note(
                request,
                session=chat_session.id,
                tools=tool_calls,
                sql=sql_events,
                sources=source_count,
                answer_chars=sum(len(part) for part in answer_parts),
                scripted=scripted or False,
                persisted=persisted,
            )

        with interaction_scope(
            interaction_id,
            session_id=str(chat_session.id),
            source=_SOURCE,
        ):
            try:
                async for event in agent_events:
                    match event:
                        case ToolCallEvent():
                            tool_calls += 1
                            logger.debug("chat step %s %s", event.tool, event.label)
                            yield _format_sse(
                                "tool_call", event.model_dump(mode="json")
                            )
                        case ToolResultEvent():
                            logger.debug(
                                "chat step %s %s -> %s",
                                event.tool,
                                event.label,
                                event.status,
                            )
                            yield _format_sse(
                                "tool_result", event.model_dump(mode="json")
                            )
                        case SqlEvent():
                            sql_events += 1
                            logger.debug(
                                "chat sql answered=%s rows=%d",
                                event.answered,
                                event.row_count,
                            )
                            yield _format_sse("sql", event.model_dump(mode="json"))
                        case TokenEvent():
                            # Accumulated as it streams, never buffered: the
                            # client sees each token as it arrives and the whole
                            # answer is still available to persist afterwards.
                            if first_token_at is None:
                                first_token_at = time.perf_counter()
                                logger.debug(
                                    "chat first token after %.1fs",
                                    first_token_at - started_at,
                                )
                            answer_parts.append(event.text)
                            yield _format_sse("token", {"text": event.text})
                        case SourcesEvent():
                            source_count = len(event.sources)
                            logger.debug("chat sources=%d", source_count)
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
                            logger.warning(
                                "chat failed in %.1fs after %d tools — %s",
                                time.perf_counter() - started_at,
                                tool_calls,
                                event.message,
                            )
                            yield _format_sse("error", {"message": event.message})
            except Exception:
                if not done_emitted:
                    logger.exception(
                        "chat crashed in %.1fs after %d tools, session %s",
                        time.perf_counter() - started_at,
                        tool_calls,
                        chat_session.id,
                    )
                    yield _format_sse("error", {"message": _ROUTE_FAILURE_MESSAGE})
                    _summarise()
                    return
                logger.exception(
                    "chat crashed after `done`, session %s", chat_session.id
                )
                _summarise()
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
                persisted = True
            except Exception:
                # The answer already reached the client; failing to remember it
                # is worth logging, not worth an error frame after `done`.
                logger.exception(
                    "chat turn not persisted for session %s", chat_session.id
                )

        _summarise()

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
