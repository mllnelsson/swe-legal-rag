"""The conversational agent behind `POST /api/chat`.

Unlike the text-to-SQL agent beside it, this one streams and is driven from a
session — but it is still a function over an injected toolset, not a service
that reaches into a database itself. `ChatToolset` is what keeps it that way,
and what keeps the dependency running `api -> agents`.
"""

from agents.chat._agent import chat_context_carry, run_chat_agent
from agents.chat._dtos import (
    EXCERPT_MAX_CHARS,
    MAX_CHAT_QUESTION_CHARS,
    AgentEvent,
    ChatAgentRequest,
    ChatTool,
    DecisionProfile,
    DecisionText,
    DecisionTextChunk,
    DoneEvent,
    ErrorEvent,
    ProgressLabel,
    SearchedChunk,
    SearchedDecision,
    SearchOutcome,
    SourceReference,
    SourcesEvent,
    SqlEvent,
    TokenEvent,
    ToolCallEvent,
    ToolResultEvent,
    ToolStatus,
    Vocabulary,
    VocabularyValue,
)
from agents.chat._protocols import ChatToolset
from agents.chat._tools import FREE_TEXT_FILTER_FIELDS, ChatState, build_chat_tools

__all__ = [
    "run_chat_agent",
    "chat_context_carry",
    "ChatAgentRequest",
    "ChatToolset",
    # Events
    "AgentEvent",
    "ToolCallEvent",
    "ToolResultEvent",
    "SqlEvent",
    "TokenEvent",
    "SourcesEvent",
    "DoneEvent",
    "ErrorEvent",
    "SourceReference",
    # The progress vocabulary the client maps to its own words
    "ChatTool",
    "ProgressLabel",
    "ToolStatus",
    # What a toolset implementation returns
    "SearchOutcome",
    "SearchedDecision",
    "SearchedChunk",
    "Vocabulary",
    "VocabularyValue",
    "DecisionText",
    "DecisionTextChunk",
    "DecisionProfile",
    # Internals worth testing against
    "ChatState",
    "build_chat_tools",
    "FREE_TEXT_FILTER_FIELDS",
    "MAX_CHAT_QUESTION_CHARS",
    "EXCERPT_MAX_CHARS",
]
