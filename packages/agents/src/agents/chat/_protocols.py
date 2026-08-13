"""What the conversational agent needs the world to be able to do.

The agent drives the deterministic retrieval tool set, which lives in `api`.
`api` already depends on `agents` — for `run_sql_agent` — so importing back the
other way would close a cycle. This Protocol is the seam instead: `agents`
declares the capabilities in its own shapes, and `api` supplies an object that
satisfies them.

That also keeps the agent testable without a database. A scripted toolset is a
plain object with five methods, not a session, a storage backend and an
embedding provider.
"""

from __future__ import annotations

import uuid
from typing import Protocol, runtime_checkable

from shared.dtos.search import DocumentFilter

from agents.chat._dtos import (
    DecisionProfile,
    DecisionText,
    SearchOutcome,
    Vocabulary,
)
from agents.sql._dtos import SqlAgentResult


@runtime_checkable
class ChatToolset(Protocol):
    """The five capabilities behind the agent's tools."""

    async def search(
        self,
        *,
        query: str,
        queries: list[str],
        document_filter: DocumentFilter,
        include_appendices: bool,
        limit: int,
        chunks_per_decision: int,
    ) -> SearchOutcome:
        """Hybrid semantic and lexical search over the decisions."""
        ...

    async def vocabulary(self, *, contains: str | None = None) -> Vocabulary:
        """The values a filter will actually match, with a count for each."""
        ...

    async def decision_text(
        self, *, document_id: uuid.UUID, include_appendices: bool
    ) -> DecisionText | None:
        """One decision's text in reading order, or None if there is no such id."""
        ...

    async def decision_profile(
        self, *, document_id: uuid.UUID
    ) -> DecisionProfile | None:
        """One decision's entities and citation graph, or None if no such id."""
        ...

    async def tabular_query(self, *, question: str) -> SqlAgentResult:
        """Counting and aggregation, answered by the text-to-SQL agent.

        Never raises for an unanswerable question — `answered=False` carries the
        reason, so the agent has one shape to handle rather than two.
        """
        ...
