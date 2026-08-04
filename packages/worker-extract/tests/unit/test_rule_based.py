from __future__ import annotations

import pytest

from shared.enums import EntityRelevance
from shared.segmentation import split_document
from worker_extract.extractors.rule_based import extract_references, extract_rule_based
from ai.dtos import EntityResult
from shared.enums import EntityType

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

# A decision laid out the way the real corpus is: header, reasoning, holding,
# trailer carrying its own identifiers, then the appealed decision as an appendix.
_FULL_DECISION = (
    "Svenska kyrkans överklagandenämnd\n"
    "Meddelat 2026-01-07\n"
    "Utlämnande av handlingar\n"
    "YRKANDE M.M.\n"
    "Kyrkoherden överklagade beslutet. "
    "Överklagandenämnden i beslut 13/2025 återförvisade ärendet till stiftet.\n"
    "Överklagandenämndens beslut: Nämnden avslår överklagandet om jäv.\n"
    "Sökord: Utlämnande av handlingar.\n"
    "Ärendenummer: ÖN 2025-0017\n"
    "Beslut: 1/2026\n"
    "…………………………\n"
    "Bilaga A\n"
    "STIFTSSTYRELSEN I X STIFT\n"
    "Domkapitlet hänvisade till ärende ÖN 2019-0001 och till Lunds församling.\n"
)


def _segments(text: str):
    return split_document(text)


class TestRuleBasedCrossReferences:
    def test_rule_based_detects_on_case_number(self) -> None:
        result = extract_rule_based(_segments(_TEXT_WITH_CASE_REF))
        assert "2021-0345" in {r.case_number for r in result.references}

    def test_rule_based_on_dnr_format(self) -> None:
        result = extract_rule_based(_segments(_TEXT_WITH_DNR))
        assert len(result.references) == 1
        assert result.references[0].case_number == "2020-1234"

    def test_rule_based_reference_context_is_non_empty(self) -> None:
        result = extract_rule_based(_segments(_TEXT_WITH_CASE_REF))
        for ref in result.references:
            assert ref.reference_context.strip()

    def test_rule_based_no_case_number_returns_empty_references(self) -> None:
        assert extract_rule_based(_segments(_TEXT_NO_REFS)).references == []

    def test_extract_references_standalone(self) -> None:
        refs = extract_references(
            _segments("Se ärende ÖN 2022-0099 och ÖN 2022-0100 för detaljer.")
        )
        assert {r.case_number for r in refs} == {"2022-0099", "2022-0100"}

    def test_case_numbers_are_canonical_without_the_on_prefix(self) -> None:
        refs = extract_references(_segments("Se ärende ÖN 2022-0099."))
        assert refs[0].case_number == "2022-0099"

    def test_beslutsnummer_references_are_detected(self) -> None:
        result = extract_rule_based(_segments(_FULL_DECISION))
        assert "13/2025" in {r.case_number for r in result.references}

    def test_own_trailer_identifiers_are_not_references(self) -> None:
        # "Ärendenummer: ÖN 2025-0017" and "Beslut: 1/2026" are this decision's own
        # identifiers; scanning the trailer made every document cite itself.
        case_numbers = {
            r.case_number
            for r in extract_rule_based(_segments(_FULL_DECISION)).references
        }
        assert "2025-0017" not in case_numbers
        assert "1/2026" not in case_numbers

    def test_appendix_references_are_ignored(self) -> None:
        # A citation inside the appendix is the lower instance citing something.
        case_numbers = {
            r.case_number
            for r in extract_rule_based(_segments(_FULL_DECISION)).references
        }
        assert "2019-0001" not in case_numbers


class TestRuleBasedEntityExtraction:
    def test_rule_based_extracts_role(self) -> None:
        result = extract_rule_based(_segments("Kyrkoherden överklagade beslutet."))
        roles = [e for e in result.entities if e.type == EntityType.ROLE]
        assert any(e.name == "kyrkoherde" for e in roles)

    def test_rule_based_extracts_regulation(self) -> None:
        text = (
            "Med hänvisning till kyrkoordningen kapitel 32 § 5 avslogs överklagandet."
        )
        result = extract_rule_based(_segments(text))
        assert [e for e in result.entities if e.type == EntityType.REGULATION]

    def test_regulation_cited_the_way_the_corpus_writes_it(self) -> None:
        # The order 213 of the corpus's 215 citations use, and the one the patterns
        # used to require the reverse of — every kyrkoordningen citation in the
        # whole corpus was missed, leaving EntityType.REGULATION an empty vocabulary.
        text = "Ett beslut får överklagas enligt 58 kap. 1 § kyrkoordningen endast om."
        result = extract_rule_based(_segments(text))
        assert [e.name for e in result.entities if e.type == EntityType.REGULATION] == [
            "58 kap. 1 § kyrkoordningen"
        ]

    @pytest.mark.parametrize(
        "citation",
        [
            "58 kap. 1 § kyrkoordningen",
            "kyrkoordningen 58 kap. 1 §",
            "58 kap 1 § KO",
            "KO 58:1",
            "58 kap. 1 § tredje stycket kyrkoordningen",
        ],
    )
    def test_every_spelling_collapses_to_one_entity(self, citation: str) -> None:
        # The entity name is a join key: four spellings of one provision would be
        # four unrelated nodes in the graph. The sub-clause is dropped because
        # "58 kap. 1 §" and "58 kap. 1 § tredje stycket" cite the same provision.
        result = extract_rule_based(_segments(f"Enligt {citation} gäller följande."))
        assert [e.name for e in result.entities if e.type == EntityType.REGULATION] == [
            "58 kap. 1 § kyrkoordningen"
        ]

    @pytest.mark.parametrize(
        "citation",
        ["40 kap. 7-8 §§ kyrkoordningen", "40 kap. 7 och 8 §§ kyrkoordningen"],
    )
    def test_both_range_spellings_yield_one_entity(self, citation: str) -> None:
        # Ranges are normalised but not expanded: "57 kap. 8-19 §§" stays one
        # entity rather than twelve.
        result = extract_rule_based(_segments(f"Enligt {citation} gäller detta."))
        assert [e.name for e in result.entities if e.type == EntityType.REGULATION] == [
            "40 kap. 7-8 §§ kyrkoordningen"
        ]

    @pytest.mark.parametrize(
        "citation", ["54 kap. kyrkoordningen", "58 kapitlet kyrkoordningen"]
    )
    def test_a_whole_chapter_is_captured(self, citation: str) -> None:
        result = extract_rule_based(_segments(f"Bestämmelserna i {citation} gäller."))
        assert [e for e in result.entities if e.type == EntityType.REGULATION]

    def test_a_citation_broken_across_a_line_wrap_still_matches(self) -> None:
        text = "Detta följer av 58 kap.\n1 § kyrkoordningen och gäller alltjämt."
        result = extract_rule_based(_segments(text))
        assert [e.name for e in result.entities if e.type == EntityType.REGULATION] == [
            "58 kap. 1 § kyrkoordningen"
        ]

    @pytest.mark.parametrize(
        "text",
        [
            "Enligt 19 kap. 3 § offentlighets- och sekretesslagen gäller detta.",
            "Enligt 2 kap. 7 § andra stycket 1 tryckfrihetsförordningen gäller.",
            "Enligt 30 kap. 5 § rättegångsbalken gäller detta.",
            "Enligt 11 kap. 2 § kyrkolagen gäller detta.",
            "En ko betade på ängen utanför kyrkan.",
        ],
    )
    def test_other_statutes_are_not_regulations(self, text: str) -> None:
        # Every one of these is cited in the identical "N kap. M §" shape.
        # Requiring the statute's own name is the only thing separating them, and
        # bare "ko" is a common Swedish noun.
        result = extract_rule_based(_segments(text))
        assert [e for e in result.entities if e.type == EntityType.REGULATION] == []

    def test_rule_based_extracts_parish(self) -> None:
        text = "Kyrkoherden i Skattkärrens församling överklagade."
        result = extract_rule_based(_segments(text))
        parishes = [e for e in result.entities if e.type == EntityType.PARISH]
        assert any("skattkärrens församling" in e.name for e in parishes)

    def test_rule_based_extracts_legal_concept(self) -> None:
        result = extract_rule_based(
            _segments("Ärendet rör frågan om jäv och behörighet.")
        )
        concepts = [e for e in result.entities if e.type == EntityType.LEGAL_CONCEPT]
        assert {"jäv", "behörighet"} <= {e.name for e in concepts}

    def test_rule_based_returns_extraction_result(self) -> None:
        assert isinstance(
            extract_rule_based(_segments(_TEXT_WITH_CASE_REF)), EntityResult
        )

    def test_rule_based_entity_names_are_lowercase(self) -> None:
        result = extract_rule_based(_segments(_TEXT_WITH_CASE_REF))
        for entity in result.entities:
            assert entity.name == entity.name.lower()


class TestRelevanceFollowsTheHolding:
    def test_entity_in_the_holding_is_primary(self) -> None:
        result = extract_rule_based(_segments(_FULL_DECISION))
        jav = next(e for e in result.entities if e.name == "jäv")
        assert jav.relevance is EntityRelevance.PRIMARY

    def test_entity_only_outside_the_holding_is_mentioned(self) -> None:
        result = extract_rule_based(_segments(_FULL_DECISION))
        kyrkoherde = next(e for e in result.entities if e.name == "kyrkoherde")
        assert kyrkoherde.relevance is EntityRelevance.MENTIONED

    def test_appendix_entities_are_extracted_but_only_mentioned(self) -> None:
        # The appealed decision's entities stay findable via the pre-filter, but
        # can never outrank the nämnd's own.
        result = extract_rule_based(_segments(_FULL_DECISION))
        by_name = {e.name: e for e in result.entities}
        assert "stiftsstyrelse" in by_name
        assert by_name["stiftsstyrelse"].relevance is EntityRelevance.MENTIONED
        assert by_name["lunds församling"].relevance is EntityRelevance.MENTIONED

    def test_tail_of_the_document_no_longer_confers_primacy(self) -> None:
        # The old heuristic promoted anything past 60% of the text, which with an
        # appendix meant promoting the appealed decision's entities.
        result = extract_rule_based(_segments(_FULL_DECISION))
        primary = {
            e.name for e in result.entities if e.relevance is EntityRelevance.PRIMARY
        }
        assert "stiftsstyrelse" not in primary
        assert "lunds församling" not in primary
