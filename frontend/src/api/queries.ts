/* TanStack Query bindings for the retrieval API.
 *
 * Caching policy worth stating once: the corpus only changes when the ingestion
 * pipeline runs, never in response to anything a user does here. Nothing in this
 * app writes. So everything is effectively immutable for the length of a session
 * and refetching on window focus is pure noise.
 */

import { useQuery, type UseQueryResult } from "@tanstack/react-query";

import {
  fetchConceptDocuments,
  fetchConcepts,
  fetchDocument,
  fetchDocumentChunks,
  fetchDocuments,
  fetchFacets,
  fetchKeywordDocuments,
  fetchKeywords,
  searchDocuments,
  type DocumentListParams,
} from "./client";
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
} from "./types";

export const queryKeys = {
  search: (query: SearchQuery) => ["search", query] as const,
  facets: () => ["facets"] as const,
  documents: (params: DocumentListParams) => ["documents", params] as const,
  document: (documentId: string) => ["document", documentId] as const,
  documentChunks: (documentId: string, section?: string) =>
    ["document", documentId, "chunks", section ?? "all"] as const,
  concepts: (params: object) => ["concepts", params] as const,
  conceptDocuments: (entityId: string, params: object) =>
    ["concepts", entityId, "documents", params] as const,
  keywords: (params: object) => ["keywords", params] as const,
  keywordDocuments: (keywordId: string, params: object) =>
    ["keywords", keywordId, "documents", params] as const,
};

/** A search runs a local embedding server-side, so it is slow enough to be worth
 *  never re-running unprompted. `enabled` keeps an empty box from firing one. */
export function useSearch(query: SearchQuery | null): UseQueryResult<SearchResponse> {
  return useQuery({
    queryKey: queryKeys.search(query ?? ({ query: "" } as SearchQuery)),
    queryFn: () => searchDocuments(query as SearchQuery),
    enabled: query !== null && query.query.trim() !== "",
    staleTime: Infinity,
  });
}

export function useFacets(): UseQueryResult<DocumentFacets> {
  return useQuery({ queryKey: queryKeys.facets(), queryFn: fetchFacets, staleTime: Infinity });
}

export function useDocuments(
  params: DocumentListParams,
  enabled = true,
): UseQueryResult<Page<DocumentSummary>> {
  return useQuery({
    queryKey: queryKeys.documents(params),
    queryFn: () => fetchDocuments(params),
    enabled,
    staleTime: Infinity,
  });
}

export function useDocument(documentId: string | undefined): UseQueryResult<DocumentDetail> {
  return useQuery({
    queryKey: queryKeys.document(documentId ?? ""),
    queryFn: () => fetchDocument(documentId as string),
    enabled: documentId !== undefined,
    staleTime: Infinity,
  });
}

export function useDocumentChunks(
  documentId: string | undefined,
  section?: "body" | "appendix",
): UseQueryResult<DocumentChunk[]> {
  return useQuery({
    queryKey: queryKeys.documentChunks(documentId ?? "", section),
    queryFn: () => fetchDocumentChunks(documentId as string, section),
    enabled: documentId !== undefined,
    staleTime: Infinity,
  });
}

export function useConcepts(params: {
  entity_type?: EntityType;
  q?: string;
  limit?: number;
  offset?: number;
}): UseQueryResult<Page<EntityWithCount>> {
  return useQuery({
    queryKey: queryKeys.concepts(params),
    queryFn: () => fetchConcepts(params),
    staleTime: Infinity,
  });
}

export function useConceptDocuments(
  entityId: string | undefined,
  params: { relevance?: "primary" | "mentioned"; limit?: number; offset?: number } = {},
): UseQueryResult<Page<EntityDocumentRef>> {
  return useQuery({
    queryKey: queryKeys.conceptDocuments(entityId ?? "", params),
    queryFn: () => fetchConceptDocuments(entityId as string, params),
    enabled: entityId !== undefined,
    staleTime: Infinity,
  });
}

export function useKeywords(
  params: { q?: string; limit?: number; offset?: number } = {},
): UseQueryResult<Page<EntityWithCount>> {
  return useQuery({
    queryKey: queryKeys.keywords(params),
    queryFn: () => fetchKeywords(params),
    staleTime: Infinity,
  });
}

export function useKeywordDocuments(
  keywordId: string | undefined,
  params: { limit?: number; offset?: number } = {},
): UseQueryResult<Page<EntityDocumentRef>> {
  return useQuery({
    queryKey: queryKeys.keywordDocuments(keywordId ?? "", params),
    queryFn: () => fetchKeywordDocuments(keywordId as string, params),
    enabled: keywordId !== undefined,
    staleTime: Infinity,
  });
}
