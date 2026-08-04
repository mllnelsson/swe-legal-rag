import React from "react";

export function Switch({ checked = false, onChange, label, disabled, style = {} }) {
  return (
    <label style={{ display: "inline-flex", alignItems: "center", gap: "var(--space-4)", cursor: disabled ? "not-allowed" : "pointer", opacity: disabled ? 0.5 : 1, fontFamily: "var(--font-sans)", ...style }}>
      <span
        onClick={() => !disabled && onChange && onChange(!checked)}
        style={{
          width: 36, height: 20, flex: "none", padding: 2, borderRadius: "var(--radius-pill)",
          background: checked ? "var(--action-primary)" : "var(--warm-300)",
          transition: "background-color var(--dur-base) var(--ease-standard)",
          display: "flex", alignItems: "center",
        }}
      >
        <span style={{ width: 16, height: 16, borderRadius: "var(--radius-pill)", background: "#fff", boxShadow: "var(--shadow-sm)", transform: `translateX(${checked ? 16 : 0}px)`, transition: "transform var(--dur-base) var(--ease-standard)" }} />
      </span>
      {label && <span style={{ fontSize: "var(--text-body-size)", color: "var(--text-strong)" }}>{label}</span>}
    </label>
  );
}
