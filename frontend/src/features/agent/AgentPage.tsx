import { useCallback, useEffect, useRef } from "react";
import { useNavigate, useParams, useSearchParams } from "react-router";

import { Composer } from "./Composer";
import { ConversationRail } from "./ConversationRail";
import { TurnView } from "./TurnView";
import { useAgentConversation } from "./useAgentConversation";

/** The question handed over from the home page's Agent mode. */
const QUESTION_PARAM = "q";

/** Agent mode.
 *
 *  The deterministic search at `/sok` answers with the nämnd's own text and
 *  nothing else. This asks a language model to research the question and write
 *  the answer, which is a different promise to the reader — so it is a separate
 *  surface with its own rules about what it may claim, not a mode bolted onto
 *  the results page.
 *
 *  Which conversation is open is carried by the URL rather than by state:
 *  `/agent` is a new one, `/agent/{id}` an earlier one. That makes a
 *  conversation a link, survives a reload, and lets the rail mark the open row
 *  without being told. A conversation started at `/agent` claims its URL as
 *  soon as the server names it. */
export function AgentPage() {
  const { sessionId: routeSessionId } = useParams();
  const [params, setParams] = useSearchParams();
  const navigate = useNavigate();
  // `replace`, not push: the fresh-conversation URL and this one are the same
  // conversation, so Back should leave the page rather than un-name it.
  const claimUrl = useCallback(
    (started: string) => void navigate(`/agent/${started}`, { replace: true }),
    [navigate],
  );
  const { turns, busy, loading, failedToLoad, ask, stop } = useAgentConversation({
    sessionId: routeSessionId,
    onSessionStarted: claimUrl,
  });
  const handedOver = useRef(false);
  const end = useRef<HTMLDivElement>(null);

  const initial = params.get(QUESTION_PARAM);

  useEffect(() => {
    if (handedOver.current || initial === null || initial.trim() === "") return;
    handedOver.current = true;
    ask(initial);
    // Dropped from the URL so a reload does not silently re-ask a question that
    // costs a model call and a minute.
    setParams(new URLSearchParams(), { replace: true });
  }, [initial, ask, setParams]);

  useEffect(() => {
    end.current?.scrollIntoView({ behavior: "smooth", block: "end" });
  }, [turns]);

  return (
    <main
      style={{
        display: "flex",
        justifyContent: "center",
        padding: "var(--space-9) var(--gutter-page) var(--space-11)",
        background: "var(--surface-page)",
        minHeight: "calc(100vh - var(--section-gap))",
      }}
    >
      <div
        style={{
          width: "100%",
          maxWidth: "var(--content-max)",
          display: "flex",
          gap: "var(--space-8)",
        }}
      >
        <div style={{ width: "var(--sidebar-w)", flex: "none" }}>
          <ConversationRail openSessionId={routeSessionId} />
        </div>

        <div
          style={{
            flex: 1,
            minWidth: 0,
            maxWidth: "var(--measure-prose)",
            display: "flex",
            flexDirection: "column",
            gap: "var(--space-9)",
          }}
        >
          {failedToLoad && <LoadFailure />}
          {loading && !failedToLoad && <Loading />}
          {turns.length === 0 && !loading && !failedToLoad ? <EmptyState /> : null}

          {turns.map((turn) => (
            <TurnView key={turn.key} turn={turn} />
          ))}

          <div ref={end} />

          <Composer
            onSubmit={ask}
            onStop={stop}
            busy={busy}
            autoFocus={turns.length === 0}
          />
        </div>
      </div>
    </main>
  );
}

function Loading() {
  return <p style={mutedStyle}>Hämtar samtalet…</p>;
}

/** Said plainly, because the composer below still works: a conversation that
 *  could not be read is one the next question will not build on. */
function LoadFailure() {
  return (
    <p style={{ ...mutedStyle, color: "var(--status-error-fg)" }}>
      Samtalet kunde inte hämtas. En ny fråga här startar ett nytt samtal.
    </p>
  );
}

function EmptyState() {
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: "var(--space-4)" }}>
      <h1
        style={{
          margin: 0,
          fontFamily: "var(--font-display)",
          fontSize: "var(--text-h1-size)",
          lineHeight: "var(--text-h1-lh)",
          letterSpacing: "var(--text-h1-ls)",
          fontWeight: "var(--weight-regular)",
          color: "var(--text-strong)",
        }}
      >
        Fråga om besluten
      </h1>
      <p
        style={{
          margin: 0,
          fontFamily: "var(--font-sans)",
          fontSize: "var(--text-body-size)",
          lineHeight: "var(--text-body-lh)",
          color: "var(--text-muted)",
          maxWidth: "var(--measure-narrow)",
        }}
      >
        Agenten söker i Överklagandenämndens beslut, läser dem vid behov och
        skriver ett svar med hänvisningar. Ett svar tar upp till en minut — du
        ser vad den gör under tiden. Följdfrågor besvaras i samma samtal.
      </p>
    </div>
  );
}

const mutedStyle = {
  margin: 0,
  fontFamily: "var(--font-sans)",
  fontSize: "var(--text-body-size)",
  color: "var(--text-muted)",
} as const;
