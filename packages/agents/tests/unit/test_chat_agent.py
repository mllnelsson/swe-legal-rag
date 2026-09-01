"""The conversational loop, driven by a scripted provider and a fake toolset.

No database, no model, no HTTP — `ChatToolset` is a Protocol precisely so the
agent can be exercised against a plain object.
"""

from __future__ import annotations

import inspect
import json
import uuid

import pytest
from agent_kit import InMemoryContextStore
from ai import interaction_scope
from ai.dtos import DecisionReading
from agent_kit.llm import (
    LLMCallRecord,
    LLMResponse,
    Message,
    Role,
    StreamChunk,
    ToolCall,
    set_trace_recorder,
)
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
from agents.chat._dtos import DecisionText, DecisionTextChunk, PassageNote
from agents.chat._tools import (
    AnswerSelection,
    ChatScratchpad,
    build_chat_tools,
    chat_scratchpad_codec,
)
from agents.config import ChatAgentSettings
from agents.sql._dtos import SqlAgentResult, SqlAttempt

_DOCUMENT_ID = uuid.UUID("11111111-1111-1111-1111-111111111111")
_BODY_CHUNK_ID = uuid.UUID("22222222-2222-2222-2222-222222222222")
_APPENDIX_CHUNK_ID = uuid.UUID("33333333-3333-3333-3333-333333333333")

_BODY_TEXT = "Nämnden avslår överklagandet med hänvisning till kyrkoordningen kap. 34."
_APPENDIX_TEXT = "Stiftet beslutade att avslå ansökan om tjänstetillsättning."
# Long enough that a test can prove it never reaches an orchestrator message.
_READ_CHUNK_IDS = [
    uuid.UUID(f"00000000-0000-0000-0000-0000000000{n:02d}") for n in (11, 12, 13)
]
# The bulk of the decision. Long on purpose: it is what must never reach the
# orchestrator, and a short string would pass that assertion by accident.
_FULL_DECISION_TEXT = "Beslutets fullständiga lydelse. " * 400
# The passage a reading points at. It *does* reach the orchestrator, because a
# handle it has never read is a handle it cannot annotate.
_READ_PASSAGE = "Nämnden fann att jäv förelåg och undanröjde beslutet."
_UNREAD_PASSAGE = "Beslutet expedierades till parterna."


def _reading(
    *, relevance: str = "carries", indices: list[int] | None = None, summary: str = ""
) -> Message:
    """A reader turn. `generate_structured` parses the content as JSON."""
    return Message(
        role=Role.assistant,
        content=json.dumps(
            {
                "relevance": relevance,
                "chunk_indices": [1] if indices is None else indices,
                "summary": summary,
            }
        ),
    )


def _route(plan: str = "(test plan)") -> Message:
    """The plan step's `begin_research` call — what routes a turn into research."""
    return Message(
        role=Role.assistant,
        tool_calls=(
            ToolCall(id="call-plan", name="begin_research", arguments={"plan": plan}),
        ),
    )


def _is_plan_call(tools) -> bool:
    """Whether this generate is the plan step: it is the only call holding the
    `begin_research` tool. The executor loop and the reader never do, so keying on
    it lets one scripted provider auto-route the plan without touching them."""
    return bool(tools) and any(
        getattr(tool, "name", None) == "begin_research" for tool in tools
    )


class ScriptedProvider:
    """Replays a fixed sequence of assistant turns, one per loop iteration.

    A turn now opens with the plan step, so by default the plan call auto-routes:
    it returns a `begin_research` call without consuming a scripted turn, and the
    scripted turns drive the executor loop that follows. A test of the direct
    reply — the plan step answering in prose — passes ``routes=False``, and then
    the first scripted turn is that reply. Reader providers are unaffected either
    way: they never hold the `begin_research` tool.
    """

    def __init__(
        self,
        *turns: Message,
        stream: tuple[str, ...] | None = None,
        routes: bool = True,
    ) -> None:
        self._turns = list(turns)
        self._stream = stream if stream is not None else ("Nämnden ", "avslog.")
        self._routes = routes
        self.seen_messages: list[list[Message]] = []

    async def generate(self, messages, *, tools=None, response_schema=None):
        self.seen_messages.append(list(messages))
        if self._routes and _is_plan_call(tools):
            return LLMResponse(message=_route())
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
                    chunk_id=chunk_id,
                    chunk_index=index,
                    text=text,
                    section=ChunkSection.BODY,
                )
                for index, (chunk_id, text) in enumerate(
                    (
                        (_READ_CHUNK_IDS[0], _FULL_DECISION_TEXT),
                        (_READ_CHUNK_IDS[1], _READ_PASSAGE),
                        (_READ_CHUNK_IDS[2], _UNREAD_PASSAGE),
                        # Index 3 is the passage search already returned, so a
                        # reading that picks it must reuse its handle.
                        (_BODY_CHUNK_ID, _BODY_TEXT),
                    )
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
            annotations=[{"handle": "c1", "carries": "bär avgörandet"}],
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
        "sources",
        "token",
        "token",
        "done",
    ]

    tokens = "".join(e.text for e in events if isinstance(e, TokenEvent))
    assert tokens == "Nämnden avslog."

    sources = next(e for e in events if isinstance(e, SourcesEvent))
    assert [s.case_number for s in sources.sources] == ["12/2024"]
    assert sources.sources[0].document_id == _DOCUMENT_ID
    assert sources.sources[0].section is ChunkSection.BODY


async def test_the_executor_sees_gathered_evidence_on_its_board() -> None:
    """After a search, the pad's board — with the decision's shorthand — is pinned
    into the executor's context on the next iteration, refreshed each pass."""
    provider = ScriptedProvider(
        _tool_call(ChatTool.SEARCH_DECISIONS, query="jäv i kyrkoråd"),
        _tool_call(
            ChatTool.ANSWER,
            call_id="call-2",
            annotations=[{"handle": "c1", "carries": "bär avgörandet"}],
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

    # Across the run's model calls, the executor's post-search iteration carries
    # the board built from what the search gathered.
    boards = [
        message
        for call in provider.seen_messages
        for message in call
        if "[scratchpad]" in message.content
    ]
    assert boards, "no scratchpad board was ever pinned into a model call"
    assert all(board.role is Role.system for board in boards)
    # The decision's shorthand (its handle and case number) is on the board.
    assert any("d1" in board.content and "12/2024" in board.content for board in boards)


async def test_search_keeps_full_chunk_text_in_the_pad_not_the_loop() -> None:
    """The loop model sees only the snippet; the writer still gets the true text."""
    long_text = "Detta är passagens fullständiga och ordagranna lydelse. " * 40
    outcome = SearchOutcome(
        decisions=[
            SearchedDecision(
                document_id=_DOCUMENT_ID,
                case_number="12/2024",
                decision_outcome="Avslag",
                category="Tjänstetillsättning",
                chunks=[
                    SearchedChunk(
                        chunk_id=_BODY_CHUNK_ID, text=long_text, vector_similarity=0.9
                    )
                ],
            )
        ]
    )
    provider = ScriptedProvider(
        _tool_call(ChatTool.SEARCH_DECISIONS, query="jäv"),
        _tool_call(
            ChatTool.ANSWER,
            call_id="call-2",
            annotations=[{"handle": "c1", "carries": "bär avgörandet"}],
        ),
    )

    await _collect(
        run_chat_agent(
            ChatAgentRequest(question="Vad beslutade nämnden?"),
            FakeToolset(outcome=outcome),
            llm_provider=provider,
            settings=_settings(chat_agent_preview_snippet_chars=40),
        )
    )

    # The last model call is the streaming synthesis prompt; everything before it
    # is the plan and the executor loop.
    loop_text = "".join(
        m.content for call in provider.seen_messages[:-1] for m in call
    )
    synthesis_prompt = "".join(m.content for m in provider.seen_messages[-1])

    assert long_text not in loop_text  # the weight never reached the loop
    assert long_text[:40] in loop_text  # only its snippet did
    assert long_text in synthesis_prompt  # the writer gets the true text, verbatim


async def test_query_keeps_full_rows_in_the_pad_not_the_loop() -> None:
    """The loop model sees a sample; the writer and the SqlEvent get every row."""
    rows = [[f"parish-{n}", n] for n in range(50)]
    tabular = SqlAgentResult(
        answered=True,
        sql="SELECT parish, count(*) FROM decisions GROUP BY parish",
        columns=["parish", "n"],
        rows=rows,
        row_count=len(rows),
    )
    provider = ScriptedProvider(
        _tool_call(ChatTool.QUERY_CORPUS, question="hur många per församling?"),
        _tool_call(ChatTool.ANSWER, call_id="call-2", annotations=[], gaps=["—"]),
    )

    events = await _collect(
        run_chat_agent(
            ChatAgentRequest(question="Hur många beslut per församling?"),
            FakeToolset(tabular=tabular),
            llm_provider=provider,
            settings=_settings(chat_agent_preview_rows=3),
        )
    )

    loop_text = "".join(
        m.content for call in provider.seen_messages[:-1] for m in call
    )
    synthesis_prompt = "".join(m.content for m in provider.seen_messages[-1])

    # A late row is absent from the loop but present for the writer.
    assert "parish-49" not in loop_text
    assert "parish-49" in synthesis_prompt
    # The early sample rows did reach the loop.
    assert "parish-0" in loop_text
    # The wire SqlEvent carries every row, read from the pad, not the sample.
    sql_event = next(e for e in events if isinstance(e, SqlEvent))
    assert sql_event.row_count == 50
    assert len(sql_event.rows) == 50


def test_the_scratchpad_codec_round_trips_every_entry_kind() -> None:
    """Persist and restore a pad holding one of each kind, through the chat codec."""
    decision = SearchedDecision(
        document_id=_DOCUMENT_ID,
        case_number="12/2024",
        decision_outcome="Avslag",
        category="Tjänstetillsättning",
        chunks=[
            SearchedChunk(
                chunk_id=_BODY_CHUNK_ID, text=_BODY_TEXT, vector_similarity=0.86
            )
        ],
    )
    pad = ChatScratchpad()
    pad.remember_decision(decision)
    pad.remember_chunk(_DOCUMENT_ID, decision.chunks[0], snippet_chars=160)
    pad.add_reading(
        DecisionReading(case_number="12/2024", handles=["c1"], summary="jäv")
    )
    pad.set_tabular(
        SqlAgentResult(
            answered=True, sql="SELECT count(*)", columns=["n"], rows=[[3]], row_count=1
        ),
        sample_rows=5,
    )
    pad.set_selection(
        AnswerSelection(
            annotations=[PassageNote(handle="c1", carries="bär")],
            gaps=["saknar årtal"],
        )
    )
    pad.record_cases(["12/2024"])

    codec = chat_scratchpad_codec(cap=40)
    restored = ChatScratchpad()
    restored.restore(pad.dump(codec.encode, cap=codec.cap), codec.decode)

    assert restored.keys() == ["d1", "c1", "r1", "sql", "selection", "cases_discussed"]
    assert restored.decision("d1") == decision
    body = restored.chunk("c1")
    assert body is not None and body.chunk.text == _BODY_TEXT
    assert restored.readings()[0].summary == "jäv"
    tabular = restored.tabular()
    assert tabular is not None and tabular.sql == "SELECT count(*)"
    selection = restored.selection()
    assert selection is not None and selection.gaps == ["saknar årtal"]
    assert restored.recall("cases_discussed") == ["12/2024"]


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
            annotations=[{"handle": "c1", "carries": "bär svaret"}],
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
            annotations=[{"handle": "c1", "carries": "bär svaret"}],
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
    # The label is the one the call went out under; `status` is what says the
    # filter was declined. One fact, one place to read it.
    assert results[0].label is ProgressLabel.SEARCH_FILTERED
    assert results[0].status is ToolStatus.REFUSED
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
            annotations=[{"handle": "c1", "carries": "bär svaret"}],
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
            annotations=[{"handle": "c1", "carries": "bär svaret"}],
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


async def test_a_reading_returns_its_passages_and_not_the_decision() -> None:
    """The reason read_decision is a sub-agent rather than a tool result.

    The line is the *whole document*, not the passages. Six selected passages
    are the same order of size as one search result and the orchestrator has to
    see them — a handle it has never read is a handle it cannot annotate. The
    other 20k characters are what the sub-agent exists to keep out.
    """
    reader = ScriptedProvider(_reading(indices=[1], summary="c-handtaget bär jävet"))
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
            annotations=[{"handle": "c1", "carries": "bär svaret"}],
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
    assert _UNREAD_PASSAGE not in orchestrator_text
    # The selected passage, verbatim, and the note pointing at it.
    assert _READ_PASSAGE in orchestrator_text
    assert "c-handtaget bär jävet" in orchestrator_text

    # The reader, by contrast, was given the whole thing — numbered, so it can
    # answer with a position rather than with prose.
    reader_text = "".join(
        message.content for messages in reader.seen_messages for message in messages
    )
    assert _FULL_DECISION_TEXT.strip() in reader_text
    assert f"[1] {_READ_PASSAGE}" in reader_text


def _read_then_answer(*, cite: str = "c3") -> ScriptedProvider:
    """Search, read one decision, then answer citing a handle the reading minted."""
    return ScriptedProvider(
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
            annotations=[{"handle": cite, "carries": "bär svaret"}],
        ),
    )


async def _run(provider, reader, **settings) -> list:
    return await _collect(
        run_chat_agent(
            ChatAgentRequest(question="Vad beslutade nämnden?"),
            FakeToolset(),
            llm_provider=provider,
            reader_provider=reader,
            settings=_settings(**settings),
        )
    )


def _sources(events: list) -> list:
    return next(e.sources for e in events if isinstance(e, SourcesEvent))


async def test_a_passage_a_reading_found_can_be_cited_like_any_other() -> None:
    """The invariant: every claim traces to a verbatim passage in `sources`.

    Search returned c1 and c2; the reading picks index 1, which is a passage
    search never surfaced, and it becomes c3. Citing c3 has to reach the reader
    of the answer, or the citation marker resolves to nothing.
    """
    events = await _run(_read_then_answer(cite="c3"), ScriptedProvider(_reading()))

    sources = _sources(events)
    assert [s.handle for s in sources] == ["c3"]
    assert sources[0].excerpt == _READ_PASSAGE


async def test_a_passage_search_already_returned_keeps_its_handle() -> None:
    """Index 3 of the decision is the chunk search returned as c1.

    Minting a second handle for it would put the same text in `sources` twice
    under two numbers, and the reader would count two sources where there is
    one passage.
    """
    provider = _read_then_answer(cite="c1")
    events = await _run(provider, ScriptedProvider(_reading(indices=[3])))

    # Asserted on what the reading handed back, not on what the answer cited:
    # citing c1 would still work if the reading had minted a c3 for the same
    # text, and the duplicate is exactly what this pins.
    read_result = next(
        message
        for messages in provider.seen_messages
        for message in messages
        if message.tool_name == ChatTool.READ_DECISION
    )
    assert json.loads(read_result.content)["passages"] == [
        {"chunk_id": "c1", "text": _BODY_TEXT, "origin": "the board's own text"}
    ]

    sources = _sources(events)
    assert [s.handle for s in sources] == ["c1"]
    assert sources[0].excerpt == _BODY_TEXT


async def test_a_reading_that_finds_nothing_contributes_nothing() -> None:
    """A decision that does not address the question used to arrive at the
    writing step as a paragraph saying so, which the writer had to read and
    discard."""
    provider = _read_then_answer(cite="c1")
    events = await _run(provider, ScriptedProvider(_reading(relevance="nothing")))

    result = next(
        e
        for e in events
        if isinstance(e, ToolResultEvent) and e.tool is ChatTool.READ_DECISION
    )
    assert result.status is ToolStatus.OK

    synthesis = provider.seen_messages[-1][-1].content
    assert "Genomläsningar:\n(inget)" in synthesis
    assert [s.handle for s in _sources(events)] == ["c1"]


async def test_an_index_outside_the_decision_is_dropped_not_fatal() -> None:
    """One bad index is a lost passage, not a lost turn — the same trade
    `_answer` makes for an unreadable annotation."""
    events = await _run(
        _read_then_answer(cite="c3"), ScriptedProvider(_reading(indices=[99, 1, -1]))
    )

    assert [s.handle for s in _sources(events)] == ["c3"]


async def test_a_reading_cannot_hand_the_whole_decision_back() -> None:
    """Without the cap the sub-agent's whole reason for existing is undone: the
    reader could select every passage and put the document in the loop."""
    provider = _read_then_answer(cite="c3")
    await _run(
        provider,
        ScriptedProvider(_reading(indices=[0, 1, 2, 3])),
        chat_agent_max_chunks_per_reading=2,
    )

    read_result = next(
        message
        for messages in provider.seen_messages
        for message in messages
        if message.tool_name == ChatTool.READ_DECISION
    )
    assert read_result.content.count('"chunk_id"') == 2


async def test_an_unreadable_reading_is_refused_rather_than_fatal() -> None:
    """`generate_structured` raises on output the schema cannot read. Unhandled
    that ends the whole request; here it is a tool result the orchestrator can
    repair from."""
    provider = _read_then_answer(cite="c1")
    reader = ScriptedProvider(Message(role=Role.assistant, content="not json at all"))

    events = await _run(provider, reader)

    result = next(
        e
        for e in events
        if isinstance(e, ToolResultEvent) and e.tool is ChatTool.READ_DECISION
    )
    assert result.status is ToolStatus.REFUSED
    # The turn still finished on the evidence search had already found.
    assert [s.handle for s in _sources(events)] == ["c1"]
    assert any(isinstance(e, DoneEvent) for e in events)


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
            annotations=[{"handle": "c1", "carries": "bär svaret"}],
        ),
    )
    reader = ScriptedProvider(_reading())

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
            annotations=[{"handle": "c1", "carries": "bär svaret"}],
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
        _tool_call(ChatTool.ANSWER, call_id="call-2", annotations=[]),
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
    # No synthesis call was made — there was nothing to synthesize from. Three
    # calls, not four: the plan step, then the search and the answer.
    assert len(provider.seen_messages) == 3


class TestConversationalTurn:
    """A message that is not a research question.

    A greeting, a thank-you, or "förklara det enklare" has nothing to retrieve.
    The plan step ends such a turn by calling no tool and writing the reply
    itself — `routes=False` scripts exactly that — and that message is what
    reaches the user, without the executor loop ever running.
    """

    @staticmethod
    def _run(*, history: list[dict] | None = None, question: str = "Tack!"):
        provider = ScriptedProvider(
            Message(role=Role.assistant, content="Varsågod!"),
            routes=False,
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

        assert [event.type for event in events] == ["sources", "token", "done"]
        assert "".join(e.text for e in events if isinstance(e, TokenEvent)) == (
            "Varsågod!"
        )
        # Not one search, not one vocabulary read, not one reading.
        assert toolset.searches == []
        assert toolset.vocabulary_calls == 0
        assert toolset.read_calls == []

    async def test_it_costs_exactly_one_model_call(self) -> None:
        """The reply is the loop's own message, not a second call to write it."""
        provider, _, agent = self._run()

        await _collect(agent)

        assert len(provider.seen_messages) == 1

    async def test_it_reports_no_step_at_all(self) -> None:
        """The absence is the point.

        The agent called no tool, so there is no work to report. A step here
        would tell the reader about a search nobody ran.
        """
        _, _, agent = self._run()

        events = await _collect(agent)

        assert not any(isinstance(e, (ToolCallEvent, ToolResultEvent)) for e in events)

    async def test_it_is_not_the_no_evidence_message(self) -> None:
        """The bug this path exists to fix, stated as an assertion.

        A loop that ends in prose used to have that prose discarded and the
        evidence gate answer in its place — a report on a search nobody wanted.
        """
        _, _, agent = self._run()

        events = await _collect(agent)

        tokens = "".join(e.text for e in events if isinstance(e, TokenEvent))
        assert "hittade inget" not in tokens

    async def test_sources_are_empty_because_the_answer_cites_nothing(self) -> None:
        _, _, agent = self._run()

        events = await _collect(agent)

        assert next(e for e in events if isinstance(e, SourcesEvent)).sources == []

    async def test_the_previous_turn_reaches_the_orchestrator(self) -> None:
        """ "Förklara det enklare" is answerable only from what was already said."""
        history = [
            {"role": "user", "content": "Vad gäller vid jäv?"},
            {"role": "assistant", "content": "Enligt beslut 12/2024 gäller..."},
        ]
        provider, _, agent = self._run(
            history=history, question="Förklara det enklare."
        )

        await _collect(agent)

        prompt = provider.seen_messages[-1][-1].content
        assert "Enligt beslut 12/2024 gäller..." in prompt
        assert "Förklara det enklare." in prompt


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


async def test_every_cited_passage_is_resolvable_by_its_handle() -> None:
    """The invariant inline citations rest on.

    Sources used to be deduplicated by decision, so two passages of one
    decision produced one reference — and a claim marked with the dropped
    handle pointed at nothing. One reference per passage, handle included.
    """
    provider = ScriptedProvider(
        _tool_call(ChatTool.SEARCH_DECISIONS, query="jäv"),
        _tool_call(
            ChatTool.ANSWER,
            call_id="call-2",
            annotations=[
                {"handle": "c1", "carries": "bär svaret"},
                {"handle": "c2", "carries": "bär undantaget"},
            ],
        ),
    )

    events = await _collect(
        run_chat_agent(
            ChatAgentRequest(question="Vad är jäv?"),
            FakeToolset(),
            llm_provider=provider,
            settings=_settings(),
        )
    )

    sources = next(e for e in events if isinstance(e, SourcesEvent)).sources
    assert [s.handle for s in sources] == ["c1", "c2"]
    # The fake toolset returns both passages under one decision; that must not
    # collapse them, or one of the two marks becomes unresolvable.
    assert len({s.document_id for s in sources}) == 1


async def test_sources_arrive_before_the_first_token() -> None:
    """A marker cannot resolve against evidence that has not been sent."""
    provider = ScriptedProvider(
        _tool_call(ChatTool.SEARCH_DECISIONS, query="jäv"),
        _tool_call(
            ChatTool.ANSWER,
            call_id="call-2",
            annotations=[{"handle": "c1", "carries": "bär svaret"}],
        ),
    )

    events = await _collect(
        run_chat_agent(
            ChatAgentRequest(question="Vad är jäv?"),
            FakeToolset(),
            llm_provider=provider,
            settings=_settings(),
        )
    )

    kinds = [event.type for event in events]
    assert kinds.index("sources") < kinds.index("token")


async def test_a_caution_and_a_gap_reach_the_writing_step() -> None:
    """The two things an annotation exists to carry, end to end."""
    provider = ScriptedProvider(
        _tool_call(ChatTool.SEARCH_DECISIONS, query="jäv"),
        _tool_call(
            ChatTool.ANSWER,
            call_id="call-2",
            annotations=[
                {
                    "handle": "c1",
                    "carries": "definierar jäv",
                    "caution": "bilaga, underinstansens ord",
                }
            ],
            gaps=["Underlaget säger inget om tidsfristen."],
        ),
    )

    await _collect(
        run_chat_agent(
            ChatAgentRequest(question="Vad är jäv?"),
            FakeToolset(),
            llm_provider=provider,
            settings=_settings(),
        )
    )

    synthesis_prompt = provider.seen_messages[-1][-1].content
    assert "c1: definierar jäv" in synthesis_prompt
    assert "bilaga, underinstansens ord" in synthesis_prompt
    assert "Underlaget säger inget om tidsfristen." in synthesis_prompt


async def test_an_unreadable_annotation_costs_one_passage_not_the_turn() -> None:
    """A malformed entry is dropped; the rest is still good evidence."""
    provider = ScriptedProvider(
        _tool_call(ChatTool.SEARCH_DECISIONS, query="jäv"),
        _tool_call(
            ChatTool.ANSWER,
            call_id="call-2",
            annotations=[
                {"handle": "c1", "carries": "bär svaret"},
                {"carries": "saknar handtag"},
            ],
        ),
    )

    events = await _collect(
        run_chat_agent(
            ChatAgentRequest(question="Vad är jäv?"),
            FakeToolset(),
            llm_provider=provider,
            settings=_settings(),
        )
    )

    assert not any(isinstance(event, ErrorEvent) for event in events)
    sources = next(e for e in events if isinstance(e, SourcesEvent)).sources
    assert len(sources) == 1


async def test_appendix_selection_keeps_its_label() -> None:
    """A cited appendix passage must stay attributable to the lower instance."""
    provider = ScriptedProvider(
        _tool_call(ChatTool.SEARCH_DECISIONS, query="stiftets beslut"),
        _tool_call(
            ChatTool.ANSWER,
            call_id="call-2",
            annotations=[{"handle": "c2", "carries": "bär svaret"}],
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
            annotations=[
                {"handle": "c1", "carries": "bär svaret"},
                {"handle": "c2", "carries": "bär svaret"},
            ],
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
                annotations=[{"handle": "c1", "carries": "bär svaret"}],
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
            "agents.chat.plan",
            "agents.chat",
            "agents.chat.read",
            "ai.synthesize_answer",
        }

    async def test_a_direct_reply_is_a_single_billed_call(self) -> None:
        """One record, and that shape is itself the diagnostic.

        A greeting costing five iterations and an embedding pass means the
        orchestrator is searching when it should be replying.
        """
        provider = ScriptedProvider(
            Message(role=Role.assistant, content="Hej!"), routes=False
        )
        await _collect(
            run_chat_agent(
                ChatAgentRequest(question="Hej!"),
                FakeToolset(),
                llm_provider=provider,
                settings=_settings(),
            )
        )

        # The plan step alone: it replied directly, so the loop and the writer
        # never ran. One record, and it is the plan call.
        assert [r.context["source"] for r in self.records] == ["agents.chat.plan"]

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
                annotations=[{"handle": "c1", "carries": "bär svaret"}],
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


class TestTheToolIndexInThePrompt:
    """The prompt's tool list is generated from the definitions.

    It used to be written out beside them and had drifted: it named a `filter`
    argument `search_decisions` does not have, and called `read_decision`
    without the appendix switch.
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

    def test_every_tool_has_a_summary(self) -> None:
        """Without one the index falls back to the full `description`, which is
        the tool payload the provider already sends — twice in one request."""
        tools, _, _ = build_chat_tools(FakeToolset(), _settings())

        for tool in tools:
            assert tool.summary, tool.name

    async def test_the_rendered_prompt_lists_every_tool_and_its_arguments(
        self,
    ) -> None:
        provider = ScriptedProvider(
            _tool_call(ChatTool.SEARCH_DECISIONS, query="jäv i kyrkoråd"),
            _tool_call(
                ChatTool.ANSWER,
                call_id="call-2",
                annotations=[{"handle": "c1", "carries": "bär avgörandet"}],
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

        prompt = provider.seen_messages[0][-1].content

        for tool in ChatTool:
            assert f"- {tool.value}(" in prompt
        # The two things the hand-written list got wrong.
        assert "document_filter" in prompt
        assert "read_decision(document_id*, question*, include_appendices)" in prompt


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
            annotations=[{"handle": "c1", "carries": "bär avgörandet"}],
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

    assert not any(isinstance(e, ErrorEvent) for e in events)
    assert any(isinstance(e, DoneEvent) for e in events)

    refused = [
        e
        for e in events
        if isinstance(e, ToolResultEvent) and e.status is ToolStatus.REFUSED
    ]
    assert len(refused) == 1
    assert refused[0].id == "call-1"


class TestContextCarryOver:
    """The scratchpad persisted to the store and restored into the next turn's plan.

    Empty on the first turn; on a later turn the planner is shown the *shorthand*
    of what earlier turns gathered — the per-entry previews — never the heavy
    values. The store keys on `request.conversation_id`; a `None` id (or no store)
    turns the mechanism off for the turn.
    """

    @staticmethod
    def _chatty(store, *, conversation_id):
        """A turn the plan answers directly — it gathers nothing."""
        provider = ScriptedProvider(
            Message(role=Role.assistant, content="Varsågod!"),
            routes=False,
        )
        agent = run_chat_agent(
            ChatAgentRequest(
                question="Tack!", history=[], conversation_id=conversation_id
            ),
            FakeToolset(),
            llm_provider=provider,
            settings=_settings(),
            context_store=store,
        )
        return provider, agent

    @staticmethod
    def _research(store, *, conversation_id):
        """A turn that searches and answers, so it fills the pad."""
        provider = ScriptedProvider(
            _tool_call(ChatTool.SEARCH_DECISIONS, query="jäv i kyrkoråd"),
            _tool_call(
                ChatTool.ANSWER,
                call_id="call-2",
                annotations=[{"handle": "c1", "carries": "bär avgörandet"}],
            ),
        )
        agent = run_chat_agent(
            ChatAgentRequest(
                question="Vad har nämnden sagt om jäv?",
                history=[],
                conversation_id=conversation_id,
            ),
            FakeToolset(),
            llm_provider=provider,
            settings=_settings(),
            context_store=store,
        )
        return provider, agent

    @staticmethod
    def _plan_user_text(provider) -> str:
        """The user message of the first (plan) model call."""
        return provider.seen_messages[0][1].content

    async def test_first_turn_plans_over_empty_shorthand(self) -> None:
        store = InMemoryContextStore()
        provider, agent = self._chatty(store, conversation_id="c1")
        await _collect(agent)
        # Turn one sees an empty pad, and a chatty turn gathered nothing to persist.
        assert "{}" in self._plan_user_text(provider)
        assert (await store.get("c1"))["scratchpad"]["entries"] == []

    async def test_a_research_turns_findings_reach_the_next_turns_plan(self) -> None:
        store = InMemoryContextStore()

        provider1, agent1 = self._research(store, conversation_id="c1")
        await _collect(agent1)
        # The turn persisted the decision handle and the cited case number.
        keys = [
            entry["key"] for entry in (await store.get("c1"))["scratchpad"]["entries"]
        ]
        assert "d1" in keys
        assert "cases_discussed" in keys

        provider2, agent2 = self._chatty(store, conversation_id="c1")
        await _collect(agent2)
        # The next turn's planner is shown the shorthand — the case number reaches
        # it, restored from the store, without any new retrieval.
        assert "12/2024" in self._plan_user_text(provider2)

    async def test_no_store_leaves_the_shorthand_empty(self) -> None:
        provider, agent = self._chatty(None, conversation_id="c1")
        await _collect(agent)
        assert "{}" in self._plan_user_text(provider)

    async def test_a_none_conversation_id_turns_the_store_off(self) -> None:
        store = InMemoryContextStore()
        provider, agent = self._chatty(store, conversation_id=None)
        await _collect(agent)
        assert "{}" in self._plan_user_text(provider)
        # Nothing was keyed, so nothing was stored.
        assert await store.get("c1") == {}
