import { useEffect, useRef } from "react";
import { useSearchParams } from "react-router";

import { Composer } from "./Composer";
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
 *  The left column is deliberately empty. Listing and reopening past
 *  conversations needs read endpoints the API does not have yet; the layout
 *  leaves the room so adding them does not move the transcript. */
export function AgentPage() {
  const [params, setParams] = useSearchParams();
  const { turns, busy, ask, stop } = useAgentConversation();
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
          maxWidth: "var(--measure-prose)",
          display: "flex",
          flexDirection: "column",
          gap: "var(--space-9)",
        }}
      >
        {turns.length === 0 ? <EmptyState /> : null}

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
    </main>
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
