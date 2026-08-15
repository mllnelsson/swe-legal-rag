/* One conversation's shape, and the reducer that folds events into it.
 *
 * Kept apart from the hook so the folding is testable without rendering
 * anything: what a turn looks like after a given sequence of frames is the part
 * that can quietly go wrong.
 */

import type {
  ChatEvent,
  ProgressDetail,
  ProgressLabel,
  SourceReference,
  SqlEvent,
  ToolStatus,
} from "../../api/chat-events";

/** One tool the agent reached for, as the client sees it.
 *
 *  A `tool_call` opens a step and its `tool_result` closes it, matched on `id`.
 *  A step with no result yet is still running — which is the whole reason these
 *  events exist, since roughly 18 seconds pass before the first token. */
export type Step = {
  id: string;
  label: ProgressLabel | string;
  status: ToolStatus | null;
  detail: ProgressDetail;
};

export type TurnStatus = "streaming" | "done" | "error" | "aborted";

export type Turn = {
  /** Client-side only; the server identifies turns by interaction id. */
  key: string;
  question: string;
  steps: Step[];
  sql: SqlEvent[];
  answer: string;
  sources: SourceReference[];
  sourcesReceived: boolean;
  interactionId: string | null;
  status: TurnStatus;
  error: string | null;
};

export function newTurn(key: string, question: string): Turn {
  return {
    key,
    question,
    steps: [],
    sql: [],
    answer: "",
    sources: [],
    sourcesReceived: false,
    interactionId: null,
    status: "streaming",
    error: null,
  };
}

/** Fold one event into a turn, returning the new turn.
 *
 *  Total over the seven event kinds, so an added frame type is a compile error
 *  here rather than a silently ignored one. */
export function applyEvent(turn: Turn, event: ChatEvent): Turn {
  switch (event.kind) {
    case "tool_call":
      return {
        ...turn,
        steps: [
          ...turn.steps,
          { id: event.id, label: event.label, status: null, detail: event.detail ?? {} },
        ],
      };

    case "tool_result":
      return {
        ...turn,
        steps: turn.steps.map((step) =>
          step.id === event.id
            ? {
                ...step,
                // The result's label wins: a refused search reports
                // `search.refused` where its call said `search.filtered`.
                label: event.label,
                status: event.status,
                detail: { ...step.detail, ...(event.detail ?? {}) },
              }
            : step,
        ),
      };

    case "sql":
      return { ...turn, sql: [...turn.sql, event] };

    case "token":
      return { ...turn, answer: turn.answer + event.text };

    case "sources":
      return { ...turn, sources: event.sources, sourcesReceived: true };

    case "done":
      return { ...turn, status: "done" };

    case "error":
      // Terminal. No `done` follows, so this is where the turn ends.
      return { ...turn, status: "error", error: event.message };
  }
}
