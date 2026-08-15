import { Icon } from "../../components/display/Icon";
import { AnswerBody } from "./AnswerBody";
import { SourceList } from "./SourceList";
import { SqlEvidence } from "./SqlEvidence";
import { TurnSteps } from "./TurnSteps";
import type { Turn } from "./conversation";

export type TurnViewProps = {
  turn: Turn;
};

/** One question and everything that came back from it. */
export function TurnView({ turn }: TurnViewProps) {
  const streaming = turn.status === "streaming";

  return (
    <article
      style={{ display: "flex", flexDirection: "column", gap: "var(--space-6)" }}
    >
      <h2
        style={{
          margin: 0,
          fontFamily: "var(--font-display)",
          fontSize: "var(--text-h2-size)",
          lineHeight: "var(--text-h2-lh)",
          letterSpacing: "var(--text-h2-ls)",
          fontWeight: "var(--weight-regular)",
          color: "var(--text-strong)",
        }}
      >
        {turn.question}
      </h2>

      <TurnSteps steps={turn.steps} streaming={streaming} />

      {/* Before the prose, so the query is on screen while the number is read. */}
      <SqlEvidence events={turn.sql} />

      {turn.answer !== "" && <AnswerBody text={turn.answer} streaming={streaming} />}

      {turn.status === "error" && <TurnNotice tone="error" text={turn.error} />}

      {turn.status === "aborted" && (
        <TurnNotice
          tone="warn"
          text={
            "Frågan avbröts. Svaret är ofullständigt, och agenten minns inte den " +
            "här frågan i nästa fråga."
          }
        />
      )}

      {/* Gated on the frame having arrived, not on the turn having finished: a
          turn that failed before `sources` has none to show, and one that got
          them has them whatever happened next. */}
      <SourceList sources={turn.sources} received={turn.sourcesReceived} />

      {turn.interactionId !== null && turn.status !== "streaming" && (
        <p
          style={{
            margin: 0,
            fontFamily: "var(--font-sans)",
            fontSize: "var(--text-caption-size)",
            color: "var(--text-faint)",
          }}
        >
          Referens{" "}
          <span style={{ fontFamily: "var(--font-mono)" }}>{turn.interactionId}</span>
        </p>
      )}
    </article>
  );
}

/** A failed or abandoned turn says which it was.
 *
 *  `error` is terminal in the contract — no `done` follows one — so the UI must
 *  stop waiting rather than leave a spinner running for something that will
 *  never arrive. */
function TurnNotice({ tone, text }: { tone: "error" | "warn"; text: string | null }) {
  const colors =
    tone === "error"
      ? { background: "var(--status-error-bg)", color: "var(--status-error-fg)" }
      : { background: "var(--status-warn-bg)", color: "var(--status-warn-fg)" };

  return (
    <p
      role="status"
      style={{
        margin: 0,
        display: "flex",
        alignItems: "flex-start",
        gap: "var(--space-3)",
        padding: "var(--space-4) var(--space-5)",
        borderRadius: "var(--radius-md)",
        fontFamily: "var(--font-sans)",
        fontSize: "var(--text-small-size)",
        lineHeight: "var(--text-small-lh)",
        ...colors,
      }}
    >
      <Icon name={tone === "error" ? "circle-alert" : "triangle-alert"} size={16} />
      {text ?? "Något gick fel."}
    </p>
  );
}
