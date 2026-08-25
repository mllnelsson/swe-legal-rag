from __future__ import annotations

import re

import pytest

from ai.prompts import (
    ANSWER_SYNTHESIS,
    CHAT_ORCHESTRATION,
    DECISION_READING,
    DOCUMENT_SUMMARIZATION,
    ENTITY_EXTRACTION,
    METADATA_EXTRACTION,
    QUERY_DECOMPOSITION,
    render,
    render_tool_index,
)
from llm_core import Role, ToolDefinition

_PLACEHOLDER_RE = re.compile(r"\{[a-z_]+\}")

_QUESTION = "Har kyrkoherden rätt att överklaga stiftets beslut om tjänstetillsättning från 2022?"
_LEGAL_TEXT = (
    "Ärendenummer: 2023/456\n"
    "Beslutsdatum: den 15 mars 2023\n"
    "Biskopen i Göteborgs stift har prövat kyrkoherdens överklagande av beslut om tjänstetillsättning.\n"
    "Beslutet avslogs med hänvisning till kyrkoordningen kapitel 34.\n"
    "Parter: Kyrkoherden i Skattkärrens församling, Göteborgs stift."
)
_NUMBERED_CHUNKS = "[0] Nämnden prövar först jäv.\n[1] Överklagandet avslås."
_CASE_NUMBER = "2023/456"
_CONVERSATION = (
    "Användare: Vad gäller för överklaganden?\n"
    "Assistent: Överklaganden regleras i kyrkoordningen."
)
_CHUNKS = (
    "Ärende 2023/456: Överklagande avslogs. Kyrkoherden överklagade utan framgång.\n"
    "Ärende 2022/100: Anställning beviljades. Beslutet överklagades inte."
)
_READINGS = "[Mål 2023/456] Nämnden avslog överklagandet med hänvisning till kap. 34."
_TABULAR = (
    "Fråga: SELECT count(*) FROM documents WHERE decision_outcome ILIKE '%avslag%'\n"
    "Rader: 1\nantal\n12"
)
_ANNOTATIONS = "c1: bär avgörandet — obs: bilaga, underinstansens ord"
_GAPS = "- Underlaget säger inget om tidsfristen."
_TODAY = "2026-08-13"

# The evidence bundle every ANSWER_SYNTHESIS render needs. Spread into a context
# so a new placeholder fails one dict here rather than every call site.
_EVIDENCE = {
    "chunks": _CHUNKS,
    "readings": _READINGS,
    "tabular": _TABULAR,
    "annotations": _ANNOTATIONS,
    "gaps": _GAPS,
}


def _has_placeholder(text: str) -> bool:
    return bool(_PLACEHOLDER_RE.search(text))


# `ai` may not import `agents`, so the renderer is exercised on definitions of
# this file's own. The real definitions are checked against their executors in
# the agents suite, which is where both halves are in scope.
_SEARCH_TOOL = ToolDefinition(
    name="search_decisions",
    summary="hybrid semantic and lexical search",
    description="Searches the decisions semantically and lexically at once.",
    parameters={
        "type": "object",
        "properties": {
            "query": {"type": "string"},
            "queries": {"type": "array"},
            "document_filter": {"type": "object"},
        },
        "required": ["query"],
    },
)
_TOOL_INDEX = render_tool_index([_SEARCH_TOOL])


_ALL_TEMPLATES = [
    (
        QUERY_DECOMPOSITION,
        {"question": _QUESTION, "conversation_history": _CONVERSATION},
    ),
    (
        ANSWER_SYNTHESIS,
        {
            "question": _QUESTION,
            "conversation_history": _CONVERSATION,
            **_EVIDENCE,
        },
    ),
    (
        CHAT_ORCHESTRATION,
        {
            "question": _QUESTION,
            "today": _TODAY,
            "conversation_history": _CONVERSATION,
            "tools": _TOOL_INDEX,
        },
    ),
    (
        DECISION_READING,
        {
            "question": _QUESTION,
            "case_number": _CASE_NUMBER,
            "numbered_chunks": _NUMBERED_CHUNKS,
            "max_selected": 6,
            "max_summary_words": 80,
        },
    ),
    (METADATA_EXTRACTION, {"raw_text": _LEGAL_TEXT}),
    (ENTITY_EXTRACTION, {"raw_text": _LEGAL_TEXT, "case_number": _CASE_NUMBER}),
    (DOCUMENT_SUMMARIZATION, {"raw_text": _LEGAL_TEXT}),
]


@pytest.mark.parametrize(("template", "context"), _ALL_TEMPLATES)
def test_render_produces_a_system_then_user_pair(template, context):
    """The shape every template shares. Per-template content is asserted below."""
    messages = render(template, context)

    assert len(messages) == 2
    assert messages[0].role == Role.system
    assert messages[1].role == Role.user


class TestQueryDecomposition:
    def test_no_unrendered_placeholders_in_user_message(self):
        messages = render(
            QUERY_DECOMPOSITION,
            {"question": _QUESTION, "conversation_history": _CONVERSATION},
        )
        assert not _has_placeholder(messages[1].content)

    def test_question_in_user_message(self):
        messages = render(
            QUERY_DECOMPOSITION,
            {"question": _QUESTION, "conversation_history": _CONVERSATION},
        )
        assert _QUESTION in messages[1].content

    def test_system_prompt_key_phrases(self):
        system = QUERY_DECOMPOSITION.system_prompt
        assert "svenska" in system.lower()
        assert "JSON" in system
        assert "semantic_query" in system

    def test_empty_conversation_history(self):
        messages = render(
            QUERY_DECOMPOSITION, {"question": _QUESTION, "conversation_history": ""}
        )
        assert len(messages) == 2
        assert not _has_placeholder(messages[1].content)


class TestAnswerSynthesis:
    def test_it_asks_for_plain_text(self):
        """The client renders the answer as text, so markdown reaches a reader
        as literal ## and **. The prompt has to say so."""
        system = ANSWER_SYNTHESIS.system_prompt
        assert "inga rubriker" in system
        assert "ingen markdown" in system

    def test_it_asks_for_a_handle_after_each_claim(self):
        """Inline citations exist only if the writer is told to emit them."""
        system = ANSWER_SYNTHESIS.system_prompt
        assert "[c3]" in system

    def test_no_unrendered_placeholders_in_user_message(self):
        messages = render(
            ANSWER_SYNTHESIS,
            {
                "question": _QUESTION,
                "conversation_history": _CONVERSATION,
                **_EVIDENCE,
            },
        )
        assert not _has_placeholder(messages[1].content)

    def test_system_prompt_key_phrases(self):
        system = ANSWER_SYNTHESIS.system_prompt
        assert "svenska" in system.lower()
        assert "ärendenummer" in system.lower()

    def test_empty_conversation_history(self):
        messages = render(
            ANSWER_SYNTHESIS,
            {"question": _QUESTION, "conversation_history": "", **_EVIDENCE},
        )
        assert not _has_placeholder(messages[1].content)

    def test_every_evidence_section_reaches_the_user_message(self):
        messages = render(
            ANSWER_SYNTHESIS,
            {
                "question": _QUESTION,
                "conversation_history": _CONVERSATION,
                **_EVIDENCE,
            },
        )
        user = messages[1].content
        for section in _EVIDENCE.values():
            assert section in user

    def test_counts_are_confined_to_tabular_evidence(self):
        """The rule that stops the model counting a relevance-ranked sample.

        Search hits are a slice of the corpus, so a total derived from them is
        wrong in a way that reads as authoritative.
        """
        system = ANSWER_SYNTHESIS.system_prompt.lower()
        assert "tabelldata" in system
        assert "räkna aldrig utdragen" in system

    def test_appendix_rule_survives_the_evidence_bundle(self):
        system = ANSWER_SYNTHESIS.system_prompt.lower()
        assert "bilaga" in system
        assert "överklagade beslutet" in system


class TestChatOrchestration:
    def test_no_unrendered_placeholders_in_user_message(self):
        messages = render(
            CHAT_ORCHESTRATION,
            {
                "question": _QUESTION,
                "today": _TODAY,
                "conversation_history": _CONVERSATION,
                "tools": _TOOL_INDEX,
            },
        )
        assert not _has_placeholder(messages[1].content)

    def test_the_tools_reach_the_user_message(self):
        """Generated into the user message, and gone from the system prompt.

        The hand-written list they replaced had drifted: it advertised a
        `filter` argument `search_decisions` does not have, and left
        `include_appendices` off `read_decision` entirely.
        """
        messages = render(
            CHAT_ORCHESTRATION,
            {
                "question": _QUESTION,
                "today": _TODAY,
                "conversation_history": _CONVERSATION,
                "tools": _TOOL_INDEX,
            },
        )

        assert _TOOL_INDEX in messages[1].content
        # No signature survives above: a second, unexecutable list is exactly
        # what drifted last time.
        assert "search_decisions(" not in messages[0].content

    def test_points_at_the_generated_list(self):
        """Named in the system prompt so `How to work` has something to refer to."""
        assert "Your tools are listed with the question" in (
            CHAT_ORCHESTRATION.system_prompt
        )

    def test_states_the_grounding_and_counting_rules(self):
        system = CHAT_ORCHESTRATION.system_prompt
        assert "list_vocabulary first" in system
        assert "Never count search hits yourself" in system

    def test_written_in_english(self):
        """Deliberate, and the one prompt here that is.

        This model plans and calls tools; it never writes a word the user reads.
        """
        system = CHAT_ORCHESTRATION.system_prompt
        assert "You research questions" in system
        assert "Du är" not in system


class TestRenderToolIndex:
    """The generated tool list. It replaced a hand-written one that had drifted
    from the schemas — naming a `filter` argument `search_decisions` does not
    have — which `llm_core.tool_loop` cannot repair from as cheaply as a wrong
    value, because it calls executors by keyword."""

    def test_required_arguments_are_marked_and_optional_ones_are_not(self):
        rendered = render_tool_index([_SEARCH_TOOL])

        assert "search_decisions(query*, queries, document_filter)" in rendered

    def test_argument_order_follows_the_schema(self):
        """So an entry reads against its definition line for line."""
        rendered = render_tool_index([_SEARCH_TOOL])

        assert rendered.index("query*") < rendered.index("queries")
        assert rendered.index("queries") < rendered.index("document_filter")

    def test_the_summary_is_used_when_set(self):
        rendered = render_tool_index([_SEARCH_TOOL])

        assert "hybrid semantic and lexical search" in rendered
        assert "Searches the decisions semantically" not in rendered

    def test_the_description_stands_in_when_no_summary_is_set(self):
        tool = ToolDefinition(
            name="run_sql",
            description="Runs one read-only statement.",
            parameters={"type": "object", "properties": {"sql": {"type": "string"}}},
        )

        assert (
            render_tool_index([tool])
            == "- run_sql(sql)\n  Runs one read-only statement."
        )

    def test_a_tool_taking_nothing_renders_empty_parentheses(self):
        tool = ToolDefinition(
            name="ping",
            summary="says hello",
            description="Says hello.",
            parameters={"type": "object", "properties": {}, "required": []},
        )

        assert render_tool_index([tool]) == "- ping()\n  says hello"

    def test_one_entry_per_tool(self):
        rendered = render_tool_index([_SEARCH_TOOL, _SEARCH_TOOL])

        assert rendered.count("- search_decisions") == 2


class TestDecisionReading:
    def test_the_caps_are_rendered_rather_than_written_into_the_system_prompt(self):
        """One source of truth for both caps: the settings the reader passes.

        `render` formats the user template only, so a cap written into the
        system prompt would reach the model as a literal `{max_selected}` and
        could drift from the number the code actually enforces.
        """
        assert "{" not in DECISION_READING.system_prompt
        messages = render(
            DECISION_READING,
            {
                "question": _QUESTION,
                "case_number": _CASE_NUMBER,
                "numbered_chunks": _NUMBERED_CHUNKS,
                "max_selected": 4,
                "max_summary_words": 55,
            },
        )
        assert "Högst 4 stycken" in messages[1].content
        assert "Högst 55 ord" in messages[1].content

    def test_no_unrendered_placeholders_in_user_message(self):
        messages = render(
            DECISION_READING,
            {
                "question": _QUESTION,
                "case_number": _CASE_NUMBER,
                "numbered_chunks": _NUMBERED_CHUNKS,
                "max_selected": 6,
                "max_summary_words": 80,
            },
        )
        assert not _has_placeholder(messages[1].content)

    def test_the_numbered_passages_reach_the_user_message(self):
        messages = render(
            DECISION_READING,
            {
                "question": _QUESTION,
                "case_number": _CASE_NUMBER,
                "numbered_chunks": _NUMBERED_CHUNKS,
                "max_selected": 6,
                "max_summary_words": 80,
            },
        )
        assert _NUMBERED_CHUNKS in messages[1].content
        assert _CASE_NUMBER in messages[1].content

    def test_carries_the_appendix_rule(self):
        """The reader sees whole documents, appendices included."""
        system = DECISION_READING.system_prompt.lower()
        assert "bilaga" in system
        assert "överklagade beslutet" in system


class TestMetadataExtraction:
    def test_no_unrendered_placeholders_in_user_message(self):
        messages = render(METADATA_EXTRACTION, {"raw_text": _LEGAL_TEXT})
        assert not _has_placeholder(messages[1].content)

    def test_raw_text_in_user_message(self):
        messages = render(METADATA_EXTRACTION, {"raw_text": _LEGAL_TEXT})
        assert _LEGAL_TEXT in messages[1].content

    def test_system_prompt_key_phrases(self):
        system = METADATA_EXTRACTION.system_prompt
        assert "svenska" in system.lower()
        assert "JSON" in system
        assert "case_number" in system

    def test_very_long_raw_text(self):
        long_text = _LEGAL_TEXT * 100
        messages = render(METADATA_EXTRACTION, {"raw_text": long_text})
        assert len(messages) == 2
        assert not _has_placeholder(messages[1].content)


class TestEntityExtraction:
    def test_no_unrendered_placeholders_in_user_message(self):
        messages = render(
            ENTITY_EXTRACTION, {"raw_text": _LEGAL_TEXT, "case_number": _CASE_NUMBER}
        )
        assert not _has_placeholder(messages[1].content)

    def test_system_prompt_key_phrases(self):
        system = ENTITY_EXTRACTION.system_prompt
        assert "svenska" in system.lower()
        assert "JSON" in system
        assert "legal_concept" in system

    def test_none_case_number_renders(self):
        messages = render(
            ENTITY_EXTRACTION, {"raw_text": _LEGAL_TEXT, "case_number": None}
        )
        assert len(messages) == 2
        assert not _has_placeholder(messages[1].content)


class TestDocumentSummarization:
    def test_no_unrendered_placeholders_in_user_message(self):
        messages = render(DOCUMENT_SUMMARIZATION, {"raw_text": _LEGAL_TEXT})
        assert not _has_placeholder(messages[1].content)

    def test_system_prompt_key_phrases(self):
        system = DOCUMENT_SUMMARIZATION.system_prompt
        assert "svenska" in system.lower()
        assert "sammanfattning" in system.lower()
        # The summary is prepended to every chunk, so its length is budgeted
        # against the embedding window. Changing the reserve without changing the
        # prompt should fail here.
        assert "60 ord" in system

    def test_very_long_raw_text(self):
        long_text = _LEGAL_TEXT * 100
        messages = render(DOCUMENT_SUMMARIZATION, {"raw_text": long_text})
        assert len(messages) == 2
        assert not _has_placeholder(messages[1].content)
