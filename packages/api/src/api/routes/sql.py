from ai import interaction_scope
from fastapi import APIRouter, Depends, Request, Response
from sqlalchemy.ext.asyncio import AsyncSession

from agents import SqlAgentRequest, SqlAgentResult, run_sql_agent
from api.correlation import INTERACTION_ID_HEADER, resolve_interaction_id
from api.dependencies import get_db

router = APIRouter()


@router.post("/api/sql")
async def sql_endpoint(
    body: SqlAgentRequest,
    request: Request,
    response: Response,
    db: AsyncSession = Depends(get_db),
) -> SqlAgentResult:
    """Answer a Swedish question with a SQL query and its rows.

    Complements `POST /api/search`, which finds passages but cannot count. The
    response carries the generated query alongside the result **and consumers are
    obliged to surface it** — a count reads as authoritative and, unlike a search
    hit, carries no excerpt to check it against. See /api/sql-agent.md.

    Never 500s on a question it cannot answer: an ungroundable or out-of-schema
    question comes back `answered: false` with the reason in `note`.
    """
    interaction_id = resolve_interaction_id(request.headers.get(INTERACTION_ID_HEADER))
    response.headers[INTERACTION_ID_HEADER] = interaction_id

    # Opened here rather than left to the agent so a client-supplied id is
    # honoured; reached this way the agent finds an interaction and joins it.
    with interaction_scope(interaction_id):
        return await run_sql_agent(
            body,
            db,
            llm_provider=request.app.state.sql_llm_provider,
        )
