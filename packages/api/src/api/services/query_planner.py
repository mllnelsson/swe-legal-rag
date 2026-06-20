from __future__ import annotations

import ai
from pydantic import BaseModel
from shared.dtos.search import DocumentFilter


class QueryPlan(BaseModel):
    semantic_query: str
    filter: DocumentFilter


async def plan_query(
    question: str,
    history: list[dict],
    *,
    llm_provider=None,
) -> QueryPlan:
    result = await ai.decompose_query(question, history, provider=llm_provider)

    date_from = None
    date_to = None
    if result.filters is not None:
        date_from = result.filters.start
        date_to = result.filters.end

    category = result.categories[0] if result.categories else None

    doc_filter = DocumentFilter(
        date_from=date_from,
        date_to=date_to,
        category=category,
        entity_names=list(result.entity_refs),
    )

    return QueryPlan(semantic_query=result.semantic_query, filter=doc_filter)
