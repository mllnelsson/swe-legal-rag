import { useCallback, useEffect, useRef, useState } from "react";
import { Link, useLocation, useNavigate, useParams } from "react-router";

import { Icon } from "../../components/display/Icon";
import { Composer } from "./Composer";
import { ConversationPanel } from "./ConversationPanel";
import { TurnView } from "./TurnView";
import { useAgentConversation } from "./useAgentConversation";

/** The question handed over from the home page's agent toggle.
 *
 *  Router state rather than a query parameter: the question is not part of the
 *  conversation's address, and putting it there meant arriving, asking, and then
 *  rewriting the URL to drop it again so a reload would not re-ask. State is not
 *  in the URL to begin with, so a reload cannot re-ask — the same promise, one
 *  navigation instead of two. */
type HandedOverQuestion = { question?: string };

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
  const { state } = useLocation();
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
  const [panelOpen, setPanelOpen] = useState(false);

  // A conversation the route names is one the server already holds. Empty, that
  // means its only turn never finished — not that nothing was ever asked.
  const reopened = routeSessionId !== undefined;

  const initial = (state as HandedOverQuestion | null)?.question;

  // Asked once per visit. The ref, not the state's absence, is what closes it:
  // router state survives a re-render, so without the guard a question would be
  // re-asked every time this effect's dependencies changed.
  useEffect(() => {
    if (handedOver.current || initial === undefined || initial.trim() === "") return;
    handedOver.current = true;
    ask(initial);
  }, [initial, ask]);

  useEffect(() => {
    end.current?.scrollIntoView({ behavior: "smooth", block: "end" });
  }, [turns]);

  return (
    <main
      style={{
        display: "flex",
        justifyContent: "center",
        padding: "var(--space-7) var(--gutter-page) var(--space-11)",
        background: "var(--surface-page)",
        minHeight: "calc(100vh - var(--section-gap))",
      }}
    >
      {/* One column, centred. The conversation is the only thing on this page,
          so nothing sits beside it. */}
      <div
        style={{
          width: "100%",
          maxWidth: "var(--measure-prose)",
          display: "flex",
          flexDirection: "column",
          gap: "var(--space-9)",
        }}
      >
        <PageActions onOpenPanel={() => setPanelOpen(true)} />

        {failedToLoad && <LoadFailure />}
        {loading && !failedToLoad && <Loading />}
        {turns.length === 0 && !loading && !failedToLoad ? (
          reopened ? <NothingKept /> : <EmptyState onPick={ask} />
        ) : null}

        {turns.map((turn) => (
          <TurnView key={turn.key} turn={turn} />
        ))}

        <Composer
          onSubmit={ask}
          onStop={stop}
          busy={busy}
          autoFocus={turns.length === 0}
        />

        {/* The scroll anchor sits *after* the composer, not before it. A finished
            turn runs well past a screen, and an anchor above the composer scrolls
            the newest text to the bottom edge with the box the reader needs next
            just below the fold. Anchoring past it keeps the composer on screen
            through the whole turn without a sticky box overlapping the answer. */}
        <div ref={end} />
      </div>

      <ConversationPanel
        open={panelOpen}
        onClose={() => setPanelOpen(false)}
        openSessionId={routeSessionId}
      />
    </main>
  );
}

/** The two things this page offers besides the conversation itself.
 *
 *  "Nytt samtal" stays on screen rather than moving into the panel with the
 *  list: starting over is a primary action, and one behind a button a reader
 *  has to know to press is one they will reach for the browser's back arrow
 *  instead of. */
function PageActions({ onOpenPanel }: { onOpenPanel: () => void }) {
  return (
    <div style={{ display: "flex", gap: "var(--space-4)" }}>
      <Link to="/agent" style={actionStyle}>
        <Icon name="plus" size={14} />
        Nytt samtal
      </Link>
      <button type="button" onClick={onOpenPanel} style={actionStyle}>
        <Icon name="history" size={14} />
        Tidigare samtal
      </button>
    </div>
  );
}

/** A conversation that was named but holds nothing.
 *
 *  The API appends a turn only after `done`, so a first question that failed or
 *  was abandoned leaves a real session row with an empty history. Rendering the
 *  new-conversation empty state over that would say "ask me something" about a
 *  conversation where something *was* asked and is now gone — the one reading
 *  the reader cannot check and the only one that is false. */
function NothingKept() {
  return (
    <p style={{ ...mutedStyle, display: "flex", alignItems: "flex-start", gap: "var(--space-2)" }}>
      <Icon name="info" size={16} />
      Det här samtalet är tomt. Frågan slutfördes aldrig, och det som inte når
      fram sparas inte — ställ den gärna igen här.
    </p>
  );
}

const actionStyle = {
  display: "inline-flex",
  alignItems: "center",
  gap: "var(--space-2)",
  height: "var(--control-h-sm)",
  padding: "0 var(--space-4)",
  borderRadius: "var(--radius-sm)",
  border: "1px solid var(--border-default)",
  background: "var(--surface-card)",
  fontFamily: "var(--font-sans)",
  fontSize: "var(--text-small-size)",
  fontWeight: "var(--weight-semibold)",
  color: "var(--text-strong)",
  textDecoration: "none",
  cursor: "pointer",
} as const;

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

/* Three questions the corpus can actually answer, and three different shapes of
 * question: one about a rule, one that counts, one about a single decision. They
 * are here because a blank box asks the reader to guess both what this holds and
 * how to address it, and neither guess is one a first-time reader should have to
 * make. Written by hand, not drawn from the corpus: a suggestion that changed with
 * the data would be a claim about what the data contains. */
const EXAMPLE_QUESTIONS = [
  "Vad krävs för att ett beslut ska upphävas på formell grund?",
  "Hur ofta bifaller nämnden ett överklagande?",
  "Vad har nämnden sagt om jäv i kyrkoråd?",
];

function EmptyState({ onPick }: { onPick: (question: string) => void }) {
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

      <ul
        style={{
          listStyle: "none",
          margin: "var(--space-4) 0 0",
          padding: 0,
          display: "flex",
          flexDirection: "column",
          gap: "var(--space-3)",
        }}
      >
        {EXAMPLE_QUESTIONS.map((question) => (
          <li key={question}>
            <button type="button" onClick={() => onPick(question)} style={exampleStyle}>
              {question}
            </button>
          </li>
        ))}
      </ul>
    </div>
  );
}

const exampleStyle = {
  width: "fit-content",
  maxWidth: "100%",
  textAlign: "left",
  padding: "var(--space-3) var(--space-5)",
  borderRadius: "var(--radius-pill)",
  border: "1px solid var(--border-default)",
  background: "var(--surface-card)",
  fontFamily: "var(--font-sans)",
  fontSize: "var(--text-small-size)",
  color: "var(--text-body)",
  cursor: "pointer",
  transition: "var(--transition-control)",
} as const;

const mutedStyle = {
  margin: 0,
  fontFamily: "var(--font-sans)",
  fontSize: "var(--text-body-size)",
  color: "var(--text-muted)",
} as const;
