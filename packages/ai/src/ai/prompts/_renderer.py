from __future__ import annotations

from dataclasses import dataclass

from llm_core import Message, Role


@dataclass(frozen=True)
class PromptTemplate:
    system_prompt: str
    user_template: str

    def render(self, context: dict) -> list[Message]:
        rendered_user = self.user_template.format_map(context)
        return [
            Message(role=Role.system, content=self.system_prompt),
            Message(role=Role.user, content=rendered_user),
        ]
