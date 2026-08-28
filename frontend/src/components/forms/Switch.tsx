import { useState, type CSSProperties } from "react";

export type SwitchSize = "sm" | "lg";

/* The design system draws the small switch at a fixed 36×20 track with a 16px
   knob; the spacing scale has no step for a control this small. `lg` is the
   prominent variant used for the home page's mode toggle, where the switch has
   to be the easy-to-find thing on the screen. Knob travel is track width minus
   knob size minus the two 2px padding steps. */
const TRACK: Record<SwitchSize, { width: string; height: string; knob: string; travel: string }> = {
  sm: { width: "36px", height: "20px", knob: "16px", travel: "16px" }, // token-exempt: fixed switch geometry
  lg: { width: "52px", height: "30px", knob: "24px", travel: "22px" }, // token-exempt: fixed switch geometry
};

const LABEL_SIZE: Record<SwitchSize, string> = {
  sm: "var(--text-small-size)",
  lg: "var(--text-body-size)",
};

export type SwitchProps = {
  checked: boolean;
  onChange: (checked: boolean) => void;
  /** Names the switch for assistive tech and labels it on screen. */
  label: string;
  /** One line under the label saying what turning it on does. */
  hint?: string | undefined;
  /** `lg` for a control that has to stand out; `sm` (default) for everything else. */
  size?: SwitchSize;
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
  size = "sm",
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
        <Track checked={checked} focus={focus} size={size} />
        <span
          style={{
            fontSize: LABEL_SIZE[size],
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

function Track({ checked, focus, size }: { checked: boolean; focus: boolean; size: SwitchSize }) {
  const geometry = TRACK[size];
  return (
    <span
      aria-hidden="true"
      style={{
        width: geometry.width,
        height: geometry.height,
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
          width: geometry.knob,
          height: geometry.knob,
          borderRadius: "var(--radius-pill)",
          background: "var(--paper)",
          boxShadow: "var(--shadow-sm)",
          transform: checked ? `translateX(${geometry.travel})` : "translateX(0)",
          transition: "transform var(--dur-base) var(--ease-standard)",
        }}
      />
    </span>
  );
}
