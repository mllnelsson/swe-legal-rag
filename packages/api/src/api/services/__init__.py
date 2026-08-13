from api.services.chat_toolset import ApiChatToolset, build_chat_toolset
from api.services.concept_service import list_concepts, list_documents_for_concept
from api.services.document_service import (
    DocumentChunk,
    DocumentDetail,
    DocumentSections,
    DocumentSummary,
    UnresolvedCitation,
    get_document_chunks,
    get_document_detail,
    get_document_pdf,
    list_documents,
)
from api.services.search_service import (
    SearchChunk,
    SearchDiagnostics,
    SearchHit,
    SearchQuery,
    SearchResponse,
    get_filters,
    search_documents,
)
from api.services.session_service import (
    append_turn,
    get_or_create_session,
    history_for_llm,
)

__all__ = [
    "append_turn",
    # The conversational agent's view of the deterministic tool set. The agent
    # itself lives in `agents`; this is the `api` side of that seam.
    "ApiChatToolset",
    "build_chat_toolset",
    "DocumentChunk",
    "DocumentDetail",
    "DocumentSections",
    "DocumentSummary",
    "get_document_chunks",
    "get_document_detail",
    "get_document_pdf",
    "get_filters",
    "get_or_create_session",
    "history_for_llm",
    "list_concepts",
    "list_documents",
    "list_documents_for_concept",
    "SearchChunk",
    "SearchDiagnostics",
    "SearchHit",
    "SearchQuery",
    "SearchResponse",
    "search_documents",
    "UnresolvedCitation",
]
