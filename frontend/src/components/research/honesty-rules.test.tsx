/* One test per honesty rule.
 *
 * These are the claims the interface makes about the corpus, and they are the part
 * of this app that is genuinely domain-specific rather than generic search UI. Each
 * rule exists because getting it wrong would put something on screen that the data
 * does not support.
 */

import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, within } from "@testing-library/react";
import type { ReactElement } from "react";
import { MemoryRouter } from "react-router";
import { afterEach, describe, expect, test, vi } from "vitest";

import { DecisionCard } from "./DecisionCard";
import { MatchBadge } from "./MatchBadge";
import { SearchEmpty } from "./SearchEmpty";
import { SearchSummary } from "./SearchSummary";
import { SectionBadge } from "./SectionBadge";
import { CitationGraph } from "../../features/decision/CitationGraph";
import { FacetRail } from "../../features/search/FacetRail";
import { ResultsPage } from "../../features/search/ResultsPage";
import { EMPTY_SEARCH } from "../../features/search/search-params";
import type { DocumentFacets, SearchResponse } from "../../api/types";
import { makeChunk, makeDiagnostics, makeHit } from "../../test/factories";

/** A decision card's title is a router `Link`, which needs a router around it. */
function renderCard(card: ReactElement) {
  return render(<MemoryRouter>{card}</MemoryRouter>);
}

/* Rules 9 and 10 are about values the API chooses, so they cannot be checked on a
 * hand-built prop: they need the response the component actually read. These two
 * helpers put the query layer and a stubbed API under a render. */

function renderWithApi(ui: ReactElement, path = "/") {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter initialEntries={[path]}>{ui}</MemoryRouter>
    </QueryClientProvider>,
  );
}

const FACETS: DocumentFacets = {
  categories: [],
  decision_outcomes: [],
  entity_types: [],
  keywords: [],
  earliest_decision_date: "2024-11-13",
  latest_decision_date: "2026-06-09",
  document_count: 184,
};

function stubApi(search: Partial<SearchResponse> = {}, facets: DocumentFacets = FACETS) {
  const response: SearchResponse = {
    items: [makeHit()],
    total: 1,
    limit: 10,
    offset: 0,
    effective_queries: ["jäv"],
    diagnostics: makeDiagnostics(),
    ...search,
  };
  vi.stubGlobal(
    "fetch",
    vi.fn((input: string) =>
      Promise.resolve({
        ok: true,
        json: () => Promise.resolve(input === "/api/search" ? response : facets),
      } as Response),
    ),
  );
}

afterEach(() => vi.unstubAllGlobals());

describe("rule 1 — appendix text is not the nämnd's words", () => {
  test("body excerpts are attributed to the nämnd", () => {
    render(<SectionBadge section="body" />);
    expect(screen.getByText("Nämndens beslut")).toBeInTheDocument();
  });

  test("appendix excerpts are marked as the appealed decision", () => {
    render(<SectionBadge section="appendix" appendixLabel="Bilaga A" />);
    expect(screen.getByText(/Bilaga A/)).toBeInTheDocument();
    expect(screen.getByText(/överklagat beslut/)).toBeInTheDocument();
  });

  test("an appendix hit carries the marker on the card itself", () => {
    const hit = makeHit({
      chunks: [makeChunk({ section: "appendix", appendix_label: "Bilaga A" })],
    });
    renderCard(<DecisionCard hit={hit} to="/beslut/x" />);
    expect(screen.getByText(/överklagat beslut/)).toBeInTheDocument();
  });
});

describe("rule 2 — widening to appendices is announced", () => {
  test("no banner when the search stayed in the decisions", () => {
    render(
      <SearchSummary effectiveQueries={["jäv"]} total={3} diagnostics={makeDiagnostics()} />,
    );
    expect(screen.queryByText(/bilagor/i)).not.toBeInTheDocument();
  });

  test("banner explains the excerpts are from appealed decisions", () => {
    render(
      <SearchSummary
        effectiveQueries={["jäv"]}
        total={3}
        diagnostics={makeDiagnostics({ widened_to_appendices: true })}
      />,
    );
    expect(screen.getByText(/Inget matchade i besluten själva/)).toBeInTheDocument();
  });
});

describe("rule 3 — two different empty results are told apart", () => {
  test("a filter that excluded everything says so, and lists the filters", () => {
    render(
      <SearchEmpty
        diagnostics={makeDiagnostics({ filter_applied: true, candidate_document_count: 0 })}
        activeFilters={["Sökord: avvisning"]}
        onClearFilters={vi.fn()}
      />,
    );
    expect(screen.getByText("Filtren matchar inga beslut")).toBeInTheDocument();
    expect(screen.getByText("Sökord: avvisning")).toBeInTheDocument();
  });

  test("a query that matched nothing is a different message", () => {
    render(
      <SearchEmpty
        diagnostics={makeDiagnostics({ candidate_document_count: null })}
        activeFilters={[]}
        onClearFilters={vi.fn()}
      />,
    );
    expect(screen.getByText("Inga stycken matchar frågan")).toBeInTheDocument();
    expect(screen.queryByText("Filtren matchar inga beslut")).not.toBeInTheDocument();
  });
});

describe("rule 4 — the fusion score is never shown as a rating", () => {
  test("how the decision was found is said in words, with no rank number", () => {
    const { container } = render(<MatchBadge vectorRank={3} textRank={1} />);
    expect(screen.getByText("Innehåller dina ord")).toBeInTheDocument();
    expect(container.textContent).not.toMatch(/#|\d/);
  });

  test("a chunk the text arm never returned says so, rather than claiming the words", () => {
    render(<MatchBadge vectorRank={1} textRank={null} />);
    expect(screen.getByText("Träff på betydelse")).toBeInTheDocument();
    expect(screen.queryByText("Innehåller dina ord")).not.toBeInTheDocument();
  });

  test("the raw score never reaches the card", () => {
    const { container } = renderCard(<DecisionCard hit={makeHit({ score: 0.01639 })} to="/beslut/x" />);
    // Anchor first: a card that rendered nothing would satisfy the negatives below
    // without proving anything.
    expect(screen.getByText("2025-0035")).toBeInTheDocument();
    expect(container.textContent).not.toContain("0.016");
    expect(container.textContent).not.toContain("%");
  });
});

describe("rule 5 — the total is a candidate pool, not a corpus count", () => {
  test("the count is stated bare", () => {
    render(
      <SearchSummary effectiveQueries={["jäv"]} total={17} diagnostics={makeDiagnostics()} />,
    );
    expect(screen.getByText("17 träffar")).toBeInTheDocument();
  });

  test("a single hit is not pluralised", () => {
    render(<SearchSummary effectiveQueries={["jäv"]} total={1} diagnostics={makeDiagnostics()} />);
    expect(screen.getByText("1 träff")).toBeInTheDocument();
  });
});

describe("rule 7 — unresolved citations are text, never links", () => {
  test("a citation to a decision we do not hold is not clickable", () => {
    render(
      <CitationGraph
        referencesOut={[]}
        referencesIn={[]}
        unresolved={[{ target_case_number: "3/2001", reference_context: null }]}
        onOpen={vi.fn()}
      />,
    );
    expect(screen.getByText("3/2001")).toBeInTheDocument();
    expect(screen.getByText(/finns inte i samlingen/)).toBeInTheDocument();
    expect(screen.queryByRole("button")).not.toBeInTheDocument();
    expect(screen.queryByRole("link")).not.toBeInTheDocument();
  });

  test("a resolved citation is navigable", () => {
    const onOpen = vi.fn();
    render(
      <CitationGraph
        referencesOut={[
          {
            document_id: "33333333-3333-3333-3333-333333333333",
            case_number: "2026-0014",
            decision_number: "23/2026",
            decision_date: "2026-06-09",
            headline: "Avskrivning",
            reference_context: null,
          },
        ]}
        referencesIn={[]}
        unresolved={[]}
        onOpen={onOpen}
      />,
    );
    expect(screen.getByRole("button")).toBeInTheDocument();
  });
});

describe("rule 8 — the two identifier spaces are labelled, never conflated", () => {
  test("ärendenummer and beslutsnummer are both shown, each labelled", () => {
    // The live corpus contains exactly this: a case opened in 2025, decided in 2026.
    renderCard(
      <DecisionCard
        hit={makeHit({ case_number: "2025-0035", decision_number: "14/2026" })}
        to="/beslut/x"
      />,
    );
    expect(screen.getByText("Ärendenummer")).toBeInTheDocument();
    expect(screen.getByText("2025-0035")).toBeInTheDocument();
    expect(screen.getByText("Beslut")).toBeInTheDocument();
    expect(screen.getByText("14/2026")).toBeInTheDocument();
  });
});

describe("rule 9 — the page size is the one the API echoed, not the one asked for", () => {
  test("pagination divides the total by the response's limit", async () => {
    // `/api/search` clamps `limit` into `[1, search_max_limit]` and echoes what
    // it actually served. Here it served 5 where the client asked for
    // `PAGE_SIZE` (10): 12 hits is three pages of five, and only two if the
    // request is trusted over the response.
    stubApi({
      items: Array.from({ length: 5 }, (_, index) =>
        makeHit({ document_id: `2222222${index}-2222-2222-2222-222222222222` }),
      ),
      total: 12,
      limit: 5,
    });
    renderWithApi(<ResultsPage />, "/sok?q=j%C3%A4v");
    expect(await screen.findByText("Sida 1 av 3")).toBeInTheDocument();
  });

  test("no pager at all when one echoed page holds everything", async () => {
    // The clamp in the other direction: 40 hits served in one page of 50 is one
    // page. Counted against the request it would be four, three of them empty.
    stubApi({ total: 40, limit: 50 });
    renderWithApi(<ResultsPage />, "/sok?q=j%C3%A4v");
    expect(await screen.findByText("40 träffar")).toBeInTheDocument();
    expect(screen.queryByLabelText("Sidnavigering")).not.toBeInTheDocument();
  });
});

describe("rule 10 — category and outcome are free text, rendered exactly as returned", () => {
  test("near-duplicate categories stay two options, never merged", async () => {
    // Both of these are in the live corpus. They almost certainly mean the same
    // thing; nothing here is entitled to decide that they do.
    stubApi(
      {},
      {
        ...FACETS,
        categories: [
          { value: "Utlämnande av handling", count: 6 },
          { value: "Utlämnande av handlingar", count: 2 },
        ],
      },
    );
    renderWithApi(<FacetRail state={EMPTY_SEARCH} onChange={vi.fn()} />);

    const kategori = await screen.findByLabelText("Kategori");
    expect(
      within(kategori).getByRole("option", { name: "Utlämnande av handling (6)" }),
    ).toBeInTheDocument();
    expect(
      within(kategori).getByRole("option", { name: "Utlämnande av handlingar (2)" }),
    ).toBeInTheDocument();
  });

  test("a long holding is shortened for display and sent back byte-identical", async () => {
    // `decision_outcome` values are the holding itself, 41–378 characters in the
    // live corpus. Shortening the label is display truncation; the value the
    // filter sends must still be the string `/api/filters` published, or it
    // matches nothing.
    const holding =
      "Överklagandenämnden upphäver domkapitlets beslut och återförvisar ärendet " +
      "till domkapitlet för ny handläggning.";
    stubApi({}, { ...FACETS, decision_outcomes: [{ value: holding, count: 3 }] });
    renderWithApi(<FacetRail state={EMPTY_SEARCH} onChange={vi.fn()} />);

    const utfall = await screen.findByLabelText("Utfall");
    const option = within(utfall).getByRole("option", { name: /…/ }) as HTMLOptionElement;
    expect(option.value).toBe(holding);
    expect(option.textContent).not.toBe(holding);
  });
});

describe("summary is optional, and its absence is not a hole", () => {
  test("the card falls back to the holding when there is no summary", () => {
    renderCard(
      <DecisionCard
        hit={makeHit({ summary: null, decision_outcome: "Nämnden avslår överklagandet." })}
        to="/beslut/x"
      />,
    );
    expect(screen.getByText("Nämnden avslår överklagandet.")).toBeInTheDocument();
  });
});

describe("a query whose words appear nowhere is flagged as matched by meaning", () => {
  test("no note when the text arm found the words", () => {
    render(
      <SearchSummary effectiveQueries={["jäv"]} total={3} diagnostics={makeDiagnostics()} />,
    );
    expect(screen.queryByText(/närmast i betydelse/)).not.toBeInTheDocument();
  });

  test("note appears when no query word occurs in the corpus", () => {
    render(
      <SearchSummary
        effectiveQueries={["ledamot som är släkt med sökanden"]}
        total={15}
        diagnostics={makeDiagnostics({
          text_hit_counts: { "ledamot som är släkt med sökanden": 0 },
          top_vector_similarity: 0.8068,
        })}
      />,
    );
    expect(screen.getByText(/närmast i betydelse/)).toBeInTheDocument();
  });
});

describe("rule 11 — a note about the list below is not shown when there is no list", () => {
  // `zzzqqq xylofon` used to return a full page: the vector arm had no similarity
  // floor, so a nearest-neighbour scan always had a nearest neighbour. It now
  // returns nothing, which makes `total: 0` with no filter reachable — and both
  // notes speak about "träffarna nedan".
  const NOTHING_MATCHED = makeDiagnostics({
    text_hit_counts: { "zzzqqq xylofon": 0 },
    vector_hit_count: 0,
    top_vector_similarity: null,
    widened_to_appendices: true,
  });

  test("neither note claims anything about a list that is empty", () => {
    render(
      <SearchSummary
        effectiveQueries={["zzzqqq xylofon"]}
        total={0}
        diagnostics={NOTHING_MATCHED}
      />,
    );
    expect(screen.queryByText(/närmast i betydelse/)).not.toBeInTheDocument();
    expect(screen.queryByText(/Inget matchade i besluten själva/)).not.toBeInTheDocument();
  });

  test("the same diagnostics with results do show both notes", () => {
    // The control: what silences the notes is the empty list, not the
    // diagnostics — otherwise the test above would pass on a component that
    // never renders them at all.
    render(
      <SearchSummary
        effectiveQueries={["zzzqqq xylofon"]}
        total={4}
        diagnostics={NOTHING_MATCHED}
      />,
    );
    expect(screen.getByText(/närmast i betydelse/)).toBeInTheDocument();
    expect(screen.getByText(/Inget matchade i besluten själva/)).toBeInTheDocument();
  });
});

describe("rule 12 — generated phrasings are attributed to the model", () => {
  test("a plain search says nothing about expansion", () => {
    render(
      <SearchSummary effectiveQueries={["jäv"]} total={3} diagnostics={makeDiagnostics()} />,
    );
    expect(screen.queryByText(/språkmodell/i)).not.toBeInTheDocument();
  });

  test("the extra phrasings are named as the model's, not the user's", () => {
    render(
      <SearchSummary
        effectiveQueries={["jäv", "jävsinvändning", "opartiskhet"]}
        total={3}
        diagnostics={makeDiagnostics({ expanded: true })}
        expandRequested
      />,
    );
    expect(screen.getByText(/föreslagna av en språkmodell/)).toBeInTheDocument();
  });

  test("expansion that failed says so rather than passing for a plain search", () => {
    // It fails open, so the results are real — but the search the user asked for
    // is not the search that ran.
    render(
      <SearchSummary
        effectiveQueries={["jäv"]}
        total={3}
        diagnostics={makeDiagnostics({ expanded: false })}
        expandRequested
      />,
    );
    expect(screen.getByText(/kunde inte hämtas/)).toBeInTheDocument();
  });

  test("a model that proposed nothing does not point at phrasings that are not there", () => {
    render(
      <SearchSummary
        effectiveQueries={["jäv"]}
        total={3}
        diagnostics={makeDiagnostics({ expanded: true })}
        expandRequested
      />,
    );
    expect(screen.getByText(/inga andra formuleringar/)).toBeInTheDocument();
  });
});
