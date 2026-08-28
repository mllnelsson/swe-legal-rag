"""Turn an evidence bundle into a streamed answer.

The synthesis step is deliberately separate from the tool loop that gathered the
evidence. A passage placed in the loop is re-sent to the model on every later
iteration; a passage placed here is sent once, in a single prompt, and the
answer streams straight back. This function is the generic half of that: it
renders a caller's template over a caller's already-formatted context and
streams the result, tagging the call so its cost is attributable.

What the evidence *is*, and how it is laid out in the prompt, stays with the
caller: it hands in a finished `context` dict and the template that consumes it.
This layer never sees a field name, so it carries no domain and no language.
"""

from __future__ import annotations

from collections.abc import AsyncIterator

from llm_core import LLMProvider, generate_stream, trace_context

from agent_kit.prompts import PromptTemplate, render


async def synthesize(
    template: PromptTemplate,
    context: dict[str, str],
    *,
    provider: LLMProvider | None = None,
    source: str,
) -> AsyncIterator[str]:
    """Render `template` over `context` and stream the answer token by token.

    `source` tags every trace record the call produces, so a turn's synthesis
    cost is separable from its planning and its tool loop. The enclosing
    `interaction`/`agent_run` scope, set further out, says which turn it belongs
    to.
    """
    with trace_context(source=source, prompt=template.name):
        async for token in generate_stream(render(template, context), provider=provider):
            yield token
