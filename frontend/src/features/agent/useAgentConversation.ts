/* The one piece of client state in agent mode.
 *
 * Not TanStack Query for the stream itself: this is a stream, not a cached read,
 * and the query client's "the corpus never changes, keep everything forever"
 * policy has nothing useful to say about it. Plain state, one AbortController.
 *
 * The conversation lives on the server, keyed by `session_id` — the client sends
 * one message per turn, never the history. Reopening an earlier conversation
 * seeds the transcript through the query layer and then hands that same id to
 * the next question, so a follow-up continues it rather than forking.
 */

import { useCallback, useEffect, useRef, useState } from "react";
import { useQueryClient } from "@tanstack/react-query";

import { ApiError } from "../../api/client";
import { openChatStream } from "../../api/chat-stream";
import { queryKeys, useSessionTranscript } from "../../api/queries";
import { applyEvent, newTurn, restoredTurn, type Turn } from "./conversation";

/** Shown when the request never opened a stream. In-band failures carry the
 *  API's own Swedish message instead. */
const UNREACHABLE = "Kunde inte nå tjänsten. Kontrollera att API:et är igång.";
const REJECTED = "Frågan kunde inte skickas. Pröva en kortare formulering.";

export type AgentConversationOptions = {
  /** The conversation to reopen, from the route. `undefined` starts a new one. */
  sessionId?: string | undefined;
  /** Called once, when a conversation started here is first named by the server.
   *
   *  A callback rather than an effect on `sessionId`: the caller's reaction is
   *  to change the route, and an effect would also fire when the route changed
   *  *away* — clicking "Nytt samtal" would bounce straight back to the
   *  conversation just left. This fires at the moment the fact is learned and
   *  at no other. */
  onSessionStarted?: ((sessionId: string) => void) | undefined;
};

export type AgentConversation = {
  turns: Turn[];
  /** True while a turn is open — the composer is disabled and Stop is offered. */
  busy: boolean;
  /** True while an earlier conversation is being read back. */
  loading: boolean;
  /** True when reading it back failed — distinct from an empty conversation. */
  failedToLoad: boolean;
  ask: (question: string) => void;
  stop: () => void;
};

export function useAgentConversation(
  options: AgentConversationOptions = {},
): AgentConversation {
  const { sessionId: routeSessionId, onSessionStarted } = options;
  const [turns, setTurns] = useState<Turn[]>([]);
  const [busy, setBusy] = useState(false);
  const [sessionId, setSessionId] = useState<string | null>(routeSessionId ?? null);
  const abort = useRef<AbortController | null>(null);
  const nextKey = useRef(0);
  const client = useQueryClient();

  // A conversation this hook started is already on screen; re-reading it from
  // the server when the URL catches up would duplicate every turn.
  const ownStarted = useRef<string | null>(null);
  const restore = routeSessionId !== ownStarted.current ? routeSessionId : undefined;

  const transcript = useSessionTranscript(restore);

  // Which conversation the transcript on screen belongs to. Seeded from the
  // route rather than from nothing, because on the first render the two already
  // agree — `turns` starts empty and `sessionId` starts at the route's id — and
  // an effect that treats mount as a change would clear a transcript that is
  // already correct.
  const shown = useRef(routeSessionId);

  // The route decides which conversation is on screen, so a *change* of route is
  // a change of conversation — whether that is opening another one from the
  // rail or starting a fresh one. Both clear what is showing; only the first
  // has anything to put back.
  //
  // The comparison is against the last route this hook acted on, not against
  // the render's own value: under StrictMode every effect runs mount → cleanup
  // → mount, so an effect that asked "does the route differ from the
  // conversation I started?" answered yes twice on a fresh `/agent` and cleared
  // the turn the page had just been opened to ask. The stream stayed live with
  // nothing on screen to fold it into, which is what made a first question look
  // like it had silently done nothing.
  useEffect(() => {
    if (routeSessionId === shown.current) return;
    shown.current = routeSessionId;
    // The URL catching up to a conversation started here is not a change of
    // conversation — it is the same one being named.
    if (routeSessionId === ownStarted.current) return;
    ownStarted.current = null;
    setTurns([]);
    setSessionId(routeSessionId ?? null);
  }, [routeSessionId]);

  const restored = transcript.data;

  useEffect(() => {
    if (restore === undefined || restored === undefined) return;
    setTurns(
      restored.turns.map((turn, index) =>
        restoredTurn(`restored-${restored.id}-${index}`, turn),
      ),
    );
  }, [restore, restored]);

  const ask = useCallback(
    (question: string) => {
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
            { session_id: sessionId, message: asked },
            { signal: controller.signal },
          );
          update((turn) => ({ ...turn, interactionId: stream.interactionId }));

          for await (const event of stream.events) {
            // The session id arrives on `done` and is what makes the next
            // question a follow-up rather than a fresh conversation.
            if (event.kind === "done") {
              const started = sessionId === null;
              ownStarted.current = event.session_id;
              setSessionId(event.session_id);
              if (started) onSessionStarted?.(event.session_id);
              // The turn just written moved this conversation to the top of the
              // list, and gave a brand-new one its title. The one query in this
              // app that genuinely goes stale.
              void client.invalidateQueries({ queryKey: queryKeys.sessions() });
            }
            update((turn) => applyEvent(turn, event));
          }

          // A stream that stops without `done` or `error` is not a success. The
          // turn was not persisted server-side either, so saying so is the
          // honest reading — see the aborted case below.
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
    },
    [client, onSessionStarted, sessionId],
  );

  const stop = useCallback(() => {
    abort.current?.abort();
  }, []);

  return {
    turns,
    busy,
    loading: restore !== undefined && transcript.isPending,
    failedToLoad: restore !== undefined && transcript.isError,
    ask,
    stop,
  };
}
