import ctypes
import io

import pytest
import pypdfium2 as pdfium
import pypdfium2.raw as r
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from shared.dtos.document import DocumentCreate, DocumentUpdate
from shared.dtos.task import TaskCreate
from shared.models.document import Document
from shared.models.task import Task
from shared.queue.base import QueueMessage
from shared.queue.sync import SyncQueuePublisher
from shared.storage.local import LocalStorageBackend
from worker_parse.parser import parse_pdf_with_pypdfium2
from worker_parse.service import process_parse

_PDF_TEXT = "Integration Test Document"


def _make_pdf_bytes(text: str) -> bytes:
    doc = pdfium.PdfDocument.new()
    page = doc.new_page(200, 200)
    textobj = r.FPDFPageObj_NewTextObj(doc, b"Helvetica", 14.0)
    encoded = (text + "\x00").encode("utf-16-le")
    ushort_array = (ctypes.c_ushort * (len(encoded) // 2)).from_buffer_copy(encoded)
    r.FPDFText_SetText(textobj, ushort_array)
    r.FPDFPageObj_Transform(textobj, 1, 0, 0, 1, 10, 100)
    r.FPDFPage_InsertObject(page, textobj)
    r.FPDFPage_GenerateContent(page)
    page.close()
    buf = io.BytesIO()
    doc.save(buf)
    buf.seek(0)
    pdf_bytes = buf.read()
    doc.close()
    return pdf_bytes


@pytest.mark.integration
async def test_parse_flow_populates_raw_text_and_completes_task(
    session: AsyncSession,
    document_repo,
    task_repo,
    local_storage: LocalStorageBackend,
    sync_publisher: SyncQueuePublisher,
    published_messages: list[QueueMessage],
) -> None:
    doc = await document_repo.create(
        session, DocumentCreate(source_url="https://example.com/doc.pdf")
    )
    await document_repo.update(
        session,
        doc.id,
        DocumentUpdate(gcs_uri=f"gs://bucket/documents/{doc.id}/original.pdf"),
    )
    task = await task_repo.create(
        session, TaskCreate(document_id=doc.id, step="parse", status="pending")
    )
    await session.commit()

    pdf_bytes = _make_pdf_bytes(_PDF_TEXT)
    local_storage.store(f"documents/{doc.id}/original.pdf", pdf_bytes)

    await process_parse(
        document_id=doc.id,
        task_id=task.id,
        storage=local_storage,
        document_repo=document_repo,
        task_repo=task_repo,
        queue_publisher=sync_publisher,
        parser=parse_pdf_with_pypdfium2,
        session=session,
        next_topic="metadata",
    )

    doc_row = (
        await session.execute(select(Document).where(Document.id == doc.id))
    ).scalar_one()
    assert doc_row.raw_text is not None
    assert _PDF_TEXT in doc_row.raw_text

    task_row = (
        await session.execute(select(Task).where(Task.id == task.id))
    ).scalar_one()
    assert task_row.status == "completed"
    assert task_row.completed_at is not None

    metadata_task = (
        await session.execute(
            select(Task).where(Task.document_id == doc.id, Task.step == "metadata")
        )
    ).scalar_one()
    assert metadata_task.status == "pending"

    assert len(published_messages) == 1
    assert published_messages[0].document_id == doc.id
