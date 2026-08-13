"""The conversational loop, driven by a scripted provider and a fake toolset.

No database, no model, no HTTP — `ChatToolset` is a Protocol precisely so the
agent can be exercised against a plain object.
"""

from __future__ import annotations

import uuid

import pytest
from ai import interaction_scope
from llm_core import LLMResponse, Message, Role, StreamChunk, ToolCall
from llm_core._tracing import LLMCallRecord, set_trace_recorder
from shared.dtos.search import DocumentFilter
from shared.enums import ChunkSection

from agents.chat import (
    ChatAgentRequest,
    ChatTool,
    DoneEvent,
    ErrorEvent,
    ProgressLabel,
    SearchedChunk,
    SearchedDecision,
    SearchOutcome,
    SourcesEvent,
    SqlEvent,
    TokenEvent,
    ToolCallEvent,
    ToolResultEvent,
    ToolStatus,
    Vocabulary,
    VocabularyValue,
    run_chat_agent,
)
from agents.chat._dtos import DecisionText, DecisionTextChunk
from agents.config import ChatAgentSettings
from agents.sql._dtos import SqlAgentResult, SqlAttempt

_DOCUMENT_ID = uuid.UUID("11111111-1111-1111-1111-111111111111")
_BODY_CHUNK_ID = uuid.UUID("22222222-2222-2222-2222-222222222222")
_APPENDIX_CHUNK_ID = uuid.UUID("33333333-3333-3333-3333-333333333333")

_BODY_TEXT = "Nämnden avslår överklagandet med hänvisning till kyrkoordningen kap. 34."
_APPENDIX_TEXT = "Stiftet beslutade att avslå ansökan om tjänstetillsättning."
# Long enough that a test can prove it never reaches an orchestrator message.
_FULL_DECISION_TEXT = "Beslutets fullständiga lydelse. " * 400


class ScriptedProvider:
    """Replays a fixed sequence of assistant turns, one per loop iteration."""

    def __init__(self, *turns: Message) -> None:
        self._turns = list(turns)
        self.seen_messages: list[list[Message]] = []

    async def generate(self, messages, *, tools=None, response_schema=None):
        self.seen_messages.append(list(messages))
        if not self._turns:
            raise AssertionError("the loop asked for more turns than were scripted")
        return LLMResponse(message=self._turns.pop(0))

    async def generate_stream(self, messages):
        self.seen_messages.append(list(messages))

        async def chunks():
            yield StreamChunk(text="Nämnden ")
            yield StreamChunk(text="avslog.")

        return chunks()


class FakeToolset:
    """A ChatToolset that answers from fixtures and records what it was asked."""

    def __init__(
        self,
        *,
        outcome: SearchOutcome | None = None,
        tabular: SqlAgentResult | None = None,
    ) -> None:
        self.outcome = outcome if outcome is not None else _search_outcome()
        self.tabular = tabular
        self.searches: list[DocumentFilter] = []
        self.vocabulary_calls = 0
        self.read_calls: list[uuid.UUID] = []

    async def search(
        self,
        *,
        query,
        queries,
        document_filter,
        include_appendices,
        limit,
        chunks_per_decision,
    ) -> SearchOutcome:
        self.searches.append(document_filter)
        return self.outcome

    async def vocabulary(self, *, contains=None) -> Vocabulary:
        self.vocabulary_calls += 1
        return Vocabulary(
            categories=[VocabularyValue(value="Tjänstetillsättning", count=41)],
            decision_outcomes=[VocabularyValue(value="Avslag", count=88)],
            keywords=[VocabularyValue(value="jäv", count=12)],
            document_count=184,
        )

    async def decision_text(self, *, document_id, include_appendices) -> DecisionText:
        self.read_calls.append(document_id)
        return DecisionText(
            document_id=document_id,
            case_number="12/2024",
            chunks=[
                DecisionTextChunk(
                    chunk_index=0, text=_FULL_DECISION_TEXT, section=ChunkSection.BODY
                )
            ],
        )

    async def decision_profile(self, *, document_id):
        return None

    async def tabular_query(self, *, question) -> SqlAgentResult:
        if self.tabular is not None:
            return self.tabular
        return SqlAgentResult(answered=False, sql=None, note="ingen fråga kunde byggas")


def _search_outcome() -> SearchOutcome:
    return SearchOutcome(
        decisions=[
            SearchedDecision(
                document_id=_DOCUMENT_ID,
                case_number="12/2024",
                decision_outcome="Avslag",
                category="Tjänstetillsättning",
                chunks=[
                    SearchedChunk(
                        chunk_id=_BODY_CHUNK_ID,
                        text=_BODY_TEXT,
                        vector_similarity=0.86,
                    ),
                    SearchedChunk(
                        chunk_id=_APPENDIX_CHUNK_ID,
                        text=_APPENDIX_TEXT,
                        section=ChunkSection.APPENDIX,
                        appendix_label="Bilaga A",
                        vector_similarity=0.81,
                    ),
                ],
            )
        ],
        total=1,
        top_vector_similarity=0.86,
    )


def _tool_call(name: str, call_id: str = "call-1", **arguments) -> Message:
    return Message(
        role=Role.assistant,
        tool_calls=(ToolCall(id=call_id, name=name, arguments=arguments),),
    )


async def _collect(agent):
    return [event async for event in agent]


def _settings(**overrides) -> ChatAgentSettings:
    return ChatAgentSettings(**overrides)


async def test_search_then_answer_streams_prose_and_sources() -> None:
    provider = ScriptedProvider(
        _tool_call(ChatTool.SEARCH_DECISIONS, query="jäv i kyrkoråd"),
        _tool_call(
            ChatTool.ANSWER,
            call_id="call-2",
            chunk_ids=["c1"],
            notes="c1 bär avgörandet.",
        ),
    )
    toolset = FakeToolset()

    events = await _collect(
        run_chat_agent(
            ChatAgentRequest(question="Vad har nämnden sagt om jäv?"),
            toolset,
            llm_provider=provider,
            settings=_settings(),
        )
    )

    kinds = [event.type for event in events]
    assert kinds == [
        "tool_call",
        "tool_result",
        "tool_call",
        "tool_result",
        "token",
        "token",
        "sources",
        "done",
    ]

    tokens = "".join(e.text for e in events if isinstance(e, TokenEvent))
    assert tokens == "Nämnden avslog."

    sources = next(e for e in events if isinstance(e, SourcesEvent))
    assert [s.case_number for s in sources.sources] == ["12/2024"]
    assert sources.sources[0].document_id == _DOCUMENT_ID
    assert sources.sources[0].section is ChunkSection.BODY


async def test_progress_events_carry_keys_not_prose() -> None:
    """The contract the client's static labels are keyed to."""
    provider = ScriptedProvider(
        _tool_call(
            ChatTool.SEARCH_DECISIONS,
            query="jäv",
            document_filter={"keywords": ["jäv"]},
        ),
        _tool_call(ChatTool.ANSWER, call_id="call-2", chunk_ids=["c1"]),
    )

    events = await _collect(
        run_chat_agent(
            ChatAgentRequest(question="Vad gäller?"),
            FakeToolset(),
            llm_provider=provider,
            settings=_settings(),
        )
    )

    calls = [e for e in events if isinstance(e, ToolCallEvent)]
    results = [e for e in events if isinstance(e, ToolResultEvent)]

    assert [c.label for c in calls] == [
        ProgressLabel.SEARCH_FILTERED,
        ProgressLabel.ANSWER_COMPOSE,
    ]
    # Every result correlates back to its call.
    assert [c.id for c in calls] == [r.id for r in results]
    # `detail` is structured; nothing here is a sentence for a user to read.
    for event in calls + results:
        for value in event.detail.values():
            assert not isinstance(value, str) or " " not in value


async def test_filtering_on_free_text_is_refused_until_grounded() -> None:
    """The precondition, and the loop repairing itself through it."""
    provider = ScriptedProvider(
        _tool_call(
            ChatTool.SEARCH_DECISIONS,
            query="tjänstetillsättning",
            document_filter={"category": "tjänstetillsättning"},
        ),
        _tool_call(ChatTool.LIST_VOCABULARY, call_id="call-2"),
        _tool_call(
            ChatTool.SEARCH_DECISIONS,
            call_id="call-3",
            query="tjänstetillsättning",
            document_filter={"category": "Tjänstetillsättning"},
        ),
        _tool_call(ChatTool.ANSWER, call_id="call-4", chunk_ids=["c1"]),
    )
    toolset = FakeToolset()

    events = await _collect(
        run_chat_agent(
            ChatAgentRequest(question="Vad gäller vid tjänstetillsättning?"),
            toolset,
            llm_provider=provider,
            settings=_settings(),
        )
    )

    results = [e for e in events if isinstance(e, ToolResultEvent)]
    assert results[0].status is ToolStatus.REFUSED
    assert results[0].label is ProgressLabel.SEARCH_FILTERED

    # The refused search never reached the toolset; the grounded one did.
    assert len(toolset.searches) == 1
    assert toolset.searches[0].category == "Tjänstetillsättning"

    # And the refusal reached the model as a tool result it could act on.
    refusal = next(
        message
        for messages in provider.seen_messages
        for message in messages
        if message.role is Role.tool_result and "list_vocabulary" in message.content
    )
    assert "free-text" in refusal.content


async def test_keyword_filter_needs_no_grounding() -> None:
    """Keywords are the nämnd's own published vocabulary, not free text."""
    provider = ScriptedProvider(
        _tool_call(
            ChatTool.SEARCH_DECISIONS,
            query="jäv",
            document_filter={"keywords": ["jäv"]},
        ),
        _tool_call(ChatTool.ANSWER, call_id="call-2", chunk_ids=["c1"]),
    )
    toolset = FakeToolset()

    events = await _collect(
        run_chat_agent(
            ChatAgentRequest(question="Vad gäller?"),
            toolset,
            llm_provider=provider,
            settings=_settings(),
        )
    )

    assert [e for e in events if isinstance(e, ToolResultEvent)][0].status is (
        ToolStatus.OK
    )
    assert toolset.vocabulary_calls == 0
    assert len(toolset.searches) == 1


async def test_counting_emits_the_query_before_the_answer() -> None:
    """The SQL agent's consumer obligation, on the wire."""
    tabular = SqlAgentResult(
        answered=True,
        sql="SELECT count(*) FROM documents WHERE decision_outcome ILIKE '%avslag%'",
        columns=["antal"],
        rows=[[12]],
        row_count=1,
        assumptions=["Årtal tolkat som decision_date."],
        attempts=[
            SqlAttempt(sql="SELECT count(*) FROM documents", ok=True, row_count=1)
        ],
    )
    provider = ScriptedProvider(
        _tool_call(ChatTool.SEARCH_DECISIONS, query="avslag"),
        _tool_call(
            ChatTool.QUERY_CORPUS,
            call_id="call-2",
            question="hur många avslogs 2024?",
        ),
        _tool_call(ChatTool.ANSWER, call_id="call-3", chunk_ids=["c1"]),
    )

    events = await _collect(
        run_chat_agent(
            ChatAgentRequest(question="Hur många överklaganden avslogs 2024?"),
            FakeToolset(tabular=tabular),
            llm_provider=provider,
            settings=_settings(),
        )
    )

    kinds = [event.type for event in events]
    sql_index = kinds.index("sql")
    assert sql_index < kinds.index("token")

    sql_event = next(e for e in events if isinstance(e, SqlEvent))
    assert sql_event.answered
    assert sql_event.sql is not None and sql_event.sql.startswith("SELECT count(*)")
    assert sql_event.assumptions == ["Årtal tolkat som decision_date."]
    assert len(sql_event.attempts) == 1

    # And the rows reach the writing step, with the query attached.
    synthesis = provider.seen_messages[-1][-1].content
    assert "SELECT count(*)" in synthesis


async def test_full_decision_text_never_enters_an_orchestrator_message() -> None:
    """The reason read_decision is a sub-agent rather than a tool result."""
    reader = ScriptedProvider(
        Message(role=Role.assistant, content="Nämnden avslog överklagandet.")
    )
    provider = ScriptedProvider(
        _tool_call(ChatTool.SEARCH_DECISIONS, query="jäv"),
        _tool_call(
            ChatTool.READ_DECISION,
            call_id="call-2",
            document_id="d1",
            question="Vad beslutade nämnden?",
        ),
        _tool_call(ChatTool.ANSWER, call_id="call-3", chunk_ids=["c1"]),
    )
    toolset = FakeToolset()

    await _collect(
        run_chat_agent(
            ChatAgentRequest(question="Vad beslutade nämnden?"),
            toolset,
            llm_provider=provider,
            reader_provider=reader,
            settings=_settings(),
        )
    )

    assert toolset.read_calls == [_DOCUMENT_ID]

    orchestrator_text = "".join(
        message.content for messages in provider.seen_messages for message in messages
    )
    assert _FULL_DECISION_TEXT not in orchestrator_text
    assert "Nämnden avslog överklagandet." in orchestrator_text

    # The reader, by contrast, was given the whole thing.
    reader_text = "".join(
        message.content for messages in reader.seen_messages for message in messages
    )
    assert _FULL_DECISION_TEXT.strip() in reader_text


async def test_reading_budget_refuses_rather_than_raising() -> None:
    provider = ScriptedProvider(
        _tool_call(ChatTool.SEARCH_DECISIONS, query="jäv"),
        _tool_call(
            ChatTool.READ_DECISION,
            call_id="call-2",
            document_id="d1",
            question="Vad beslutade nämnden?",
        ),
        _tool_call(ChatTool.ANSWER, call_id="call-3", chunk_ids=["c1"]),
    )
    reader = ScriptedProvider(Message(role=Role.assistant, content="extract"))

    events = await _collect(
        run_chat_agent(
            ChatAgentRequest(question="Vad beslutade nämnden?"),
            FakeToolset(),
            llm_provider=provider,
            reader_provider=reader,
            settings=_settings(chat_agent_max_documents_read=0),
        )
    )

    read_result = [
        e
        for e in events
        if isinstance(e, ToolResultEvent) and e.tool is ChatTool.READ_DECISION
    ][0]
    assert read_result.status is ToolStatus.REFUSED


async def test_unknown_handle_is_refused_with_the_valid_ones() -> None:
    provider = ScriptedProvider(
        _tool_call(ChatTool.SEARCH_DECISIONS, query="jäv"),
        _tool_call(ChatTool.INSPECT_DECISION, call_id="call-2", document_id="d99"),
        _tool_call(ChatTool.ANSWER, call_id="call-3", chunk_ids=["c1"]),
    )

    events = await _collect(
        run_chat_agent(
            ChatAgentRequest(question="Vad gäller?"),
            FakeToolset(),
            llm_provider=provider,
            settings=_settings(),
        )
    )

    inspect_result = [
        e
        for e in events
        if isinstance(e, ToolResultEvent) and e.tool is ChatTool.INSPECT_DECISION
    ][0]
    assert inspect_result.status is ToolStatus.REFUSED

    refusal = next(
        message
        for messages in provider.seen_messages
        for message in messages
        if message.role is Role.tool_result and "d99" in message.content
    )
    assert "Available: d1" in refusal.content


async def test_no_evidence_says_so_rather_than_improvising() -> None:
    provider = ScriptedProvider(
        _tool_call(ChatTool.SEARCH_DECISIONS, query="tomater"),
        _tool_call(ChatTool.ANSWER, call_id="call-2", chunk_ids=[]),
    )

    events = await _collect(
        run_chat_agent(
            ChatAgentRequest(question="Hur odlar man tomater?"),
            FakeToolset(outcome=SearchOutcome()),
            llm_provider=provider,
            settings=_settings(),
        )
    )

    assert isinstance(events[-1], DoneEvent)
    tokens = "".join(e.text for e in events if isinstance(e, TokenEvent))
    assert "hittade inget" in tokens
    assert next(e for e in events if isinstance(e, SourcesEvent)).sources == []
    # No synthesis call was made — there was nothing to synthesize from.
    assert len(provider.seen_messages) == 2


async def test_exhausted_loop_ends_with_a_terminal_error() -> None:
    provider = ScriptedProvider(
        *[_tool_call(ChatTool.SEARCH_DECISIONS, query="jäv") for _ in range(3)]
    )

    events = await _collect(
        run_chat_agent(
            ChatAgentRequest(question="Vad gäller?"),
            FakeToolset(),
            llm_provider=provider,
            settings=_settings(chat_agent_max_iterations=2),
        )
    )

    assert isinstance(events[-1], ErrorEvent)
    assert not any(isinstance(event, DoneEvent) for event in events)


async def test_appendix_selection_keeps_its_label() -> None:
    """A cited appendix passage must stay attributable to the lower instance."""
    provider = ScriptedProvider(
        _tool_call(ChatTool.SEARCH_DECISIONS, query="stiftets beslut"),
        _tool_call(ChatTool.ANSWER, call_id="call-2", chunk_ids=["c2"]),
    )

    events = await _collect(
        run_chat_agent(
            ChatAgentRequest(question="Vad beslutade stiftet?"),
            FakeToolset(),
            llm_provider=provider,
            settings=_settings(),
        )
    )

    source = next(e for e in events if isinstance(e, SourcesEvent)).sources[0]
    assert source.section is ChunkSection.APPENDIX
    assert source.appendix_label == "Bilaga A"


async def test_citations_are_capped() -> None:
    provider = ScriptedProvider(
        _tool_call(ChatTool.SEARCH_DECISIONS, query="jäv"),
        _tool_call(ChatTool.ANSWER, call_id="call-2", chunk_ids=["c1", "c2"]),
    )

    await _collect(
        run_chat_agent(
            ChatAgentRequest(question="Vad gäller?"),
            FakeToolset(),
            llm_provider=provider,
            settings=_settings(chat_agent_max_chunks_cited=1),
        )
    )

    synthesis = provider.seen_messages[-1][-1].content
    assert _BODY_TEXT in synthesis
    assert _APPENDIX_TEXT not in synthesis


@pytest.mark.parametrize("question", ["", "x" * 4001])
def test_question_bounds_are_enforced(question: str) -> None:
    with pytest.raises(ValueError):
        ChatAgentRequest(question=question)


class TestCorrelation:
    """One turn, one interaction id — the basis for costing a question.

    A turn fans out into the orchestrator's iterations, the reading sub-agent
    and the streamed synthesis, each its own billed call. Summing what the turn
    cost is a sum over one key only if all of them carry the same one.
    """

    def setup_method(self):
        self.records: list[LLMCallRecord] = []

        class Recording:
            def record(inner, record: LLMCallRecord) -> None:
                self.records.append(record)

        set_trace_recorder(Recording())

    def teardown_method(self):
        set_trace_recorder(None)

    async def _run_a_turn(self):
        reader = ScriptedProvider(
            Message(role=Role.assistant, content="Nämnden avslog överklagandet.")
        )
        provider = ScriptedProvider(
            _tool_call(ChatTool.SEARCH_DECISIONS, query="jäv"),
            _tool_call(
                ChatTool.READ_DECISION,
                call_id="call-2",
                document_id="d1",
                question="Vad beslutade nämnden?",
            ),
            _tool_call(ChatTool.ANSWER, call_id="call-3", chunk_ids=["c1"]),
        )
        await _collect(
            run_chat_agent(
                ChatAgentRequest(question="Vad beslutade nämnden?"),
                FakeToolset(),
                llm_provider=provider,
                reader_provider=reader,
                settings=_settings(),
            )
        )

    async def test_every_call_in_a_turn_shares_the_callers_interaction_id(self) -> None:
        with interaction_scope("aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa"):
            await self._run_a_turn()

        assert self.records
        assert {r.context["interaction_id"] for r in self.records} == {
            "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa"
        }

    async def test_the_orchestrator_reader_and_synthesis_are_all_traced(self) -> None:
        """Each is a separate billed call and must be separable within the turn."""
        await self._run_a_turn()

        assert {r.context["source"] for r in self.records} == {
            "agents.chat",
            "agents.chat.read",
            "ai.synthesize_answer",
        }

    async def test_a_run_without_a_caller_mints_its_own_interaction_id(self) -> None:
        """`scripts/run_agent.py` has no enclosing interaction to join."""
        await self._run_a_turn()

        assert self.records
        assert len({r.context["interaction_id"] for r in self.records}) == 1

    async def test_orchestration_records_name_their_prompt(self) -> None:
        """Without it these records cannot be attributed to a prompt version."""
        await self._run_a_turn()

        orchestration = [
            r for r in self.records if r.context["source"] == "agents.chat"
        ]
        assert orchestration
        assert {r.context["prompt"] for r in orchestration} == {"CHAT_ORCHESTRATION"}
