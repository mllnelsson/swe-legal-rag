"""Reading one whole decision, in a sub-agent rather than in the loop.

A decision runs to ~10k characters on average and 165k at worst. Handing them to
the orchestrator would make its context grow with every document it opens, and
pay for that growth again on every later iteration.

So the document goes to a cheaper, longer-context model on its own, with the
question attached. What comes back is a *selection*, not a summary: the reader is
shown the decision as numbered passages and returns the numbers, so the text
downstream is fetched from the database rather than written by a model. That is
what gives the reading path the same ground truth the search path has — the
reader chooses which passages carry the answer and never what they say.

The orchestrator's context still never holds a whole decision, which is what
makes the size of the worst document uninteresting.
"""

from __future__ import annotations

from ai import agent_run_scope
from ai.prompts import DECISION_READING, render
from agent_kit.llm import LLMProvider, generate_structured
from shared.enums import ChunkSection

from agents.chat._dtos import DecisionText, ReadingSelection

__all__ = ["read_decision_text", "format_numbered_chunks"]

_SOURCE = "agents.chat.read"

_UNKNOWN_CASE = "utan ärendenummer"


def format_numbered_chunks(decision: DecisionText) -> str:
    """The decision as numbered passages, with each appendix marked where it starts.

    The number is the address the reader answers with, so it is the chunk's
    position in this list and nothing else — never `chunk_index`, which counts
    over the whole document and does not survive a body-only fetch.

    The appendix marker is the other half of the point: an appendix is the
    appealed decision, and a reader that cannot see where the board's own text
    ends will attribute the wrong words to it.
    """
    parts: list[str] = []
    current_label: str | None = None
    in_appendix = False

    for position, chunk in enumerate(decision.chunks):
        is_appendix = chunk.section is ChunkSection.APPENDIX
        label = chunk.appendix_label or "Bilaga"
        if is_appendix and (not in_appendix or label != current_label):
            parts.append(f"\n--- {label} (det överklagade beslutet) ---")
            current_label = label
        elif not is_appendix and in_appendix:
            parts.append("\n--- Nämndens egen text ---")
            current_label = None
        in_appendix = is_appendix
        parts.append(f"[{position}] {chunk.text}")

    return "\n".join(parts)


async def read_decision_text(
    decision: DecisionText,
    question: str,
    *,
    max_selected: int,
    summary_words: int,
    provider: LLMProvider | None = None,
) -> ReadingSelection:
    """Which passages of this decision bear on `question`, and how they connect.

    Raises whatever `generate_structured` raises when the model returns output
    the schema cannot read. That is a refusal for the caller to turn into a tool
    result, not a failed turn — see `_tools._read_decision`.
    """
    messages = render(
        DECISION_READING,
        {
            "question": question,
            "case_number": decision.case_number or _UNKNOWN_CASE,
            "numbered_chunks": format_numbered_chunks(decision),
            "max_selected": max_selected,
            "max_summary_words": summary_words,
        },
    )
    # One reading is one sub-agent invocation, the same as one `query_corpus`
    # call, so it gets its own `agent_run_id`. A turn may read up to
    # `chat_agent_max_documents_read` decisions; without this they would share
    # the orchestrator's id and every other key, leaving them indistinguishable
    # from one another in the trace stream.
    with agent_run_scope(source=_SOURCE, prompt=DECISION_READING.name):
        return await generate_structured(messages, ReadingSelection, provider=provider)
