from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class SqlAgentSettings(BaseSettings):
    """Bounds on the text-to-SQL agent.

    Separate from the retrieval and search settings in `api.config` for the same
    reason those are separate from each other: the three answer different
    questions and should tune without disturbing one another.
    """

    model_config = SettingsConfigDict(env_prefix="")

    # Iterations the tool loop may take. Generous enough for the intended shape —
    # ground a column, ground a second, query, repair once — and short enough
    # that a model talking to itself gives up rather than billing indefinitely.
    sql_agent_max_iterations: int = 8
    # Rows a query may return. An aggregate answer is a handful of rows; a cap
    # this size only bites on a listing query, which is then flagged truncated.
    sql_agent_max_rows: int = 200
    # Wall-clock ceiling per statement. The corpus is small enough that anything
    # slower than this is a cross join, not a slow query.
    sql_agent_statement_timeout_ms: int = 5000
    # Distinct values `list_column_values` returns per call. Large enough to show
    # the whole vocabulary of the free-text columns at current corpus size.
    sql_agent_max_column_values: int = 100


@lru_cache(maxsize=1)
def get_sql_agent_settings() -> SqlAgentSettings:
    return SqlAgentSettings()


class ChatAgentSettings(BaseSettings):
    """Bounds on the conversational agent's tool loop."""

    model_config = SettingsConfigDict(env_prefix="")

    # Iterations the orchestrator may take before giving up. Sized for the
    # intended shape — ground the vocabulary, search, maybe count, maybe read a
    # decision, then answer — with room for one repair.
    chat_agent_max_iterations: int = 8
    # Decisions the agent may have read in full in one run. Each is a separate
    # sub-agent call over a whole document, so this is the run's cost ceiling
    # more than its context ceiling: the extracts come back small either way.
    chat_agent_max_documents_read: int = 5
    # Passages the answer may be built from. Every one is read verbatim by the
    # synthesis step, and a citation list longer than this stops being a
    # citation list.
    chat_agent_max_chunks_cited: int = 12
    # Passages one reading may point at. The reader sees a whole decision and
    # hands back indices, so without a cap it can hand the whole document back
    # and undo the reason it is a sub-agent at all.
    chat_agent_max_chunks_per_reading: int = 6
    # Words the reader's connecting note may run to. It is guidance about which
    # passage carries what, not the finding — and a note long enough to be read
    # instead of the passages is the failure this whole path exists to avoid.
    chat_agent_reading_summary_words: int = 80
    # Decisions one search returns. The agent reads their passages, so this
    # trades recall against how much lands in its context per call.
    chat_agent_search_limit: int = 8
    # Passages per decision a search returns. Measured against the real corpus,
    # the deterministic default of 3 puts ~33k characters of verbatim text into
    # one tool result — which the loop then re-sends on every later iteration.
    # Two is enough to judge a decision's relevance; the whole text is a
    # `read_decision` away, and that goes to a sub-agent rather than here.
    chat_agent_chunks_per_decision: int = 2


@lru_cache(maxsize=1)
def get_chat_agent_settings() -> ChatAgentSettings:
    return ChatAgentSettings()
