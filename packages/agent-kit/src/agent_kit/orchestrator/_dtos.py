"""The shapes a host hands `run_agent` to configure a turn.

The orchestrator owns the *control flow* — plan, execute, synthesize, and the
context-blob thread — and nothing else. Everything domain-specific arrives
through these: the prompts to render, the tool that signals a plan, how to read
the plan back, and how a turn's carry-over is derived. That split is what lets
one orchestrator drive agents over entirely different corpora.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, Protocol, runtime_checkable

from llm_core import Message, ToolDefinition

# A conversation's carry-over blob, injected into the plan call. See
# `agent_kit.context`.
JsonBlob = dict[str, Any]


@runtime_checkable
class AgentRequest(Protocol):
    """The question and the prior turns. A host's request type satisfies this.

    Read-only members, so a frozen request model (a pydantic `frozen=True`, say)
    satisfies the protocol — a writable attribute member would force invariance
    the host cannot meet.
    """

    @property
    def question(self) -> str: ...

    @property
    def history(self) -> list[dict]: ...


@dataclass(frozen=True)
class PlanPhase:
    """Phase 1: read the question and either reply directly or set a strategy.

    `build_messages` renders the plan prompt from the request, the executor's
    tools (so the plan it writes is realistic) and the carry-over `blob`.
    `plan_tool` is the single, inert tool whose call means "research this"; the
    plan rides on its arguments. `read_plan` returns the strategy string, or
    `None` when the model replied directly and there is no work to hand off.
    """

    build_messages: Callable[[AgentRequest, list[ToolDefinition], JsonBlob], list[Message]]
    plan_tool: ToolDefinition
    read_plan: Callable[[Message], str | None]
    prompt_name: str
    source: str


@dataclass(frozen=True)
class ExecutionPhase:
    """Phase 2: gather evidence with the tools, carrying the strategy.

    `build_messages` renders the executor prompt from the request, the tools and
    the strategy the plan set. The loop ends when the model calls one of
    `terminal_tools`, or after `max_iterations`. `prompt_name` tags the loop's
    trace records, which otherwise inherit the interaction default.
    """

    build_messages: Callable[[AgentRequest, list[ToolDefinition], str], list[Message]]
    terminal_tools: set[str]
    max_iterations: int
    prompt_name: str
