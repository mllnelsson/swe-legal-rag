/* Rule 6 — declared and inferred vocabularies are never presented alike.
 *
 * `keyword` comes off each decision's own `Sökord:` line, written by the nämnd.
 * `regulation`, `legal_concept`, `role` and `parish` are guessed from prose by the
 * extraction step. Both are useful for finding decisions; only one is the corpus
 * speaking for itself, and a user deciding how much weight to give a match needs to
 * know which they are looking at.
 */

import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router";
import { afterEach, beforeEach, expect, test, vi } from "vitest";

import { VocabularyPage } from "./VocabularyPage";

const KEYWORD_PAGE = {
  items: [{ id: "a", name: "avvisning", type: "keyword", document_count: 7 }],
  total: 1,
  limit: 50,
  offset: 0,
};

const CONCEPT_PAGE = {
  items: [
    { id: "b", name: "57 kap. 10 § kyrkoordningen", type: "regulation", document_count: 8 },
  ],
  total: 1,
  limit: 50,
  offset: 0,
};

beforeEach(() => {
  vi.stubGlobal(
    "fetch",
    vi.fn((input: string) =>
      Promise.resolve({
        ok: true,
        json: () => Promise.resolve(input.includes("/api/keywords") ? KEYWORD_PAGE : CONCEPT_PAGE),
      } as Response),
    ),
  );
});

afterEach(() => vi.unstubAllGlobals());

function renderPage(ui: React.ReactElement) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter>{ui}</MemoryRouter>
    </QueryClientProvider>,
  );
}

test("the Sökord vocabulary is attributed to the nämnd", async () => {
  renderPage(<VocabularyPage kind="keywords" />);
  expect(await screen.findByText("avvisning")).toBeInTheDocument();
  expect(screen.getByText("Nämndens egna")).toBeInTheDocument();
  expect(screen.queryByText("Härledda ur texten")).not.toBeInTheDocument();
});

test("the concept vocabulary is marked as inferred, not declared", async () => {
  renderPage(<VocabularyPage kind="concepts" entityType="regulation" />);
  expect(await screen.findByText("57 kap. 10 § kyrkoordningen")).toBeInTheDocument();
  expect(screen.getByText("Härledda ur texten")).toBeInTheDocument();
  expect(screen.queryByText("Nämndens egna")).not.toBeInTheDocument();
});

test("document counts are singular-aware", async () => {
  renderPage(<VocabularyPage kind="concepts" entityType="regulation" />);
  expect(await screen.findByText("8 beslut")).toBeInTheDocument();
});
