import React from "react";
import { Icon } from "../display/Icon.jsx";

const tones = {
  info: { icon: "info", fg: "var(--status-info-fg)", bg: "var(--surface-card)" },
  ok: { icon: "check", fg: "var(--status-ok-fg)", bg: "var(--surface-card)" },
  warn: { icon: "triangle-alert", fg: "var(--status-warn-fg)", bg: "var(--surface-card)" },
  error: { icon: "circle-alert", fg: "var(--status-error-fg)", bg: "var(--surface-card)" },
};

export function Toast({ tone = "info", title, message, action, onDismiss, style = {} }) {
  const t = tones[tone];
  return (
    <div role="status" style={{
      display: "flex", alignItems: "flex-start", gap: "var(--space-4)", width: 380, maxWidth: "100%",
      padding: "var(--space-5)", background: t.bg, border: "1px solid var(--border-hairline)",
      borderRadius: "var(--radius-md)", boxShadow: "var(--shadow-lg)", fontFamily: "var(--font-sans)", ...style,
    }}>
      <Icon name={t.icon} size={17} color={t.fg} style={{ marginTop: 1 }} />
      <div style={{ flex: 1, display: "flex", flexDirection: "column", gap: 2 }}>
        <span style={{ fontSize: "var(--text-body-size)", fontWeight: "var(--weight-semibold)", color: "var(--text-strong)" }}>{title}</span>
        {message && <span style={{ fontSize: "var(--text-small-size)", color: "var(--text-muted)" }}>{message}</span>}
        {action && <span style={{ marginTop: "var(--space-3)" }}>{action}</span>}
      </div>
      {onDismiss && (
        <button onClick={onDismiss} aria-label="Dismiss" style={{ border: "none", background: "transparent", cursor: "pointer", padding: 0, color: "var(--text-faint)" }}>
          <Icon name="x" size={15} />
        </button>
      )}
    </div>
  );
}
