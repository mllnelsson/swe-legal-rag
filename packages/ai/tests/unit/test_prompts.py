from __future__ import annotations

import re

from ai.prompts import (
    ANSWER_SYNTHESIS,
    DOCUMENT_SUMMARIZATION,
    ENTITY_EXTRACTION,
    METADATA_EXTRACTION,
    QUERY_DECOMPOSITION,
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


class TestQueryDecomposition:
    def test_render_returns_two_messages(self):
        messages = QUERY_DECOMPOSITION.render({"question": _QUESTION, "conversation_history": _CONVERSATION})
        assert len(messages) == 2

    def test_render_roles(self):
        messages = QUERY_DECOMPOSITION.render({"question": _QUESTION, "conversation_history": _CONVERSATION})
        assert messages[0].role == Role.system
        assert messages[1].role == Role.user

    def test_no_unrendered_placeholders_in_user_message(self):
        messages = QUERY_DECOMPOSITION.render({"question": _QUESTION, "conversation_history": _CONVERSATION})
        assert not _has_placeholder(messages[1].content)

    def test_question_in_user_message(self):
        messages = QUERY_DECOMPOSITION.render({"question": _QUESTION, "conversation_history": _CONVERSATION})
        assert _QUESTION in messages[1].content

    def test_system_prompt_key_phrases(self):
        system = QUERY_DECOMPOSITION.system_prompt
        assert "svenska" in system.lower()
        assert "JSON" in system
        assert "semantic_query" in system

    def test_empty_conversation_history(self):
        messages = QUERY_DECOMPOSITION.render({"question": _QUESTION, "conversation_history": ""})
        assert len(messages) == 2
        assert not _has_placeholder(messages[1].content)


class TestAnswerSynthesis:
    def test_render_returns_two_messages(self):
        messages = ANSWER_SYNTHESIS.render({"question": _QUESTION, "chunks": _CHUNKS, "conversation_history": _CONVERSATION})
        assert len(messages) == 2

    def test_render_roles(self):
        messages = ANSWER_SYNTHESIS.render({"question": _QUESTION, "chunks": _CHUNKS, "conversation_history": _CONVERSATION})
        assert messages[0].role == Role.system
        assert messages[1].role == Role.user

    def test_no_unrendered_placeholders_in_user_message(self):
        messages = ANSWER_SYNTHESIS.render({"question": _QUESTION, "chunks": _CHUNKS, "conversation_history": _CONVERSATION})
        assert not _has_placeholder(messages[1].content)

    def test_system_prompt_key_phrases(self):
        system = ANSWER_SYNTHESIS.system_prompt
        assert "svenska" in system.lower()
        assert "ärendenummer" in system.lower()

    def test_empty_conversation_history(self):
        messages = ANSWER_SYNTHESIS.render({"question": _QUESTION, "chunks": _CHUNKS, "conversation_history": ""})
        assert not _has_placeholder(messages[1].content)


class TestMetadataExtraction:
    def test_render_returns_two_messages(self):
        messages = METADATA_EXTRACTION.render({"raw_text": _LEGAL_TEXT})
        assert len(messages) == 2

    def test_render_roles(self):
        messages = METADATA_EXTRACTION.render({"raw_text": _LEGAL_TEXT})
        assert messages[0].role == Role.system
        assert messages[1].role == Role.user

    def test_no_unrendered_placeholders_in_user_message(self):
        messages = METADATA_EXTRACTION.render({"raw_text": _LEGAL_TEXT})
        assert not _has_placeholder(messages[1].content)

    def test_raw_text_in_user_message(self):
        messages = METADATA_EXTRACTION.render({"raw_text": _LEGAL_TEXT})
        assert _LEGAL_TEXT in messages[1].content

    def test_system_prompt_key_phrases(self):
        system = METADATA_EXTRACTION.system_prompt
        assert "svenska" in system.lower()
        assert "JSON" in system
        assert "case_number" in system

    def test_very_long_raw_text(self):
        long_text = _LEGAL_TEXT * 100
        messages = METADATA_EXTRACTION.render({"raw_text": long_text})
        assert len(messages) == 2
        assert not _has_placeholder(messages[1].content)


class TestEntityExtraction:
    def test_render_returns_two_messages(self):
        messages = ENTITY_EXTRACTION.render({"raw_text": _LEGAL_TEXT, "case_number": _CASE_NUMBER})
        assert len(messages) == 2

    def test_render_roles(self):
        messages = ENTITY_EXTRACTION.render({"raw_text": _LEGAL_TEXT, "case_number": _CASE_NUMBER})
        assert messages[0].role == Role.system
        assert messages[1].role == Role.user

    def test_no_unrendered_placeholders_in_user_message(self):
        messages = ENTITY_EXTRACTION.render({"raw_text": _LEGAL_TEXT, "case_number": _CASE_NUMBER})
        assert not _has_placeholder(messages[1].content)

    def test_system_prompt_key_phrases(self):
        system = ENTITY_EXTRACTION.system_prompt
        assert "svenska" in system.lower()
        assert "JSON" in system
        assert "legal_concept" in system

    def test_none_case_number_renders(self):
        messages = ENTITY_EXTRACTION.render({"raw_text": _LEGAL_TEXT, "case_number": None})
        assert len(messages) == 2
        assert not _has_placeholder(messages[1].content)


class TestDocumentSummarization:
    def test_render_returns_two_messages(self):
        messages = DOCUMENT_SUMMARIZATION.render({"raw_text": _LEGAL_TEXT})
        assert len(messages) == 2

    def test_render_roles(self):
        messages = DOCUMENT_SUMMARIZATION.render({"raw_text": _LEGAL_TEXT})
        assert messages[0].role == Role.system
        assert messages[1].role == Role.user

    def test_no_unrendered_placeholders_in_user_message(self):
        messages = DOCUMENT_SUMMARIZATION.render({"raw_text": _LEGAL_TEXT})
        assert not _has_placeholder(messages[1].content)

    def test_system_prompt_key_phrases(self):
        system = DOCUMENT_SUMMARIZATION.system_prompt
        assert "svenska" in system.lower()
        assert "sammanfattning" in system.lower()

    def test_very_long_raw_text(self):
        long_text = _LEGAL_TEXT * 100
        messages = DOCUMENT_SUMMARIZATION.render({"raw_text": long_text})
        assert len(messages) == 2
        assert not _has_placeholder(messages[1].content)
