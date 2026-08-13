"""The correlation scope every unit of work opens around its LLM calls.

Lives here rather than in `llm-core` because `interaction_id` is a project
concept: llm-core carries the trace context as an opaque mapping and
deliberately declines to give any key a meaning. This module gives two of them
one, next to `worker_trace_scope` for the same reason.

See [Observability](/observability.md) for the wiring invariant.
"""

from __future__ import annotations

import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any

from llm_core import current_trace_context, trace_context

__all__ = ["agent_run_scope", "interaction_scope"]

_INTERACTION_ID = "interaction_id"
_AGENT_RUN_ID = "agent_run_id"


@contextmanager
def interaction_scope(
    interaction_id: str | None = None, **values: Any
) -> Iterator[str]:
    """Correlate every LLM call in one unit of work, reusing an enclosing id.

    An explicit id wins; failing that an id already in the context is inherited;
    failing that one is minted. Inheriting is the whole point: a sub-agent joins
    the interaction that called it instead of starting its own, so summing cost
    over one `interaction_id` covers the turn rather than part of it. Minting is
    what still correlates a standalone `POST /api/sql` or a `run_agent.py` case,
    which have no caller to inherit from.

    `trace_context` merges innermost-wins, which is right for `source` and wrong
    for this — hence a scope that decides whether to set the key at all rather
    than a change to the merge.

    Yields the id in use, which a caller returns to a client or persists.
    """
    resolved = (
        interaction_id or current_trace_context().get(_INTERACTION_ID) or _new_id()
    )
    with trace_context(**{_INTERACTION_ID: resolved}, **values):
        yield resolved


@contextmanager
def agent_run_scope(**values: Any) -> Iterator[str]:
    """Identify one agent invocation inside an interaction.

    Always mints, unlike `interaction_scope`. Inheriting an `interaction_id`
    costs the ability to tell two invocations of the same sub-agent apart — two
    `query_corpus` calls in one turn share every other correlation key — and
    this is what gives each its own identity back.
    """
    resolved = _new_id()
    with trace_context(**{_AGENT_RUN_ID: resolved}, **values):
        yield resolved


def _new_id() -> str:
    return str(uuid.uuid4())
