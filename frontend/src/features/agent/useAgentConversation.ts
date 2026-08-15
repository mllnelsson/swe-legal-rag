/* The one piece of client state in agent mode.
 *
 * Not TanStack Query: this is a stream, not a cached read, and the query
 * client's "the corpus never changes, keep everything forever" policy has
 * nothing useful to say about it. Plain state, one AbortController, done.
 *
 * The conversation itself lives on the server, keyed by `session_id` — the
 * client sends one message per turn, never the history. That id is held for the
 * length of the visit; reopening past conversations is a separate feature and
 * needs read endpoints that do not exist yet.
 */

import { useCallback, useRef, useState } from "react";

import { ApiError } from "../../api/client";
import { openChatStream } from "../../api/chat-stream";
import { applyEvent, newTurn, type Turn } from "./conversation";

/** Shown when the request never opened a stream. In-band failures carry the
 *  API's own Swedish message instead. */
const UNREACHABLE = "Kunde inte nå tjänsten. Kontrollera att API:et är igång.";
const REJECTED = "Frågan kunde inte skickas. Pröva en kortare formulering.";

export type AgentConversation = {
  turns: Turn[];
  /** True while a turn is open — the composer is disabled and Stop is offered. */
  busy: boolean;
  ask: (question: string) => void;
  stop: () => void;
};

export function useAgentConversation(): AgentConversation {
  const [turns, setTurns] = useState<Turn[]>([]);
  const [busy, setBusy] = useState(false);
  const sessionId = useRef<string | null>(null);
  const abort = useRef<AbortController | null>(null);
  const nextKey = useRef(0);

  const ask = useCallback((question: string) => {
    const asked = question.trim();
    if (asked === "") return;

    const key = `turn-${nextKey.current++}`;
    const controller = new AbortController();
    abort.current = controller;
    setTurns((current) => [...current, newTurn(key, asked)]);
    setBusy(true);

    const update = (change: (turn: Turn) => Turn) =>
      setTurns((current) => current.map((t) => (t.key === key ? change(t) : t)));

    void (async () => {
      try {
        const stream = await openChatStream(
          { session_id: sessionId.current, message: asked },
          { signal: controller.signal },
        );
        update((turn) => ({ ...turn, interactionId: stream.interactionId }));

        for await (const event of stream.events) {
          // The session id arrives on `done` and is what makes the next
          // question a follow-up rather than a fresh conversation.
          if (event.kind === "done") sessionId.current = event.session_id;
          update((turn) => applyEvent(turn, event));
        }

        // A stream that stops without `done` or `error` is not a success. The
        // turn was not persisted server-side either, so saying so is the honest
        // reading — see the aborted case below.
        update((turn) =>
          turn.status === "streaming" ? { ...turn, status: "aborted" } : turn,
        );
      } catch (cause) {
        if (controller.signal.aborted) {
          update((turn) => ({ ...turn, status: "aborted" }));
          return;
        }
        const message =
          cause instanceof ApiError && cause.status !== 0 ? REJECTED : UNREACHABLE;
        update((turn) => ({ ...turn, status: "error", error: message }));
      } finally {
        if (abort.current === controller) {
          abort.current = null;
          setBusy(false);
        }
      }
    })();
  }, []);

  const stop = useCallback(() => {
    abort.current?.abort();
  }, []);

  return { turns, busy, ask, stop };
}
