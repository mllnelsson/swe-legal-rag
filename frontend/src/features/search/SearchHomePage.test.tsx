/* The one screen every reader starts on, and the choice it asks them to make.
 *
 * The box is deliberately dumb — it hands text to the page and knows nothing
 * about modes or destinations — so where a question ends up is decided here and
 * nowhere else. Getting that wrong sends a research question to a keyword search,
 * or spends a minute of model time on one that wanted a keyword search.
 */

import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen } from "@testing-library/react";
import { MemoryRouter, Route, Routes, useLocation } from "react-router";
import { afterEach, beforeEach, describe, expect, test, vi } from "vitest";

import { SearchHomePage } from "./SearchHomePage";

const FACETS = {
  categories: [],
  decision_outcomes: [],
  keywords: [{ value: "jäv", count: 4 }],
  entity_types: [],
  document_count: 187,
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

/** Reports where a submission landed, and what it carried. */
function Destination() {
  const location = useLocation();
  return (
    <span data-testid="went">
      {`${location.pathname}${location.search}|${(location.state as { question?: string } | null)?.question ?? ""}`}
    </span>
  );
}

function renderHome() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter initialEntries={["/"]}>
        <Destination />
        <Routes>
          <Route path="/" element={<SearchHomePage />} />
          <Route path="/sok" element={<span>results</span>} />
          <Route path="/agent" element={<span>agent</span>} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

function submit(text: string) {
  const box = screen.getByRole("textbox");
  fireEvent.change(box, { target: { value: text } });
  // The form, not the input: submitting the input itself is not what a reader
  // pressing Enter does, and jsdom rejects it.
  fireEvent.submit(box.closest("form") as HTMLFormElement);
}

describe("choosing what the question is for", () => {
  test("the choice is a switch, off by default", () => {
    renderHome();
    const toggle = screen.getByRole("switch", { name: /Agentläge/ });
    expect(toggle).toHaveAttribute("aria-checked", "false");
  });

  test("a question goes to search while the switch is off", () => {
    renderHome();
    submit("jäv i kyrkoråd");
    expect(screen.getByTestId("went")).toHaveTextContent("/sok");
  });

  test("with the switch on it goes to the agent, carrying the question", () => {
    // Router state, not the query string: the question is not part of the
    // conversation's address, and a reload must not re-ask it.
    renderHome();
    fireEvent.click(screen.getByRole("switch", { name: /Agentläge/ }));
    submit("Hur ofta bifaller nämnden?");

    expect(screen.getByTestId("went")).toHaveTextContent(
      "/agent|Hur ofta bifaller nämnden?",
    );
  });

  test("the switch says what turning it on changes", () => {
    // "Agentläge" alone does not tell a first-time reader that this one takes a
    // minute and writes prose rather than returning the nämnd's own words.
    renderHome();
    expect(screen.getByText(/Visar nämndens egna ord/)).toBeInTheDocument();

    fireEvent.click(screen.getByRole("switch", { name: /Agentläge/ }));
    expect(screen.getByText(/upp till en minut/)).toBeInTheDocument();
  });

  test("an empty box goes nowhere in either mode", () => {
    renderHome();
    submit("   ");
    expect(screen.getByTestId("went")).toHaveTextContent("/|");
  });
});

describe("what the page says about the corpus", () => {
  test("the count is the API's, and the keywords are the nämnd's own", async () => {
    renderHome();
    expect(await screen.findByText(/187 beslut i samlingen/)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "jäv" })).toBeInTheDocument();
  });
});
