import React from "react";

export function Tabs({ tabs = [], value, onChange, variant = "underline", style = {} }) {
  const items = tabs.map((t) => (typeof t === "string" ? { value: t, label: t } : t));
  const active = value ?? items[0]?.value;
  if (variant === "pill") {
    return (
      <div style={{ display: "inline-flex", gap: "var(--space-1)", padding: 3, background: "var(--surface-sunken)", borderRadius: "var(--radius-pill)", fontFamily: "var(--font-sans)", ...style }}>
        {items.map((t) => (
          <button key={t.value} onClick={() => onChange && onChange(t.value)} style={{
            height: 30, padding: "0 var(--space-5)", border: "none", borderRadius: "var(--radius-pill)", cursor: "pointer",
            background: t.value === active ? "var(--surface-card)" : "transparent",
            boxShadow: t.value === active ? "var(--shadow-xs)" : "none",
            color: t.value === active ? "var(--text-strong)" : "var(--text-muted)",
            font: "inherit", fontSize: "var(--text-small-size)", fontWeight: "var(--weight-semibold)",
            transition: "var(--transition-control)",
          }}>{t.label}</button>
        ))}
      </div>
    );
  }
  return (
    <div style={{ display: "flex", gap: "var(--space-7)", borderBottom: "1px solid var(--border-hairline)", fontFamily: "var(--font-sans)", ...style }}>
      {items.map((t) => (
        <button key={t.value} onClick={() => onChange && onChange(t.value)} style={{
          position: "relative", padding: "0 0 var(--space-4)", border: "none", background: "transparent", cursor: "pointer",
          color: t.value === active ? "var(--text-strong)" : "var(--text-muted)",
          font: "inherit", fontSize: "var(--text-body-size)", fontWeight: "var(--weight-semibold)",
          boxShadow: t.value === active ? "inset 0 -2px 0 var(--burgundy-600)" : "none",
          transition: "var(--transition-control)",
        }}>
          {t.label}
          {t.count != null && <span style={{ marginLeft: "var(--space-3)", color: "var(--text-faint)", fontWeight: "var(--weight-regular)" }}>{t.count}</span>}
        </button>
      ))}
    </div>
  );
}
