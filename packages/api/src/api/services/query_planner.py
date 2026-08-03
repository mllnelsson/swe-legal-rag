from __future__ import annotations

import ai
from pydantic import BaseModel
from shared.dtos.search import DocumentFilter


# DEPRECATED — chat-surface service, slated to move out of the api package with
# POST /api/chat. See /api/chat-endpoint.md. Deliberately not reused by
# deterministic search: it infers filters from conversation history, which would
# silently override a caller's explicit ones. See /retrieval/query-expansion.md.


class QueryPlan(BaseModel):
    semantic_query: str
    filter: DocumentFilter
    # Whether the question is about the appealed decision rather than the nämnd's
    # own ruling. Kept off the DocumentFilter because it selects parts of a
    # document, not documents.
    include_appendices: bool = False


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

    return QueryPlan(
        semantic_query=result.semantic_query,
        filter=doc_filter,
        include_appendices=result.include_appendices,
    )
