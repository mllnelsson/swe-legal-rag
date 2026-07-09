from __future__ import annotations

from dataclasses import dataclass

from llm_core import Message, Role


@dataclass(frozen=True)
class PromptTemplate:
    """Inert prompt data: a system prompt plus a user template. Rendering into
    concrete messages is done by :func:`render`, keeping this a pure data type."""

    system_prompt: str
    user_template: str


def render(template: PromptTemplate, context: dict) -> list[Message]:
    rendered_user = template.user_template.format_map(context)
    return [
        Message(role=Role.system, content=template.system_prompt),
        Message(role=Role.user, content=rendered_user),
    ]
