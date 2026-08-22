"""Canned `POST /api/chat` streams, for looking at agent mode without a model.

A live turn costs a chat model, a read sub-agent and a SQL sub-agent, and takes
about a minute. The things that most need a human eye — how the wait *feels*
with progress steps ticking over it, whether a token-by-token answer scrolls
pleasantly, where the Stop button lands — are exactly the things a unit test
cannot report. So this module holds the same turn as data: a list of events and
the pause before each one.

The events are the real `agents.chat` DTOs rather than hand-written dicts, which
is what makes a script a check on the contract instead of a second, drifting
copy of it. Renaming a `ProgressLabel` member breaks these fixtures at import.

The route replays them in place of `run_chat_agent`; everything else about the
request — the SSE framing, the session row, the interaction id, the persisted
turn — is the real thing. See `api.config.ChatScript` for the switch.
"""

from __future__ import annotations

import asyncio
import uuid
from collections.abc import AsyncIterator, Sequence
from dataclasses import dataclass
from datetime import date

from agents.chat import (
    AgentEvent,
    ChatTool,
    DoneEvent,
    ErrorEvent,
    ProgressLabel,
    SourceReference,
    SourcesEvent,
    SqlEvent,
    TokenEvent,
    ToolCallEvent,
    ToolResultEvent,
    ToolStatus,
)
from agents.sql import SqlAttempt
from shared.enums import ChunkSection

from api.config import ChatScript

__all__ = [
    "DIRECT_SCRIPT_MAX_WORDS",
    "SCRIPTS",
    "ScriptedFrame",
    "replay",
    "select_script",
    "stream_text",
]

# --- timing -----------------------------------------------------------------
#
# Named rather than spelled into the arrays below, so the whole feel of a
# scripted turn is tunable in one place. The totals are the estimates in
# /api/chat-endpoint.md#latency: about 18 seconds to the first token.

# One orchestrator iteration deciding what to do next.
THINKING_DELAY = 1.5
# A tool returning — a search, a vocabulary read.
TOOL_DELAY = 1.2
# A sub-agent: the SQL loop, or reading a whole decision.
SUBAGENT_DELAY = 3.0
# Between two words of a streamed answer.
TOKEN_DELAY = 0.035
# Long enough to notice the turn started, short enough to feel immediate.
DIRECT_DELAY = 0.6

# A message this short is a greeting, a thank-you or a follow-up about the
# previous answer — the shape of turn the real agent answers from context
# without retrieving anything.
DIRECT_SCRIPT_MAX_WORDS = 3


@dataclass(frozen=True)
class ScriptedFrame:
    """One event and the pause before it."""

    delay: float
    event: AgentEvent


def _after(delay: float, frames: list[ScriptedFrame]) -> list[ScriptedFrame]:
    """`frames`, with the first one waiting `delay` instead of its own."""
    if not frames:
        return frames
    first, *rest = frames
    return [ScriptedFrame(delay, first.event), *rest]


def stream_text(text: str, *, delay: float = TOKEN_DELAY) -> list[ScriptedFrame]:
    """One frame per word, spaces kept, so the pieces rejoin to `text` exactly.

    A fixture that dropped the spaces would make every scripted answer subtly
    wrong in a way easy to miss on screen.
    """
    pieces = text.split(" ")
    return [
        ScriptedFrame(
            delay,
            TokenEvent(text=piece if index == len(pieces) - 1 else f"{piece} "),
        )
        for index, piece in enumerate(pieces)
    ]


def _step(
    step_id: str,
    tool: ChatTool,
    label: ProgressLabel,
    *,
    duration: float,
    result_label: ProgressLabel | None = None,
    status: ToolStatus = ToolStatus.OK,
    call_detail: dict | None = None,
    result_detail: dict | None = None,
) -> list[ScriptedFrame]:
    """A `tool_call` and the `tool_result` that closes it.

    `result_label` exists because the two may legitimately differ: a search that
    goes out as `search.filtered` comes back as `search.refused` when the filter
    is declined, since `search.filtered` would name a search that never ran.
    """
    return [
        ScriptedFrame(
            THINKING_DELAY,
            ToolCallEvent(id=step_id, tool=tool, label=label, detail=call_detail or {}),
        ),
        ScriptedFrame(
            duration,
            ToolResultEvent(
                id=step_id,
                tool=tool,
                label=result_label or label,
                status=status,
                detail=result_detail or {},
            ),
        ),
    ]


# --- the fabricated evidence ------------------------------------------------
#
# The case numbers say DEMO and the answers say so in their first sentence. A
# scripted turn is written to the sessions table by the same `append_turn` as a
# real one, and a month later nothing in the row would distinguish them; the
# prose announcing itself costs nothing and removes the whole problem.
#
# The document ids are invented, so the `pdf_url` the route attaches will 404.
# Making it resolve would mean querying for real ids or shipping a PDF fixture,
# and neither is what a layout check needs.

_DEMO_SOURCES = [
    SourceReference(
        document_id=uuid.UUID("d0000000-0000-4000-8000-000000000001"),
        case_number="DEMO-2024-001",
        decision_date=date(2024, 3, 14),
        decision_outcome="Avslag",
        category="Kyrkoval",
        excerpt=(
            "Detta är påhittad exempeltext från ett skriptat svar. Nämnden fann "
            "att jäv förelåg eftersom ledamoten var närstående till en av de "
            "sökande, och att beslutet därför skulle undanröjas."
        ),
        section=ChunkSection.BODY,
    ),
    SourceReference(
        document_id=uuid.UUID("d0000000-0000-4000-8000-000000000002"),
        case_number="DEMO-2023-118",
        decision_date=date(2023, 11, 2),
        decision_outcome="Bifall",
        category="Anställning",
        excerpt=(
            "Påhittad exempeltext. Överklagandenämnden har tidigare uttalat att "
            "enbart ett avlägset släktskap inte i sig grundar jäv."
        ),
        section=ChunkSection.BODY,
    ),
    SourceReference(
        document_id=uuid.UUID("d0000000-0000-4000-8000-000000000003"),
        case_number="DEMO-2023-047",
        decision_date=date(2023, 5, 22),
        decision_outcome="Avslag",
        category="Kyrkoval",
        excerpt=(
            "Påhittad exempeltext ur det överklagade beslutet: kyrkorådet ansåg "
            "att någon jävssituation inte uppkommit."
        ),
        section=ChunkSection.APPENDIX,
        appendix_label="Bilaga A",
    ),
]

_DEMO_SQL = SqlEvent(
    answered=True,
    sql=(
        "SELECT decision_outcome, count(*) AS antal\n"
        "FROM documents\n"
        "WHERE category = 'Kyrkoval'\n"
        "GROUP BY decision_outcome\n"
        "ORDER BY antal DESC"
    ),
    columns=["decision_outcome", "antal"],
    rows=[["Avslag", 41], ["Bifall", 12], ["Avvisning", 3]],
    row_count=3,
    truncated=False,
    # No trailing full stops: the client joins these with "; " into one line, and
    # a sentence-ending period would land mid-list as ".;".
    assumptions=[
        "Skriptad exempeldata — siffrorna kommer inte från någon databas",
        "'Kyrkoval' lästes ur kategorivärdena innan frågan byggdes",
    ],
    attempts=[
        SqlAttempt(
            sql="SELECT outcome, count(*) FROM documents GROUP BY outcome",
            ok=False,
            error='column "outcome" does not exist',
            row_count=None,
        ),
        SqlAttempt(
            sql=(
                "SELECT decision_outcome, count(*) AS antal FROM documents "
                "WHERE category = 'Kyrkoval' GROUP BY decision_outcome "
                "ORDER BY antal DESC"
            ),
            ok=True,
            error=None,
            row_count=3,
        ),
    ],
)

# Plain running text, no markdown: `AnswerBody` renders paragraphs as text on
# purpose, so a `**` here would reach the reader as two asterisks.
_RESEARCH_ANSWER = (
    "Det här är ett skriptat demosvar — ingenting nedan kommer från "
    "Överklagandenämndens beslut. Texten finns för att visa hur ett svar ser "
    "ut medan det skrivs fram.\n\n"
    "Jäv bedöms utifrån om den som deltagit i beslutet haft en sådan koppling "
    "till saken att opartiskheten kan sättas i fråga. I den påhittade "
    "exempelsamlingen ovan undanröjs beslutet när en ledamot varit närstående "
    "till en sökande, medan ett avlägset släktskap inte i sig räckt.\n\n"
    "Av de tre exemplen rör två kyrkoval och ett en anställning. Sifferunderlaget "
    "i frågerutan ovan är lika påhittat som resten."
)

_DIRECT_ANSWER = (
    "Det här är ett skriptat demosvar, inte något som hämtats ur besluten. "
    "En riktig sådan här tur svarar utifrån vad som redan sagts i samtalet, "
    "utan att söka i beslutssamlingen."
)

_ERROR_MESSAGE = "Ett fel uppstod när frågan besvarades."


# --- the scripts ------------------------------------------------------------

# The full shape: every progress label the client has words for, the sql
# evidence block, and roughly eighteen seconds before the first token.
_RESEARCH_SCRIPT: list[ScriptedFrame] = [
    *_step(
        "s1",
        ChatTool.LIST_VOCABULARY,
        ProgressLabel.VOCABULARY_LIST,
        duration=TOOL_DELAY,
    ),
    # The call says filtered, the result says refused: the one asymmetry in the
    # contract, and the one a client is most likely to fold wrongly.
    *_step(
        "s2",
        ChatTool.SEARCH_DECISIONS,
        ProgressLabel.SEARCH_FILTERED,
        result_label=ProgressLabel.SEARCH_REFUSED,
        status=ToolStatus.REFUSED,
        duration=TOOL_DELAY,
        call_detail={"has_filter": True, "filter_fields": ["decision_outcome"]},
    ),
    *_step(
        "s3",
        ChatTool.SEARCH_DECISIONS,
        ProgressLabel.SEARCH_BROAD,
        duration=TOOL_DELAY,
        result_detail={"decision_count": 7, "widened_to_appendices": True},
    ),
    *_step(
        "s4",
        ChatTool.QUERY_CORPUS,
        ProgressLabel.SQL_QUERY,
        duration=SUBAGENT_DELAY,
        result_detail={"answered": True, "row_count": 3},
    ),
    # After its result, like the real route: the query is evidence for the
    # count, so it arrives once the count exists.
    ScriptedFrame(0.2, _DEMO_SQL),
    *_step(
        "s5",
        ChatTool.READ_DECISION,
        ProgressLabel.DECISION_READ,
        duration=SUBAGENT_DELAY,
        call_detail={"document_id": str(_DEMO_SOURCES[0].document_id)},
    ),
    *_step(
        "s6",
        ChatTool.INSPECT_DECISION,
        ProgressLabel.DECISION_INSPECT,
        duration=TOOL_DELAY,
        call_detail={"document_id": str(_DEMO_SOURCES[1].document_id)},
    ),
    *_step(
        "s7",
        ChatTool.ANSWER,
        ProgressLabel.ANSWER_COMPOSE,
        duration=TOOL_DELAY,
        result_detail={"cited_chunks": 3},
    ),
    *stream_text(_RESEARCH_ANSWER),
    ScriptedFrame(0.3, SourcesEvent(sources=_DEMO_SOURCES)),
    ScriptedFrame(0.0, DoneEvent()),
]

# Nothing to retrieve, and so no step at all: the agent called no tool, which is
# exactly what a client sees. The empty sources list is the truthful one.
_DIRECT_SCRIPT: list[ScriptedFrame] = [
    # The pause rides on the first token rather than on a step frame: there is
    # no step to show, and a reply with no thinking time at all reads as canned.
    *_after(DIRECT_DELAY, stream_text(_DIRECT_ANSWER)),
    ScriptedFrame(0.2, SourcesEvent(sources=[])),
    ScriptedFrame(0.0, DoneEvent()),
]

# Terminal, and deliberately without a `done` after it — a client that waits for
# one hangs, which is the failure this script exists to make reachable.
_ERROR_SCRIPT: list[ScriptedFrame] = [
    *_step(
        "e1",
        ChatTool.LIST_VOCABULARY,
        ProgressLabel.VOCABULARY_LIST,
        duration=TOOL_DELAY,
    ),
    *_step(
        "e2",
        ChatTool.SEARCH_DECISIONS,
        ProgressLabel.SEARCH_BROAD,
        duration=TOOL_DELAY,
        status=ToolStatus.ERROR,
    ),
    ScriptedFrame(THINKING_DELAY, ErrorEvent(message=_ERROR_MESSAGE)),
]

SCRIPTS: dict[ChatScript, list[ScriptedFrame]] = {
    ChatScript.RESEARCH: _RESEARCH_SCRIPT,
    ChatScript.DIRECT: _DIRECT_SCRIPT,
    ChatScript.ERROR: _ERROR_SCRIPT,
}


def select_script(setting: ChatScript, message: str) -> ChatScript | None:
    """Which script this turn plays, or `None` to run the real agent.

    Pure, so the rule unit-tests without a route, a database or a clock.
    """
    match setting:
        case ChatScript.OFF:
            return None
        case ChatScript.AUTO:
            # Length only. A failure is never selected this way: a stray short
            # question looking broken would be worse than useless.
            words = len(message.split())
            return (
                ChatScript.DIRECT
                if words <= DIRECT_SCRIPT_MAX_WORDS
                else ChatScript.RESEARCH
            )
        case ChatScript.RESEARCH | ChatScript.DIRECT | ChatScript.ERROR:
            return setting


async def replay(frames: Sequence[ScriptedFrame]) -> AsyncIterator[AgentEvent]:
    """Yield the frames, pausing before each.

    The same `AsyncIterator[AgentEvent]` `run_chat_agent` returns, which is what
    keeps the route's branch to a single assignment. Cancelling the stream — the
    Stop button, a closed tab — raises out of the sleep and unwinds this
    generator, so the abort path is genuinely exercised too.
    """
    for frame in frames:
        await asyncio.sleep(frame.delay)
        yield frame.event
