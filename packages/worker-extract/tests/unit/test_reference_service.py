from __future__ import annotations

import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

from shared.dtos.document import DocumentRead
from shared.dtos.document_reference import DocumentReferenceRead
from shared.dtos.unresolved_reference import UnresolvedReferenceRead
from ai.dtos import ExtractedReference
from worker_extract.services.reference_service import (
    process_references,
    reconcile_references,
)

# Sentinel standing in for the AsyncSession handle threaded to the repo functions.
session = MagicMock()


def _doc_read(case_number: str | None = "2021-0001") -> DocumentRead:
    now = datetime.now(tz=timezone.utc)
    return DocumentRead(
        id=uuid.uuid4(),
        source_url="https://example.com/doc.pdf",
        source_document_id=None,
        source_headline=None,
        source_decision_number=None,
        source_published_at=None,
        gcs_uri=None,
        raw_text="text",
        summary=None,
        case_number=case_number,
        decision_number=None,
        decision_date=None,
        decision_outcome=None,
        category=None,
        created_at=now,
        updated_at=now,
    )


def _ref(case_number: str, context: str = "some context") -> ExtractedReference:
    return ExtractedReference(case_number=case_number, reference_context=context)


def _unresolved_read(source_id: uuid.UUID, case_number: str) -> UnresolvedReferenceRead:
    return UnresolvedReferenceRead(
        id=uuid.uuid4(),
        source_document_id=source_id,
        target_case_number=case_number,
        reference_context="context",
        created_at=datetime.now(tz=timezone.utc),
    )


def _doc_ref_read(source_id: uuid.UUID, target_id: uuid.UUID) -> DocumentReferenceRead:
    return DocumentReferenceRead(
        source_document_id=source_id,
        target_document_id=target_id,
        reference_context="context",
    )


class TestProcessReferences:
    async def test_process_reference_resolved_creates_doc_reference(self) -> None:
        target_doc = _doc_read("2021-0999")
        doc_repo = MagicMock()
        doc_repo.get_by_case_number = AsyncMock(return_value=target_doc)
        ref_repo = MagicMock()
        ref_repo.upsert = AsyncMock()
        unresolved_repo = MagicMock()
        unresolved_repo.upsert = AsyncMock()

        source_id = uuid.uuid4()
        await process_references(
            session,
            doc_repo,
            ref_repo,
            unresolved_repo,
            source_id,
            ["2021-0001"],
            [_ref("2021-0999")],
        )

        ref_repo.upsert.assert_called_once()
        unresolved_repo.upsert.assert_not_called()
        create_dto = ref_repo.upsert.call_args[0][1]
        assert create_dto.source_document_id == source_id
        assert create_dto.target_document_id == target_doc.id

    async def test_process_reference_unresolvable_creates_unresolved(self) -> None:
        doc_repo = MagicMock()
        doc_repo.get_by_case_number = AsyncMock(return_value=None)
        ref_repo = MagicMock()
        ref_repo.upsert = AsyncMock()
        unresolved_repo = MagicMock()
        unresolved_repo.upsert = AsyncMock()

        source_id = uuid.uuid4()
        await process_references(
            session,
            doc_repo,
            ref_repo,
            unresolved_repo,
            source_id,
            ["2021-0001"],
            [_ref("2021-0999")],
        )

        ref_repo.upsert.assert_not_called()
        unresolved_repo.upsert.assert_called_once()
        create_dto = unresolved_repo.upsert.call_args[0][1]
        assert create_dto.target_case_number == "2021-0999"

    async def test_process_reference_skips_self_reference(self) -> None:
        doc_repo = MagicMock()
        doc_repo.get_by_case_number = AsyncMock()
        ref_repo = MagicMock()
        ref_repo.upsert = AsyncMock()
        unresolved_repo = MagicMock()
        unresolved_repo.upsert = AsyncMock()

        await process_references(
            session,
            doc_repo,
            ref_repo,
            unresolved_repo,
            uuid.uuid4(),
            ["2021-0001"],
            [_ref("2021-0001")],
        )

        doc_repo.get_by_case_number.assert_not_called()
        ref_repo.upsert.assert_not_called()
        unresolved_repo.upsert.assert_not_called()

    async def test_process_reference_empty_list_does_nothing(self) -> None:
        doc_repo = MagicMock()
        doc_repo.get_by_case_number = AsyncMock()
        ref_repo = MagicMock()
        ref_repo.upsert = AsyncMock()
        unresolved_repo = MagicMock()
        unresolved_repo.upsert = AsyncMock()

        await process_references(
            session, doc_repo, ref_repo, unresolved_repo, uuid.uuid4(), [], []
        )

        ref_repo.upsert.assert_not_called()
        unresolved_repo.upsert.assert_not_called()

    async def test_process_reference_no_source_case_number_does_not_skip(self) -> None:
        doc_repo = MagicMock()
        doc_repo.get_by_case_number = AsyncMock(return_value=None)
        ref_repo = MagicMock()
        ref_repo.upsert = AsyncMock()
        unresolved_repo = MagicMock()
        unresolved_repo.upsert = AsyncMock()

        await process_references(
            session,
            doc_repo,
            ref_repo,
            unresolved_repo,
            uuid.uuid4(),
            [],
            [_ref("2021-0999")],
        )

        unresolved_repo.upsert.assert_called_once()


class TestIdentifierSpaces:
    async def test_beslutsnummer_resolves_against_decision_number(self) -> None:
        # "13/2025" is a beslutsnummer; it can only match documents.decision_number.
        target_doc = _doc_read("2021-0999")
        doc_repo = MagicMock()
        doc_repo.get_by_case_number = AsyncMock(return_value=None)
        doc_repo.get_by_decision_number = AsyncMock(return_value=target_doc)
        ref_repo = MagicMock()
        ref_repo.upsert = AsyncMock()
        unresolved_repo = MagicMock()
        unresolved_repo.upsert = AsyncMock()

        await process_references(
            session,
            doc_repo,
            ref_repo,
            unresolved_repo,
            uuid.uuid4(),
            [],
            [_ref("13/2025")],
        )

        doc_repo.get_by_decision_number.assert_called_once_with(session, "13/2025")
        doc_repo.get_by_case_number.assert_not_called()
        ref_repo.upsert.assert_called_once()

    async def test_arendenummer_resolves_against_case_number(self) -> None:
        doc_repo = MagicMock()
        doc_repo.get_by_case_number = AsyncMock(return_value=_doc_read("2021-0999"))
        doc_repo.get_by_decision_number = AsyncMock()
        ref_repo = MagicMock()
        ref_repo.upsert = AsyncMock()
        unresolved_repo = MagicMock()
        unresolved_repo.upsert = AsyncMock()

        await process_references(
            session,
            doc_repo,
            ref_repo,
            unresolved_repo,
            uuid.uuid4(),
            [],
            [_ref("2021-0999")],
        )

        doc_repo.get_by_case_number.assert_called_once_with(session, "2021-0999")
        doc_repo.get_by_decision_number.assert_not_called()

    async def test_self_reference_skipped_in_either_space(self) -> None:
        doc_repo = MagicMock()
        doc_repo.get_by_case_number = AsyncMock()
        doc_repo.get_by_decision_number = AsyncMock()
        ref_repo = MagicMock()
        ref_repo.upsert = AsyncMock()
        unresolved_repo = MagicMock()
        unresolved_repo.upsert = AsyncMock()

        await process_references(
            session,
            doc_repo,
            ref_repo,
            unresolved_repo,
            uuid.uuid4(),
            ["2025-0017", "1/2026"],
            [_ref("2025-0017"), _ref("1/2026")],
        )

        ref_repo.upsert.assert_not_called()
        unresolved_repo.upsert.assert_not_called()


class TestReconcileReferences:
    async def test_reconcil_resolves_unresolved_references(self) -> None:
        source_id = uuid.uuid4()
        document_id = uuid.uuid4()
        ur = _unresolved_read(source_id, "2021-0999")

        unresolved_repo = MagicMock()
        unresolved_repo.get_by_target_case_number = AsyncMock(return_value=[ur])
        unresolved_repo.delete = AsyncMock()
        ref_repo = MagicMock()
        ref_repo.upsert = AsyncMock(return_value=_doc_ref_read(source_id, document_id))

        await reconcile_references(
            session, unresolved_repo, ref_repo, document_id, ["2021-0999"]
        )

        ref_repo.upsert.assert_called_once()
        create_dto = ref_repo.upsert.call_args[0][1]
        assert create_dto.source_document_id == source_id
        assert create_dto.target_document_id == document_id

    async def test_reconcil_deletes_resolved_unresolved_row(self) -> None:
        source_id = uuid.uuid4()
        document_id = uuid.uuid4()
        ur = _unresolved_read(source_id, "2021-0999")

        unresolved_repo = MagicMock()
        unresolved_repo.get_by_target_case_number = AsyncMock(return_value=[ur])
        unresolved_repo.delete = AsyncMock()
        ref_repo = MagicMock()
        ref_repo.upsert = AsyncMock(return_value=_doc_ref_read(source_id, document_id))

        await reconcile_references(
            session, unresolved_repo, ref_repo, document_id, ["2021-0999"]
        )

        unresolved_repo.delete.assert_called_once_with(session, ur.id)

    async def test_reconcil_returns_count(self) -> None:
        source_id = uuid.uuid4()
        document_id = uuid.uuid4()
        unresolved = [_unresolved_read(source_id, "2021-0999") for _ in range(3)]

        unresolved_repo = MagicMock()
        unresolved_repo.get_by_target_case_number = AsyncMock(return_value=unresolved)
        unresolved_repo.delete = AsyncMock()
        ref_repo = MagicMock()
        ref_repo.upsert = AsyncMock(return_value=_doc_ref_read(source_id, document_id))

        count = await reconcile_references(
            session, unresolved_repo, ref_repo, document_id, ["2021-0999"]
        )

        assert count == 3

    async def test_reconcile_covers_both_identifier_spaces(self) -> None:
        # A decision cited as "2025-0017" by one document and "1/2026" by another
        # must collect both when it lands.
        source_id = uuid.uuid4()
        document_id = uuid.uuid4()
        by_identifier = {
            "2025-0017": [_unresolved_read(source_id, "2025-0017")],
            "1/2026": [_unresolved_read(uuid.uuid4(), "1/2026")],
        }

        unresolved_repo = MagicMock()
        unresolved_repo.get_by_target_case_number = AsyncMock(
            side_effect=lambda _s, identifier: by_identifier[identifier]
        )
        unresolved_repo.delete = AsyncMock()
        ref_repo = MagicMock()
        ref_repo.upsert = AsyncMock(return_value=_doc_ref_read(source_id, document_id))

        count = await reconcile_references(
            session, unresolved_repo, ref_repo, document_id, ["2025-0017", "1/2026"]
        )

        assert count == 2

    async def test_reconcile_drops_a_self_edge_instead_of_creating_one(self) -> None:
        # document_references has a composite PK over (source, target); a row
        # pointing a document at itself would be a self-edge, so it is discarded.
        document_id = uuid.uuid4()
        ur = _unresolved_read(document_id, "2025-0017")

        unresolved_repo = MagicMock()
        unresolved_repo.get_by_target_case_number = AsyncMock(return_value=[ur])
        unresolved_repo.delete = AsyncMock()
        ref_repo = MagicMock()
        ref_repo.upsert = AsyncMock()

        count = await reconcile_references(
            session, unresolved_repo, ref_repo, document_id, ["2025-0017"]
        )

        assert count == 0
        ref_repo.upsert.assert_not_called()
        unresolved_repo.delete.assert_called_once_with(session, ur.id)

    async def test_reconcil_empty_returns_zero(self) -> None:
        unresolved_repo = MagicMock()
        unresolved_repo.get_by_target_case_number = AsyncMock(return_value=[])
        unresolved_repo.delete = AsyncMock()
        ref_repo = MagicMock()
        ref_repo.upsert = AsyncMock()

        count = await reconcile_references(
            session, unresolved_repo, ref_repo, uuid.uuid4(), ["2021-0999"]
        )

        assert count == 0
        ref_repo.upsert.assert_not_called()
