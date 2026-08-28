/* The filter rail is a disclosure now, closed by default.
 *
 * The point of the change is that the results page opens on what came back, not on
 * a wall of controls — so "closed by default" and "still says how many filters are
 * in force" are the two claims worth pinning down.
 */

import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, test, vi } from "vitest";

import { FacetRail } from "./FacetRail";
import { EMPTY_SEARCH, type SearchState } from "./search-params";

const FACETS = {
  categories: [{ value: "Avvisning", count: 4 }],
  decision_outcomes: [],
  keywords: [{ value: "jäv", count: 4 }],
  entity_types: [],
  document_count: 187,
  earliest_decision_date: null,
  latest_decision_date: null,
};

beforeEach(() => {
  vi.stubGlobal(
    "fetch",
    vi.fn(() => Promise.resolve({ ok: true, json: () => Promise.resolve(FACETS) } as Response)),
  );
});

afterEach(() => {
  vi.unstubAllGlobals();
});

function renderRail(state: SearchState) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <FacetRail state={state} onChange={vi.fn()} />
    </QueryClientProvider>,
  );
}

describe("FacetRail disclosure", () => {
  test("is collapsed by default", () => {
    const { container } = renderRail(EMPTY_SEARCH);
    expect(container.querySelector("details")).not.toHaveAttribute("open");
    expect(screen.getByText("Filter")).toBeInTheDocument();
  });

  test("counts the filters in force when any are active", () => {
    renderRail({ ...EMPTY_SEARCH, category: "Avvisning", keywords: ["jäv"] });
    expect(screen.getByText("2")).toBeInTheDocument();
  });

  test("shows no count when nothing is narrowing the search", () => {
    renderRail(EMPTY_SEARCH);
    // The only number a bare rail could show is a count; there should be none.
    expect(screen.queryByText(/^\d+$/)).not.toBeInTheDocument();
  });
});
