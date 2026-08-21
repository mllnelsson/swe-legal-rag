from __future__ import annotations

from dataclasses import dataclass

from llm_core import Message, Role, ToolDefinition

# Suffixed to an argument the tool cannot be called without. The legend
# explaining it belongs to the calling template, in that template's language.
_REQUIRED_MARK = "*"


@dataclass(frozen=True)
class PromptTemplate:
    """Inert prompt data: a system prompt plus a user template. Rendering into
    concrete messages is done by :func:`render`, keeping this a pure data type."""

    name: str
    system_prompt: str
    user_template: str


def render(template: PromptTemplate, context: dict) -> list[Message]:
    rendered_user = template.user_template.format_map(context)
    return [
        Message(role=Role.system, content=template.system_prompt),
        Message(role=Role.user, content=rendered_user),
    ]


def _signature(tool: ToolDefinition) -> str:
    properties = tool.parameters.get("properties", {})
    required = set(tool.parameters.get("required", []))
    arguments = ", ".join(
        f"{name}{_REQUIRED_MARK}" if name in required else name for name in properties
    )
    return f"{tool.name}({arguments})"


def render_tool_index(tools: list[ToolDefinition]) -> str:
    """One entry per tool: its signature, then its summary on an indented line.

    Generated rather than written out beside the prompt. A hand-kept list drifts
    from the schemas it describes, and an argument name is the one thing it
    cannot afford to be wrong about: `llm_core.tool_loop` calls executors by
    keyword, so a name the schema does not have costs an iteration at best.

    Argument order follows the schema's own `properties`, so an entry can be
    read against the definition it came from line for line. Returns the entries
    alone — the heading above them and the legend for `*` belong to the calling
    template, which is what lets a Swedish prompt and an English one share this.
    """
    return "\n".join(
        f"- {_signature(tool)}\n  {tool.summary or tool.description}" for tool in tools
    )
