"""The text-to-SQL agent: a question in, a query and its rows out.

It deliberately does not interpret what the rows mean. A count reads as
authoritative and carries no excerpt to check it against, so the query travels
with the answer and whoever consumes this is expected to show it.
"""

from __future__ import annotations

import logging

from ai import LLMRole, agent_run_scope, create_llm_provider, interaction_scope
from ai.prompts import TEXT_TO_SQL, render
from llm_core import LLMProvider, MaxIterationsError, ToolExecutionError, tool_loop
from sqlalchemy.ext.asyncio import AsyncSession

from agents.config import SqlAgentSettings, get_sql_agent_settings
from agents.sql._dtos import SqlAgentRequest, SqlAgentResult
from agents.sql._schema import build_examples_block, build_schema_description
from agents.sql._semantic_model import SemanticModelDocument, resolve
from agents.sql._tools import GroundingState, build_sql_tools

logger = logging.getLogger(__name__)

__all__ = ["run_sql_agent"]

_SOURCE = "agents.sql"


def _result_from_state(
    state: GroundingState, *, note: str, iterations: int
) -> SqlAgentResult:
    """Assemble the answer from the trail the loop left behind.

    The last *successful* `run_sql` is the answer — the convention the system
    prompt states — so exploratory queries along the way do not have to be
    distinguished by anything more fragile than their order.
    """
    successful = [attempt for attempt in state.attempts if attempt.ok]
    if not successful or state.last_rows is None:
        return SqlAgentResult(
            answered=False,
            sql=None,
            note=note,
            assumptions=state.assumptions,
            attempts=state.attempts,
            iterations=iterations,
        )

    return SqlAgentResult(
        answered=True,
        sql=successful[-1].sql,
        columns=state.last_rows.columns,
        rows=state.last_rows.rows,
        row_count=state.last_rows.row_count,
        truncated=state.last_rows.truncated,
        note=note,
        assumptions=state.assumptions,
        attempts=state.attempts,
        iterations=iterations,
    )


async def run_sql_agent(
    request: SqlAgentRequest,
    session: AsyncSession,
    *,
    llm_provider: LLMProvider | None = None,
    settings: SqlAgentSettings | None = None,
    document: SemanticModelDocument | None = None,
) -> SqlAgentResult:
    """Answer `request.question` with a SQL query and its result set.

    Never raises for a question it cannot answer: an exhausted loop, a rejected
    query or a model that gave up all return `answered=False` with a reason, so
    the caller has one shape to handle rather than two.
    """
    settings = settings or get_sql_agent_settings()
    provider = llm_provider or create_llm_provider(LLMRole.SQL)
    # Resolved once so the prompt the model reads and the policy the tools
    # enforce come from the same document.
    model = resolve(document)
    tools, executors, state = build_sql_tools(session, settings, model)

    messages = render(
        TEXT_TO_SQL,
        {
            "question": request.question,
            "schema": build_schema_description(model),
            "examples": build_examples_block(model),
        },
    )

    # Called two ways: standalone from `POST /api/sql`, where there is no
    # enclosing interaction and one is minted, and as the conversational agent's
    # `query_corpus` tool, where inheriting is what keeps this loop's spend
    # inside the turn that asked for it instead of under an id of its own.
    with (
        interaction_scope(source=_SOURCE, prompt=TEXT_TO_SQL.name) as interaction_id,
        agent_run_scope(),
    ):
        logger.info("SQL agent interaction %s", interaction_id)

        try:
            loop_result = await tool_loop(
                messages,
                tools,
                executors,
                provider=provider,
                max_iterations=settings.sql_agent_max_iterations,
            )
        except MaxIterationsError:
            logger.warning(
                "SQL agent %s exhausted its iteration budget", interaction_id
            )
            return _result_from_state(
                state,
                note=(
                    "Agenten nådde sitt iterationstak utan att bli klar. "
                    "Formulera frågan mer avgränsat."
                ),
                iterations=settings.sql_agent_max_iterations,
            )
        except ToolExecutionError:
            # An executor raised rather than returning an error result, which
            # means a defect here and not a bad query — the tools turn every
            # expected failure into a tool result on purpose.
            logger.exception("SQL agent %s tool executor failed", interaction_id)
            return _result_from_state(
                state,
                note="Ett internt fel uppstod när frågan kördes.",
                iterations=len(state.attempts),
            )

    return _result_from_state(
        state,
        note=loop_result.message.content,
        iterations=loop_result.iterations,
    )
