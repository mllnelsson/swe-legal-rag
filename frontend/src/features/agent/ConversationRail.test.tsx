/* The conversation rail.
 *
 * What is worth pinning here is what the rail says when it has nothing to show,
 * and that the one destructive action in this app cannot happen by accident.
 * The ordering itself is the API's job — `last_active_at DESC` in SQL — so what
 * is tested is that the rail renders what it is given rather than resorting it.
 */

import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router";
import { afterEach, beforeEach, describe, expect, test, vi } from "vitest";

import { ConversationRail } from "./ConversationRail";
import { makeSessionSummary } from "../../test/factories";
import type { SessionSummary } from "../../api/types";

/** A conversation is its URL, so the open one is set by where the router is. */
function renderRail(openSessionId?: string) {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  const at = openSessionId === undefined ? "/agent" : `/agent/${openSessionId}`;
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter initialEntries={[at]}>
        <ConversationRail openSessionId={openSessionId} />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

function respondWith(items: SessionSummary[]) {
  vi.stubGlobal(
    "fetch",
    vi.fn(async () =>
      Response.json({ items, total: items.length, limit: 20, offset: 0 }),
    ),
  );
}

beforeEach(() => {
  vi.restoreAllMocks();
});

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("what the rail shows", () => {
  test("lists conversations in the order the API returned them", async () => {
    respondWith([
      makeSessionSummary({ id: "s-new", title: "Senaste frågan" }),
      makeSessionSummary({ id: "s-old", title: "Äldre frågan" }),
    ]);

    renderRail();

    const links = await screen.findAllByRole("link", { name: /frågan/ });
    expect(links.map((link) => link.textContent)).toEqual([
      expect.stringContaining("Senaste frågan"),
      expect.stringContaining("Äldre frågan"),
    ]);
  });

  test("a title is the question as asked, not a generated label", async () => {
    respondWith([makeSessionSummary({ title: "Vad gäller vid jäv i kyrkoråd?" })]);
    renderRail();
    expect(
      await screen.findByText("Vad gäller vid jäv i kyrkoråd?"),
    ).toBeInTheDocument();
  });

  test("the open conversation is marked", async () => {
    respondWith([
      makeSessionSummary({ id: "s-open", title: "Öppen" }),
      makeSessionSummary({ id: "s-other", title: "Annan" }),
    ]);

    renderRail("s-open");

    const open = await screen.findByRole("link", { name: /Öppen/ });
    const other = screen.getByRole("link", { name: /Annan/ });
    expect(open).toHaveAttribute("aria-current", "page");
    expect(other).not.toHaveAttribute("aria-current");
  });

  test("it says the app has no accounts, rather than leaving it to be noticed", async () => {
    // Someone else's question appearing in the list should not be a surprise.
    respondWith([makeSessionSummary()]);
    renderRail();
    expect(await screen.findByText(/inga konton/i)).toBeInTheDocument();
  });

  test("no conversations yet says so", async () => {
    respondWith([]);
    renderRail();
    expect(await screen.findByText(/Inga tidigare samtal/i)).toBeInTheDocument();
  });

  test("a failed fetch says so instead of looking empty", async () => {
    // An empty rail and an unreachable API mean opposite things to someone
    // wondering where their earlier question went.
    vi.stubGlobal("fetch", vi.fn(async () => new Response("", { status: 500 })));

    renderRail();

    expect(await screen.findByText(/Kunde inte hämta/i)).toBeInTheDocument();
    expect(screen.queryByText(/Inga tidigare samtal/i)).not.toBeInTheDocument();
  });

  test("a new conversation is always one link away", async () => {
    respondWith([makeSessionSummary()]);
    renderRail();
    expect(screen.getByRole("link", { name: /Nytt samtal/ })).toHaveAttribute(
      "href",
      "/agent",
    );
  });
});

describe("deleting a conversation", () => {
  test("nothing is deleted when the confirmation is declined", async () => {
    const fetchMock = vi.fn(async (_input: string | URL | Request, _init?: RequestInit) =>
      Response.json({
        items: [makeSessionSummary({ title: "Behåll mig" })],
        total: 1,
        limit: 20,
        offset: 0,
      }),
    );
    vi.stubGlobal("fetch", fetchMock);
    vi.spyOn(window, "confirm").mockReturnValue(false);

    renderRail();
    await screen.findByText("Behåll mig");
    fireEvent.click(screen.getByRole("button", { name: /Ta bort samtalet/ }));

    expect(window.confirm).toHaveBeenCalled();
    expect(
      fetchMock.mock.calls.some(([, init]) => init?.method === "DELETE"),
    ).toBe(false);
  });

  test("confirming sends the delete for that conversation", async () => {
    const fetchMock = vi.fn(async (_input: string | URL | Request, init?: RequestInit) => {
      if (init?.method === "DELETE") return new Response(null, { status: 204 });
      return Response.json({
        items: [makeSessionSummary({ id: "s-doomed", title: "Ta bort mig" })],
        total: 1,
        limit: 20,
        offset: 0,
      });
    });
    vi.stubGlobal("fetch", fetchMock);
    vi.spyOn(window, "confirm").mockReturnValue(true);

    renderRail();
    await screen.findByText("Ta bort mig");
    fireEvent.click(screen.getByRole("button", { name: /Ta bort samtalet/ }));

    await waitFor(() => {
      expect(fetchMock).toHaveBeenCalledWith(
        "/api/sessions/s-doomed",
        expect.objectContaining({ method: "DELETE" }),
      );
    });
  });
});
