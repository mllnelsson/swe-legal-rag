from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any


class Role(StrEnum):
    system = "system"
    user = "user"
    assistant = "assistant"
    tool_call = "tool_call"
    tool_result = "tool_result"


@dataclass(frozen=True, slots=True)
class ToolCall:
    id: str
    name: str
    arguments: dict[str, Any]


@dataclass(frozen=True, slots=True)
class Message:
    role: Role
    content: str = ""
    tool_calls: tuple[ToolCall, ...] = ()
    tool_call_id: str | None = None
    tool_name: str | None = None


@dataclass(frozen=True, slots=True)
class ToolDefinition:
    name: str
    description: str
    parameters: dict[str, Any]


@dataclass(frozen=True, slots=True)
class LLMResponse:
    message: Message
    raw: Any = field(default=None, repr=False)


@dataclass(frozen=True, slots=True)
class StreamChunk:
    text: str
    raw: Any = field(default=None, repr=False)
