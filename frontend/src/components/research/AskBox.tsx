import { useState, type CSSProperties } from "react";

import { Icon } from "../display/Icon";

/** token-exempt: matches the scope pill in the skill's SearchField; no token. */
const SCOPE_PILL_HEIGHT = "28px";

export type AskBoxProps = {
  value: string;
  onChange: (value: string) => void;
  onSubmit: (value: string) => void;
  placeholder?: string;
  /** Short note on what the search is currently narrowed to, e.g. "3 filter".
   *  Purely informational — the box does not interpret it. */
  scope?: string | undefined;
  submitLabel?: string;
  disabled?: boolean;
  /** Larger presentation for the empty search screen. */
  size?: "md" | "lg";
  autoFocus?: boolean;
  style?: CSSProperties;
};

/** The product's one hero control, and deliberately the dumbest thing in the app.
 *
 *  It takes text and hands it to the caller. It does not decompose the question,
 *  plan filters, call a model, or stream anything back. What the user types goes
 *  to POST /api/search verbatim; every word they read afterwards is either the
 *  nämnd's own text or a label we wrote.
 *
 *  One per screen. */
export function AskBox({
  value,
  onChange,
  onSubmit,
  placeholder = "Sök i nämndens beslut",
  scope,
  submitLabel = "Sök",
  disabled = false,
  size = "md",
  autoFocus = false,
  style,
}: AskBoxProps) {
  const [focus, setFocus] = useState(false);

  return (
    <form
      onSubmit={(event) => {
        event.preventDefault();
        onSubmit(value);
      }}
      style={{
        display: "flex",
        alignItems: "center",
        gap: "var(--space-4)",
        padding: "var(--space-3) var(--space-3) var(--space-3) var(--space-6)",
        background: "var(--surface-card)",
        border: `1px solid ${focus ? "var(--apricot-400)" : "var(--border-hairline)"}`,
        borderRadius: "var(--radius-xl)",
        boxShadow: focus ? "var(--ring-focus), var(--shadow-md)" : "var(--shadow-md)",
        transition: "var(--transition-control)",
        fontFamily: "var(--font-sans)",
        ...style,
      }}
    >
      <Icon name="search" size={20} color="var(--burgundy-600)" />
      <input
        value={value}
        disabled={disabled}
        placeholder={placeholder}
        aria-label="Sökfråga"
        autoFocus={autoFocus}
        onChange={(event) => onChange(event.target.value)}
        onFocus={() => setFocus(true)}
        onBlur={() => setFocus(false)}
        style={{
          flex: 1,
          minWidth: 0,
          border: "none",
          outline: "none",
          background: "transparent",
          font: "inherit",
          fontSize: size === "lg" ? "var(--text-body-lg-size)" : "var(--text-body-size)",
          color: "var(--text-strong)",
        }}
      />
      {scope !== undefined && (
        <span
          style={{
            display: "inline-flex",
            alignItems: "center",
            gap: "var(--space-2)",
            padding: "0 var(--space-4)",
            height: SCOPE_PILL_HEIGHT,
            borderRadius: "var(--radius-pill)",
            background: "var(--apricot-50)",
            border: "1px solid var(--apricot-200)",
            color: "var(--burgundy-600)",
            fontSize: "var(--text-caption-size)",
            fontWeight: "var(--weight-semibold)",
            whiteSpace: "nowrap",
          }}
        >
          <Icon name="funnel" size={13} />
          {scope}
        </span>
      )}
      <button
        type="submit"
        disabled={disabled || value.trim() === ""}
        style={{
          height: "var(--control-h-md)",
          padding: "0 var(--space-6)",
          borderRadius: "var(--radius-pill)",
          border: "1px solid var(--burgundy-700)",
          background: "var(--action-primary)",
          color: "var(--apricot-50)",
          font: "inherit",
          fontSize: "var(--text-small-size)",
          fontWeight: "var(--weight-semibold)",
          cursor: disabled || value.trim() === "" ? "not-allowed" : "pointer",
          opacity: disabled || value.trim() === "" ? 0.42 : 1,
          transition: "var(--transition-control)",
        }}
      >
        {submitLabel}
      </button>
    </form>
  );
}
