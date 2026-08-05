import { useState } from "react";
import { useNavigate } from "react-router";

import { AskBox } from "../../components/research/AskBox";
import { Tag } from "../../components/display/Tag";
import { useFacets } from "../../api/queries";
import { formatCount } from "../../lib/format";
import { EMPTY_SEARCH, toSearchParams } from "./search-params";

/** How many of the nämnd's own Sökord to offer as a starting point. */
const SUGGESTED_KEYWORDS = 8;

export function SearchHomePage() {
  const navigate = useNavigate();
  const [query, setQuery] = useState("");
  const facets = useFacets();

  function runSearch(text: string) {
    if (text.trim() === "") return;
    navigate(`/sok?${toSearchParams({ ...EMPTY_SEARCH, query: text }).toString()}`);
  }

  function searchKeyword(keyword: string) {
    navigate(
      `/sok?${toSearchParams({ ...EMPTY_SEARCH, query: keyword, keywords: [keyword] }).toString()}`,
    );
  }

  return (
    <main
      style={{
        minHeight: "calc(100vh - var(--section-gap))",
        background: "var(--gradient-wash)",
        display: "flex",
        justifyContent: "center",
        padding: "var(--space-12) var(--gutter-page)",
      }}
    >
      <div
        style={{
          width: "100%",
          maxWidth: "var(--measure-prose)",
          display: "flex",
          flexDirection: "column",
          gap: "var(--space-8)",
        }}
      >
        <h1
          style={{
            fontFamily: "var(--font-display)",
            fontSize: "var(--text-display-size)",
            lineHeight: "var(--text-display-lh)",
            letterSpacing: "var(--text-display-ls)",
            fontWeight: "var(--text-display-weight)",
            color: "var(--text-strong)",
            margin: 0,
          }}
        >
          Vad vill du veta?
        </h1>

        <AskBox
          value={query}
          onChange={setQuery}
          onSubmit={runSearch}
          size="lg"
          autoFocus
          placeholder="Sök i Överklagandenämndens beslut"
        />

        {facets.data !== undefined && (
          <div style={{ display: "flex", flexDirection: "column", gap: "var(--space-5)" }}>
            <p
              style={{
                margin: 0,
                fontSize: "var(--text-small-size)",
                color: "var(--text-muted)",
                fontFamily: "var(--font-sans)",
              }}
            >
              {formatCount(facets.data.document_count)} beslut i samlingen
            </p>

            <div style={{ display: "flex", flexDirection: "column", gap: "var(--space-3)" }}>
              <span
                style={{
                  fontSize: "var(--text-overline-size)",
                  letterSpacing: "var(--text-overline-ls)",
                  textTransform: "uppercase",
                  fontWeight: "var(--text-overline-weight)",
                  color: "var(--text-faint)",
                  fontFamily: "var(--font-sans)",
                }}
              >
                Nämndens egna sökord
              </span>
              <div style={{ display: "flex", flexWrap: "wrap", gap: "var(--space-3)" }}>
                {facets.data.keywords.slice(0, SUGGESTED_KEYWORDS).map((keyword) => (
                  <Tag key={keyword.value} onClick={() => searchKeyword(keyword.value)}>
                    {keyword.value}
                  </Tag>
                ))}
              </div>
            </div>
          </div>
        )}
      </div>
    </main>
  );
}
