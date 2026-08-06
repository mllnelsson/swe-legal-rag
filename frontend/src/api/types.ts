/* Domain types, re-exported from the generated OpenAPI schema.
 *
 * Nothing in the app imports `schema.d.ts` directly: the generated shape is
 * `components["schemas"]["SearchHit"]`, which is noise at every call site. These
 * aliases are the whole indirection — they add no types of their own, so a
 * backend contract change still surfaces here as a TypeScript error.
 */

import type { components } from "./schema";

type Schemas = components["schemas"];

export type SearchQuery = Schemas["SearchQuery"];
export type SearchResponse = Schemas["SearchResponse"];
export type SearchHit = Schemas["SearchHit"];
export type SearchChunk = Schemas["SearchChunk"];
export type SearchDiagnostics = Schemas["SearchDiagnostics"];
export type DocumentFilter = Schemas["DocumentFilter"];

export type DocumentFacets = Schemas["DocumentFacets"];
export type FacetValue = Schemas["FacetValue"];

export type DocumentSummary = Schemas["DocumentSummary"];
export type DocumentDetail = Schemas["DocumentDetail"];
export type DocumentSections = Schemas["DocumentSections"];
export type DocumentChunk = Schemas["DocumentChunk"];
export type DocumentEntityDetail = Schemas["DocumentEntityDetail"];
export type ReferenceEdge = Schemas["ReferenceEdge"];
export type UnresolvedCitation = Schemas["UnresolvedCitation"];

export type EntityWithCount = Schemas["EntityWithCount"];
export type EntityDocumentRef = Schemas["EntityDocumentRef"];

export type ChunkSection = Schemas["ChunkSection"];
export type EntityType = Schemas["EntityType"];
export type EntityRelevance = Schemas["EntityRelevance"];

/** A page of results. The API returns this shape from every list endpoint. */
export type Page<T> = {
  items: T[];
  total: number;
  limit: number;
  offset: number;
};
