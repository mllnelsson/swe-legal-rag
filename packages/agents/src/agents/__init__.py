"""Agent loops over the corpus.

An *agent* here is an LLM driving a tool loop toward an answer, as opposed to the
deterministic retrieval tool set in `api`. Each one is a stateless function: no
sessions, no user interaction, no streaming — so it can be called as a tool by
something else, including a future conversational agent.
"""

from agents.config import SqlAgentSettings, get_sql_agent_settings
from agents.errors import (
    AgentError,
    SemanticModelIncompleteError,
    SemanticModelInvalidError,
    SemanticModelNotFoundError,
    SqlRejectedError,
)
from agents.sql import (
    MAX_QUESTION_CHARS,
    SemanticModelDocument,
    SqlAgentRequest,
    SqlAgentResult,
    SqlAttempt,
    SqlRows,
    build_examples_block,
    build_schema_description,
    check_semantic_model,
    find_semantic_model_path,
    get_semantic_model,
    load_semantic_model,
    run_sql_agent,
)

__all__ = [
    # The text-to-SQL agent: a question in, a query and its rows out. It never
    # interprets the rows — see /api/sql-agent.md on the caller's obligation to
    # surface the query alongside the answer.
    "run_sql_agent",
    "SqlAgentRequest",
    "SqlAgentResult",
    "SqlAttempt",
    "SqlRows",
    "MAX_QUESTION_CHARS",
    # The semantic model: what the agent is told the database holds, and the
    # check that it still matches the ORM. `check_semantic_model` is fatal at
    # API startup — see /reference/semantic-model.md.
    "check_semantic_model",
    "get_semantic_model",
    "load_semantic_model",
    "find_semantic_model_path",
    "SemanticModelDocument",
    "build_schema_description",
    "build_examples_block",
    # Configuration
    "SqlAgentSettings",
    "get_sql_agent_settings",
    # Errors
    "AgentError",
    "SqlRejectedError",
    "SemanticModelNotFoundError",
    "SemanticModelInvalidError",
    "SemanticModelIncompleteError",
]
