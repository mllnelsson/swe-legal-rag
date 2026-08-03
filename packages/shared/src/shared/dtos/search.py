import uuid
from datetime import date

from pydantic import BaseModel

from shared.enums import ChunkSection


class DocumentFilter(BaseModel):
    date_from: date | None = None
    date_to: date | None = None
    category: str | None = None
    decision_outcome: str | None = None
    # Exact identity match. Distinct from ``references_case_number`` below, which
    # asks for documents that *cite or are cited by* the given case.
    case_number: str | None = None
    decision_number: str | None = None
    entity_names: list[str] = []
    entity_types: list[str] = []
    # Matched exactly, unlike the substring match ``entity_names`` does: keywords
    # are a controlled vocabulary the facets publish verbatim, so a caller filters
    # by a value it was handed rather than by a guess.
    keywords: list[str] = []
    references_case_number: str | None = None


class ChunkSearchResult(BaseModel):
    id: uuid.UUID
    document_id: uuid.UUID
    chunk_text: str
    chunk_index: int
    score: float
    section: ChunkSection = ChunkSection.BODY
    appendix_label: str | None = None


class FacetValue(BaseModel):
    value: str
    count: int


class DocumentFacets(BaseModel):
    """The values the metadata filters will actually match.

    ``category`` and ``decision_outcome`` are free text lifted off the PDFs by
    regex, not a controlled vocabulary, so a client has no way to guess valid
    values — it has to be told.

    ``keywords`` is the exception and the strongest of the four: it is the nämnd's
    own ``Sökord`` classification, so its values are a real vocabulary rather than
    whatever the regexes happened to lift.
    """

    categories: list[FacetValue]
    decision_outcomes: list[FacetValue]
    entity_types: list[FacetValue]
    keywords: list[FacetValue]
    earliest_decision_date: date | None
    latest_decision_date: date | None
    document_count: int
