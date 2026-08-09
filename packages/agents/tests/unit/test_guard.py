from __future__ import annotations

import pytest

from agents.errors import SqlRejectedError
from agents.sql._guard import check_sql, find_predicate_columns


def _rejection(sql: str) -> str:
    with pytest.raises(SqlRejectedError) as exc_info:
        check_sql(sql)
    return str(exc_info.value)


class TestAllowedStatements:
    """What the agent legitimately needs to be able to run."""

    @pytest.mark.parametrize(
        "sql",
        [
            "SELECT count(*) FROM documents",
            "SELECT category, count(*) FROM documents GROUP BY 1",
            "WITH per_year AS (SELECT extract(year FROM decision_date) AS y FROM documents) "
            "SELECT y, count(*) FROM per_year GROUP BY 1",
            "SELECT d.case_number FROM documents d "
            "JOIN document_entities de ON de.document_id = d.id "
            "JOIN entities e ON e.id = de.entity_id",
            # Arithmetic must survive the SELECT * check, which also looks at `*`.
            "SELECT 100.0 * count(*) / 185 AS andel FROM documents",
        ],
    )
    def test_accepted(self, sql: str) -> None:
        check_sql(sql)

    def test_keyword_inside_a_string_literal_is_not_a_keyword(self) -> None:
        """A literal must not be parsed as SQL.

        `category ILIKE '%create%'` is an ordinary predicate; rejecting it would
        make a whole class of legitimate questions unanswerable.
        """
        check_sql("SELECT id FROM documents WHERE category ILIKE '%create%'")

    def test_comment_is_stripped_before_the_head_keyword_check(self) -> None:
        check_sql("-- räknar besluten\nSELECT count(*) FROM documents")

    @pytest.mark.parametrize(
        "sql",
        [
            "SELECT count(*) FROM documents WHERE extract(year FROM decision_date) = 2026",
            "SELECT substring(summary FROM 1 FOR 40) FROM documents",
            "SELECT count(*) FROM documents "
            "WHERE extract(year FROM coalesce(decision_date, created_at)) = 2026",
        ],
    )
    def test_from_as_a_function_argument_separator_is_not_a_table(
        self, sql: str
    ) -> None:
        """`extract(year FROM decision_date)` names a column, not a table.

        Year filtering is the agent's most common operation, so treating this
        FROM as a table reference would reject a large share of valid queries.
        """
        check_sql(sql)

    def test_blocked_column_inside_such_a_call_is_still_caught(self) -> None:
        with pytest.raises(SqlRejectedError):
            check_sql("SELECT substring(raw_text FROM 1 FOR 40) FROM documents")


class TestRejectedStatements:
    def test_multiple_statements(self) -> None:
        message = _rejection("SELECT 1 FROM documents; SELECT 2 FROM documents")
        assert "en sats" in message.lower()

    def test_trailing_semicolon_is_allowed(self) -> None:
        check_sql("SELECT count(*) FROM documents;")

    def test_non_select_head(self) -> None:
        assert "SELECT" in _rejection("DELETE FROM documents")

    def test_data_modifying_cte(self) -> None:
        """The head keyword is WITH, so only the keyword scan catches this."""
        message = _rejection(
            "WITH gone AS (DELETE FROM documents RETURNING id) SELECT * FROM gone"
        )
        assert "DELETE" in message

    def test_comment_hidden_second_statement(self) -> None:
        message = _rejection(
            "SELECT count(*) FROM documents /* x */; DROP TABLE chunks"
        )
        assert "en sats" in message.lower()

    @pytest.mark.parametrize("table", ["sessions", "tasks"])
    def test_non_corpus_tables_are_unreachable(self, table: str) -> None:
        """The allow-list is what keeps conversation history and pipeline state out.

        Load-bearing: the agent runs on the application's own connection, so
        nothing else prevents a SELECT against these.
        """
        message = _rejection(f"SELECT id FROM {table}")
        assert table in message

    def test_system_catalog(self) -> None:
        assert "pg_" in _rejection("SELECT tablename FROM pg_tables")

    def test_star_expansion(self) -> None:
        assert "SELECT *" in _rejection("SELECT * FROM documents")

    def test_qualified_star_expansion(self) -> None:
        assert "SELECT *" in _rejection("SELECT d.* FROM documents d")

    @pytest.mark.parametrize("column", ["embedding", "tsv", "raw_text"])
    def test_payload_sized_columns(self, column: str) -> None:
        table = "documents" if column == "raw_text" else "chunks"
        assert column in _rejection(f"SELECT {column} FROM {table}")

    def test_empty(self) -> None:
        _rejection("   ")


class TestFindPredicateColumns:
    """Which free-text columns a statement *filters* on.

    The distinction from merely selecting them is what stops forced grounding
    deadlocking: the model's own grounding query is a GROUP BY over the very
    column it has not grounded yet.
    """

    def test_grouping_is_not_filtering(self) -> None:
        assert (
            find_predicate_columns(
                "SELECT category, count(*) FROM documents GROUP BY 1"
            )
            == set()
        )

    def test_where_clause_is_filtering(self) -> None:
        assert find_predicate_columns(
            "SELECT count(*) FROM documents WHERE category = 'Avvisning'"
        ) == {("documents", "category")}

    def test_having_clause_is_filtering(self) -> None:
        assert find_predicate_columns(
            "SELECT decision_outcome FROM documents GROUP BY 1 "
            "HAVING decision_outcome ILIKE '%avslår%'"
        ) == {("documents", "decision_outcome")}

    def test_entity_name_in_join_condition(self) -> None:
        assert find_predicate_columns(
            "SELECT count(*) FROM entities e "
            "JOIN document_entities de ON de.entity_id = e.id AND e.name = 'jäv'"
        ) == {("entities", "name")}

    def test_literal_mentioning_a_column_name_does_not_count(self) -> None:
        assert (
            find_predicate_columns(
                "SELECT count(*) FROM documents WHERE summary ILIKE '%category%'"
            )
            == set()
        )

    def test_structural_column_needs_no_grounding(self) -> None:
        assert (
            find_predicate_columns(
                "SELECT count(*) FROM documents WHERE decision_date >= '2026-01-01'"
            )
            == set()
        )

    def test_grouping_after_a_join_is_still_not_filtering(self) -> None:
        """The deadlock, reintroduced by a JOIN.

        A predicate region used to run from the first WHERE/HAVING/ON to the end
        of the statement, so a join's ON clause dragged the trailing GROUP BY
        into it — and the model's own grounding query over a joined table was
        refused for not having been grounded.
        """
        assert (
            find_predicate_columns(
                "SELECT e.name, count(*) AS antal "
                "FROM entities AS e "
                "JOIN document_entities AS de ON de.entity_id = e.id "
                "WHERE e.type = 'keyword' "
                "GROUP BY e.name ORDER BY antal DESC LIMIT 20"
            )
            == set()
        )

    def test_ordering_by_a_free_text_column_is_not_filtering(self) -> None:
        assert (
            find_predicate_columns(
                "SELECT category FROM documents WHERE decision_date IS NOT NULL "
                "ORDER BY category"
            )
            == set()
        )

    def test_a_subquery_predicate_still_counts(self) -> None:
        """A SELECT closes the enclosing region, but the subquery opens its own."""
        assert find_predicate_columns(
            "SELECT count(*) FROM documents WHERE id IN ("
            "SELECT document_id FROM document_entities de "
            "JOIN entities e ON e.id = de.entity_id WHERE e.name = 'jäv')"
        ) == {("entities", "name")}

    def test_a_keyword_argument_separator_cannot_hide_a_filter(self) -> None:
        """`FROM` is deliberately not a region terminator.

        Treating it as one would truncate the region at `substring(... FROM ...)`
        and let a filter on a free-text column through ungrounded.
        """
        assert find_predicate_columns(
            "SELECT count(*) FROM documents "
            "WHERE substring(decision_outcome FROM 1 FOR 5) = 'Överk'"
        ) == {("documents", "decision_outcome")}
