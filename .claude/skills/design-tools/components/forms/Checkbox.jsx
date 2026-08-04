import React from "react";
import { Icon } from "../display/Icon.jsx";

export function Checkbox({ label, description, checked = false, onChange, disabled, style = {} }) {
  return (
    <label style={{ display: "flex", gap: "var(--space-4)", alignItems: "flex-start", cursor: disabled ? "not-allowed" : "pointer", opacity: disabled ? 0.5 : 1, fontFamily: "var(--font-sans)", ...style }}>
      <span
        onClick={() => !disabled && onChange && onChange(!checked)}
        style={{
          width: 17, height: 17, marginTop: 1, flex: "none", display: "inline-flex", alignItems: "center", justifyContent: "center",
          borderRadius: "var(--radius-xs)",
          border: `1px solid ${checked ? "var(--burgundy-600)" : "var(--border-strong)"}`,
          background: checked ? "var(--action-primary)" : "var(--surface-card)",
          transition: "var(--transition-control)",
        }}
      >
        {checked && <Icon name="check" size={12} color="var(--apricot-50)" />}
      </span>
      <span style={{ display: "flex", flexDirection: "column", gap: 2 }}>
        <span style={{ fontSize: "var(--text-body-size)", color: "var(--text-strong)" }}>{label}</span>
        {description && <span style={{ fontSize: "var(--text-caption-size)", color: "var(--text-muted)" }}>{description}</span>}
      </span>
    </label>
  );
}
