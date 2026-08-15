/* Folding a stream of frames into one turn.
 *
 * The interesting part is not any single frame but the order they arrive in:
 * a call opens a step that a later result closes, tokens accumulate rather than
 * replace, and two frames are terminal. Getting the fold wrong shows up as a
 * step stuck at "running" or an answer that keeps only its last token.
 */

import { describe, expect, it } from "vitest";

import { applyEvent, newTurn, type Turn } from "./conversation";
import type { ChatEvent } from "../../api/chat-events";
import { makeSource, makeSqlEvent } from "../../test/factories";

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

  it("takes the label from the result, not the call", () => {
    // A refused search reports `search.refused` where its call said
    // `search.filtered` — the result names what actually happened.
    const turn = fold(searchCall, {
      kind: "tool_result",
      id: "tc-1",
      tool: "search_decisions",
      label: "search.refused",
      status: "refused",
      detail: {},
    });

    expect(turn.steps[0]?.label).toBe("search.refused");
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
