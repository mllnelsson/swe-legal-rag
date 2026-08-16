import { useEffect, useState } from "react";
import { useSearchParams } from "react-router";

import { AskBox } from "../../components/research/AskBox";
import { DecisionCard } from "../../components/research/DecisionCard";
import { SearchEmpty } from "../../components/research/SearchEmpty";
import { SearchSummary } from "../../components/research/SearchSummary";
import { Tag } from "../../components/display/Tag";
import { FacetRail } from "./FacetRail";
import { useSearch } from "../../api/queries";
import {
  clearFilters,
  countActiveFilters,
  describeFilters,
  parseSearchState,
  toSearchParams,
  toSearchQuery,
  type SearchState,
} from "./search-params";

/** Leaves room for the pinned AskBox so the last card is never behind it. */
const BOTTOM_GUTTER = "var(--space-13)";

export function ResultsPage() {
  const [searchParams, setSearchParams] = useSearchParams();

  const state = parseSearchState(searchParams);
  const search = useSearch(toSearchQuery(state));

  // The box holds a draft; the URL holds what was actually searched. Re-sync when
  // navigation changes the query out from under it (back button, a keyword chip).
  const [draft, setDraft] = useState(state.query);
  useEffect(() => setDraft(state.query), [state.query]);

  function apply(next: SearchState) {
    setSearchParams(toSearchParams(next));
  }

  const activeFilters = describeFilters(state);
  const filterCount = countActiveFilters(state);
  // The page size is whatever the API echoed back, never what the client asked
  // for: `/api/search` clamps an out-of-range `limit` silently (`clamp_limit`,
  // bounded by `search_max_limit`), so dividing by `PAGE_SIZE` would promise
  // pages the response cannot fill. `limit` is always at least 1.
  const maxPage =
    search.data === undefined ? 1 : Math.ceil(search.data.total / search.data.limit);

  return (
    <main
      className="layout-columns"
      style={{
        maxWidth: "var(--content-max)",
        margin: "0 auto",
        padding: `var(--space-8) var(--gutter-page) ${BOTTOM_GUTTER}`,
        fontFamily: "var(--font-sans)",
      }}
    >
      <FacetRail state={state} onChange={apply} />

      <div
        className="layout-main"
        style={{
          display: "flex",
          flexDirection: "column",
          gap: "var(--space-6)",
        }}
      >
      {search.isPending && (
        <p style={{ margin: 0, color: "var(--text-muted)" }}>Söker…</p>
      )}

      {search.isError && (
        <p style={{ margin: 0, color: "var(--status-error-fg)" }}>
          Sökningen kunde inte köras. Kontrollera att tjänsten är igång.
        </p>
      )}

      {search.data !== undefined && (
        <>
          <SearchSummary
            effectiveQueries={search.data.effective_queries}
            total={search.data.total}
            diagnostics={search.data.diagnostics}
            expandRequested={state.expand}
          />

          {activeFilters.length > 0 && (
            <div style={{ display: "flex", flexWrap: "wrap", gap: "var(--space-3)" }}>
              {state.keywords.map((keyword) => (
                <Tag
                  key={keyword}
                  selected
                  onRemove={() =>
                    apply({
                      ...state,
                      page: 1,
                      keywords: state.keywords.filter((each) => each !== keyword),
                    })
                  }
                >
                  {keyword}
                </Tag>
              ))}
              {state.category !== null && (
                <Tag selected onRemove={() => apply({ ...state, category: null, page: 1 })}>
                  {state.category}
                </Tag>
              )}
              {state.referencesCaseNumber !== null && (
                <Tag
                  selected
                  onRemove={() => apply({ ...state, referencesCaseNumber: null, page: 1 })}
                >
                  {`Hänvisar till ${state.referencesCaseNumber}`}
                </Tag>
              )}
            </div>
          )}

          {search.data.items.length === 0 ? (
            <SearchEmpty
              diagnostics={search.data.diagnostics}
              activeFilters={activeFilters}
              onClearFilters={() => apply(clearFilters(state))}
            />
          ) : (
            <div style={{ display: "flex", flexDirection: "column", gap: "var(--space-4)" }}>
              {search.data.items.map((hit) => (
                <DecisionCard
                  key={hit.document_id}
                  hit={hit}
                  to={`/beslut/${hit.document_id}`}
                />
              ))}
            </div>
          )}

          {maxPage > 1 && (
            <nav
              aria-label="Sidnavigering"
              style={{ display: "flex", alignItems: "center", gap: "var(--space-4)" }}
            >
              <button
                type="button"
                disabled={state.page <= 1}
                onClick={() => apply({ ...state, page: state.page - 1 })}
                style={pagerStyle(state.page <= 1)}
              >
                Föregående
              </button>
              <span style={{ fontSize: "var(--text-small-size)", color: "var(--text-muted)" }}>
                {`Sida ${state.page} av ${maxPage}`}
              </span>
              <button
                type="button"
                disabled={state.page >= maxPage}
                onClick={() => apply({ ...state, page: state.page + 1 })}
                style={pagerStyle(state.page >= maxPage)}
              >
                Nästa
              </button>
            </nav>
          )}
        </>
      )}
      </div>

      {/* The stupid box. It takes text and runs a search — nothing else. */}
      <div
        style={{
          position: "fixed",
          bottom: 0,
          left: 0,
          right: 0,
          background: "var(--gradient-fade-page)",
          pointerEvents: "none",
        }}
      >
        {/* Mirrors the page grid so the box sits over the results column rather
            than straddling the filter rail. */}
        <div
          className="layout-columns"
          style={{
            maxWidth: "var(--content-max)",
            margin: "0 auto",
            padding: "var(--space-8) var(--gutter-page) var(--space-6)",
          }}
        >
          <div className="layout-rail-spacer" aria-hidden />
          <div className="layout-main" style={{ pointerEvents: "auto" }}>
            <AskBox
              value={draft}
              onChange={setDraft}
              onSubmit={(text) => apply({ ...state, query: text, page: 1 })}
              scope={filterCount === 0 ? undefined : `${filterCount} filter`}
            />
          </div>
        </div>
      </div>
    </main>
  );
}

function pagerStyle(disabled: boolean) {
  return {
    height: "var(--control-h-sm)",
    padding: "0 var(--space-5)",
    borderRadius: "var(--radius-sm)",
    border: "1px solid var(--border-default)",
    background: "var(--surface-card)",
    color: disabled ? "var(--text-faint)" : "var(--text-strong)",
    font: "inherit",
    fontSize: "var(--text-small-size)",
    cursor: disabled ? "not-allowed" : "pointer",
  } as const;
}
