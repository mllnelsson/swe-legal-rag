from __future__ import annotations

import datetime

from shared.segmentation import split_document
from worker_metadata.patterns import (
    MetadataResult,
    extract_case_number,
    extract_category,
    extract_decision_date,
    extract_decision_number,
    extract_decision_outcome,
    extract_metadata_rule_based,
    is_complete,
)

# The extractors work on segments, not raw text, so that an appended lower-instance
# decision cannot contribute its own date, outcome or diarienummer.


def _segments(text: str):
    return split_document(text)


# --- extract_case_number ---


def test_extract_case_number_from_trailer() -> None:
    text = "Beslut i ärendet\nSökord: Avvisning.\nÄrendenummer: ÖN 2023-0042\n"
    assert extract_case_number(_segments(text)) == "2023-0042"


def test_extract_case_number_falls_back_to_body() -> None:
    text = "Ärendenummer: ÖN 2023-0042\n\nBeslut i ärendet"
    assert extract_case_number(_segments(text)) == "2023-0042"


def test_extract_case_number_no_match() -> None:
    text = "Överklagandenämnden för Svenska kyrkan\n\nBeslut i ärendet om kyrkogård"
    assert extract_case_number(_segments(text)) is None


def test_extract_case_number_ignores_appendix_diarienummer() -> None:
    text = (
        "Sökord: Avvisning.\n"
        "Ärendenummer: ÖN 2023-0042\n"
        "Beslut: 3/2024\n"
        "Bilaga A\n"
        "Ärendenummer: ÖN 2020-0001\n"
    )
    assert extract_case_number(_segments(text)) == "2023-0042"


# --- extract_decision_number ---


def test_extract_decision_number_from_trailer() -> None:
    text = "Sökord: Avvisning.\nÄrendenummer: ÖN 2025-0024\nBeslut: 3/2026\n"
    assert extract_decision_number(_segments(text)) == "3/2026"


def test_extract_decision_number_strips_leading_zero() -> None:
    text = "Sökord: Avvisning.\nBeslut: 03/2026\n"
    assert extract_decision_number(_segments(text)) == "3/2026"


def test_extract_decision_number_no_match() -> None:
    assert extract_decision_number(_segments("Sökord: Avvisning.\n")) is None


# --- extract_decision_date ---


def test_extract_decision_date_meddelat_prefix() -> None:
    segments = _segments("Meddelat 2023-01-15 i ärendet")
    assert extract_decision_date(segments) == datetime.date(2023, 1, 15)


def test_extract_decision_date_no_match() -> None:
    assert extract_decision_date(_segments("Överklagandenämnden")) is None


def test_extract_decision_date_ignores_appendix_date() -> None:
    text = "Meddelat 2023-01-15\nSökord: X\nBilaga A\nMeddelat 2020-05-05\n"
    assert extract_decision_date(_segments(text)) == datetime.date(2023, 1, 15)


# --- extract_decision_outcome ---


def test_extract_decision_outcome_prefers_the_holding() -> None:
    text = (
        "Nämnden avslår överklagandet i sin helhet.\n"
        "Överklagandenämndens beslut: Överklagandenämnden avvisar överklagandet.\n"
        "Sökord: Avvisning.\n"
    )
    assert (
        extract_decision_outcome(_segments(text))
        == "Överklagandenämnden avvisar överklagandet."
    )


def test_extract_decision_outcome_holding_collapses_newlines() -> None:
    text = (
        "Överklagandenämndens beslut:\n"
        "1. Nämnden avslår överklagandet.\n"
        "2. Nämnden undanröjer stiftets beslut.\n"
        "Sökord: X\n"
    )
    result = extract_decision_outcome(_segments(text))
    assert result is not None
    assert "\n" not in result
    assert result.startswith("1. Nämnden avslår överklagandet.")


def test_extract_decision_outcome_bifaller_keyword_fallback() -> None:
    text = "Överklagandenämnden bifaller överklagandet och upphäver beslutet."
    result = extract_decision_outcome(_segments(text))
    assert result is not None
    assert "bifaller" in result


def test_extract_decision_outcome_avslar_keyword_fallback() -> None:
    result = extract_decision_outcome(_segments("Nämnden avslår överklagandet."))
    assert result is not None
    assert "avslår" in result


def test_extract_decision_outcome_no_match() -> None:
    text = "Ärendet gäller kyrkogårdsförvaltning i Stockholms stift."
    assert extract_decision_outcome(_segments(text)) is None


def test_extract_decision_outcome_ignores_appendix_outcome() -> None:
    text = (
        "Ärendet gäller kyrkogårdsförvaltning.\n"
        "Sökord: X\n"
        "Bilaga A\n"
        "Stiftet avslår överklagandet.\n"
    )
    assert extract_decision_outcome(_segments(text)) is None


# --- extract_category ---


def test_extract_category_two_lines_after_heading() -> None:
    text = (
        "Svenska kyrkans överklagandenämnd\n"
        "Meddelat 2023-01-15\n"
        "Kyrkogårdsförvaltning\n"
        "Bakgrund"
    )
    assert extract_category(_segments(text)) == "Kyrkogårdsförvaltning"


def test_extract_category_no_match() -> None:
    text = "Överklagandenämnden beslutade att bifalla överklagandet."
    assert extract_category(_segments(text)) is None


# --- MetadataResult + is_complete ---


def test_is_complete_all_fields() -> None:
    result = MetadataResult(
        case_number="2023-0042",
        decision_date=datetime.date(2023, 1, 15),
        decision_outcome="bifaller överklagandet",
        category="Kyrkogårdsförvaltning",
    )
    assert is_complete(result) is True


def test_is_complete_ignores_decision_number() -> None:
    result = MetadataResult(
        case_number="2023-0042",
        decision_number=None,
        decision_date=datetime.date(2023, 1, 15),
        decision_outcome="bifaller överklagandet",
        category="Kyrkogårdsförvaltning",
    )
    assert is_complete(result) is True


def test_is_complete_missing_one_field() -> None:
    result = MetadataResult(
        case_number="2023-0042",
        decision_date=datetime.date(2023, 1, 15),
        decision_outcome=None,
        category="Kyrkogårdsförvaltning",
    )
    assert is_complete(result) is False


def test_is_complete_all_none() -> None:
    assert is_complete(MetadataResult()) is False


def test_extract_metadata_rule_based_combines_all() -> None:
    text = (
        "Svenska kyrkans överklagandenämnd\n"
        "Meddelat 2023-01-15\n"
        "Kyrkogårdsförvaltning\n"
        "Överklagandenämndens beslut:\n"
        "Nämnden bifaller överklagandet och upphäver det överklagade beslutet.\n"
        "Sökord: kyrkogård\n"
        "Ärendenummer: ÖN 2023-0042\n"
        "Beslut: 7/2023\n"
    )
    result = extract_metadata_rule_based(text)
    assert result.case_number == "2023-0042"
    assert result.decision_number == "7/2023"
    assert result.decision_date == datetime.date(2023, 1, 15)
    assert result.category == "Kyrkogårdsförvaltning"
    assert result.decision_outcome is not None
    assert "bifaller" in result.decision_outcome


_TRAILER_SOKORD_LAST = (
    "Svenska kyrkans överklagandenämnd\n"
    "Meddelat 2026-06-09\n"
    "Avskrivning m.m.\n"
    "Överklagandenämndens beslut: Nämnden avvisar överklagandet.\n"
    "Ärendenummer: ÖN 2026-0014\n"
    "Beslut: 23-2026\n"
    "Sökord: Avskrivning\n"
)


class TestSourceHeadlineCorroboration:
    def test_decision_number_resolves_from_a_sokord_last_trailer(self) -> None:
        result = extract_metadata_rule_based(_TRAILER_SOKORD_LAST)
        assert result.decision_number == "23/2026"

    def test_decision_number_falls_back_to_the_headline(self) -> None:
        # A decision whose trailer carries no Beslut: line at all. The crawler's
        # listing is the only remaining source.
        text = "Svenska kyrkans överklagandenämnd\nMeddelat 2026-06-09\nAvskrivning\n"
        result = extract_metadata_rule_based(text, "Beslut 2026-23  Avskrivning")
        assert result.decision_number == "23/2026"

    def test_the_trailer_wins_over_a_disagreeing_headline(self) -> None:
        # The PDF is the authoritative artefact; source_headline is a listing
        # field the crawler copied.
        result = extract_metadata_rule_based(
            _TRAILER_SOKORD_LAST, "Beslut 2026-99 Något annat"
        )
        assert result.decision_number == "23/2026"

    def test_the_header_category_wins_over_the_headline_title(self) -> None:
        # Where the two differ the PDF is the richer of the pair.
        result = extract_metadata_rule_based(
            _TRAILER_SOKORD_LAST, "Beslut 2026-23  Avskrivning"
        )
        assert result.category == "Avskrivning m.m."

    def test_category_falls_back_to_the_headline_title(self) -> None:
        text = "Ett dokument utan rubrikrad.\nÄrendenummer: ÖN 2026-0014\n"
        result = extract_metadata_rule_based(text, "Beslut 2026-23  Avskrivning")
        assert result.category == "Avskrivning"

    def test_no_headline_is_not_an_error(self) -> None:
        result = extract_metadata_rule_based(_TRAILER_SOKORD_LAST, None)
        assert result.decision_number == "23/2026"
