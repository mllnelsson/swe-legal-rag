import React from "react";
import { Icon } from "../display/Icon.jsx";

export function Input({ label, hint, error, iconLeft, size = "md", disabled, id, style = {}, ...rest }) {
  const [focus, setFocus] = React.useState(false);
  const uid = id || React.useId();
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: "var(--space-3)", fontFamily: "var(--font-sans)" }}>
      {label && (
        <label htmlFor={uid} style={{ fontSize: "var(--text-small-size)", fontWeight: "var(--weight-semibold)", color: "var(--text-strong)" }}>
          {label}
        </label>
      )}
      <div
        style={{
          display: "flex", alignItems: "center", gap: "var(--space-3)",
          height: size === "sm" ? "var(--control-h-sm)" : size === "lg" ? "var(--control-h-lg)" : "var(--control-h-md)",
          padding: "0 var(--space-4)", background: disabled ? "var(--surface-sunken)" : "var(--surface-card)",
          border: `1px solid ${error ? "var(--status-error-fg)" : focus ? "var(--apricot-400)" : "var(--border-default)"}`,
          borderRadius: "var(--radius-sm)",
          boxShadow: focus ? (error ? "var(--ring-error)" : "var(--ring-focus)") : "var(--shadow-xs)",
          transition: "var(--transition-control)", ...style,
        }}
      >
        {iconLeft && (typeof iconLeft === "string" ? <Icon name={iconLeft} size={16} color="var(--text-faint)" /> : iconLeft)}
        <input
          id={uid}
          disabled={disabled}
          onFocus={() => setFocus(true)}
          onBlur={() => setFocus(false)}
          {...rest}
          style={{
            flex: 1, minWidth: 0, border: "none", outline: "none", background: "transparent",
            font: "inherit", fontSize: "var(--text-body-size)", color: "var(--text-strong)",
          }}
        />
      </div>
      {(hint || error) && (
        <span style={{ fontSize: "var(--text-caption-size)", color: error ? "var(--status-error-fg)" : "var(--text-muted)" }}>{error || hint}</span>
      )}
    </div>
  );
}
