from __future__ import annotations

import re

import pytest

from ai.prompts import (
    ANSWER_SYNTHESIS,
    DOCUMENT_SUMMARIZATION,
    ENTITY_EXTRACTION,
    METADATA_EXTRACTION,
    QUERY_DECOMPOSITION,
    render,
)
from llm_core import Role

_PLACEHOLDER_RE = re.compile(r"\{[a-z_]+\}")

_QUESTION = "Har kyrkoherden rätt att överklaga stiftets beslut om tjänstetillsättning från 2022?"
_LEGAL_TEXT = (
    "Ärendenummer: 2023/456\n"
    "Beslutsdatum: den 15 mars 2023\n"
    "Biskopen i Göteborgs stift har prövat kyrkoherdens överklagande av beslut om tjänstetillsättning.\n"
    "Beslutet avslogs med hänvisning till kyrkoordningen kapitel 34.\n"
    "Parter: Kyrkoherden i Skattkärrens församling, Göteborgs stift."
)
_CASE_NUMBER = "2023/456"
_CONVERSATION = (
    "Användare: Vad gäller för överklaganden?\n"
    "Assistent: Överklaganden regleras i kyrkoordningen."
)
_CHUNKS = (
    "Ärende 2023/456: Överklagande avslogs. Kyrkoherden överklagade utan framgång.\n"
    "Ärende 2022/100: Anställning beviljades. Beslutet överklagades inte."
)


def _has_placeholder(text: str) -> bool:
    return bool(_PLACEHOLDER_RE.search(text))


_ALL_TEMPLATES = [
    (
        QUERY_DECOMPOSITION,
        {"question": _QUESTION, "conversation_history": _CONVERSATION},
    ),
    (
        ANSWER_SYNTHESIS,
        {
            "question": _QUESTION,
            "chunks": _CHUNKS,
            "conversation_history": _CONVERSATION,
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
    def test_no_unrendered_placeholders_in_user_message(self):
        messages = render(
            ANSWER_SYNTHESIS,
            {
                "question": _QUESTION,
                "chunks": _CHUNKS,
                "conversation_history": _CONVERSATION,
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
            {"question": _QUESTION, "chunks": _CHUNKS, "conversation_history": ""},
        )
        assert not _has_placeholder(messages[1].content)


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
