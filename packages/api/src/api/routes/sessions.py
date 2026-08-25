"""Reading and forgetting past conversations.

The retrieval endpoints are stateless and read-only; this is the exception on
both counts. `sessions` is the one table the API writes, and `DELETE` here is
the only route in the API that removes anything.

There is no owner filter because there are no accounts — this is a single-user
tool, so every conversation it has ever held is listed to whoever opens it. That
is a product decision, and [the frontend states it on
screen](/frontend/overview.md) rather than leaving it to be discovered.
"""

import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from api.access_log import note
from api.config import SearchSettings, get_search_settings
from api.dependencies import get_db
from api.pagination import Page, clamp_limit
from api.services.session_service import (
    delete_session,
    get_transcript,
    list_sessions,
)
from shared.dtos.session import SessionSummary, SessionTranscript

router = APIRouter()


@router.get("/api/sessions")
async def list_sessions_endpoint(
    request: Request,
    limit: int | None = Query(default=None, ge=1),
    offset: int = Query(default=0, ge=0),
    db: AsyncSession = Depends(get_db),
    settings: SearchSettings = Depends(get_search_settings),
) -> Page[SessionSummary]:
    """The conversations, most recently active first.

    A summary rather than a transcript: the title is the opening question and
    nothing else is read, so drawing a list of fifty conversations does not pull
    fifty conversations' worth of answers out of the database.

    Conversations whose turn never completed are absent. A session row is
    created before the agent runs, so a failed, aborted or rejected request
    leaves one behind with an empty history; those are not conversations.
    """
    page = await list_sessions(
        db,
        limit=clamp_limit(
            limit,
            default=settings.search_default_limit,
            maximum=settings.search_max_limit,
        ),
        offset=offset,
    )
    note(
        request,
        count=len(page.items),
        total=page.total,
        limit=page.limit,
        offset=page.offset,
    )
    return page


@router.get("/api/sessions/{session_id}")
async def session_transcript_endpoint(
    session_id: uuid.UUID,
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> SessionTranscript:
    """One conversation, as the turns it was appended as.

    **What was said, not what it rested on.** Only the question and the answer
    are persisted — never the passages, extracts or query rows a turn gathered —
    so a reopened conversation has no citations to show, and a client must say
    so rather than render an empty source list.
    """
    transcript = await get_transcript(session_id, db)
    note(
        request,
        session=session_id,
        turns=len(transcript.turns) if transcript else 0,
    )
    if transcript is None:
        raise HTTPException(status_code=404, detail="Session not found")
    return transcript


@router.delete("/api/sessions/{session_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_session_endpoint(
    session_id: uuid.UUID,
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> Response:
    """Forget a conversation.

    No soft delete: the row holds one person's own questions and nothing else
    references it. The [traces](/observability.md) the turns produced are keyed
    by `interaction_id` in file storage and outlive it, so what is actually lost
    is the transcript, not the record of what the turns cost.
    """
    removed = await delete_session(session_id, db)
    note(request, session=session_id, removed=removed)
    if not removed:
        raise HTTPException(status_code=404, detail="Session not found")
    return Response(status_code=status.HTTP_204_NO_CONTENT)
