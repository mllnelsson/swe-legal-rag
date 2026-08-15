/* Typed wrappers over the retrieval API.
 *
 * Every call goes to a same-origin relative URL, proxied to the API in dev. That
 * keeps `/api/documents/{id}/pdf` usable directly as an iframe src, which is the
 * whole reason the backend proxies the PDF rather than handing out storage URLs.
 *
 * These functions do one thing: build a request and return a parsed body. They do
 * not cache, retry or report — that is the query layer's job.
 */

import type {
  DocumentChunk,
  DocumentDetail,
  DocumentFacets,
  DocumentSummary,
  EntityDocumentRef,
  EntityType,
  EntityWithCount,
  Page,
  SearchQuery,
  SearchResponse,
  SessionSummary,
  SessionTranscript,
} from "./types";

/** A failed API call. `status` is 0 when the request never reached the server. */
export class ApiError extends Error {
  readonly status: number;

  constructor(status: number, message: string, options?: ErrorOptions) {
    super(message, options);
    this.name = "ApiError";
    this.status = status;
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let response: Response;
  try {
    response = await fetch(path, init);
  } catch (cause) {
    // fetch only rejects when the request never completed: the API is down, DNS
    // failed, the user went offline. Worth distinguishing from a 500.
    throw new ApiError(0, "Kunde inte nå tjänsten", { cause });
  }

  if (!response.ok) {
    throw new ApiError(response.status, `${response.status} ${response.statusText}`);
  }

  return (await response.json()) as T;
}

/** For a response with no body to parse. `request` always reads JSON, and a 204
 *  has none — reading it would throw on the one call that succeeded. */
async function requestNoContent(path: string, init?: RequestInit): Promise<void> {
  let response: Response;
  try {
    response = await fetch(path, init);
  } catch (cause) {
    throw new ApiError(0, "Kunde inte nå tjänsten", { cause });
  }

  if (!response.ok) {
    throw new ApiError(response.status, `${response.status} ${response.statusText}`);
  }
}

/** Drop empty values, and repeat a key per element for the list-valued filters. */
function buildQuery(params: Record<string, string | number | boolean | string[] | undefined>) {
  const search = new URLSearchParams();
  for (const [key, value] of Object.entries(params)) {
    if (value === undefined || value === "") continue;
    if (Array.isArray(value)) {
      for (const item of value) search.append(key, item);
    } else {
      search.set(key, String(value));
    }
  }
  const query = search.toString();
  return query === "" ? "" : `?${query}`;
}

export function searchDocuments(query: SearchQuery): Promise<SearchResponse> {
  return request<SearchResponse>("/api/search", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(query),
  });
}

/** The only source of the category and outcome vocabularies — they are free text
 *  lifted by regex, so a client cannot guess them and must be told. */
export function fetchFacets(): Promise<DocumentFacets> {
  return request<DocumentFacets>("/api/filters");
}

export type DocumentListParams = {
  date_from?: string;
  date_to?: string;
  category?: string;
  decision_outcome?: string;
  case_number?: string;
  decision_number?: string;
  entity_name?: string[];
  entity_type?: string[];
  keyword?: string[];
  references_case_number?: string;
  newest_first?: boolean;
  limit?: number;
  offset?: number;
};

export function fetchDocuments(params: DocumentListParams): Promise<Page<DocumentSummary>> {
  return request<Page<DocumentSummary>>(`/api/documents${buildQuery({ ...params })}`);
}

export function fetchDocument(documentId: string): Promise<DocumentDetail> {
  return request<DocumentDetail>(`/api/documents/${documentId}`);
}

/** Returns a bare array rather than a Page — the API does not paginate chunks. */
export function fetchDocumentChunks(
  documentId: string,
  section?: "body" | "appendix",
): Promise<DocumentChunk[]> {
  return request<DocumentChunk[]>(
    `/api/documents/${documentId}/chunks${buildQuery({ section })}`,
  );
}

/** Not fetched — handed to an iframe. The API proxies the bytes so one URL shape
 *  works for both local and bucket storage. */
export function documentPdfUrl(documentId: string): string {
  return `/api/documents/${documentId}/pdf`;
}

export function fetchConcepts(params: {
  entity_type?: EntityType;
  q?: string;
  limit?: number;
  offset?: number;
}): Promise<Page<EntityWithCount>> {
  return request<Page<EntityWithCount>>(`/api/concepts${buildQuery({ ...params })}`);
}

export function fetchConceptDocuments(
  entityId: string,
  params: { relevance?: "primary" | "mentioned"; limit?: number; offset?: number } = {},
): Promise<Page<EntityDocumentRef>> {
  return request<Page<EntityDocumentRef>>(
    `/api/concepts/${entityId}/documents${buildQuery({ ...params })}`,
  );
}

/** The nämnd's own Sökord vocabulary — the one classification the corpus vouches
 *  for, as opposed to the concepts inferred from prose. */
export function fetchKeywords(params: {
  q?: string;
  limit?: number;
  offset?: number;
}): Promise<Page<EntityWithCount>> {
  return request<Page<EntityWithCount>>(`/api/keywords${buildQuery({ ...params })}`);
}

export function fetchKeywordDocuments(
  keywordId: string,
  params: { limit?: number; offset?: number } = {},
): Promise<Page<EntityDocumentRef>> {
  return request<Page<EntityDocumentRef>>(
    `/api/keywords/${keywordId}/documents${buildQuery({ ...params })}`,
  );
}

/* Past conversations. The only mutable data this app reads, and the only thing
 * it deletes — everything above is corpus the ingestion pipeline owns. */

/** Titles and sizes, never transcripts: the list endpoint projects in SQL so
 *  drawing a rail does not pull every answer ever written. */
export function fetchSessions(
  params: { limit?: number; offset?: number } = {},
): Promise<Page<SessionSummary>> {
  return request<Page<SessionSummary>>(`/api/sessions${buildQuery({ ...params })}`);
}

/** One conversation's turns. Carries no sources — the API stores the question
 *  and the answer only, which the UI has to state rather than imply. */
export function fetchSessionTranscript(sessionId: string): Promise<SessionTranscript> {
  return request<SessionTranscript>(`/api/sessions/${sessionId}`);
}

export function deleteSession(sessionId: string): Promise<void> {
  return requestNoContent(`/api/sessions/${sessionId}`, { method: "DELETE" });
}
