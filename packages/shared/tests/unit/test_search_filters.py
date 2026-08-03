from datetime import date

from shared.dtos.search import DocumentFilter
from shared.search import is_empty_filter


class TestIsEmptyFilter:
    def test_default_filter_constrains_nothing(self):
        assert is_empty_filter(DocumentFilter()) is True

    def test_date_from_makes_non_empty(self):
        assert is_empty_filter(DocumentFilter(date_from=date(2023, 1, 1))) is False

    def test_category_makes_non_empty(self):
        assert is_empty_filter(DocumentFilter(category="Kyrkogård")) is False

    def test_entity_names_makes_non_empty(self):
        assert is_empty_filter(DocumentFilter(entity_names=["kyrkorådet"])) is False

    def test_entity_types_makes_non_empty(self):
        assert is_empty_filter(DocumentFilter(entity_types=["legal_concept"])) is False

    def test_references_case_number_makes_non_empty(self):
        assert (
            is_empty_filter(DocumentFilter(references_case_number="2020-0123")) is False
        )

    def test_case_number_makes_non_empty(self):
        assert is_empty_filter(DocumentFilter(case_number="2024-0142")) is False

    def test_decision_number_makes_non_empty(self):
        assert is_empty_filter(DocumentFilter(decision_number="12/2024")) is False

    def test_explicitly_passed_defaults_still_count_as_empty(self):
        """A caller spelling out the defaults must not look like a real filter.

        The check compares values, not which fields were set, so an API client
        that serialises every field cannot accidentally trigger a candidate
        lookup that narrows nothing.
        """
        explicit = DocumentFilter(
            date_from=None,
            date_to=None,
            category=None,
            decision_outcome=None,
            case_number=None,
            decision_number=None,
            entity_names=[],
            entity_types=[],
            references_case_number=None,
        )
        assert is_empty_filter(explicit) is True
