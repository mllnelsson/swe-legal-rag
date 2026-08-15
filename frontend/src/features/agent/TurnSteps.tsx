import { Icon } from "../../components/display/Icon";
import type { IconName } from "../../components/display/icon-paths";
import type { Step } from "./conversation";
import { isStepFailure, progressDetailText, progressText } from "./progress-text";

export type TurnStepsProps = {
  steps: Step[];
  /** While the turn is open the last step is what is happening right now. */
  streaming: boolean;
};

/** token-exempt: the marker column is sized to the 14px glyph it holds. */
const MARKER_SIZE = "18px";

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

/** What the agent did, in the order it did it.
 *
 *  The reason the progress events exist: roughly 18 seconds pass before the
 *  first token, and this is what makes that wait legible rather than blank. */
export function TurnSteps({ steps, streaming }: TurnStepsProps) {
  if (steps.length === 0 && !streaming) return null;

  return (
    <ol
      aria-label="Agentens arbetssteg"
      style={{
        listStyle: "none",
        margin: 0,
        padding: 0,
        display: "flex",
        flexDirection: "column",
        gap: "var(--space-2)",
        fontFamily: "var(--font-sans)",
        fontSize: "var(--text-small-size)",
        lineHeight: "var(--text-small-lh)",
      }}
    >
      {steps.map((step) => {
        const phase = step.status === null ? "running" : "finished";
        const marker = markerFor(step);
        const detail = progressDetailText(step.label, step.detail, phase);
        return (
          <li
            key={step.id}
            style={{ display: "flex", gap: "var(--space-3)", alignItems: "baseline" }}
          >
            <span
              aria-hidden="true"
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
            <span style={{ color: phase === "running" ? "var(--text-body)" : "var(--text-muted)" }}>
              {progressText(step.label, phase)}
              {detail !== null && (
                <span style={{ color: "var(--text-faint)" }}> — {detail}</span>
              )}
            </span>
          </li>
        );
      })}

      {streaming && steps.length === 0 && (
        <li style={{ color: "var(--text-muted)", paddingLeft: "var(--space-7)" }}>
          Läser frågan
        </li>
      )}
    </ol>
  );
}
