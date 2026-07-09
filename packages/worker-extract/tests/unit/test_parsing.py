from __future__ import annotations

import json

import pytest

from worker_extract.models import ExtractionResult, EntityRelevance
from worker_extract.parsing import parse_llm_response

_VALID_JSON = json.dumps(
    {
        "entities": [
            {
                "name": "Överklaganderätt",
                "type": "legal_concept",
                "relevance": "primary",
            },
            {"name": "  Kyrkoherde  ", "type": "role", "relevance": "mentioned"},
        ],
        "references": [
            {
                "case_number": "ÖN 2021-0345",
                "reference_context": "Se ärende ÖN 2021-0345.",
            },
        ],
    }
)

_DUPLICATE_ENTITY_JSON = json.dumps(
    {
        "entities": [
            {"name": "jäv", "type": "legal_concept", "relevance": "mentioned"},
            {"name": "jäv", "type": "legal_concept", "relevance": "primary"},
        ],
        "references": [],
    }
)

_INVALID_TYPE_JSON = json.dumps(
    {
        "entities": [
            {"name": "foo", "type": "unknown_type", "relevance": "primary"},
        ],
        "references": [],
    }
)

_INVALID_RELEVANCE_JSON = json.dumps(
    {
        "entities": [
            {"name": "kyrkoherde", "type": "role", "relevance": "invalid_relevance"},
        ],
        "references": [],
    }
)

_DUPLICATE_REF_JSON = json.dumps(
    {
        "entities": [],
        "references": [
            {"case_number": "ÖN 2021-0345", "reference_context": "First mention."},
            {"case_number": "ÖN 2021-0345", "reference_context": "Second mention."},
        ],
    }
)


class TestParseLLMResponse:
    def test_parse_valid_json_returns_extraction_result(self) -> None:
        result = parse_llm_response(_VALID_JSON)
        assert isinstance(result, ExtractionResult)
        assert len(result.entities) == 2
        assert len(result.references) == 1

    def test_parse_normalizes_names_to_lowercase(self) -> None:
        result = parse_llm_response(_VALID_JSON)
        names = [e.name for e in result.entities]
        assert all(n == n.lower() for n in names)

    def test_parse_strips_whitespace_from_names(self) -> None:
        result = parse_llm_response(_VALID_JSON)
        names = [e.name for e in result.entities]
        assert all(n == n.strip() for n in names)

    def test_parse_deduplicates_entities_keeps_primary(self) -> None:
        result = parse_llm_response(_DUPLICATE_ENTITY_JSON)
        assert len(result.entities) == 1
        assert result.entities[0].relevance == EntityRelevance.PRIMARY

    def test_parse_skips_entities_with_invalid_type(self) -> None:
        result = parse_llm_response(_INVALID_TYPE_JSON)
        assert len(result.entities) == 0

    def test_parse_skips_entities_with_invalid_relevance(self) -> None:
        result = parse_llm_response(_INVALID_RELEVANCE_JSON)
        assert len(result.entities) == 0

    def test_parse_malformed_json_raises_json_decode_error(self) -> None:
        with pytest.raises(json.JSONDecodeError):
            parse_llm_response("{not valid json}")

    def test_parse_empty_entities_and_references(self) -> None:
        data = json.dumps({"entities": [], "references": []})
        result = parse_llm_response(data)
        assert result.entities == []
        assert result.references == []

    def test_parse_deduplicates_references_by_case_number(self) -> None:
        result = parse_llm_response(_DUPLICATE_REF_JSON)
        assert len(result.references) == 1

    def test_parse_reference_context_preserved(self) -> None:
        result = parse_llm_response(_VALID_JSON)
        assert result.references[0].reference_context == "Se ärende ÖN 2021-0345."
