import { useState, type CSSProperties } from "react";

/* The design system draws the switch at a fixed 36×20 track with a 16px knob;
   the spacing scale has no step for a control this small. */
const TRACK_WIDTH = "36px"; // token-exempt: fixed switch geometry
const TRACK_HEIGHT = "20px"; // token-exempt: fixed switch geometry
const KNOB_SIZE = "16px"; // token-exempt: fixed switch geometry
const KNOB_TRAVEL = "16px"; // token-exempt: knob travel is track minus knob

export type SwitchProps = {
  checked: boolean;
  onChange: (checked: boolean) => void;
  /** Names the switch for assistive tech and labels it on screen. */
  label: string;
  /** One line under the label saying what turning it on does. */
  hint?: string | undefined;
  disabled?: boolean;
  style?: CSSProperties;
};

/** A two-state control for a choice the reader makes before acting.
 *
 *  A real `<button role="switch">` rather than the design system's clickable
 *  span: this is the only control on the home page besides the box itself, and
 *  one a keyboard cannot reach is one half the readers of a legal-research tool
 *  cannot use. Space and Enter come free with the element. */
export function Switch({
  checked,
  onChange,
  label,
  hint,
  disabled = false,
  style,
}: SwitchProps) {
  const [focus, setFocus] = useState(false);

  return (
    <div
      style={{
        display: "flex",
        flexDirection: "column",
        alignItems: "center",
        gap: "var(--space-2)",
        fontFamily: "var(--font-sans)",
        ...style,
      }}
    >
      <button
        type="button"
        role="switch"
        aria-checked={checked}
        disabled={disabled}
        onClick={() => onChange(!checked)}
        onFocus={() => setFocus(true)}
        onBlur={() => setFocus(false)}
        style={{
          display: "inline-flex",
          alignItems: "center",
          gap: "var(--space-4)",
          padding: 0,
          border: "none",
          background: "transparent",
          font: "inherit",
          cursor: disabled ? "not-allowed" : "pointer",
          opacity: disabled ? 0.42 : 1,
        }}
      >
        <Track checked={checked} focus={focus} />
        <span
          style={{
            fontSize: "var(--text-small-size)",
            fontWeight: "var(--weight-semibold)",
            color: checked ? "var(--text-strong)" : "var(--text-muted)",
            transition: "var(--transition-control)",
          }}
        >
          {label}
        </span>
      </button>

      {/* Reserved whether or not it says anything, so switching does not move
          the control above it. */}
      {hint !== undefined && (
        <p
          style={{
            margin: 0,
            maxWidth: "var(--measure-narrow)",
            textAlign: "center",
            fontSize: "var(--text-caption-size)",
            lineHeight: "var(--text-caption-lh)",
            color: "var(--text-muted)",
          }}
        >
          {hint}
        </p>
      )}
    </div>
  );
}

function Track({ checked, focus }: { checked: boolean; focus: boolean }) {
  return (
    <span
      aria-hidden="true"
      style={{
        width: TRACK_WIDTH,
        height: TRACK_HEIGHT,
        flex: "none",
        padding: "var(--space-1)",
        borderRadius: "var(--radius-pill)",
        background: checked ? "var(--action-primary)" : "var(--warm-300)",
        boxShadow: focus ? "var(--ring-focus)" : "none",
        display: "flex",
        alignItems: "center",
        transition:
          "background-color var(--dur-base) var(--ease-standard), box-shadow var(--dur-fast) var(--ease-standard)",
      }}
    >
      <span
        style={{
          width: KNOB_SIZE,
          height: KNOB_SIZE,
          borderRadius: "var(--radius-pill)",
          background: "var(--paper)",
          boxShadow: "var(--shadow-sm)",
          transform: checked ? `translateX(${KNOB_TRAVEL})` : "translateX(0)",
          transition: "transform var(--dur-base) var(--ease-standard)",
        }}
      />
    </span>
  );
}
