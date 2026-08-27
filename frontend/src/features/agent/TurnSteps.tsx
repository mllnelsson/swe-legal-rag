import { useEffect, useRef, useState } from "react";

import { Icon } from "../../components/display/Icon";
import type { IconName } from "../../components/display/icon-paths";
import type { Step } from "./conversation";
import { isStepFailure, progressDetailText, progressText } from "./progress-text";

export type TurnStepsProps = {
  steps: Step[];
  /** While the turn is open the last step is what is happening right now. */
  streaming: boolean;
  /** True once the answer has begun arriving.
   *
   *  What the agent did matters most while it is the only thing there is to
   *  look at. Once prose is landing, the steps are provenance rather than
   *  news, so they get out of the way of the thing the reader came for. */
  writing?: boolean;
};

/** token-exempt: the marker column is sized to the 14px glyph it holds. */
const MARKER_SIZE = "18px";

/** token-exempt: a 2px rule width, the same class as a border. */
const ACCENT_RULE = "2px";

const TICK_MS = 1000;

function markerFor(step: Step): { name: IconName; color: string } {
  if (step.status === null) return { name: "chevron-right", color: "var(--text-faint)" };
  if (isStepFailure(step.status)) {
    return { name: "triangle-alert", color: "var(--status-error-fg)" };
  }
  // A refusal is a step the agent repairs from, not a problem the reader has to
  // act on, so it gets an ordinary informational marker.
  if (step.status === "refused") return { name: "info", color: "var(--text-muted)" };
  return { name: "check", color: "var(--status-ok-fg)" };
}

/** Whole seconds since this turn started working.
 *
 *  Counted here rather than carried on the turn because it is a property of
 *  watching, not of the conversation: a turn read back out of a session has no
 *  meaningful elapsed time, and nothing about it should be persisted.
 *
 *  It is the honest form of a progress bar. The agent cannot say how far along
 *  it is — it does not know how many tools it will reach for, nor how long each
 *  will take — but it can say how long it has been going. A count that keeps
 *  climbing is what tells the reader it is still working rather than stuck. */
function useElapsedSeconds(running: boolean): number {
  const startedAt = useRef<number | null>(null);
  const [seconds, setSeconds] = useState(0);

  useEffect(() => {
    if (!running) return;
    startedAt.current ??= Date.now();
    const started = startedAt.current;
    const tick = () => setSeconds(Math.floor((Date.now() - started) / TICK_MS));
    tick();
    const timer = window.setInterval(tick, TICK_MS);
    return () => window.clearInterval(timer);
  }, [running]);

  return seconds;
}

/** How long the step running right now has been running.
 *
 *  Resets when the running step changes, so it measures this step and not the
 *  turn. It fills the one gap the turn counter cannot: a single step that sits
 *  open while the steps around it do not move — the SQL sub-agent's own loop
 *  behind `query_corpus` is several model round-trips reported as one step, and
 *  a slow reading is another — long enough to read as stuck. */
function useRunningStepSeconds(stepId: string | undefined): number {
  const runningStep = useRef<{ id: string; at: number } | null>(null);
  const [seconds, setSeconds] = useState(0);

  useEffect(() => {
    if (stepId === undefined) {
      runningStep.current = null;
      setSeconds(0);
      return;
    }
    if (runningStep.current?.id !== stepId) {
      runningStep.current = { id: stepId, at: Date.now() };
    }
    const started = runningStep.current.at;
    const tick = () => setSeconds(Math.floor((Date.now() - started) / TICK_MS));
    tick();
    const timer = window.setInterval(tick, TICK_MS);
    return () => window.clearInterval(timer);
  }, [stepId]);

  return seconds;
}

/** How long a reader may wait before the first token, and a big question can run
 *  for minutes. Past this the steps alone read as a stall, so a plain-language
 *  line says the wait is expected. */
const LONG_WAIT_SECONDS = 30;

/** A single step open longer than this reads as stuck rather than working — the
 *  SQL sub-loop behind `query_corpus` runs several model round-trips here — so a
 *  quiet note on that step says it is still going. Shorter than the turn-level
 *  ceiling, because one stalled step is legible well before the whole turn is. */
const STEP_SLOW_SECONDS = 8;

/** What the agent did, in the order it did it.
 *
 *  The reason the progress events exist: tens of seconds pass before the first
 *  token — and a question that searches and reads several decisions runs for
 *  minutes — so this is what makes that wait legible rather than blank. It was
 *  legible in the strict sense and almost invisible in practice — 13px, grey,
 *  4px apart, no movement — so while the wait is all there is, it is the loudest
 *  thing on the page. */
export function TurnSteps({ steps, streaming, writing = false }: TurnStepsProps) {
  const thinking = streaming && !writing;
  const seconds = useElapsedSeconds(streaming);
  // The open step, if any: at most one is unfinished at a time, since a
  // `tool_result` closes the `tool_call` it matches before the next begins.
  const runningStepId = streaming
    ? steps.find((step) => step.status === null)?.id
    : undefined;
  const stepSeconds = useRunningStepSeconds(runningStepId);

  if (steps.length === 0 && !streaming) return null;

  const list = (
    <ol
      aria-label="Agentens arbetssteg"
      style={{
        listStyle: "none",
        margin: 0,
        padding: 0,
        display: "flex",
        flexDirection: "column",
        gap: thinking ? "var(--space-4)" : "var(--space-2)",
        fontFamily: "var(--font-sans)",
        fontSize: thinking ? "var(--text-body-size)" : "var(--text-small-size)",
        lineHeight: thinking ? "var(--text-body-lh)" : "var(--text-small-lh)",
      }}
    >
      {steps.map((step) => {
        const phase = step.status === null ? "running" : "finished";
        const running = phase === "running" && streaming;
        const marker = markerFor(step);
        const detail = progressDetailText(step.label, step.detail, phase);
        return (
          <li
            key={step.id}
            style={{ display: "flex", gap: "var(--space-3)", alignItems: "baseline" }}
          >
            <span
              aria-hidden="true"
              className={running ? "step-active-marker" : undefined}
              style={{
                width: MARKER_SIZE,
                flex: "none",
                color: marker.color,
                display: "inline-flex",
                justifyContent: "center",
              }}
            >
              <Icon name={marker.name} size={14} />
            </span>
            <span style={{ color: running ? "var(--text-body)" : "var(--text-muted)" }}>
              <span className={running ? "step-active-label" : undefined}>
                {progressText(step.label, phase)}
              </span>
              {detail !== null && (
                <span style={{ color: "var(--text-faint)" }}> — {detail}</span>
              )}
              {/* Only on the step running right now, and only once it has been
                  running a while: the SQL sub-loop and a slow reading are the
                  steps that sit here longest with nothing else moving. */}
              {running &&
                step.id === runningStepId &&
                stepSeconds >= STEP_SLOW_SECONDS && (
                  <span style={{ color: "var(--text-faint)" }}> — tar en stund…</span>
                )}
            </span>
          </li>
        );
      })}

      {/* The first tool call is itself a model round trip away, so this covers
          the seconds before there is any step at all to show. */}
      {streaming && steps.length === 0 && (
        <li style={{ display: "flex", gap: "var(--space-3)", alignItems: "baseline" }}>
          <span
            aria-hidden="true"
            className="step-active-marker"
            style={{
              width: MARKER_SIZE,
              flex: "none",
              color: "var(--text-faint)",
              display: "inline-flex",
              justifyContent: "center",
            }}
          >
            <Icon name="chevron-right" size={14} />
          </span>
          <span className="step-active-label" style={{ color: "var(--text-body)" }}>
            Läser frågan
          </span>
        </li>
      )}
    </ol>
  );

  if (!thinking) {
    // Finished, or overtaken by the answer. Kept on the page and kept open
    // unless prose has arrived to take the attention.
    return writing ? (
      <details style={{ fontFamily: "var(--font-sans)" }}>
        <summary
          style={{
            cursor: "pointer",
            fontSize: "var(--text-small-size)",
            color: "var(--text-muted)",
          }}
        >
          {summarise(steps, seconds)}
        </summary>
        <div style={{ marginTop: "var(--space-4)" }}>{list}</div>
      </details>
    ) : (
      list
    );
  }

  return (
    <section
      aria-label="Agenten arbetar"
      style={{
        padding: "var(--space-6)",
        borderRadius: "var(--radius-lg)",
        background: "var(--surface-accent)",
        boxShadow: "var(--shadow-xs)",
      }}
    >
      {/* The ember gradient, which the design system allows only as a rule this
          thin. Drawn as an element rather than a `border-image`, which would
          ignore the card's own corner radius and square its top off. */}
      <div
        aria-hidden="true"
        style={{
          height: ACCENT_RULE,
          borderRadius: "var(--radius-pill)",
          background: "var(--gradient-ember)",
          marginBottom: "var(--space-5)",
        }}
      />

      <div
        style={{
          display: "flex",
          alignItems: "baseline",
          justifyContent: "space-between",
          gap: "var(--space-4)",
          marginBottom: "var(--space-5)",
        }}
      >
        <span
          style={{
            fontFamily: "var(--font-sans)",
            fontSize: "var(--text-overline-size)",
            letterSpacing: "var(--text-overline-ls)",
            fontWeight: "var(--text-overline-weight)",
            textTransform: "uppercase",
            color: "var(--burgundy-600)",
          }}
        >
          Agenten arbetar
        </span>
        {/* `aria-live` deliberately absent: a screen reader announcing a new
            number every second would drown out the steps themselves. */}
        <span
          style={{
            fontFamily: "var(--font-mono)",
            fontSize: "var(--text-caption-size)",
            color: "var(--text-muted)",
          }}
        >
          {`${seconds} s`}
        </span>
      </div>

      {list}

      {/* A big question — one that searches, then reads several decisions — runs
          well past the first-token wait, and the steps alone can sit unchanged
          long enough to read as a stall. This says the wait is expected rather
          than a fault, so the reader holds on rather than reaching for reload. */}
      {seconds >= LONG_WAIT_SECONDS && (
        <p
          style={{
            margin: "var(--space-5) 0 0",
            fontFamily: "var(--font-sans)",
            fontSize: "var(--text-small-size)",
            lineHeight: "var(--text-small-lh)",
            color: "var(--text-muted)",
          }}
        >
          Större frågor kan ta ett par minuter — den arbetar fortfarande.
        </p>
      )}
    </section>
  );
}

/** "4 steg · 21 s" — what the block says once it has folded itself away. */
function summarise(steps: Step[], seconds: number): string {
  const count = steps.length === 1 ? "1 steg" : `${steps.length} steg`;
  return `${count} · ${seconds} s`;
}
