from __future__ import annotations

from worker_extract.extractors.rule_based import extract_references, extract_rule_based
from worker_extract.models import EntityType, ExtractionResult

_TEXT_WITH_CASE_REF = (
    "Överklagandenämnden för Svenska kyrkan\n\n"
    "Ärende: Tjänstetillsättning\n\n"
    "Kyrkoherden i Skattkärrens församling överklagade Göteborgs stifts beslut. "
    "Ärendet rör behörighet och jäv. "
    "Beslutet fattades med hänvisning till kyrkoordningen kapitel 32 § 5.\n\n"
    "Nämnden avslår överklagandet. Hänvisas även till ärende ÖN 2021-0345."
)

_TEXT_WITH_DNR = "Kyrkoherden överklagade med hänvisning till ärende ÖN dnr 2020-1234."

_TEXT_NO_REFS = (
    "Kyrkoherden överklagade beslut om behörighet utan att nämna tidigare ärenden."
)


class TestRuleBasedCrossReferences:
    def test_rule_based_detects_on_case_number(self) -> None:
        result = extract_rule_based(_TEXT_WITH_CASE_REF)
        case_numbers = [r.case_number for r in result.references]
        assert any("2021-0345" in cn for cn in case_numbers)

    def test_rule_based_on_dnr_format(self) -> None:
        result = extract_rule_based(_TEXT_WITH_DNR)
        assert len(result.references) == 1
        assert "2020-1234" in result.references[0].case_number

    def test_rule_based_reference_context_is_non_empty(self) -> None:
        result = extract_rule_based(_TEXT_WITH_CASE_REF)
        for ref in result.references:
            assert ref.reference_context.strip()

    def test_rule_based_no_case_number_returns_empty_references(self) -> None:
        result = extract_rule_based(_TEXT_NO_REFS)
        assert result.references == []

    def test_extract_references_standalone(self) -> None:
        refs = extract_references(
            "Se ärende ÖN 2022-0099 och ÖN 2022-0100 för detaljer."
        )
        assert len(refs) == 2
        case_numbers = {r.case_number for r in refs}
        assert any("2022-0099" in cn for cn in case_numbers)
        assert any("2022-0100" in cn for cn in case_numbers)


class TestRuleBasedEntityExtraction:
    def test_rule_based_extracts_role(self) -> None:
        text = "Kyrkoherden överklagade beslutet."
        result = extract_rule_based(text)
        roles = [e for e in result.entities if e.type == EntityType.ROLE]
        assert any(e.name == "kyrkoherde" for e in roles)

    def test_rule_based_extracts_regulation(self) -> None:
        text = (
            "Med hänvisning till kyrkoordningen kapitel 32 § 5 avslogs överklagandet."
        )
        result = extract_rule_based(text)
        regs = [e for e in result.entities if e.type == EntityType.REGULATION]
        assert len(regs) >= 1

    def test_rule_based_extracts_parish(self) -> None:
        text = "Kyrkoherden i Skattkärrens församling överklagade."
        result = extract_rule_based(text)
        parishes = [e for e in result.entities if e.type == EntityType.PARISH]
        assert any("skattkärrens församling" in e.name for e in parishes)

    def test_rule_based_extracts_legal_concept(self) -> None:
        text = "Ärendet rör frågan om jäv och behörighet."
        result = extract_rule_based(text)
        concepts = [e for e in result.entities if e.type == EntityType.LEGAL_CONCEPT]
        names = {e.name for e in concepts}
        assert "jäv" in names
        assert "behörighet" in names

    def test_rule_based_returns_extraction_result(self) -> None:
        result = extract_rule_based(_TEXT_WITH_CASE_REF)
        assert isinstance(result, ExtractionResult)

    def test_rule_based_entity_names_are_lowercase(self) -> None:
        result = extract_rule_based(_TEXT_WITH_CASE_REF)
        for entity in result.entities:
            assert entity.name == entity.name.lower()
