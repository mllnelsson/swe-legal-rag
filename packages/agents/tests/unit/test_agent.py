"""The loop, driven by a scripted provider rather than a real model."""

from __future__ import annotations

from typing import cast

import pytest
from ai import interaction_scope
from agent_kit.llm import (
    LLMCallRecord,
    LLMResponse,
    Message,
    Role,
    ToolCall,
    set_trace_recorder,
)
from sqlalchemy.ext.asyncio import AsyncSession

from agents.config import SqlAgentSettings
from agents.sql import SqlAgentRequest, _tools, run_sql_agent
from agents.sql._agent import _closing_note
from agents.sql._dtos import SqlRows

# The sandbox is stubbed in every test here, so the session is threaded through
# but never touched.
NO_SESSION = cast("AsyncSession", object())


class ScriptedProvider:
    """Replays a fixed sequence of assistant turns, one per loop iteration."""

    def __init__(self, *turns: Message) -> None:
        self._turns = list(turns)
        self.seen_messages: list[list[Message]] = []

    async def generate(
        self, messages, *, tools=None, response_schema=None
    ) -> LLMResponse:
        self.seen_messages.append(list(messages))
        return LLMResponse(message=self._turns.pop(0))

    async def generate_stream(self, messages):  # pragma: no cover - unused here
        raise NotImplementedError


def _tool_call(name: str, **arguments) -> Message:
    return Message(
        role=Role.assistant,
        tool_calls=(ToolCall(id=f"call-{name}", name=name, arguments=arguments),),
    )


def _final(content: str) -> Message:
    return Message(role=Role.assistant, content=content)


@pytest.fixture(autouse=True)
def stub_sandbox(monkeypatch: pytest.MonkeyPatch) -> None:
    async def fake_execute_readonly(
        session, sql, *, max_rows, statement_timeout_ms, params=None
    ):
        # `AS varde` is what `_column_values_sql` builds and nothing the model
        # writes; the count query also contains `count(*)` and `WHERE`, so those
        # do not tell the two apart.
        if "AS varde" in sql:
            return SqlRows(
                columns=["varde", "antal"],
                rows=[["Utlämnande av handling", 17]],
                row_count=1,
                truncated=False,
            )
        return SqlRows(columns=["antal"], rows=[[12]], row_count=1, truncated=False)

    monkeypatch.setattr(_tools, "execute_readonly", fake_execute_readonly)


async def _run(*turns: Message):
    provider = ScriptedProvider(*turns)
    result = await run_sql_agent(
        SqlAgentRequest(question="Hur många avslogs 2026?"),
        NO_SESSION,
        llm_provider=provider,
        settings=SqlAgentSettings(),
    )
    return result, provider


async def test_grounds_then_queries_then_answers() -> None:
    result, _provider = await _run(
        _tool_call("list_column_values", table="documents", column="category"),
        _tool_call("note_assumption", assumption="tolkade 2026 som decision_date"),
        _tool_call(
            "run_sql",
            sql=(
                "SELECT count(*) AS antal FROM documents "
                "WHERE category = 'Utlämnande av handling'"
            ),
        ),
        _final("Räknade besluten i kategorin."),
    )

    assert result.answered is True
    assert result.sql is not None and "count(*)" in result.sql
    assert result.rows == [[12]]
    assert result.columns == ["antal"]
    assert result.assumptions == ["tolkade 2026 som decision_date"]
    assert result.note == "Räknade besluten i kategorin."
    assert result.iterations == 4


async def test_the_last_successful_query_is_the_answer() -> None:
    """Exploration precedes the real query, so order decides, not guesswork."""
    result, _provider = await _run(
        _tool_call(
            "run_sql", sql="SELECT category, count(*) FROM documents GROUP BY 1"
        ),
        _tool_call(
            "run_sql",
            sql="SELECT count(*) AS antal FROM documents WHERE decision_date >= '2026-01-01'",
        ),
        _final("Klart."),
    )

    assert result.sql is not None
    assert result.sql.startswith("SELECT count(*) AS antal")
    assert len([a for a in result.attempts if a.ok]) == 2


async def test_a_refusal_is_fed_back_and_the_agent_recovers() -> None:
    """An ungrounded query must not end the run — it must correct it.

    This is the whole point of returning refusals as tool results rather than
    raising: the loop's normal repair path does the work.
    """
    result, provider = await _run(
        _tool_call(
            "run_sql",
            sql="SELECT count(*) FROM documents WHERE category = 'Avvisning'",
        ),
        _tool_call("list_column_values", table="documents", column="category"),
        _tool_call(
            "run_sql",
            sql="SELECT count(*) AS antal FROM documents WHERE category = 'Avvisning'",
        ),
        _final("Klart."),
    )

    assert result.answered is True
    assert [a.ok for a in result.attempts] == [False, True]
    # The refusal reached the model as a tool result it could act on.
    refusals = [
        message
        for turn in provider.seen_messages
        for message in turn
        if message.role is Role.tool_result and "list_column_values" in message.content
    ]
    assert refusals


async def test_no_successful_query_means_not_answered() -> None:
    """The refusal path: say so rather than return an invented query."""
    result, _provider = await _run(
        _final("Frågan går inte att besvara utifrån schemat — utfallet är fritext.")
    )

    assert result.answered is False
    assert result.sql is None
    assert result.rows == []
    assert "fritext" in result.note


async def test_exhausted_iterations_returns_a_reason_rather_than_raising() -> None:
    settings = SqlAgentSettings(sql_agent_max_iterations=2)
    provider = ScriptedProvider(
        _tool_call("list_column_values", table="documents", column="category"),
        _tool_call("list_column_values", table="documents", column="category"),
    )

    result = await run_sql_agent(
        SqlAgentRequest(question="Hur många?"),
        NO_SESSION,
        llm_provider=provider,
        settings=settings,
    )

    assert result.answered is False
    assert "iterationstak" in result.note


class TestClosingNote:
    """`note` is rendered to the user and fed back to the conversational agent,
    so it must never carry content the model emitted alongside a tool call —
    a host that does not separate a reasoning model's channel puts the
    chain-of-thought there.
    """

    def test_prose_with_no_tool_calls_is_the_note(self) -> None:
        assert _closing_note(_final("Räknade besluten.")) == "Räknade besluten."

    def test_content_accompanying_a_tool_call_is_dropped(self) -> None:
        thinking = Message(
            role=Role.assistant,
            content="We need count decisions in 2024. Use query.",
            tool_calls=(
                ToolCall(id="call-1", name="run_sql", arguments={"sql": "..."}),
            ),
        )

        assert _closing_note(thinking) == ""


async def test_the_schema_and_examples_reach_the_model() -> None:
    """Both come from `semantic_model.yaml` and both land in the user message —
    which is also what puts the exact prompt into every trace record."""
    _result, provider = await _run(_final("Klart."))

    system_and_user = provider.seen_messages[0]
    assert system_and_user[0].role is Role.system

    user = system_and_user[1].content
    assert "FRITEXT" in user
    assert "documents —" in user
    assert "Exempel:" in user
    assert "Kommentar:" in user


class TestCorrelation:
    """Whether this agent joins its caller's interaction or starts its own.

    Both matter: reached from `POST /api/sql` there is no caller to join, and
    reached as the conversational agent's `query_corpus` tool an id of its own
    would put this loop's spend outside the turn that paid for it.
    """

    def setup_method(self):
        self.records: list[LLMCallRecord] = []

        class Recording:
            def record(inner, record: LLMCallRecord) -> None:
                self.records.append(record)

        set_trace_recorder(Recording())

    def teardown_method(self):
        set_trace_recorder(None)

    async def test_standalone_run_mints_its_own_interaction_id(self) -> None:
        await _run(_final("Klart."))

        assert self.records
        assert len({r.context["interaction_id"] for r in self.records}) == 1

    async def test_nested_run_inherits_the_callers_interaction_id(self) -> None:
        with interaction_scope("aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa"):
            await _run(_final("Klart."))

        assert self.records
        assert {r.context["interaction_id"] for r in self.records} == {
            "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa"
        }

    async def test_each_run_gets_its_own_agent_run_id(self) -> None:
        """Two `query_corpus` calls in one turn are otherwise indistinguishable."""
        with interaction_scope("aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa"):
            await _run(_final("Klart."))
            first = {r.context["agent_run_id"] for r in self.records}
            await _run(_final("Klart."))

        second = {r.context["agent_run_id"] for r in self.records} - first
        assert len(first) == 1
        assert len(second) == 1
        assert first != second
