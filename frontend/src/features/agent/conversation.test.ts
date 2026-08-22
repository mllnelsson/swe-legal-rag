/* Folding a stream of frames into one turn.
 *
 * The interesting part is not any single frame but the order they arrive in:
 * a call opens a step that a later result closes, tokens accumulate rather than
 * replace, and two frames are terminal. Getting the fold wrong shows up as a
 * step stuck at "running" or an answer that keeps only its last token.
 */

import { describe, expect, it } from "vitest";

import { applyEvent, newTurn, restoredTurn, type Turn } from "./conversation";
import type { ChatEvent } from "../../api/chat-events";
import { makeSessionTurn, makeSource, makeSqlEvent } from "../../test/factories";

function fold(...events: ChatEvent[]): Turn {
  return events.reduce(applyEvent, newTurn("t1", "Vad gäller vid jäv?"));
}

const searchCall: ChatEvent = {
  kind: "tool_call",
  id: "tc-1",
  tool: "search_decisions",
  label: "search.filtered",
  detail: { has_filter: true },
};

describe("steps", () => {
  it("opens a step on the call and leaves it running", () => {
    const turn = fold(searchCall);

    expect(turn.steps).toHaveLength(1);
    expect(turn.steps[0]?.status).toBeNull();
  });

  it("closes the matching step on the result, by id", () => {
    const turn = fold(
      searchCall,
      {
        kind: "tool_call",
        id: "tc-2",
        tool: "read_decision",
        label: "decision.read",
        detail: {},
      },
      {
        kind: "tool_result",
        id: "tc-1",
        tool: "search_decisions",
        label: "search.filtered",
        status: "ok",
        detail: { decision_count: 7 },
      },
    );

    expect(turn.steps.map((s) => s.status)).toEqual(["ok", null]);
    expect(turn.steps[0]?.detail.decision_count).toBe(7);
  });

  it("takes the label and the status from the result", () => {
    // A declined filter is reported by `status`, not by a label of its own —
    // the step is still the search the call named.
    const turn = fold(searchCall, {
      kind: "tool_result",
      id: "tc-1",
      tool: "search_decisions",
      label: "search.filtered",
      status: "refused",
      detail: {},
    });

    expect(turn.steps[0]?.label).toBe("search.filtered");
    expect(turn.steps[0]?.status).toBe("refused");
  });

  it("ignores a result for a step it never saw opened", () => {
    const turn = fold({
      kind: "tool_result",
      id: "unknown",
      tool: "answer",
      label: "answer.compose",
      status: "ok",
      detail: {},
    });

    expect(turn.steps).toEqual([]);
  });
});

describe("the answer", () => {
  it("accumulates tokens rather than replacing them", () => {
    const turn = fold(
      { kind: "token", text: "Enligt " },
      { kind: "token", text: "beslut " },
      { kind: "token", text: "14/2026" },
    );

    expect(turn.answer).toBe("Enligt beslut 14/2026");
  });
});

describe("terminal frames", () => {
  it("done finishes the turn", () => {
    const turn = fold({ kind: "done", session_id: "s-1" });

    expect(turn.status).toBe("done");
    expect(turn.error).toBeNull();
  });

  it("error finishes it too, carrying the message", () => {
    const turn = fold({ kind: "error", message: "Ett fel uppstod." });

    expect(turn.status).toBe("error");
    expect(turn.error).toBe("Ett fel uppstod.");
  });

  it("starts streaming and stays there until one of them arrives", () => {
    expect(fold(searchCall, { kind: "token", text: "Hej" }).status).toBe("streaming");
  });
});

describe("sources and counts", () => {
  it("records that the sources frame arrived, even when empty", () => {
    // The distinction between "no sources yet" and "no sources, and that is the
    // answer" is what lets the UI say the second one out loud.
    const empty = fold({ kind: "sources", sources: [] });

    expect(empty.sourcesReceived).toBe(true);
    expect(empty.sources).toEqual([]);
    expect(newTurn("t2", "?").sourcesReceived).toBe(false);
  });

  it("keeps every sql frame — a turn may count more than once", () => {
    const turn = fold(makeSqlEvent(), makeSqlEvent({ sql: "SELECT 2" }));

    expect(turn.sql).toHaveLength(2);
  });

  it("keeps the sources it was given", () => {
    const turn = fold({ kind: "sources", sources: [makeSource()] });

    expect(turn.sources[0]?.case_number).toBe("2025-0035");
  });
});

describe("a turn read back out of a past conversation", () => {
  it("is finished, because only a finished turn was ever stored", () => {
    // The API appends a turn after `done` and not before, so anything in a
    // stored history completed. There is no such thing as a restored turn that
    // is still streaming, or an aborted one.
    const turn = restoredTurn("r0", makeSessionTurn());

    expect(turn.status).toBe("done");
    expect(turn.origin).toBe("restored");
    expect(turn.error).toBeNull();
  });

  it("carries the question and the answer and nothing else", () => {
    const turn = restoredTurn(
      "r0",
      makeSessionTurn({ question: "Vad gäller?", answer: "Detta gäller." }),
    );

    expect(turn.question).toBe("Vad gäller?");
    expect(turn.answer).toBe("Detta gäller.");
    expect(turn.steps).toEqual([]);
    expect(turn.sql).toEqual([]);
    expect(turn.sources).toEqual([]);
  });

  it("does not pretend the sources frame arrived", () => {
    // `sourcesReceived` is what makes the UI say "this answer cites nothing".
    // A restored turn cited something; what was not kept is the record of it.
    expect(restoredTurn("r0", makeSessionTurn()).sourcesReceived).toBe(false);
  });

  it("keeps the interaction id, so an old bad answer is still traceable", () => {
    const turn = restoredTurn("r0", makeSessionTurn({ interaction_id: "i-9" }));
    expect(turn.interactionId).toBe("i-9");
  });

  it("tolerates a turn stored before interaction ids existed", () => {
    const turn = restoredTurn("r0", makeSessionTurn({ interaction_id: null }));
    expect(turn.interactionId).toBeNull();
  });
});
