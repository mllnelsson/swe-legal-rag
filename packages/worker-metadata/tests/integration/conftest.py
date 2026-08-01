"""Database and queue fixtures come from the `shared.testing.fixtures` plugin.
The hand-off topic and the Swedish sample decision are specific to this worker.
"""

from __future__ import annotations

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from shared.dtos.document import DocumentCreate, DocumentUpdate
from shared.dtos.task import TaskCreate

# Laid out the way a real decision is, because the rule-based extractor keys off
# that layout: the category is the third header line, and both identifiers sit on
# their own labelled lines in the trailer. Free-form prose extracts nothing.
SWEDISH_DECISION_TEXT = (
    "Svenska kyrkans överklagandenämnd\n"
    "Meddelat 2023-01-15\n"
    "Kyrkogårdsförvaltning\n"
    "Överklagandenämndens beslut:\n"
    "Nämnden bifaller överklagandet och upphäver det överklagade beslutet.\n"
    "Sökord: kyrkogård\n"
    "Ärendenummer: ÖN 2023-0042\n"
    "Beslut: 7/2023\n"
)


@pytest.fixture
def next_topic() -> str:
    return "extract"


@pytest.fixture
async def test_document(session: AsyncSession, document_repo):
    doc = await document_repo.create(
        session, DocumentCreate(source_url="https://example.com/decision.pdf")
    )
    await document_repo.update(
        session, doc.id, DocumentUpdate(raw_text=SWEDISH_DECISION_TEXT)
    )
    await session.commit()
    return await document_repo.get_by_id(session, doc.id)


@pytest.fixture
async def metadata_task(session: AsyncSession, task_repo, test_document):
    created = await task_repo.create(
        session,
        TaskCreate(document_id=test_document.id, step="metadata", status="pending"),
    )
    await session.commit()
    return created
