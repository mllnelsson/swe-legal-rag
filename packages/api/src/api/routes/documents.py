import uuid
from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response
from sqlalchemy.ext.asyncio import AsyncSession

from api.access_log import note
from api.config import SearchSettings, get_search_settings
from api.dependencies import get_db
from api.pagination import Page, clamp_limit
from api.services.document_service import (
    DocumentChunk,
    DocumentDetail,
    DocumentSummary,
    get_document_chunks,
    get_document_detail,
    get_document_pdf,
    list_documents,
)
from shared.dtos.search import DocumentFilter
from shared.search import is_empty_filter
from shared.enums import ChunkSection

router = APIRouter()

PDF_MEDIA_TYPE = "application/pdf"


@router.get("/api/documents")
async def list_documents_endpoint(
    request: Request,
    date_from: date | None = None,
    date_to: date | None = None,
    category: str | None = None,
    decision_outcome: str | None = None,
    case_number: str | None = None,
    decision_number: str | None = None,
    entity_name: list[str] = Query(default=[]),
    entity_type: list[str] = Query(default=[]),
    keyword: list[str] = Query(default=[]),
    references_case_number: str | None = None,
    newest_first: bool = True,
    limit: int | None = Query(default=None, ge=1),
    offset: int = Query(default=0, ge=0),
    db: AsyncSession = Depends(get_db),
    settings: SearchSettings = Depends(get_search_settings),
) -> Page[DocumentSummary]:
    """Browse decisions by metadata alone, with no query text.

    Filters are spelled out as query parameters rather than taking a nested
    object, so a plain link can express a filtered view.
    """
    document_filter = DocumentFilter(
        date_from=date_from,
        date_to=date_to,
        category=category,
        decision_outcome=decision_outcome,
        case_number=case_number,
        decision_number=decision_number,
        entity_names=entity_name,
        entity_types=entity_type,
        keywords=keyword,
        references_case_number=references_case_number,
    )
    page = await list_documents(
        db,
        document_filter,
        limit=clamp_limit(
            limit,
            default=settings.search_default_limit,
            maximum=settings.search_max_limit,
        ),
        offset=offset,
        newest_first=newest_first,
    )
    note(
        request,
        count=len(page.items),
        total=page.total,
        limit=page.limit,
        offset=page.offset,
        filtered=not is_empty_filter(document_filter),
    )
    return page


@router.get("/api/documents/{document_id}")
async def document_detail_endpoint(
    document_id: uuid.UUID,
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> DocumentDetail:
    """One decision with its concepts, regulations and citations.

    Every id in the response is a valid traversal target for another endpoint.
    """
    detail = await get_document_detail(db, document_id)
    note(request, doc=document_id, found=detail is not None)
    if detail is None:
        raise HTTPException(status_code=404, detail="Document not found")
    return detail


@router.get("/api/documents/{document_id}/chunks")
async def document_chunks_endpoint(
    document_id: uuid.UUID,
    request: Request,
    section: ChunkSection | None = None,
    db: AsyncSession = Depends(get_db),
) -> list[DocumentChunk]:
    """The decision's text in reading order, chunk by chunk."""
    chunks = await get_document_chunks(db, document_id, section=section)
    note(
        request,
        doc=document_id,
        chunks=len(chunks) if chunks is not None else 0,
        section=section or "all",
    )
    if chunks is None:
        raise HTTPException(status_code=404, detail="Document not found")
    return chunks


@router.get("/api/documents/{document_id}/pdf")
async def document_pdf_endpoint(
    document_id: uuid.UUID,
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> Response:
    """The original PDF, inline so a browser renders it in place."""
    pdf_bytes = await get_document_pdf(db, document_id, request.app.state.storage)
    note(request, doc=document_id, bytes=len(pdf_bytes) if pdf_bytes else 0)
    if pdf_bytes is None:
        raise HTTPException(status_code=404, detail="PDF not found")
    return Response(
        content=pdf_bytes,
        media_type=PDF_MEDIA_TYPE,
        headers={
            "Content-Disposition": f'inline; filename="{document_id}.pdf"',
        },
    )
