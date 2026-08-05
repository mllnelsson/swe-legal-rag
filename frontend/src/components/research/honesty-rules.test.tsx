/* One test per honesty rule.
 *
 * These are the claims the interface makes about the corpus, and they are the part
 * of this app that is genuinely domain-specific rather than generic search UI. Each
 * rule exists because getting it wrong would put something on screen that the data
 * does not support.
 */

import { render, screen } from "@testing-library/react";
import { describe, expect, test, vi } from "vitest";

import { DecisionCard } from "./DecisionCard";
import { RankBadges } from "./RankBadges";
import { SearchEmpty } from "./SearchEmpty";
import { SearchSummary } from "./SearchSummary";
import { SectionBadge } from "./SectionBadge";
import { CitationGraph } from "../../features/decision/CitationGraph";
import { makeChunk, makeDiagnostics, makeHit } from "../../test/factories";

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
    render(<DecisionCard hit={hit} onOpen={vi.fn()} />);
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
  test("ranks are shown instead of the score", () => {
    render(<RankBadges vectorRank={3} textRank={1} />);
    expect(screen.getByText("Vektor #3")).toBeInTheDocument();
    expect(screen.getByText("Text #1")).toBeInTheDocument();
  });

  test("an arm that did not return the chunk is simply absent", () => {
    render(<RankBadges vectorRank={1} textRank={null} />);
    expect(screen.getByText("Vektor #1")).toBeInTheDocument();
    expect(screen.queryByText(/Text #/)).not.toBeInTheDocument();
  });

  test("the raw score never reaches the card", () => {
    const { container } = render(<DecisionCard hit={makeHit({ score: 0.01639 })} onOpen={vi.fn()} />);
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
    render(
      <DecisionCard
        hit={makeHit({ case_number: "2025-0035", decision_number: "14/2026" })}
        onOpen={vi.fn()}
      />,
    );
    expect(screen.getByText("Ärendenummer")).toBeInTheDocument();
    expect(screen.getByText("2025-0035")).toBeInTheDocument();
    expect(screen.getByText("Beslut")).toBeInTheDocument();
    expect(screen.getByText("14/2026")).toBeInTheDocument();
  });
});

describe("summary is optional, and its absence is not a hole", () => {
  test("the card falls back to the holding when there is no summary", () => {
    render(
      <DecisionCard
        hit={makeHit({ summary: null, decision_outcome: "Nämnden avslår överklagandet." })}
        onOpen={vi.fn()}
      />,
    );
    expect(screen.getByText("Nämnden avslår överklagandet.")).toBeInTheDocument();
  });
});

describe("a query whose words appear nowhere is flagged as weak", () => {
  test("no note when the text arm found the words", () => {
    render(
      <SearchSummary effectiveQueries={["jäv"]} total={3} diagnostics={makeDiagnostics()} />,
    );
    expect(screen.queryByText(/närmast i betydelse/)).not.toBeInTheDocument();
  });

  test("note appears when no query word occurs in the corpus", () => {
    // The vector arm has no similarity floor and the fused score is rank-derived,
    // so nonsense still returns a full page of confident-looking hits.
    render(
      <SearchSummary
        effectiveQueries={["zzzqqq xylofon"]}
        total={15}
        diagnostics={makeDiagnostics({ text_hit_counts: { "zzzqqq xylofon": 0 } })}
      />,
    );
    expect(screen.getByText(/närmast i betydelse/)).toBeInTheDocument();
  });
});
