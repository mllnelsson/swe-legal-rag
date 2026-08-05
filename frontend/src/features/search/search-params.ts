/* The search URL is the search state.
 *
 * Every filter lives in the query string so a search can be pasted into another
 * tab, bookmarked or sent to a colleague and reproduce the same view. That is what
 * the API's query-param filters are for; keeping this state in React would throw
 * it away.
 *
 * Param names are Swedish to match the interface. Pure functions only — parsing
 * and serialising, no routing and no fetching.
 */

import type { DocumentFilter, SearchQuery } from "../../api/types";

/** The API's own default page size (`search_default_limit`). */
export const PAGE_SIZE = 10;

export type SearchState = {
  query: string;
  /** Exact-match against the nämnd's declared Sökord vocabulary, lowercased. */
  keywords: string[];
  category: string | null;
  outcome: string | null;
  dateFrom: string | null;
  dateTo: string | null;
  /** Decisions that cite, or are cited by, this case. */
  referencesCaseNumber: string | null;
  page: number;
};

export const EMPTY_SEARCH: SearchState = {
  query: "",
  keywords: [],
  category: null,
  outcome: null,
  dateFrom: null,
  dateTo: null,
  referencesCaseNumber: null,
  page: 1,
};

const PARAM = {
  query: "q",
  keyword: "sokord",
  category: "kategori",
  outcome: "utfall",
  dateFrom: "fran",
  dateTo: "tom",
  references: "refs",
  page: "sida",
} as const;

function readPage(raw: string | null): number {
  if (raw === null) return 1;
  const parsed = Number.parseInt(raw, 10);
  return Number.isFinite(parsed) && parsed > 0 ? parsed : 1;
}

export function parseSearchState(params: URLSearchParams): SearchState {
  return {
    query: params.get(PARAM.query) ?? "",
    keywords: params.getAll(PARAM.keyword),
    category: params.get(PARAM.category),
    outcome: params.get(PARAM.outcome),
    dateFrom: params.get(PARAM.dateFrom),
    dateTo: params.get(PARAM.dateTo),
    referencesCaseNumber: params.get(PARAM.references),
    page: readPage(params.get(PARAM.page)),
  };
}

export function toSearchParams(state: SearchState): URLSearchParams {
  const params = new URLSearchParams();
  if (state.query !== "") params.set(PARAM.query, state.query);
  for (const keyword of state.keywords) params.append(PARAM.keyword, keyword);
  if (state.category !== null) params.set(PARAM.category, state.category);
  if (state.outcome !== null) params.set(PARAM.outcome, state.outcome);
  if (state.dateFrom !== null) params.set(PARAM.dateFrom, state.dateFrom);
  if (state.dateTo !== null) params.set(PARAM.dateTo, state.dateTo);
  if (state.referencesCaseNumber !== null) {
    params.set(PARAM.references, state.referencesCaseNumber);
  }
  if (state.page > 1) params.set(PARAM.page, String(state.page));
  return params;
}

function toDocumentFilter(state: SearchState): DocumentFilter {
  return {
    date_from: state.dateFrom,
    date_to: state.dateTo,
    category: state.category,
    decision_outcome: state.outcome,
    case_number: null,
    decision_number: null,
    entity_names: [],
    entity_types: [],
    keywords: state.keywords,
    references_case_number: state.referencesCaseNumber,
  };
}

export function toSearchQuery(state: SearchState): SearchQuery {
  return {
    query: state.query,
    queries: null,
    // Server-side expansion is the one search parameter that invokes an LLM role.
    // Leaving it off keeps the app runnable with no model credentials configured.
    expand: false,
    filter: toDocumentFilter(state),
    limit: PAGE_SIZE,
    offset: (state.page - 1) * PAGE_SIZE,
    include_appendices: false,
    chunks_per_document: null,
  };
}

export function countActiveFilters(state: SearchState): number {
  return (
    state.keywords.length +
    (state.category === null ? 0 : 1) +
    (state.outcome === null ? 0 : 1) +
    (state.dateFrom === null ? 0 : 1) +
    (state.dateTo === null ? 0 : 1) +
    (state.referencesCaseNumber === null ? 0 : 1)
  );
}

/** Readable descriptions of what is currently narrowing the search, for the empty
 *  state to list back when a filter combination excluded everything. */
export function describeFilters(state: SearchState): string[] {
  const described: string[] = [];
  for (const keyword of state.keywords) described.push(`Sökord: ${keyword}`);
  if (state.category !== null) described.push(`Kategori: ${state.category}`);
  if (state.outcome !== null) described.push(`Utfall: ${state.outcome}`);
  if (state.dateFrom !== null) described.push(`Från: ${state.dateFrom}`);
  if (state.dateTo !== null) described.push(`Till: ${state.dateTo}`);
  if (state.referencesCaseNumber !== null) {
    described.push(`Hänvisar till: ${state.referencesCaseNumber}`);
  }
  return described;
}

export function clearFilters(state: SearchState): SearchState {
  return { ...EMPTY_SEARCH, query: state.query };
}
