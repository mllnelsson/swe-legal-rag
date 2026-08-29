"""The orchestrator's control flow, driven by a scripted provider.

Each test scripts what the model says at the plan and executor calls, supplies a
trivial synthesizer, and checks the event stream `run_agent` produces. The real
provider never runs — synthesis is the host's callable here, so the scripted
provider only has to answer the plan and executor `generate` calls.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from typing import Any

from llm_core import (
    LLMResponse,
    Message,
    Role,
    StreamChunk,
    ToolCall,
    ToolDefinition,
)

from agent_kit import (
    DoneEvent,
    ErrorEvent,
    EvidenceEvent,
    ExecutionPhase,
    InMemoryContextStore,
    PlanPhase,
    PlanReplyEvent,
    TokenEvent,
    ToolCallEvent,
    ToolResultEvent,
    ToolStatus,
    run_agent,
)

_PLAN_TOOL = ToolDefinition(
    name="begin",
    description="begin research",
    parameters={
        "type": "object",
        "properties": {"strategy": {"type": "string"}},
        "required": ["strategy"],
    },
)
_ANSWER_TOOL = ToolDefinition(
    name="answer", description="finish", parameters={"type": "object", "properties": {}}
)
_SEARCH_TOOL = ToolDefinition(
    name="search", description="gather", parameters={"type": "object", "properties": {}}
)


async def _empty_stream() -> AsyncIterator[StreamChunk]:
    if False:  # pragma: no cover - the host supplies synthesis in these tests
        yield StreamChunk(text="")


async def _ok(**_kwargs: Any) -> dict[str, Any]:
    return {"ok": True}


class ScriptedProvider:
    """Returns each queued message in turn from `generate`; never streams."""

    def __init__(self, responses: list[Message]) -> None:
        self._responses = list(responses)

    async def generate(
        self,
        messages: list[Message],
        *,
        tools: list[ToolDefinition] | None = None,
        response_schema: Any = None,
    ) -> LLMResponse:
        return LLMResponse(message=self._responses.pop(0))

    async def generate_stream(
        self, messages: list[Message]
    ) -> AsyncIterator[StreamChunk]:
        return _empty_stream()


class RaisingProvider:
    async def generate(
        self,
        messages: list[Message],
        *,
        tools: list[ToolDefinition] | None = None,
        response_schema: Any = None,
    ) -> LLMResponse:
        raise RuntimeError("provider is down")

    async def generate_stream(
        self, messages: list[Message]
    ) -> AsyncIterator[StreamChunk]:
        return _empty_stream()


@dataclass(frozen=True)
class Req:
    question: str
    history: list[dict] = field(default_factory=list)


@dataclass
class Evidence:
    answered: bool = False


def _plan_call(strategy: str) -> Message:
    return Message(
        role=Role.assistant,
        tool_calls=(ToolCall(id="p1", name="begin", arguments={"strategy": strategy}),),
    )


def _tool_call(name: str, call_id: str) -> Message:
    return Message(
        role=Role.assistant,
        tool_calls=(ToolCall(id=call_id, name=name, arguments={}),),
    )


def _read_plan(message: Message) -> str | None:
    for call in message.tool_calls:
        if call.name == "begin":
            strategy = call.arguments.get("strategy")
            return strategy if isinstance(strategy, str) else ""
    return None


def _plan_phase(
    build: Any = None,
) -> PlanPhase:
    return PlanPhase(
        build_messages=build
        or (lambda req, tools, blob: [Message(role=Role.user, content=req.question)]),
        plan_tool=_PLAN_TOOL,
        read_plan=_read_plan,
        prompt_name="plan",
        source="test.plan",
    )


def _execution_phase(max_iterations: int = 5) -> ExecutionPhase:
    return ExecutionPhase(
        build_messages=lambda req, tools, strategy: [
            Message(role=Role.user, content=strategy)
        ],
        terminal_tools={"answer"},
        max_iterations=max_iterations,
        prompt_name="exec",
    )


def _make_synth() -> Any:
    async def _synth(req: Any, evidence: Evidence) -> AsyncIterator[str]:
        if not evidence.answered:
            yield "NOTHING"
            return
        for token in ("a", "b"):
            yield token

    return _synth


async def _collect(events: AsyncIterator[Any]) -> list[Any]:
    return [event async for event in events]


async def test_direct_reply_skips_execution_and_synthesis() -> None:
    provider = ScriptedProvider([Message(role=Role.assistant, content="hej")])
    evidence = Evidence()

    events = await _collect(
        run_agent(
            Req("hi"),
            tools=[_ANSWER_TOOL],
            executors={},
            evidence=evidence,
            plan=_plan_phase(),
            execution=_execution_phase(),
            synthesize=_make_synth(),
            plan_provider=provider,
        )
    )

    assert [type(e) for e in events] == [PlanReplyEvent, DoneEvent]
    assert events[0].text == "hej"


async def test_research_then_synthesis_streams_tokens() -> None:
    async def _answer(**_kwargs: Any) -> dict[str, Any]:
        evidence.answered = True
        return {"ok": True}

    provider = ScriptedProvider([_plan_call("look it up"), _tool_call("answer", "a1")])
    evidence = Evidence()

    events = await _collect(
        run_agent(
            Req("q"),
            tools=[_ANSWER_TOOL],
            executors={"answer": _answer},
            evidence=evidence,
            plan=_plan_phase(),
            execution=_execution_phase(),
            synthesize=_make_synth(),
            plan_provider=provider,
        )
    )

    assert [type(e) for e in events] == [
        ToolCallEvent,
        ToolResultEvent,
        EvidenceEvent,
        TokenEvent,
        TokenEvent,
        DoneEvent,
    ]
    assert events[0].name == "answer"
    assert events[1].status is ToolStatus.OK
    assert events[1].arguments == {}
    assert events[2].evidence is evidence
    assert [e.text for e in events if isinstance(e, TokenEvent)] == ["a", "b"]


async def test_no_evidence_lets_the_synthesizer_speak() -> None:
    """The executor writes prose instead of calling a tool; evidence stays empty."""
    provider = ScriptedProvider(
        [_plan_call("try"), Message(role=Role.assistant, content="prose, no tool")]
    )
    evidence = Evidence()

    events = await _collect(
        run_agent(
            Req("q"),
            tools=[_ANSWER_TOOL],
            executors={"answer": _ok},
            evidence=evidence,
            plan=_plan_phase(),
            execution=_execution_phase(),
            synthesize=_make_synth(),
            plan_provider=provider,
        )
    )

    assert [type(e) for e in events] == [EvidenceEvent, TokenEvent, DoneEvent]
    assert events[1].text == "NOTHING"


async def test_exhausted_loop_ends_in_error_without_done() -> None:
    async def _search(**_kwargs: Any) -> dict[str, Any]:
        return {"ok": True}

    provider = ScriptedProvider([_plan_call("keep going"), _tool_call("search", "s1")])

    events = await _collect(
        run_agent(
            Req("q"),
            tools=[_SEARCH_TOOL, _ANSWER_TOOL],
            executors={"search": _search, "answer": _ok},
            evidence=Evidence(),
            plan=_plan_phase(),
            execution=_execution_phase(max_iterations=1),
            synthesize=_make_synth(),
            plan_provider=provider,
        )
    )

    assert isinstance(events[-1], ErrorEvent)
    assert not any(isinstance(e, DoneEvent) for e in events)


async def test_a_failing_plan_call_ends_in_error() -> None:
    events = await _collect(
        run_agent(
            Req("q"),
            tools=[_ANSWER_TOOL],
            executors={},
            evidence=Evidence(),
            plan=_plan_phase(),
            execution=_execution_phase(),
            synthesize=_make_synth(),
            plan_provider=RaisingProvider(),
        )
    )

    assert [type(e) for e in events] == [ErrorEvent]


async def test_context_blob_is_injected_into_the_plan_and_persisted() -> None:
    """Empty on turn one, carried forward, and re-read on turn two."""
    store = InMemoryContextStore()
    seen: list[dict] = []

    def _build(req: Any, tools: Any, blob: dict) -> list[Message]:
        seen.append(dict(blob))
        return [Message(role=Role.user, content=req.question)]

    def _derive(blob: dict, req: Any, evidence: Any) -> dict:
        return {"turns": blob.get("turns", 0) + 1}

    async def _turn() -> None:
        await _collect(
            run_agent(
                Req("hi"),
                tools=[_ANSWER_TOOL],
                executors={},
                evidence=Evidence(),
                plan=_plan_phase(build=_build),
                execution=_execution_phase(),
                synthesize=_make_synth(),
                plan_provider=ScriptedProvider(
                    [Message(role=Role.assistant, content="hej")]
                ),
                context_store=store,
                conversation_id="c1",
                derive_context=_derive,
            )
        )

    await _turn()
    await _turn()

    assert seen[0] == {}
    assert seen[1] == {"turns": 1}
    assert await store.get("c1") == {"turns": 2}


async def test_no_store_means_no_persistence() -> None:
    """Without a store and derive_context, a turn keeps no carry-over."""
    seen: list[dict] = []

    def _build(req: Any, tools: Any, blob: dict) -> list[Message]:
        seen.append(dict(blob))
        return [Message(role=Role.user, content=req.question)]

    await _collect(
        run_agent(
            Req("hi"),
            tools=[_ANSWER_TOOL],
            executors={},
            evidence=Evidence(),
            plan=_plan_phase(build=_build),
            execution=_execution_phase(),
            synthesize=_make_synth(),
            plan_provider=ScriptedProvider(
                [Message(role=Role.assistant, content="hej")]
            ),
        )
    )

    assert seen == [{}]
