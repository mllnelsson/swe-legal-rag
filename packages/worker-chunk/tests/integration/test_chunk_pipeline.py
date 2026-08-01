from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from ai.dtos import SummarizeResult
from shared.dtos.document import DocumentCreate, DocumentUpdate
from shared.dtos.task import TaskCreate
from shared.testing.pipeline import redrive_task
from shared.queue.sync import SyncQueuePublisher
from worker_chunk.service import process_chunking

_SWEDISH_LEGAL_TEXT = """
Överklagandenämnden för Svenska kyrkan

Mål nr ÖKN 2024-001

Bakgrund och yrkanden

Kyrkoherden i Skattkärrens församling, nedan kallad klaganden, överklagade den 15 mars 2024
Göteborgs stifts beslut om tjänstetillsättning. Klaganden yrkade att beslutet skulle upphävas
och att tjänsten skulle tillsättas på nytt med beaktande av klagandens meriter och erfarenhet.

Stiftet bestred bifall till överklagandet och anförde att tillsättningsförfarandet genomförts
i enlighet med gällande bestämmelser i kyrkoordningen. Domkapitlet hade beaktat samtliga
sökandes meriter och erfarenhet vid sin bedömning.

Rättslig grund

Kyrkoordningens bestämmelser om tjänstetillsättning återfinns i kapitel 32. Enligt 32 kap. 5 §
kyrkoordningen ska Domkapitlet vid tillsättning av kyrkoherdetjänst pröva de sökandes
lämplighet med avseende på personliga egenskaper, ledarskapsförmåga och teologisk kompetens.

Överklagandet ska prövas av Överklagandenämnden för Svenska kyrkan i enlighet med
32 kap. 14 § kyrkoordningen. Nämndens prövning är begränsad till frågan om beslutet
strider mot gällande bestämmelser.

Nämndens bedömning

Överklagandenämnden konstaterar att Domkapitlet har följt föreskrivet förfarande vid
tillsättningen av kyrkoherdetjänsten. Domkapitlet har inhämtat yttranden från berörda
parter och genomfört intervjuer med de sökande.

Nämnden finner inte att Domkapitlets beslut strider mot gällande bestämmelser i
kyrkoordningen. Det förhållandet att klaganden anser sig ha bättre meriter än den
tillförordnade kyrkoherden utgör inte i sig skäl att upphäva beslutet.

Överklagandenämnden avslår överklagandet.

Beslutet kan inte överklagas.

Ordförande: Domarens namn
Ledamöter: Ledamot A, Ledamot B, Ledamot C

Detta beslut har fattats enhälligt.
"""

_CANNED_SUMMARY = (
    "Kyrkoherden överklagade Göteborgs stifts beslut om tjänstetillsättning. "
    "Överklagandenämnden fann att Domkapitlet följt föreskrivet förfarande och avslog överklagandet. "
    "Beslutet grundades på att tillsättningsförfarandet genomförts i enlighet med kyrkoordningen."
)


@pytest.fixture
async def document_with_text(
    document_repo,
    session: AsyncSession,
) -> tuple:
    doc = await document_repo.create(
        session, DocumentCreate(source_url="https://example.com/test.pdf")
    )
    await document_repo.update(
        session, doc.id, DocumentUpdate(raw_text=_SWEDISH_LEGAL_TEXT)
    )
    await session.commit()
    doc = await document_repo.get_by_id(session, doc.id)
    assert doc is not None
    return doc


@pytest.fixture
async def chunk_task(
    document_with_text,
    task_repo,
    session: AsyncSession,
) -> object:
    task = await task_repo.create(
        session,
        TaskCreate(document_id=document_with_text.id, step="chunk", status="pending"),
    )
    await session.commit()
    return task


async def _run_chunking(
    document_id,
    task_id,
    document_repo,
    chunk_repo,
    task_repo,
    sync_publisher: SyncQueuePublisher,
    session: AsyncSession,
) -> None:
    with patch(
        "worker_chunk.service.summarize_document", new=AsyncMock()
    ) as mock_summarize:
        mock_summarize.return_value = SummarizeResult(summary=_CANNED_SUMMARY)
        await process_chunking(
            document_id=document_id,
            task_id=task_id,
            document_repo=document_repo,
            chunk_repo=chunk_repo,
            task_repo=task_repo,
            queue_publisher=sync_publisher,
            session=session,
        )


class TestChunkPipelineEndToEnd:
    async def test_document_summary_is_stored(
        self,
        document_with_text,
        chunk_task,
        document_repo,
        chunk_repo,
        task_repo,
        sync_publisher: SyncQueuePublisher,
        session: AsyncSession,
    ) -> None:
        await _run_chunking(
            document_with_text.id,
            chunk_task.id,
            document_repo,
            chunk_repo,
            task_repo,
            sync_publisher,
            session,
        )

        updated_doc = await document_repo.get_by_id(session, document_with_text.id)
        assert updated_doc is not None
        assert updated_doc.summary == _CANNED_SUMMARY

    async def test_chunks_created_with_correct_document_id(
        self,
        document_with_text,
        chunk_task,
        document_repo,
        chunk_repo,
        task_repo,
        sync_publisher: SyncQueuePublisher,
        session: AsyncSession,
    ) -> None:
        await _run_chunking(
            document_with_text.id,
            chunk_task.id,
            document_repo,
            chunk_repo,
            task_repo,
            sync_publisher,
            session,
        )

        chunks = await chunk_repo.get_by_document_id(session, document_with_text.id)
        assert len(chunks) > 0
        for chunk in chunks:
            assert chunk.document_id == document_with_text.id

    async def test_chunks_have_sequential_index(
        self,
        document_with_text,
        chunk_task,
        document_repo,
        chunk_repo,
        task_repo,
        sync_publisher: SyncQueuePublisher,
        session: AsyncSession,
    ) -> None:
        await _run_chunking(
            document_with_text.id,
            chunk_task.id,
            document_repo,
            chunk_repo,
            task_repo,
            sync_publisher,
            session,
        )

        chunks = await chunk_repo.get_by_document_id(session, document_with_text.id)
        indices = [c.chunk_index for c in chunks]
        assert indices == list(range(len(chunks)))

    async def test_contextual_text_contains_summary(
        self,
        document_with_text,
        chunk_task,
        document_repo,
        chunk_repo,
        task_repo,
        sync_publisher: SyncQueuePublisher,
        session: AsyncSession,
    ) -> None:
        await _run_chunking(
            document_with_text.id,
            chunk_task.id,
            document_repo,
            chunk_repo,
            task_repo,
            sync_publisher,
            session,
        )

        chunks = await chunk_repo.get_by_document_id(session, document_with_text.id)
        for chunk in chunks:
            assert chunk.contextual_text is not None
            assert _CANNED_SUMMARY in chunk.contextual_text

    async def test_chunk_text_does_not_contain_summary(
        self,
        document_with_text,
        chunk_task,
        document_repo,
        chunk_repo,
        task_repo,
        sync_publisher: SyncQueuePublisher,
        session: AsyncSession,
    ) -> None:
        await _run_chunking(
            document_with_text.id,
            chunk_task.id,
            document_repo,
            chunk_repo,
            task_repo,
            sync_publisher,
            session,
        )

        chunks = await chunk_repo.get_by_document_id(session, document_with_text.id)
        for chunk in chunks:
            assert _CANNED_SUMMARY not in chunk.chunk_text

    async def test_embed_message_published(
        self,
        document_with_text,
        chunk_task,
        document_repo,
        chunk_repo,
        task_repo,
        sync_publisher: SyncQueuePublisher,
        published_messages: list,
        session: AsyncSession,
    ) -> None:
        await _run_chunking(
            document_with_text.id,
            chunk_task.id,
            document_repo,
            chunk_repo,
            task_repo,
            sync_publisher,
            session,
        )

        assert len(published_messages) == 1
        assert published_messages[0].document_id == document_with_text.id


class TestChunkPipelineIdempotency:
    async def test_rerun_produces_same_chunk_count(
        self,
        document_with_text,
        chunk_task,
        document_repo,
        chunk_repo,
        task_repo,
        sync_publisher: SyncQueuePublisher,
        session: AsyncSession,
    ) -> None:
        await _run_chunking(
            document_with_text.id,
            chunk_task.id,
            document_repo,
            chunk_repo,
            task_repo,
            sync_publisher,
            session,
        )

        first_count = len(
            await chunk_repo.get_by_document_id(session, document_with_text.id)
        )

        await redrive_task(session, task_repo, chunk_task.id)

        await _run_chunking(
            document_with_text.id,
            chunk_task.id,
            document_repo,
            chunk_repo,
            task_repo,
            sync_publisher,
            session,
        )

        second_count = len(
            await chunk_repo.get_by_document_id(session, document_with_text.id)
        )
        assert first_count == second_count

    async def test_rerun_replaces_old_chunks(
        self,
        document_with_text,
        chunk_task,
        document_repo,
        chunk_repo,
        task_repo,
        sync_publisher: SyncQueuePublisher,
        session: AsyncSession,
    ) -> None:
        await _run_chunking(
            document_with_text.id,
            chunk_task.id,
            document_repo,
            chunk_repo,
            task_repo,
            sync_publisher,
            session,
        )

        first_run_ids = {
            c.id
            for c in await chunk_repo.get_by_document_id(session, document_with_text.id)
        }

        await redrive_task(session, task_repo, chunk_task.id)

        await _run_chunking(
            document_with_text.id,
            chunk_task.id,
            document_repo,
            chunk_repo,
            task_repo,
            sync_publisher,
            session,
        )

        second_run_ids = {
            c.id
            for c in await chunk_repo.get_by_document_id(session, document_with_text.id)
        }
        assert first_run_ids.isdisjoint(second_run_ids)
