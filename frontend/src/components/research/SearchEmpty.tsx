import { Icon } from "../display/Icon";
import type { SearchDiagnostics } from "../../api/types";

export type SearchEmptyProps = {
  diagnostics: SearchDiagnostics;
  /** Human-readable descriptions of the filters currently applied. */
  activeFilters: string[];
  onClearFilters: () => void;
};

/** Two different nothings, told apart.
 *
 *  `/api/search` narrows by filter first and stops if that leaves no candidates —
 *  it does not silently widen, unlike the chat retriever. So an empty result means
 *  one of two quite different things, and `candidate_document_count === 0`
 *  distinguishes them:
 *
 *    the filters excluded every decision   → loosen the filters
 *    the filters were fine, the text missed → change the words
 *
 *  Collapsing these into one "no results" message would send the user to fix the
 *  wrong end of their query. */
export function SearchEmpty({ diagnostics, activeFilters, onClearFilters }: SearchEmptyProps) {
  const filtersExcludedEverything = diagnostics.candidate_document_count === 0;

  return (
    <section
      style={{
        display: "flex",
        flexDirection: "column",
        gap: "var(--space-4)",
        padding: "var(--space-9) var(--space-7)",
        textAlign: "center",
        alignItems: "center",
        fontFamily: "var(--font-sans)",
        color: "var(--text-body)",
      }}
    >
      <Icon name="search" size={20} color="var(--text-faint)" />

      <h2
        style={{
          margin: 0,
          fontFamily: "var(--font-display)",
          fontSize: "var(--text-h3-size)",
          color: "var(--text-strong)",
        }}
      >
        {filtersExcludedEverything ? "Filtren matchar inga beslut" : "Inga stycken matchar frågan"}
      </h2>

      <p style={{ margin: 0, fontSize: "var(--text-body-size)", maxWidth: "var(--measure-narrow)" }}>
        {filtersExcludedEverything
          ? "Ingen sökning kördes — urvalet var tomt redan innan frågan ställdes."
          : "Sökningen kördes mot hela urvalet men hittade ingen text som liknar frågan."}
      </p>

      {filtersExcludedEverything && activeFilters.length > 0 && (
        <>
          <ul
            style={{
              margin: 0,
              padding: 0,
              listStyle: "none",
              display: "flex",
              flexWrap: "wrap",
              gap: "var(--space-3)",
              justifyContent: "center",
              fontSize: "var(--text-small-size)",
              color: "var(--text-muted)",
            }}
          >
            {activeFilters.map((filter) => (
              <li key={filter}>{filter}</li>
            ))}
          </ul>
          <button
            type="button"
            onClick={onClearFilters}
            style={{
              border: "none",
              background: "transparent",
              padding: 0,
              font: "inherit",
              fontSize: "var(--text-small-size)",
              color: "var(--text-link)",
              cursor: "pointer",
              textDecoration: "underline",
            }}
          >
            Rensa filtren
          </button>
        </>
      )}
    </section>
  );
}
