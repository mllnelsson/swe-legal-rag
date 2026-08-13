"""Reading one whole decision, in a sub-agent rather than in the loop.

A decision runs to ~10k characters on average and 165k at worst. Handing them to
the orchestrator would make its context grow with every document it opens, and
pay for that growth again on every later iteration and every later turn of the
conversation.

So the document goes to a cheaper, longer-context model on its own, with the
question attached, and only the extract comes back. The orchestrator's context
never holds a decision, which is what makes the size of the worst document
uninteresting.
"""

from __future__ import annotations

from ai import trace_context
from ai.prompts import DECISION_READING, render
from llm_core import LLMProvider, generate
from shared.enums import ChunkSection

from agents.chat._dtos import DecisionText

__all__ = ["read_decision_text", "format_decision_text"]

_SOURCE = "agents.chat.read"

_UNKNOWN_CASE = "utan ärendenummer"


def format_decision_text(decision: DecisionText) -> str:
    """The decision as one string, with each appendix marked where it starts.

    The marker is the whole point of passing chunks rather than `raw_text`: an
    appendix is the appealed decision, and a reader that cannot see where the
    board's own text ends will attribute the wrong words to it.
    """
    parts: list[str] = []
    current_label: str | None = None
    in_appendix = False

    for chunk in decision.chunks:
        is_appendix = chunk.section is ChunkSection.APPENDIX
        label = chunk.appendix_label or "Bilaga"
        if is_appendix and (not in_appendix or label != current_label):
            parts.append(f"\n--- {label} (det överklagade beslutet) ---")
            current_label = label
        elif not is_appendix and in_appendix:
            parts.append("\n--- Nämndens egen text ---")
            current_label = None
        in_appendix = is_appendix
        parts.append(chunk.text)

    return "\n".join(parts)


async def read_decision_text(
    decision: DecisionText,
    question: str,
    *,
    provider: LLMProvider | None = None,
) -> str:
    """What this decision has to say about `question`, in a few hundred words."""
    messages = render(
        DECISION_READING,
        {
            "question": question,
            "case_number": decision.case_number or _UNKNOWN_CASE,
            "decision_text": format_decision_text(decision),
        },
    )
    with trace_context(source=_SOURCE, prompt=DECISION_READING.name):
        response = await generate(messages, provider=provider)
    return response.message.content
