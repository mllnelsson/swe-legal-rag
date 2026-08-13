"""Agent loops over the corpus.

An *agent* here is an LLM driving a tool loop toward an answer, as opposed to the
deterministic retrieval tool set in `api`. Each one is a function over its
inputs rather than a service that reaches into a database itself, which is what
lets one be called as a tool by another.

Two live here, and they differ in shape:

- `run_sql_agent` is stateless and one-shot — a question in, a query and its
  rows out. It is the counting tool the conversational agent calls.
- `run_chat_agent` streams, and is driven from a conversation. It still takes no
  database of its own: `ChatToolset` is injected by `api`, which is what keeps
  the dependency running `api -> agents` rather than closing a cycle.
"""

from agents.chat import (
    AgentEvent,
    ChatAgentRequest,
    ChatTool,
    ChatToolset,
    ProgressLabel,
    run_chat_agent,
)
from agents.config import (
    ChatAgentSettings,
    SqlAgentSettings,
    get_chat_agent_settings,
    get_sql_agent_settings,
)
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
    # The conversational agent: a question in, a stream of progress and
    # prose out. Takes its tools as an injected `ChatToolset`, which is what
    # keeps `api -> agents` and not the other way.
    "run_chat_agent",
    "ChatAgentRequest",
    "ChatToolset",
    "AgentEvent",
    "ChatTool",
    "ProgressLabel",
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
    "ChatAgentSettings",
    "get_chat_agent_settings",
    # Errors
    "AgentError",
    "SqlRejectedError",
    "SemanticModelNotFoundError",
    "SemanticModelInvalidError",
    "SemanticModelIncompleteError",
]
