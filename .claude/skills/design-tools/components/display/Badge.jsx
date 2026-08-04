import React from "react";

const tones = {
  neutral: { background: "var(--warm-100)", color: "var(--text-body)", border: "var(--border-hairline)" },
  binding: { background: "var(--burgundy-50)", color: "var(--burgundy-600)", border: "var(--burgundy-200)" },
  persuasive: { background: "var(--apricot-100)", color: "var(--apricot-700)", border: "var(--apricot-200)" },
  ok: { background: "var(--status-ok-bg)", color: "var(--status-ok-fg)", border: "var(--status-ok-bg)" },
  warn: { background: "var(--status-warn-bg)", color: "var(--status-warn-fg)", border: "var(--status-warn-bg)" },
  error: { background: "var(--status-error-bg)", color: "var(--status-error-fg)", border: "var(--status-error-bg)" },
  info: { background: "var(--status-info-bg)", color: "var(--status-info-fg)", border: "var(--status-info-bg)" },
};

export function Badge({ children, tone = "neutral", icon, style = {} }) {
  const t = tones[tone];
  return (
    <span style={{
      display: "inline-flex", alignItems: "center", gap: "var(--space-2)", height: 21, padding: "0 var(--space-3)",
      borderRadius: "var(--radius-xs)", background: t.background, color: t.color, border: `1px solid ${t.border}`,
      fontFamily: "var(--font-sans)", fontSize: "var(--text-caption-size)", fontWeight: "var(--weight-semibold)",
      letterSpacing: "0.01em", whiteSpace: "nowrap", ...style,
    }}>{icon}{children}</span>
  );
}
