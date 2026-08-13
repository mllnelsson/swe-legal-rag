"""The correlation id an agent endpoint accepts and echoes.

One id spans everything a question cost — the orchestrator's iterations, both
sub-agents and the streamed answer — so handing it to the client is what lets a
reported bad answer be found in the [trace stream](/observability.md) later.
"""

from __future__ import annotations

import uuid

__all__ = ["INTERACTION_ID_HEADER", "resolve_interaction_id"]

INTERACTION_ID_HEADER = "X-Interaction-Id"


def resolve_interaction_id(supplied: str | None) -> str:
    """Honour a client-supplied correlation id, or mint one.

    Accepted only when it parses as a UUID. The value lands in the `context` of
    every trace record the request produces and becomes the key those records
    are searched by, so arbitrary client text would be both an injection surface
    and a collision risk.

    A rejected value is not an error — it matches how an unrecognized
    `session_id` silently starts a fresh session. The client can still tell,
    because the id actually in use is always echoed back.
    """
    if supplied is None:
        return str(uuid.uuid4())
    try:
        # Canonicalises case and brace forms, so one id has one stored spelling.
        return str(uuid.UUID(supplied))
    except ValueError:
        return str(uuid.uuid4())
