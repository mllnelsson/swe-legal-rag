"""The conversational loop, driven by a scripted provider and a fake toolset.

No database, no model, no HTTP — `ChatToolset` is a Protocol precisely so the
agent can be exercised against a plain object.
"""

from __future__ import annotations

import inspect
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
from agents.chat._tools import build_chat_tools
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

    def __init__(self, *turns: Message, stream: tuple[str, ...] | None = None) -> None:
        self._turns = list(turns)
        self._stream = stream if stream is not None else ("Nämnden ", "avslog.")
        self.seen_messages: list[list[Message]] = []

    async def generate(self, messages, *, tools=None, response_schema=None):
        self.seen_messages.append(list(messages))
        if not self._turns:
            raise AssertionError("the loop asked for more turns than were scripted")
        return LLMResponse(message=self._turns.pop(0))

    async def generate_stream(self, messages):
        self.seen_messages.append(list(messages))
        streamed = self._stream

        async def chunks():
            for text in streamed:
                yield StreamChunk(text=text)

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
        _tool_call(
            ChatTool.ANSWER,
            call_id="call-2",
            chunk_ids=["c1"],
            notes="Underlaget bär svaret.",
        ),
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
        _tool_call(
            ChatTool.ANSWER,
            call_id="call-4",
            chunk_ids=["c1"],
            notes="Underlaget bär svaret.",
        ),
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
    # The call went out as a filtered search; the result says a search was
    # declined. `search.filtered` here would name a search that never ran.
    assert results[0].label is ProgressLabel.SEARCH_REFUSED
    calls = [e for e in events if isinstance(e, ToolCallEvent)]
    assert calls[0].label is ProgressLabel.SEARCH_FILTERED

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
        _tool_call(
            ChatTool.ANSWER,
            call_id="call-2",
            chunk_ids=["c1"],
            notes="Underlaget bär svaret.",
        ),
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
        _tool_call(
            ChatTool.ANSWER,
            call_id="call-3",
            chunk_ids=["c1"],
            notes="Underlaget bär svaret.",
        ),
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
        _tool_call(
            ChatTool.ANSWER,
            call_id="call-3",
            chunk_ids=["c1"],
            notes="Underlaget bär svaret.",
        ),
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
        _tool_call(
            ChatTool.ANSWER,
            call_id="call-3",
            chunk_ids=["c1"],
            notes="Underlaget bär svaret.",
        ),
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
        _tool_call(
            ChatTool.ANSWER,
            call_id="call-3",
            chunk_ids=["c1"],
            notes="Underlaget bär svaret.",
        ),
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
        _tool_call(
            ChatTool.ANSWER,
            call_id="call-2",
            chunk_ids=[],
            notes="Underlaget bär svaret.",
        ),
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


class TestConversationalTurn:
    """A message that is not a research question.

    A greeting, a thank-you, or "förklara det enklare" has nothing to retrieve.
    Before `reply_from_context` existed, such a turn reached the evidence gate
    empty-handed and was answered with "jag hittade inget i besluten" — which is
    a report on a search that was never worth running.
    """

    @staticmethod
    def _run(*, history: list[dict] | None = None, question: str = "Tack!"):
        provider = ScriptedProvider(
            _tool_call(
                ChatTool.REPLY_FROM_CONTEXT,
                notes="Användaren tackar för föregående svar.",
            ),
            stream=("Varsågod!",),
        )
        toolset = FakeToolset()
        return (
            provider,
            toolset,
            run_chat_agent(
                ChatAgentRequest(question=question, history=history or []),
                toolset,
                llm_provider=provider,
                settings=_settings(),
            ),
        )

    async def test_it_answers_without_touching_the_corpus(self) -> None:
        provider, toolset, agent = self._run()

        events = await _collect(agent)

        assert [event.type for event in events] == [
            "tool_call",
            "tool_result",
            "token",
            "sources",
            "done",
        ]
        assert "".join(e.text for e in events if isinstance(e, TokenEvent)) == (
            "Varsågod!"
        )
        # Not one search, not one vocabulary read, not one reading.
        assert toolset.searches == []
        assert toolset.vocabulary_calls == 0
        assert toolset.read_calls == []

    async def test_it_is_not_the_no_evidence_message(self) -> None:
        """The bug this path exists to fix, stated as an assertion."""
        _, _, agent = self._run()

        events = await _collect(agent)

        tokens = "".join(e.text for e in events if isinstance(e, TokenEvent))
        assert "hittade inget" not in tokens

    async def test_it_reports_a_label_of_its_own(self) -> None:
        """A client must be able to say "svarar direkt", not "söker"."""
        _, _, agent = self._run()

        events = await _collect(agent)

        call = next(e for e in events if isinstance(e, ToolCallEvent))
        result = next(e for e in events if isinstance(e, ToolResultEvent))
        assert call.label is ProgressLabel.ANSWER_DIRECT
        assert result.label is ProgressLabel.ANSWER_DIRECT
        assert result.status is ToolStatus.OK

    async def test_sources_are_empty_because_the_answer_cites_nothing(self) -> None:
        _, _, agent = self._run()

        events = await _collect(agent)

        assert next(e for e in events if isinstance(e, SourcesEvent)).sources == []

    async def test_the_previous_turn_reaches_the_writing_step(self) -> None:
        """ "Förklara det enklare" is answerable only from what was already said."""
        history = [
            {"role": "user", "content": "Vad gäller vid jäv?"},
            {"role": "assistant", "content": "Enligt beslut 12/2024 gäller..."},
        ]
        provider, _, agent = self._run(
            history=history, question="Förklara det enklare."
        )

        await _collect(agent)

        reply_prompt = provider.seen_messages[-1][-1].content
        assert "Enligt beslut 12/2024 gäller..." in reply_prompt
        assert "Förklara det enklare." in reply_prompt


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
        _tool_call(
            ChatTool.ANSWER,
            call_id="call-2",
            chunk_ids=["c2"],
            notes="Underlaget bär svaret.",
        ),
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
        _tool_call(
            ChatTool.ANSWER,
            call_id="call-2",
            chunk_ids=["c1", "c2"],
            notes="Underlaget bär svaret.",
        ),
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


class TestTheToolIndexInThePrompt:
    """The prompt's tool list is generated from the definitions.

    It used to be written out beside them and had drifted: it named a `filter`
    argument `search_decisions` does not have, called `read_decision` without
    the appendix switch, and did not mark `notes` required on `answer`.
    """

    def test_every_schema_property_is_a_real_executor_parameter(self) -> None:
        """Closes prompt <- schema <- executor.

        The prompt is generated from the schemas now, so this is what keeps the
        generated text executable: a property with no matching parameter would
        put an argument in the prompt that `tool_loop` cannot pass.
        """
        tools, executors, _ = build_chat_tools(FakeToolset(), _settings())

        for tool in tools:
            parameters = set(inspect.signature(executors[tool.name]).parameters)
            declared = set(tool.parameters.get("properties", {}))
            assert declared <= parameters, tool.name

    def test_every_required_property_is_declared(self) -> None:
        """A `required` naming a property that does not exist renders a `*` on
        an argument the index never lists."""
        tools, _, _ = build_chat_tools(FakeToolset(), _settings())

        for tool in tools:
            declared = set(tool.parameters.get("properties", {}))
            assert set(tool.parameters.get("required", [])) <= declared, tool.name

    async def test_the_rendered_prompt_lists_every_tool_and_its_arguments(
        self,
    ) -> None:
        provider = ScriptedProvider(
            _tool_call(ChatTool.REPLY_FROM_CONTEXT, notes="En hälsning."),
        )

        await _collect(
            run_chat_agent(
                ChatAgentRequest(question="Hej"),
                FakeToolset(),
                llm_provider=provider,
                settings=_settings(),
            )
        )

        prompt = provider.seen_messages[0][-1].content

        for tool in ChatTool:
            assert f"- {tool.value}(" in prompt
        # The three things the hand-written list got wrong.
        assert "document_filter" in prompt
        assert "read_decision(document_id*, question*, include_appendices)" in prompt
        assert "answer(chunk_ids*, document_ids, notes*)" in prompt


async def test_a_wrong_argument_name_is_refused_and_the_loop_goes_on() -> None:
    """The failure the generated tool index exists to prevent.

    A model calling `search_decisions(filter=...)` — which is what the old
    prompt asked for — used to end the turn: executors are called by keyword,
    so the `TypeError` became a `ToolExecutionError` and the agent yielded an
    `ErrorEvent`. Now it costs one iteration, like every other bad call.
    """
    provider = ScriptedProvider(
        _tool_call(ChatTool.SEARCH_DECISIONS, query="jäv", filter={"category": "x"}),
        _tool_call(ChatTool.SEARCH_DECISIONS, call_id="call-2", query="jäv i kyrkoråd"),
        _tool_call(
            ChatTool.ANSWER,
            call_id="call-3",
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

    assert not any(isinstance(event, ErrorEvent) for event in events)

    refusals = [
        event
        for event in events
        if isinstance(event, ToolResultEvent) and event.status is ToolStatus.REFUSED
    ]
    assert len(refusals) == 1

    # The malformed call never reached the toolset, and the turn still answered.
    assert len(toolset.searches) == 1
    assert isinstance(events[-1], DoneEvent)


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
            _tool_call(
                ChatTool.ANSWER,
                call_id="call-3",
                chunk_ids=["c1"],
                notes="Underlaget bär svaret.",
            ),
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

    async def test_a_direct_reply_is_traced_as_its_own_kind_of_call(self) -> None:
        """It is a billed call like any other, and a different one from synthesis."""
        provider = ScriptedProvider(
            _tool_call(ChatTool.REPLY_FROM_CONTEXT, notes="hälsning"),
            stream=("Hej!",),
        )
        await _collect(
            run_chat_agent(
                ChatAgentRequest(question="Hej!"),
                FakeToolset(),
                llm_provider=provider,
                settings=_settings(),
            )
        )

        assert {r.context["source"] for r in self.records} == {
            "agents.chat",
            "ai.reply_from_context",
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

    async def test_two_readings_in_one_turn_are_distinguishable(self) -> None:
        """A turn may read several decisions; each is its own sub-agent run.

        Sharing the orchestrator's `agent_run_id` would leave two readings
        identical in every correlation key they carry.
        """
        reader = ScriptedProvider(
            Message(role=Role.assistant, content="Första läsningen."),
            Message(role=Role.assistant, content="Andra läsningen."),
        )
        provider = ScriptedProvider(
            _tool_call(ChatTool.SEARCH_DECISIONS, query="jäv"),
            _tool_call(
                ChatTool.READ_DECISION,
                call_id="call-2",
                document_id="d1",
                question="Vad beslutade nämnden?",
            ),
            _tool_call(
                ChatTool.READ_DECISION,
                call_id="call-3",
                document_id="d1",
                question="Vilka skäl angavs?",
            ),
            _tool_call(
                ChatTool.ANSWER,
                call_id="call-4",
                chunk_ids=["c1"],
                notes="Underlaget bär svaret.",
            ),
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

        readings = [
            r for r in self.records if r.context["source"] == "agents.chat.read"
        ]
        assert len(readings) == 2
        assert len({r.context["agent_run_id"] for r in readings}) == 2

    async def test_a_reading_does_not_take_the_orchestrators_run_id(self) -> None:
        await self._run_a_turn()

        by_source = {
            source: {
                r.context["agent_run_id"]
                for r in self.records
                if r.context["source"] == source
            }
            for source in ("agents.chat", "agents.chat.read")
        }
        assert by_source["agents.chat"].isdisjoint(by_source["agents.chat.read"])


class TestTheHandoffToTheWritingStep:
    """What the orchestrator hands forward when it ends the turn."""

    async def test_an_answer_without_notes_is_refused_and_the_loop_goes_on(
        self,
    ) -> None:
        """A missing handoff is repaired, not fatal.

        The evidence is already gathered by this point, so ending the run here
        would answer a searchable question with the no-evidence message.
        """
        provider = ScriptedProvider(
            _tool_call(ChatTool.SEARCH_DECISIONS, query="jäv"),
            _tool_call(ChatTool.ANSWER, call_id="call-2", chunk_ids=["c1"]),
            _tool_call(
                ChatTool.ANSWER,
                call_id="call-3",
                chunk_ids=["c1"],
                notes="c1 bär avgörandet.",
            ),
        )

        events = await _collect(
            run_chat_agent(
                ChatAgentRequest(question="Vad har nämnden sagt om jäv?"),
                FakeToolset(),
                llm_provider=provider,
                settings=_settings(),
            )
        )

        refusals = [
            event
            for event in events
            if isinstance(event, ToolResultEvent)
            and event.status is ToolStatus.REFUSED
            and event.tool is ChatTool.ANSWER
        ]
        assert len(refusals) == 1

        assert [event.type for event in events][-3:] == ["token", "sources", "done"]
        tokens = "".join(e.text for e in events if isinstance(e, TokenEvent))
        assert tokens == "Nämnden avslog."
        # The refusal reached the model, so it could tell what to fix.
        assert any(
            "answer needs notes" in message.content
            for turn in provider.seen_messages
            for message in turn
        )

    async def test_what_the_agent_said_on_its_way_out_reaches_synthesis(self) -> None:
        """Text written alongside the terminal call is guidance, not litter."""
        answer = _tool_call(
            ChatTool.ANSWER,
            call_id="call-2",
            chunk_ids=["c1"],
            notes="c1 bär avgörandet.",
        )
        provider = ScriptedProvider(
            _tool_call(ChatTool.SEARCH_DECISIONS, query="jäv"),
            Message(
                role=answer.role,
                content="Observera att bilagan är underinstansens ord.",
                tool_calls=answer.tool_calls,
            ),
        )

        await _collect(
            run_chat_agent(
                ChatAgentRequest(question="Vad har nämnden sagt om jäv?"),
                FakeToolset(),
                llm_provider=provider,
                settings=_settings(),
            )
        )

        synthesis = provider.seen_messages[-1]
        rendered = "\n".join(message.content for message in synthesis)
        assert "Observera att bilagan är underinstansens ord." in rendered
        # The notes it did write are kept alongside, not replaced.
        assert "c1 bär avgörandet." in rendered

    async def test_a_direct_reply_keeps_it_too(self) -> None:
        reply = _tool_call(
            ChatTool.REPLY_FROM_CONTEXT, call_id="call-1", notes="Ett tack."
        )
        provider = ScriptedProvider(
            Message(
                role=reply.role,
                content="Användaren tackar bara.",
                tool_calls=reply.tool_calls,
            ),
            stream=("Varsågod!",),
        )

        await _collect(
            run_chat_agent(
                ChatAgentRequest(question="tack!"),
                FakeToolset(),
                llm_provider=provider,
                settings=_settings(),
            )
        )

        rendered = "\n".join(message.content for message in provider.seen_messages[-1])
        assert "Användaren tackar bara." in rendered
        assert "Ett tack." in rendered


async def test_closing_the_stream_early_stops_the_tool_loop() -> None:
    """A reader who reloads mid-answer takes the loop down with the stream.

    The tools hold the request-scoped database session, and the request
    teardown commits it as soon as this generator is done — so nothing may
    still be running by then.
    """
    provider = ScriptedProvider(
        _tool_call(ChatTool.SEARCH_DECISIONS, call_id="call-1", query="jäv"),
        _tool_call(ChatTool.SEARCH_DECISIONS, call_id="call-2", query="jäv igen"),
        _tool_call(
            ChatTool.ANSWER,
            call_id="call-3",
            chunk_ids=["c1"],
            notes="c1 bär avgörandet.",
        ),
    )
    toolset = FakeToolset()

    agent = run_chat_agent(
        ChatAgentRequest(question="Vad har nämnden sagt om jäv?"),
        toolset,
        llm_provider=provider,
        settings=_settings(),
    )
    assert isinstance(await anext(agent), ToolCallEvent)
    assert isinstance(await anext(agent), ToolResultEvent)
    await agent.aclose()

    assert len(toolset.searches) == 1
    assert len(provider.seen_messages) == 1
