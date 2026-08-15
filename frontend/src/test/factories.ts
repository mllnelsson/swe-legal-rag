/* Test data, typed off the generated schema.
 *
 * These are not fixtures standing in for the API — the app talks to the live API.
 * They exist so component tests can pin one field at a time. Because the types come
 * from `schema.d.ts`, a backend contract change breaks these at compile time rather
 * than letting tests pass against a shape the API no longer returns.
 *
 * Values mirror the real corpus, including the case where the ärendenummer year and
 * the beslutsnummer year disagree (2025-0035 decided as 14/2026).
 */

import type { SourceReference, SqlEvent } from "../api/chat-events";
import type { SearchChunk, SearchDiagnostics, SearchHit } from "../api/types";

export function makeChunk(overrides: Partial<SearchChunk> = {}): SearchChunk {
  return {
    chunk_id: "11111111-1111-1111-1111-111111111111",
    chunk_index: 0,
    text: "Överklagandenämnden avslår överklagandet.",
    section: "body",
    appendix_label: null,
    score: 0.01639,
    vector_rank: 1,
    text_rank: null,
    vector_similarity: 0.8584,
    text_score: null,
    ...overrides,
  };
}

export function makeHit(overrides: Partial<SearchHit> = {}): SearchHit {
  return {
    document_id: "22222222-2222-2222-2222-222222222222",
    case_number: "2025-0035",
    decision_number: "14/2026",
    decision_date: "2026-03-16",
    category: "Obehörighet att utöva kyrkans vigningstjänst",
    decision_outcome: "Överklagandenämnden upphäver domkapitlets beslut.",
    headline: "Obehörighet att utöva kyrkans vigningstjänst",
    summary: "Nämnden upphävde domkapitlets beslut om prövotid för kyrkoherden.",
    source_url: "https://www.svenskakyrkan.se/default.aspx?id=3081221&ptid=",
    score: 0.01639,
    matched_chunk_count: 2,
    chunks: [makeChunk()],
    ...overrides,
  };
}

/* The chat stream's frames are hand-typed rather than generated — the endpoint
 * streams, so its events are absent from the OpenAPI document. See
 * `api/chat-events.ts`. */

export function makeSource(overrides: Partial<SourceReference> = {}): SourceReference {
  return {
    document_id: "22222222-2222-2222-2222-222222222222",
    case_number: "2025-0035",
    decision_date: "2026-03-16",
    decision_outcome: "Överklagandenämnden upphäver domkapitlets beslut.",
    category: "Obehörighet att utöva kyrkans vigningstjänst",
    excerpt: "Överklagandenämnden avslår överklagandet.",
    section: "body",
    appendix_label: null,
    pdf_url: "/api/documents/22222222-2222-2222-2222-222222222222/pdf",
    ...overrides,
  };
}

export function makeSqlEvent(overrides: Partial<SqlEvent> = {}): SqlEvent {
  return {
    kind: "sql",
    answered: true,
    sql: "SELECT count(*) FROM documents WHERE decision_outcome ILIKE '%avslag%'",
    columns: ["antal"],
    rows: [[12]],
    row_count: 1,
    truncated: false,
    assumptions: [],
    attempts: [],
    ...overrides,
  };
}

export function makeDiagnostics(overrides: Partial<SearchDiagnostics> = {}): SearchDiagnostics {
  return {
    filter_applied: false,
    candidate_document_count: null,
    vector_hit_count: 50,
    text_hit_counts: { "jäv i kyrkoråd": 3 },
    fused_chunk_count: 50,
    expanded: false,
    widened_to_appendices: false,
    vector_similarity_floor: 0.78,
    top_vector_similarity: 0.8584,
    ...overrides,
  };
}
