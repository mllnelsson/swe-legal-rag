/* Which conversation the page is in.
 *
 * The one thing here that is genuinely easy to get wrong: `session_id` is the
 * whole of the client's conversation state, and it now comes from three places
 * — the route on a reopened conversation, the `done` frame on a new one, and
 * nowhere at all after "Nytt samtal". A mistake shows up as a follow-up that
 * silently forks a new conversation, or as an old transcript still on screen
 * under a new one.
 */

import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter, Route, Routes, useLocation } from "react-router";
import { afterEach, describe, expect, test, vi } from "vitest";

import { AgentPage } from "./AgentPage";
import { makeSessionSummary, makeSessionTurn } from "../../test/factories";
import type { SessionTurn } from "../../api/types";

const SESSION_ID = "33333333-3333-3333-3333-333333333333";

type ChatCall = { session_id: string | null; message: string };

/** One fetch mock over the three endpoints the page touches, recording the chat
 *  request bodies so the session id a follow-up carries is observable. */
function stubApi(turns: SessionTurn[] = []) {
  const chatCalls: ChatCall[] = [];

  vi.stubGlobal(
    "fetch",
    vi.fn(async (input: string | URL | Request, init?: RequestInit) => {
      const url = String(input);

      if (url === "/api/chat") {
        chatCalls.push(JSON.parse(String(init?.body)) as ChatCall);
        return new Response(
          'event: token\ndata: {"text":"Svar."}\n\n' +
            'event: sources\ndata: {"sources":[]}\n\n' +
            `event: done\ndata: {"session_id":"${SESSION_ID}"}\n\n`,
          { headers: { "X-Interaction-Id": "i-1" } },
        );
      }

      if (url.startsWith("/api/sessions/")) {
        return Response.json({
          id: SESSION_ID,
          created_at: "2026-08-14T09:00:00Z",
          last_active_at: "2026-08-14T09:12:00Z",
          turns,
        });
      }

      return Response.json({
        items: [makeSessionSummary({ id: SESSION_ID })],
        total: 1,
        limit: 20,
        offset: 0,
      });
    }),
  );

  return chatCalls;
}

function LocationProbe() {
  return <span data-testid="location">{useLocation().pathname}</span>;
}

function renderAt(path: string) {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter initialEntries={[path]}>
        <LocationProbe />
        <Routes>
          <Route path="/agent" element={<AgentPage />} />
          <Route path="/agent/:sessionId" element={<AgentPage />} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

function ask(question: string) {
  const box = screen.getByRole("textbox");
  fireEvent.change(box, { target: { value: question } });
  fireEvent.keyDown(box, { key: "Enter" });
}

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("reopening a conversation", () => {
  test("the stored turns are on screen", async () => {
    stubApi([
      makeSessionTurn({ question: "Vad gäller vid jäv?", answer: "Detta gäller." }),
    ]);

    renderAt(`/agent/${SESSION_ID}`);

    expect(await screen.findByText("Vad gäller vid jäv?")).toBeInTheDocument();
    expect(screen.getByText("Detta gäller.")).toBeInTheDocument();
  });

  test("a follow-up continues it rather than starting a new one", async () => {
    // The whole point of the route carrying the id. Sending null here would
    // fork a second conversation that knows nothing about the first.
    const chatCalls = stubApi([makeSessionTurn()]);

    renderAt(`/agent/${SESSION_ID}`);
    await screen.findByText(makeSessionTurn().question);

    ask("Förklara det enklare.");

    await waitFor(() => expect(chatCalls).toHaveLength(1));
    expect(chatCalls[0]?.session_id).toBe(SESSION_ID);
  });
});

describe("starting over", () => {
  test("Nytt samtal leaves nothing of the previous conversation on screen", async () => {
    // The route changes but the component does not remount, so clearing the
    // transcript is something the hook has to do rather than get for free.
    const chatCalls = stubApi([
      makeSessionTurn({ question: "Tidigare fråga", answer: "Tidigare svar." }),
    ]);

    renderAt(`/agent/${SESSION_ID}`);
    await screen.findByText("Tidigare fråga");

    fireEvent.click(screen.getByRole("link", { name: /Nytt samtal/ }));

    await waitFor(() =>
      expect(screen.queryByText("Tidigare fråga")).not.toBeInTheDocument(),
    );

    ask("En ny fråga.");
    await waitFor(() => expect(chatCalls).toHaveLength(1));
    // The new conversation must not inherit the old one's id.
    expect(chatCalls[0]?.session_id).toBeNull();
  });
});

describe("a new conversation", () => {
  test("starts with no session id and claims its URL once the server names it", async () => {
    // `replace`, so Back leaves the page rather than un-naming the conversation
    // that is still on screen.
    const chatCalls = stubApi();

    renderAt("/agent");
    expect(screen.getByTestId("location")).toHaveTextContent("/agent");

    ask("Vad gäller vid jäv?");

    await waitFor(() => expect(chatCalls).toHaveLength(1));
    expect(chatCalls[0]?.session_id).toBeNull();

    await waitFor(() =>
      expect(screen.getByTestId("location")).toHaveTextContent(
        `/agent/${SESSION_ID}`,
      ),
    );
  });

  test("the answer is not re-fetched as a transcript when the URL catches up", async () => {
    // The turn is already on screen. Reading it back would render it twice.
    stubApi();

    renderAt("/agent");
    ask("Vad gäller vid jäv?");

    await waitFor(() =>
      expect(screen.getByTestId("location")).toHaveTextContent(
        `/agent/${SESSION_ID}`,
      ),
    );

    expect(screen.getAllByText("Svar.")).toHaveLength(1);
  });
});
