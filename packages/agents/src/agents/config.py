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
