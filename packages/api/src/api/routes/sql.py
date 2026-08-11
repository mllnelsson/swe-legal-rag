from fastapi import APIRouter, Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from agents import SqlAgentRequest, SqlAgentResult, run_sql_agent
from api.dependencies import get_db

router = APIRouter()


@router.post("/api/sql")
async def sql_endpoint(
    body: SqlAgentRequest,
    request: Request,
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
    return await run_sql_agent(
        body,
        db,
        llm_provider=request.app.state.sql_llm_provider,
    )
