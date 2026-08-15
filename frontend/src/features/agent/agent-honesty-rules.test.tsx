/* One test per honesty rule for agent mode.
 *
 * The search UI has twelve of these already, and they all answer the same
 * question: what may this interface claim about the data behind it? Agent mode
 * adds a harder version of that question, because the words on screen are
 * written by a language model rather than lifted from a decision. These are the
 * rules that keep the reader able to tell those two apart.
 *
 * Numbered from 13 to continue `documentation/frontend/honesty-rules.md`.
 */

import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router";
import { describe, expect, test } from "vitest";

import { AnswerBody } from "./AnswerBody";
import { SourceList } from "./SourceList";
import { SqlEvidence } from "./SqlEvidence";
import { TurnSteps } from "./TurnSteps";
import { TurnView } from "./TurnView";
import { applyEvent, newTurn, type Step, type Turn } from "./conversation";
import { makeSource, makeSqlEvent } from "../../test/factories";

function renderTurn(turn: Turn) {
  return render(
    <MemoryRouter>
      <TurnView turn={turn} />
    </MemoryRouter>,
  );
}

function step(overrides: Partial<Step> = {}): Step {
  return { id: "tc-1", label: "search.broad", status: "ok", detail: {}, ...overrides };
}

describe("rule 13 — an appendix source is not the nämnd's words", () => {
  test("a body source is attributed to the nämnd", () => {
    render(
      <MemoryRouter>
        <SourceList sources={[makeSource()]} received />
      </MemoryRouter>,
    );
    expect(screen.getByText("Nämndens beslut")).toBeInTheDocument();
  });

  test("an appendix source is marked as the appealed decision", () => {
    render(
      <MemoryRouter>
        <SourceList
          sources={[makeSource({ section: "appendix", appendix_label: "Bilaga A" })]}
          received
        />
      </MemoryRouter>,
    );
    expect(screen.getByText(/Bilaga A/)).toBeInTheDocument();
    expect(screen.getByText(/överklagat beslut/)).toBeInTheDocument();
  });
});

describe("rule 14 — a count is never shown without the query behind it", () => {
  test("the generated SQL is on screen beside the answer", () => {
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

  test("it is not hidden behind a disclosure the reader has to open", () => {
    // A collapsed query is the same as no query for the reader who most needs
    // it — the one who took the number at face value. The attempt trail may
    // collapse; the query that produced the answer may not.
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
    expect(query).toBeVisible();
    for (const details of container.querySelectorAll("details")) {
      expect(details.contains(query)).toBe(false);
    }
  });

  test("a query that could not be built says so rather than staying silent", () => {
    render(<SqlEvidence events={[makeSqlEvent({ answered: false, sql: null })]} />);
    expect(screen.getByText(/ingen räkning/i)).toBeInTheDocument();
  });

  test("the interpretation the SQL agent made travels with the rows", () => {
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
  test("it is described as the agent waiting for the values, not as an error", () => {
    render(
      <TurnSteps
        steps={[step({ label: "search.refused", status: "refused" })]}
        streaming={false}
      />,
    );

    expect(screen.getByText(/Avvaktade med filtret/)).toBeInTheDocument();
    expect(screen.queryByText(/fel/i)).not.toBeInTheDocument();
  });

  test("a genuine tool error is distinguishable from it", () => {
    const { container } = render(
      <TurnSteps steps={[step({ status: "error" })]} streaming={false} />,
    );
    // The error marker is the warning triangle; a refusal never gets one.
    expect(container.querySelector("svg")).toBeInTheDocument();
    expect(screen.getByText("Sökte i besluten")).toBeInTheDocument();
  });
});

describe("rule 17 — streaming text is not a finished answer", () => {
  test("a turn still streaming says it is still being written", () => {
    render(<AnswerBody text="Enligt beslut 14/2026" streaming />);
    expect(screen.getByText(/Skriver vidare/)).toBeInTheDocument();
  });

  test("a finished answer carries no such marker", () => {
    render(<AnswerBody text="Enligt beslut 14/2026 gäller följande." streaming={false} />);
    expect(screen.queryByText(/Skriver/)).not.toBeInTheDocument();
  });

  test("sources are not shown until the frame carrying them has arrived", () => {
    // Otherwise a half-streamed answer would appear to be sourced by whatever
    // the previous turn cited, or by nothing at all.
    render(
      <MemoryRouter>
        <SourceList sources={[]} received={false} />
      </MemoryRouter>,
    );
    expect(screen.queryByText(/vilar inte/)).not.toBeInTheDocument();
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
    render(
      <MemoryRouter>
        <SourceList sources={[makeSource()]} received />
      </MemoryRouter>,
    );

    expect(screen.getByText("Ärendenummer")).toBeInTheDocument();
    expect(screen.getByText("2025-0035")).toBeInTheDocument();
    expect(screen.queryByText("Beslut")).not.toBeInTheDocument();
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
