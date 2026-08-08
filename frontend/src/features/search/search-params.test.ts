import { describe, expect, it } from "vitest";

import {
  EMPTY_SEARCH,
  clearFilters,
  parseSearchState,
  toSearchParams,
  toSearchQuery,
} from "./search-params";

/* The URL is the search state, so what these assert is shareability: a search a
 * colleague opens from a pasted link has to be the search that was run. */

describe("query expansion in the URL", () => {
  it("is off when the param is absent", () => {
    expect(parseSearchState(new URLSearchParams()).expand).toBe(false);
  });

  it("is on for the one spelling we write", () => {
    expect(parseSearchState(new URLSearchParams("utoka=1")).expand).toBe(true);
  });

  it("treats any other value as off", () => {
    // A truthy-looking param nobody wrote should not silently start spending
    // model calls.
    expect(parseSearchState(new URLSearchParams("utoka=true")).expand).toBe(false);
  });

  it("round-trips through the URL", () => {
    const state = { ...EMPTY_SEARCH, query: "jäv", expand: true };
    expect(parseSearchState(toSearchParams(state))).toEqual(state);
  });

  it("writes no param when it is off, so a plain search has a clean URL", () => {
    expect(toSearchParams({ ...EMPTY_SEARCH, query: "jäv" }).has("utoka")).toBe(false);
  });

  it("reaches the API query", () => {
    expect(toSearchQuery({ ...EMPTY_SEARCH, expand: true }).expand).toBe(true);
    expect(toSearchQuery(EMPTY_SEARCH).expand).toBe(false);
  });

  it("survives clearing the filters", () => {
    // Clearing filters is an attempt to find more results. Undoing expansion,
    // which also widens, would work against the thing the user just asked for.
    const state = { ...EMPTY_SEARCH, query: "jäv", category: "Avvisning", expand: true };
    expect(clearFilters(state)).toEqual({ ...EMPTY_SEARCH, query: "jäv", expand: true });
  });
});
