import React from "react";

export function Radio({ label, description, checked = false, onChange, name, disabled, style = {} }) {
  return (
    <label style={{ display: "flex", gap: "var(--space-4)", alignItems: "flex-start", cursor: disabled ? "not-allowed" : "pointer", opacity: disabled ? 0.5 : 1, fontFamily: "var(--font-sans)", ...style }}>
      <input type="radio" name={name} checked={checked} disabled={disabled} onChange={() => onChange && onChange(true)} style={{ position: "absolute", opacity: 0, width: 0, height: 0 }} />
      <span style={{ width: 17, height: 17, marginTop: 1, flex: "none", borderRadius: "var(--radius-pill)", border: `1px solid ${checked ? "var(--burgundy-600)" : "var(--border-strong)"}`, background: "var(--surface-card)", display: "inline-flex", alignItems: "center", justifyContent: "center", transition: "var(--transition-control)" }}>
        {checked && <span style={{ width: 8, height: 8, borderRadius: "var(--radius-pill)", background: "var(--action-primary)" }} />}
      </span>
      <span style={{ display: "flex", flexDirection: "column", gap: 2 }}>
        <span style={{ fontSize: "var(--text-body-size)", color: "var(--text-strong)" }}>{label}</span>
        {description && <span style={{ fontSize: "var(--text-caption-size)", color: "var(--text-muted)" }}>{description}</span>}
      </span>
    </label>
  );
}
