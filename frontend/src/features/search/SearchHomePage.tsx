import { useState } from "react";
import { useNavigate } from "react-router";

import { AskBox } from "../../components/research/AskBox";
import { Tabs } from "../../components/navigation/Tabs";
import { Tag } from "../../components/display/Tag";
import { useFacets } from "../../api/queries";
import { formatCount } from "../../lib/format";
import { EMPTY_SEARCH, toSearchParams } from "./search-params";

/** How many of the nämnd's own Sökord to offer as a starting point. */
const SUGGESTED_KEYWORDS = 8;

/** The two things the box can do with a question, and they are not the same
 *  promise. Search returns the nämnd's own text, ranked; the agent researches
 *  and writes prose. Which one runs is the reader's choice, made before they
 *  type — not something inferred from the wording. */
type Mode = "search" | "agent";

const MODES = [
  { value: "search", label: "Sök" },
  { value: "agent", label: "Agent" },
];

const PLACEHOLDER: Record<Mode, string> = {
  search: "Sök i Överklagandenämndens beslut",
  agent: "Fråga om Överklagandenämndens beslut",
};

const SUBMIT_LABEL: Record<Mode, string> = { search: "Sök", agent: "Fråga" };

/* One line for each mode, in the same place, because the choice between them is
 * the only thing this page asks the reader to decide and the words "Sök" and
 * "Agent" do not settle it. A note on the agent alone left search unexplained —
 * and moved the box every time the mode changed. */
const MODE_NOTE: Record<Mode, string> = {
  search:
    "Söker i besluten och visar nämndens egna ord, med utdrag ur de beslut som matchar.",
  agent:
    "Agenten söker, läser och skriver ett svar med hänvisningar. Det tar upp till en minut.",
};

export function SearchHomePage() {
  const navigate = useNavigate();
  const [query, setQuery] = useState("");
  const [mode, setMode] = useState<Mode>("search");
  const facets = useFacets();

  function submit(text: string) {
    if (mode === "agent") return askAgent(text);
    return runSearch(text);
  }

  function runSearch(text: string) {
    if (text.trim() === "") return;
    navigate(`/sok?${toSearchParams({ ...EMPTY_SEARCH, query: text }).toString()}`);
  }

  /** The question travels in the URL so the agent page can start on arrival; it
   *  drops the param immediately, so a reload never re-asks. */
  function askAgent(text: string) {
    if (text.trim() === "") return;
    navigate(`/agent?${new URLSearchParams({ q: text }).toString()}`);
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

        <div style={{ display: "flex", flexDirection: "column", gap: "var(--space-4)" }}>
          <Tabs
            tabs={MODES}
            value={mode}
            onChange={(value) => setMode(value as Mode)}
            variant="pill"
            label="Sökläge"
            style={{ alignSelf: "flex-start" }}
          />

          <AskBox
            value={query}
            onChange={setQuery}
            onSubmit={submit}
            size="lg"
            autoFocus
            placeholder={PLACEHOLDER[mode]}
            submitLabel={SUBMIT_LABEL[mode]}
          />

          <p
            style={{
              margin: 0,
              fontFamily: "var(--font-sans)",
              fontSize: "var(--text-small-size)",
              color: "var(--text-muted)",
            }}
          >
            {MODE_NOTE[mode]}
          </p>
        </div>

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
