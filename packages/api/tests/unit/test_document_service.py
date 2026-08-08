from __future__ import annotations

import uuid
from datetime import date, datetime
from unittest.mock import AsyncMock, MagicMock, patch

from api.services.document_service import (
    get_document_chunks,
    get_document_detail,
    get_document_pdf,
    list_documents,
)
from shared.dtos.chunk import ChunkRead
from shared.dtos.document import DocumentRead
from shared.dtos.document_entity import DocumentEntityDetail
from shared.dtos.document_reference import ReferenceEdge, ReferenceEdges
from shared.dtos.search import DocumentFilter
from shared.dtos.unresolved_reference import UnresolvedReferenceRead
from shared.enums import ChunkSection, EntityRelevance, EntityType


def _doc(document_id: uuid.UUID, *, gcs_uri: str | None = "gs://bucket/key"):
    now = datetime.now()
    return DocumentRead(
        id=document_id,
        source_url="https://example.com/beslut.pdf",
        source_document_id=None,
        source_headline="Beslut om utlämnande",
        source_decision_number=None,
        source_published_at=None,
        gcs_uri=gcs_uri,
        raw_text="text",
        summary="Sammanfattning",
        case_number="2024-0142",
        decision_number="12/2024",
        decision_date=date(2024, 5, 3),
        decision_outcome="avslår överklagandet",
        category="Utlämnande av handlingar",
        created_at=now,
        updated_at=now,
    )


def _chunk_read(
    document_id: uuid.UUID,
    index: int,
    section: ChunkSection = ChunkSection.BODY,
    appendix_label: str | None = None,
) -> ChunkRead:
    return ChunkRead(
        id=uuid.uuid4(),
        document_id=document_id,
        chunk_index=index,
        chunk_text=f"stycke {index}",
        contextual_text="kontext",
        embedding=[0.1] * 8,
        section=section,
        appendix_label=appendix_label,
        created_at=datetime.now(),
    )


def _entity(name: str, entity_type: str) -> DocumentEntityDetail:
    return DocumentEntityDetail(
        entity_id=uuid.uuid4(),
        name=name,
        type=entity_type,
        relevance=EntityRelevance.PRIMARY,
    )


class TestListDocuments:
    async def test_returns_a_page_with_the_repository_total(self):
        document_id = uuid.uuid4()
        with patch("api.services.document_service.search_repo") as mock_search:
            mock_search.list_filtered_documents = AsyncMock(
                return_value=[_doc(document_id)]
            )
            mock_search.count_filtered_documents = AsyncMock(return_value=37)

            page = await list_documents(
                MagicMock(), DocumentFilter(), limit=10, offset=0
            )

        assert page.total == 37
        assert len(page.items) == 1
        assert page.items[0].document_id == document_id
        assert page.items[0].has_pdf is True

    async def test_document_without_stored_pdf_reports_has_pdf_false(self):
        with patch("api.services.document_service.search_repo") as mock_search:
            mock_search.list_filtered_documents = AsyncMock(
                return_value=[_doc(uuid.uuid4(), gcs_uri=None)]
            )
            mock_search.count_filtered_documents = AsyncMock(return_value=1)

            page = await list_documents(MagicMock(), DocumentFilter(), limit=10)

        assert page.items[0].has_pdf is False


class TestGetDocumentDetail:
    async def test_unknown_document_returns_none(self):
        with patch("api.services.document_service.document_repo") as mock_doc:
            mock_doc.get_by_id = AsyncMock(return_value=None)
            assert await get_document_detail(MagicMock(), uuid.uuid4()) is None

    async def test_entities_are_bucketed_by_type(self):
        document_id = uuid.uuid4()
        entities = [
            _entity("utlämnande av handlingar", EntityType.KEYWORD),
            _entity("offentlighetsprincipen", EntityType.LEGAL_CONCEPT),
            _entity("kyrkoordningen 54 kap", EntityType.REGULATION),
            _entity("kyrkoherde", EntityType.ROLE),
            _entity("lunds domkyrkoförsamling", EntityType.PARISH),
            _entity("okänd", "something_else"),
        ]
        with (
            patch("api.services.document_service.document_repo") as mock_doc,
            patch("api.services.document_service.document_entity_repo") as mock_de,
            patch("api.services.document_service.document_reference_repo") as mock_ref,
            patch(
                "api.services.document_service.unresolved_reference_repo"
            ) as mock_unresolved,
            patch("api.services.document_service.chunk_repo") as mock_chunk,
        ):
            mock_doc.get_by_id = AsyncMock(return_value=_doc(document_id))
            mock_de.list_entities_for_document = AsyncMock(return_value=entities)
            mock_ref.list_references_for_document = AsyncMock(
                return_value=ReferenceEdges(outgoing=[], incoming=[])
            )
            mock_unresolved.get_by_source_document_id = AsyncMock(return_value=[])
            mock_chunk.get_by_document_id = AsyncMock(return_value=[])

            detail = await get_document_detail(MagicMock(), document_id)

        assert detail is not None
        # Declared by the nämnd, so kept out of `concepts`, which is inferred.
        assert [e.name for e in detail.keywords] == ["utlämnande av handlingar"]
        assert [e.name for e in detail.concepts] == ["offentlighetsprincipen"]
        # Church-law references are regulation entities, not a separate table.
        assert [e.name for e in detail.regulations] == ["kyrkoordningen 54 kap"]
        assert [e.name for e in detail.roles] == ["kyrkoherde"]
        assert [e.name for e in detail.parishes] == ["lunds domkyrkoförsamling"]
        # An unrecognised type is surfaced rather than dropped.
        assert [e.name for e in detail.other_entities] == ["okänd"]

    async def test_sections_report_chunk_counts_and_appendix_labels(self):
        document_id = uuid.uuid4()
        chunks = [
            _chunk_read(document_id, 0),
            _chunk_read(document_id, 1),
            _chunk_read(document_id, 2, ChunkSection.APPENDIX, "Bilaga A"),
            _chunk_read(document_id, 3, ChunkSection.APPENDIX, "Bilaga A"),
            _chunk_read(document_id, 4, ChunkSection.APPENDIX, "Bilaga B"),
        ]
        with (
            patch("api.services.document_service.document_repo") as mock_doc,
            patch("api.services.document_service.document_entity_repo") as mock_de,
            patch("api.services.document_service.document_reference_repo") as mock_ref,
            patch(
                "api.services.document_service.unresolved_reference_repo"
            ) as mock_unresolved,
            patch("api.services.document_service.chunk_repo") as mock_chunk,
        ):
            mock_doc.get_by_id = AsyncMock(return_value=_doc(document_id))
            mock_de.list_entities_for_document = AsyncMock(return_value=[])
            mock_ref.list_references_for_document = AsyncMock(
                return_value=ReferenceEdges(outgoing=[], incoming=[])
            )
            mock_unresolved.get_by_source_document_id = AsyncMock(return_value=[])
            mock_chunk.get_by_document_id = AsyncMock(return_value=chunks)

            detail = await get_document_detail(MagicMock(), document_id)

        assert detail is not None
        assert detail.sections.body_chunk_count == 2
        assert detail.sections.appendix_chunk_count == 3
        assert detail.sections.appendix_labels == ["Bilaga A", "Bilaga B"]

    async def test_both_reference_directions_and_dangling_citations_are_returned(self):
        document_id = uuid.uuid4()
        outgoing = ReferenceEdge(
            document_id=uuid.uuid4(),
            case_number="2020-0031",
            decision_number="3/2020",
            decision_date=date(2020, 2, 1),
            headline="Tidigare beslut",
            reference_context="Jämför ÖN 2020-0031.",
        )
        incoming = ReferenceEdge(
            document_id=uuid.uuid4(),
            case_number="2025-0009",
            decision_number=None,
            decision_date=None,
            headline=None,
            reference_context="Se ÖN 2024-0142.",
        )
        with (
            patch("api.services.document_service.document_repo") as mock_doc,
            patch("api.services.document_service.document_entity_repo") as mock_de,
            patch("api.services.document_service.document_reference_repo") as mock_ref,
            patch(
                "api.services.document_service.unresolved_reference_repo"
            ) as mock_unresolved,
            patch("api.services.document_service.chunk_repo") as mock_chunk,
        ):
            mock_doc.get_by_id = AsyncMock(return_value=_doc(document_id))
            mock_de.list_entities_for_document = AsyncMock(return_value=[])
            mock_ref.list_references_for_document = AsyncMock(
                return_value=ReferenceEdges(outgoing=[outgoing], incoming=[incoming])
            )
            mock_unresolved.get_by_source_document_id = AsyncMock(
                return_value=[
                    UnresolvedReferenceRead(
                        id=uuid.uuid4(),
                        source_document_id=document_id,
                        target_case_number="2019-0031",
                        reference_context="Jämför ÖN 2019-0031.",
                        created_at=datetime.now(),
                    )
                ]
            )
            mock_chunk.get_by_document_id = AsyncMock(return_value=[])

            detail = await get_document_detail(MagicMock(), document_id)

        assert detail is not None
        assert detail.references_out[0].case_number == "2020-0031"
        assert detail.references_in[0].case_number == "2025-0009"
        assert detail.unresolved_references[0].target_case_number == "2019-0031"


class TestGetDocumentChunks:
    async def test_unknown_document_returns_none(self):
        with patch("api.services.document_service.document_repo") as mock_doc:
            mock_doc.get_by_id = AsyncMock(return_value=None)
            assert await get_document_chunks(MagicMock(), uuid.uuid4()) is None

    async def test_embedding_and_contextual_text_are_not_exposed(self):
        document_id = uuid.uuid4()
        with (
            patch("api.services.document_service.document_repo") as mock_doc,
            patch("api.services.document_service.chunk_repo") as mock_chunk,
        ):
            mock_doc.get_by_id = AsyncMock(return_value=_doc(document_id))
            mock_chunk.get_by_document_id = AsyncMock(
                return_value=[_chunk_read(document_id, 0)]
            )

            chunks = await get_document_chunks(MagicMock(), document_id)

        assert chunks is not None
        fields = set(chunks[0].model_dump())
        assert "embedding" not in fields
        assert "contextual_text" not in fields

    async def test_section_filter_narrows_to_that_section(self):
        document_id = uuid.uuid4()
        with (
            patch("api.services.document_service.document_repo") as mock_doc,
            patch("api.services.document_service.chunk_repo") as mock_chunk,
        ):
            mock_doc.get_by_id = AsyncMock(return_value=_doc(document_id))
            mock_chunk.get_by_document_id = AsyncMock(
                return_value=[
                    _chunk_read(document_id, 0),
                    _chunk_read(document_id, 1, ChunkSection.APPENDIX, "Bilaga A"),
                ]
            )

            chunks = await get_document_chunks(
                MagicMock(), document_id, section=ChunkSection.APPENDIX
            )

        assert chunks is not None
        assert len(chunks) == 1
        assert chunks[0].section == ChunkSection.APPENDIX


class TestGetDocumentPdf:
    async def test_unknown_document_returns_none(self):
        with patch("api.services.document_service.document_repo") as mock_doc:
            mock_doc.get_by_id = AsyncMock(return_value=None)
            result = await get_document_pdf(MagicMock(), uuid.uuid4(), MagicMock())
        assert result is None

    async def test_document_without_stored_pdf_returns_none_without_touching_storage(
        self,
    ):
        storage = MagicMock()
        with patch("api.services.document_service.document_repo") as mock_doc:
            mock_doc.get_by_id = AsyncMock(
                return_value=_doc(uuid.uuid4(), gcs_uri=None)
            )
            result = await get_document_pdf(MagicMock(), uuid.uuid4(), storage)

        assert result is None
        storage.retrieve.assert_not_called()

    async def test_bytes_are_read_from_the_shared_key(self):
        document_id = uuid.uuid4()
        storage = MagicMock()
        storage.retrieve.return_value = b"%PDF-1.7"
        with patch("api.services.document_service.document_repo") as mock_doc:
            mock_doc.get_by_id = AsyncMock(return_value=_doc(document_id))
            result = await get_document_pdf(MagicMock(), document_id, storage)

        assert result == b"%PDF-1.7"
        storage.retrieve.assert_called_once_with(
            f"documents/{document_id}/original.pdf"
        )

    async def test_missing_bytes_degrade_to_none_rather_than_raising(self):
        """Database and storage having diverged is a 404, not a 500."""
        document_id = uuid.uuid4()
        storage = MagicMock()
        storage.retrieve.side_effect = FileNotFoundError("gone")
        with patch("api.services.document_service.document_repo") as mock_doc:
            mock_doc.get_by_id = AsyncMock(return_value=_doc(document_id))
            result = await get_document_pdf(MagicMock(), document_id, storage)

        assert result is None
