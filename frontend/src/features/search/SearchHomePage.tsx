import { useState } from "react";
import { useNavigate } from "react-router";

import { AskBox } from "../../components/research/AskBox";
import { Switch } from "../../components/forms/Switch";
import { useFacets } from "../../api/queries";
import { formatCount } from "../../lib/format";
import { EMPTY_SEARCH, toSearchParams } from "./search-params";
import { ASK_BOX_TRANSITION_NAME } from "../agent/ask-box-transition";

/** How many of the nämnd's own Sökord to offer as a starting point.
 *
 *  Three, on one line, not the eight the page used to stack under the box. They
 *  are a hint that the nämnd has a vocabulary of its own, not a browsing
 *  surface — `/sokord` is that. */
const SUGGESTED_KEYWORDS = 3;

/** The house metadata separator. */
const SEPARATOR = " · ";

/** The two things the box can do with a question, and they are not the same
 *  promise. Search returns the nämnd's own text, ranked; the agent researches
 *  and writes prose. Which one runs is the reader's choice, made before they
 *  type — not something inferred from the wording. */
type Mode = "search" | "agent";

const PLACEHOLDER: Record<Mode, string> = {
  search: "Sök i Överklagandenämndens beslut",
  agent: "Fråga om Överklagandenämndens beslut",
};

const SUBMIT_LABEL: Record<Mode, string> = { search: "Sök", agent: "Fråga" };

/* One line for each mode, in the same place, because the choice between them is
 * the only thing this page asks the reader to decide and the word "Agentläge"
 * does not settle it. It sits under the switch rather than under the box, so
 * turning the switch does not move the box. */
const MODE_NOTE: Record<Mode, string> = {
  search: "Visar nämndens egna ord, med utdrag ur de beslut som matchar.",
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

  /** The question travels in router state, not in the URL, so the agent page can
   *  start on arrival and a reload never re-asks.
   *
   *  `viewTransition` is what makes this read as the box moving rather than the
   *  page being replaced: the ask box here and the composer there share a
   *  `view-transition-name`, so the browser interpolates between them. Browsers
   *  without the API swap instantly, which is the behaviour this replaces. */
  function askAgent(text: string) {
    if (text.trim() === "") return;
    navigate("/agent", { state: { question: text }, viewTransition: true });
  }

  function searchKeyword(keyword: string) {
    navigate(
      `/sok?${toSearchParams({ ...EMPTY_SEARCH, query: keyword, keywords: [keyword] }).toString()}`,
    );
  }

  return (
    <main
      style={{
        minHeight: "100vh",
        background: "var(--gradient-wash-soft)",
        display: "flex",
        flexDirection: "column",
        alignItems: "center",
        // Centred on the box, not on the whole column: the caption line below it
        // is a footnote, and counting it into the centring would push the box
        // above the middle of the screen.
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
          alignItems: "center",
          gap: "var(--space-8)",
        }}
      >
        {/* The wordmark is the page's heading. There is nothing to say above the
            box that the box does not already ask. */}
        <h1
          style={{
            margin: 0,
            fontFamily: "var(--font-display)",
            fontSize: "var(--text-display-size)",
            lineHeight: "var(--text-display-lh)",
            letterSpacing: "var(--text-display-ls)",
            fontWeight: "var(--text-display-weight)",
            color: "var(--burgundy-600)",
          }}
        >
          Svk Beslutsök
        </h1>

        <div
          style={{
            width: "100%",
            display: "flex",
            flexDirection: "column",
            alignItems: "center",
            gap: "var(--space-5)",
          }}
        >
          <AskBox
            value={query}
            onChange={setQuery}
            onSubmit={submit}
            size="lg"
            autoFocus
            placeholder={PLACEHOLDER[mode]}
            submitLabel={SUBMIT_LABEL[mode]}
            style={{ width: "100%", viewTransitionName: ASK_BOX_TRANSITION_NAME }}
          />

          <Switch
            checked={mode === "agent"}
            onChange={(on) => setMode(on ? "agent" : "search")}
            label="Agentläge"
            hint={MODE_NOTE[mode]}
          />
        </div>

        {facets.data !== undefined && (
          <p
            style={{
              margin: 0,
              textAlign: "center",
              fontFamily: "var(--font-sans)",
              fontSize: "var(--text-caption-size)",
              lineHeight: "var(--text-caption-lh)",
              color: "var(--text-muted)",
            }}
          >
            {`${formatCount(facets.data.document_count)} beslut i samlingen`}
            {facets.data.keywords.slice(0, SUGGESTED_KEYWORDS).map((keyword) => (
              <span key={keyword.value}>
                {SEPARATOR}
                <button
                  type="button"
                  onClick={() => searchKeyword(keyword.value)}
                  style={keywordStyle}
                >
                  {keyword.value}
                </button>
              </span>
            ))}
          </p>
        )}
      </div>
    </main>
  );
}

const keywordStyle = {
  padding: 0,
  border: "none",
  background: "none",
  font: "inherit",
  color: "var(--text-link)",
  cursor: "pointer",
} as const;
