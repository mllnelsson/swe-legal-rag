from __future__ import annotations

import datetime

from worker_metadata.patterns import (
    MetadataResult,
    extract_case_number,
    extract_category,
    extract_decision_date,
    extract_decision_outcome,
    extract_metadata_rule_based,
    is_complete,
)

# --- extract_case_number ---


def test_extract_case_number_arendenummer_prefix() -> None:
    text = "Ärendenummer: ÖN 2023-0042\n\nBeslut i ärendet"
    assert extract_case_number(text) == "2023-0042"


def test_extract_case_number_no_match() -> None:
    text = "Överklagandenämnden för Svenska kyrkan\n\nBeslut i ärendet om kyrkogård"
    assert extract_case_number(text) is None


# --- extract_decision_date ---


def test_extract_decision_date_meddelat_prefix() -> None:
    assert extract_decision_date("Meddelat 2023-01-15 i ärendet") == datetime.date(
        2023, 1, 15
    )


def test_extract_decision_date_no_match() -> None:
    assert extract_decision_date("Överklagandenämnden för Svenska kyrkan") is None


# --- extract_decision_outcome ---


def test_extract_decision_outcome_bifaller() -> None:
    text = "Överklagandenämnden bifaller överklagandet och upphäver beslutet."
    result = extract_decision_outcome(text)
    assert result is not None
    assert "bifaller" in result


def test_extract_decision_outcome_avslar() -> None:
    text = "Nämnden avslår överklagandet i sin helhet."
    result = extract_decision_outcome(text)
    assert result is not None
    assert "avslår" in result


def test_extract_decision_outcome_no_match() -> None:
    text = "Ärendet gäller kyrkogårdsförvaltning i Stockholms stift."
    assert extract_decision_outcome(text) is None


# --- extract_category ---


def test_extract_category_two_lines_after_heading() -> None:
    text = (
        "Svenska kyrkans överklagandenämnd\n"
        "Ärendenummer: ÖN 2023-0042\n"
        "Kyrkogårdsförvaltning\n"
        "Bakgrund"
    )
    assert extract_category(text) == "Kyrkogårdsförvaltning"


def test_extract_category_no_match() -> None:
    assert (
        extract_category("Överklagandenämnden beslutade att bifalla överklagandet.")
        is None
    )


# --- MetadataResult + is_complete ---


def test_is_complete_all_fields() -> None:
    result = MetadataResult(
        case_number="2023-0042",
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
        "Ärendenummer: ÖN 2023-0042\n"
        "Kyrkogårdsförvaltning\n"
        "Meddelat 2023-01-15\n"
        "Överklagandenämndens beslut:\n"
        "Nämnden bifaller överklagandet och upphäver det överklagade beslutet.\n"
        "Sökord: kyrkogård\n"
    )
    result = extract_metadata_rule_based(text)
    assert result.case_number == "2023-0042"
    assert result.decision_date == datetime.date(2023, 1, 15)
    assert result.category == "Kyrkogårdsförvaltning"
    assert result.decision_outcome is not None
    assert "bifaller" in result.decision_outcome
