/* One test per honesty rule for agent mode.
 *
 * The search UI has twelve of these already, and they all answer the same
 * question: what may this interface claim about the data behind it? Agent mode
 * adds a harder version of that question, because the words on screen are
 * written by a language model rather than lifted from a decision. These are the
 * rules that keep the reader able to tell those two apart.
 *
 * Numbered from 13 to continue `documentation/frontend/honesty-rules.md`. Rule
 * 21 covers a turn read back out of a past conversation, where the prose
 * survived and the evidence did not.
 */

import { fireEvent, render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router";
import { describe, expect, test } from "vitest";

import { AnswerBody } from "./AnswerBody";
import { SourceList, type SourceListProps } from "./SourceList";
import { SqlEvidence } from "./SqlEvidence";
import { TurnSteps } from "./TurnSteps";
import { TurnView } from "./TurnView";
import { applyEvent, newTurn, restoredTurn, type Step, type Turn } from "./conversation";
import { makeSessionTurn, makeSource, makeSqlEvent } from "../../test/factories";
import type { SourceReference } from "../../api/chat-events";

function renderTurn(turn: Turn) {
  return render(
    <MemoryRouter>
      <TurnView turn={turn} />
    </MemoryRouter>,
  );
}

/** The sources live behind a button now — a card is read by opening the panel.
 *  The trigger is labelled "N källor" / "1 källa", so the regex finds either. */
function renderOpenSources(props: SourceListProps) {
  const result = render(
    <MemoryRouter>
      <SourceList {...props} />
    </MemoryRouter>,
  );
  fireEvent.click(screen.getByRole("button", { name: /käll(a|or)/i }));
  return result;
}

function step(overrides: Partial<Step> = {}): Step {
  return { id: "tc-1", label: "search.broad", status: "ok", detail: {}, ...overrides };
}

describe("rule 13 — an appendix source is not the nämnd's words", () => {
  test("a body source is attributed to the nämnd", () => {
    renderOpenSources({ sources: [makeSource()], received: true });
    expect(screen.getByText("Nämndens beslut")).toBeInTheDocument();
  });

  test("an appendix source is marked as the appealed decision", () => {
    renderOpenSources({
      sources: [makeSource({ section: "appendix", appendix_label: "Bilaga A" })],
      received: true,
    });
    expect(screen.getByText(/Bilaga A/)).toBeInTheDocument();
    expect(screen.getByText(/överklagat beslut/)).toBeInTheDocument();
  });
});

describe("rule 14 — a count's query is always reachable", () => {
  test("the generated query and its rows are reachable beside the answer", () => {
    const turn = {
      ...newTurn("t1", "Hur många avslogs 2024?"),
      sql: [makeSqlEvent()],
      answer: "Tolv överklaganden avslogs under 2024.",
      status: "done" as const,
    };
    renderTurn(turn);

    expect(screen.getByText(/SELECT count\(\*\)/)).toBeInTheDocument();
    expect(screen.getByText("12")).toBeInTheDocument();
  });

  test("the query is one click away, not forced open on the reader", () => {
    // The obligation shifted from "on screen" to "reachable": a non-technical
    // reader skips a block that opens on SELECT, so the query, its rows and its
    // assumptions live behind a disclosure that is discreet by default — but
    // present, closed rather than absent, with a summary that opens it.
    const { container } = render(
      <SqlEvidence
        events={[
          makeSqlEvent({
            attempts: [
              { sql: "SELECT 1", ok: false, error: "kolumn saknas", row_count: null },
              {
                sql: "SELECT count(*) FROM documents",
                ok: true,
                error: null,
                row_count: 1,
              },
            ],
          }),
        ]}
      />,
    );

    const query = screen.getByText(/SELECT count\(\*\) FROM documents WHERE/);
    // Reachable: in the DOM, inside the drill-down, which starts closed.
    expect(query).toBeInTheDocument();
    const disclosure = container.querySelector("details");
    expect(disclosure).not.toBeNull();
    expect((disclosure as HTMLDetailsElement).open).toBe(false);
    expect(disclosure?.contains(query)).toBe(true);
    // And openable: the summary the reader clicks is there to be found.
    expect(screen.getByText("Så räknades siffrorna fram")).toBeInTheDocument();
  });

  test("a query that could not be built says so rather than staying silent", () => {
    // The one branch that is not a drill-down: a turn with no query has nothing
    // to open, so it says so plainly and inline.
    render(<SqlEvidence events={[makeSqlEvent({ answered: false, sql: null })]} />);
    expect(screen.getByText(/ingen räkning/i)).toBeInTheDocument();
  });

  test("the interpretation the SQL agent made travels with the query", () => {
    render(
      <SqlEvidence
        events={[makeSqlEvent({ assumptions: ["Årtal tolkat som decision_date."] })]}
      />,
    );
    expect(screen.getByText(/Årtal tolkat som decision_date/)).toBeInTheDocument();
  });
});

describe("rule 15 — an error is terminal", () => {
  test("the failure is shown and nothing waits for a done that will not come", () => {
    let turn = newTurn("t1", "Vad gäller?");
    turn = applyEvent(turn, { kind: "token", text: "Enligt beslut" });
    turn = applyEvent(turn, {
      kind: "error",
      message: "Ett fel uppstod när frågan besvarades.",
    });

    renderTurn(turn);

    expect(screen.getByText(/Ett fel uppstod/)).toBeInTheDocument();
    // The partial answer is kept — it is what the agent actually said — but
    // nothing claims it is still being written.
    expect(screen.getByText("Enligt beslut")).toBeInTheDocument();
    expect(screen.queryByText(/Skriver/)).not.toBeInTheDocument();
  });
});

describe("rule 16 — a refused step is a step, not a failure", () => {
  test("it is not described as an error", () => {
    // The rule rides on `status`, not on a label of its own: a declined filter
    // is a search that reported `refused`, and the next step is the lookup.
    const { container } = render(
      <TurnSteps
        steps={[step({ label: "search.filtered", status: "refused" })]}
        streaming={false}
      />,
    );

    expect(screen.queryByText(/fel/i)).not.toBeInTheDocument();
    // Every step carries a marker; only a failure carries the error colour.
    expect(container.innerHTML).not.toContain("--status-error-fg");
  });

  test("a genuine tool error is distinguishable from it", () => {
    const { container } = render(
      <TurnSteps steps={[step({ status: "error" })]} streaming={false} />,
    );
    expect(container.innerHTML).toContain("--status-error-fg");
    expect(screen.getByText("Sökte i besluten")).toBeInTheDocument();
  });
});

describe("rule 17 — streaming text is not a finished answer", () => {
  test("a turn still streaming says it is still being written", () => {
    render(<AnswerBody sources={[]} text="Enligt beslut 14/2026" streaming />);
    expect(screen.getByText(/Skriver vidare/)).toBeInTheDocument();
  });

  test("a finished answer carries no such marker", () => {
    render(<AnswerBody sources={[]} text="Enligt beslut 14/2026 gäller följande." streaming={false} />);
    expect(screen.queryByText(/Skriver/)).not.toBeInTheDocument();
  });

  test("nothing is shown until the sources frame has arrived", () => {
    // Sources now precede the prose, so `received` is what separates "this
    // turn cites nothing" from "this turn has not said yet".
    render(
      <MemoryRouter>
        <SourceList sources={[]} received={false} />
      </MemoryRouter>,
    );
    expect(screen.queryByText(/vilar inte/)).not.toBeInTheDocument();
  });

  test("the writing marker is what says the answer is unfinished", () => {
    // Sources arriving first must not read as a finished turn: they are the
    // evidence the answer is about to rest on, not proof that it does yet.
    render(
      <MemoryRouter>
        <TurnView
          turn={{
            ...newTurn("t1", "Vad gäller vid jäv?"),
            sources: [makeSource()],
            sourcesReceived: true,
            answer: "Enligt beslut 14/2026",
            status: "streaming" as const,
          }}
        />
      </MemoryRouter>,
    );
    expect(screen.getByText(/Skriver vidare/)).toBeInTheDocument();
  });
});

describe("rule 22 — an inline citation resolves to a passage the reader can reach", () => {
  const cited = (answer: string, sources: SourceReference[]) =>
    render(
      <MemoryRouter>
        <TurnView
          turn={{
            ...newTurn("t1", "Vad gäller vid jäv?"),
            sources,
            sourcesReceived: true,
            answer,
            status: "done" as const,
          }}
        />
      </MemoryRouter>,
    );

  const openSources = () =>
    fireEvent.click(screen.getByRole("button", { name: /käll(a|or)/i }));

  test("the superscript is numbered, and its source carries the same number", () => {
    cited("Fristen löper från delgivning[c1].", [makeSource({ handle: "c1" })]);

    // Inline, the superscript stands on its own — the passage is a click away.
    expect(screen.getByLabelText("Källa 1")).toBeInTheDocument();
    // Opened, the mark and the card it points at are labelled alike, so
    // counting down the list lands on the passage the mark named.
    openSources();
    expect(screen.getAllByLabelText("Källa 1")).toHaveLength(2);
  });

  test("an unresolvable marker is removed, never shown raw", () => {
    cited("Fristen löper från delgivning[c9].", [makeSource({ handle: "c1" })]);

    expect(screen.queryByText(/\[c9\]/)).not.toBeInTheDocument();
    expect(screen.getByText(/Fristen löper från delgivning\./)).toBeInTheDocument();
  });

  test("a cited appendix passage keeps its badge", () => {
    // Rule 13, at the citation. A superscript pointing at the appealed decision
    // must not let the reader take it for the nämnd's reasoning — the badge is
    // on the card the mark resolves to, one click away in the panel.
    cited("Stiftet avslog begäran[c1].", [
      makeSource({ handle: "c1", section: "appendix", appendix_label: "Bilaga A" }),
    ]);

    openSources();
    expect(screen.getByText(/Bilaga A/)).toBeInTheDocument();
    expect(screen.getByText(/överklagat beslut/)).toBeInTheDocument();
  });

  test("two passages of one decision stay two resolvable citations", () => {
    const id = "33333333-3333-3333-3333-333333333333";
    cited("Först[c1], men också[c2].", [
      makeSource({ handle: "c1", document_id: id }),
      makeSource({ handle: "c2", document_id: id }),
    ]);

    openSources();
    expect(screen.getAllByLabelText("Källa 1")).toHaveLength(2);
    expect(screen.getAllByLabelText("Källa 2")).toHaveLength(2);
  });
});

describe("rule 18 — an aborted turn says the agent does not remember it", () => {
  test("stopping mid-answer is not presented as a completed turn", () => {
    // The API persists a turn only after `done`, so a stopped question is
    // absent from the conversation the next question is answered against.
    let turn = newTurn("t1", "Vad gäller?");
    turn = applyEvent(turn, { kind: "token", text: "Enligt" });
    renderTurn({ ...turn, status: "aborted" });

    expect(screen.getByText(/avbröts/)).toBeInTheDocument();
    expect(screen.getByText(/minns inte/)).toBeInTheDocument();
  });
});

describe("rule 19 — an empty source list is stated, not implied", () => {
  test("an answer that cites nothing says so", () => {
    // Both a search that found nothing and a turn that needed no search send an
    // empty `sources` frame. Rendering nothing would leave the reader to assume
    // the prose was sourced.
    render(
      <MemoryRouter>
        <SourceList sources={[]} received />
      </MemoryRouter>,
    );
    expect(screen.getByText(/vilar inte på något citerat beslut/)).toBeInTheDocument();
  });
});

describe("rule 20 — the two identifier spaces are not conflated", () => {
  test("the chat source shows an ärendenummer, labelled, and invents no beslutsnummer", () => {
    // The chat contract carries no decision_number. Presenting the case number
    // under a "Beslut" label would merge two identifier spaces the corpus keeps
    // apart — 2025-0035 is decided as 14/2026.
    renderOpenSources({ sources: [makeSource()], received: true });

    expect(screen.getByText("Ärendenummer")).toBeInTheDocument();
    expect(screen.getByText("2025-0035")).toBeInTheDocument();
    expect(screen.queryByText("Beslut")).not.toBeInTheDocument();
  });
});

describe("rule 21 — a reopened conversation shows what was said, not what it rested on", () => {
  test("a restored turn says its citations were not kept", () => {
    // The API persists the question and the answer only. The passages the turn
    // was built from are genuinely gone, so the gap where sources would be has
    // to be named rather than left for the reader to interpret.
    renderTurn(restoredTurn("r0", makeSessionTurn()));

    expect(screen.getByText(/tidigare samtal/i)).toBeInTheDocument();
    expect(screen.getByText(/hänvisningar sparas inte/i)).toBeInTheDocument();
  });

  test("it does not claim the answer cited nothing", () => {
    // The distinction from rule 19, and the reason `sourcesReceived` stays
    // false: "this answer rests on no decision" is a different statement from
    // "we did not keep the decisions it rested on", and only the second is true.
    renderTurn(restoredTurn("r0", makeSessionTurn()));

    expect(screen.queryByText(/vilar inte på något citerat beslut/)).not.toBeInTheDocument();
    expect(screen.queryByText("Källor")).not.toBeInTheDocument();
  });

  test("its prose shows no marker it cannot resolve", () => {
    // The persisted answer still has `[c1]` in it — the passages are gone, so
    // there is nothing for a superscript to point at, and a bare `[c1]` on
    // screen would be a reference to nothing.
    renderTurn(
      restoredTurn(
        "r0",
        makeSessionTurn({ answer: "Fristen löper från delgivning[c1]." }),
      ),
    );

    expect(screen.queryByText(/\[c1\]/)).not.toBeInTheDocument();
    expect(screen.getByText(/Fristen löper från delgivning\./)).toBeInTheDocument();
  });

  test("a live turn that cited nothing keeps saying so, and carries no marker", () => {
    let turn = newTurn("t1", "tack");
    turn = applyEvent(turn, { kind: "token", text: "Varsågod!" });
    turn = applyEvent(turn, { kind: "sources", sources: [] });
    turn = applyEvent(turn, { kind: "done", session_id: "s1" });

    renderTurn(turn);

    expect(screen.getByText(/vilar inte på något citerat beslut/)).toBeInTheDocument();
    expect(screen.queryByText(/hänvisningar sparas inte/i)).not.toBeInTheDocument();
  });

  test("a restored turn is finished, and holds no half-written state", () => {
    const turn = restoredTurn("r0", makeSessionTurn());

    expect(turn.status).toBe("done");
    expect(turn.origin).toBe("restored");
    expect(turn.steps).toEqual([]);
    expect(turn.sql).toEqual([]);
    expect(turn.sourcesReceived).toBe(false);
  });

  test("the trace reference survives, so a bad old answer is still findable", () => {
    renderTurn(restoredTurn("r0", makeSessionTurn()));
    expect(
      screen.getByText("44444444-4444-4444-4444-444444444444"),
    ).toBeInTheDocument();
  });
});

describe("the turn's reference is recoverable for a bad answer", () => {
  test("the interaction id is on screen once the turn has finished", () => {
    // What turns "this answer was wrong" into a lookup in the trace store
    // rather than a guess from timestamps.
    const turn = {
      ...newTurn("t1", "Vad gäller?"),
      interactionId: "11111111-1111-4111-8111-111111111111",
      status: "done" as const,
    };
    renderTurn(turn);

    expect(
      screen.getByText("11111111-1111-4111-8111-111111111111"),
    ).toBeInTheDocument();
  });
});
