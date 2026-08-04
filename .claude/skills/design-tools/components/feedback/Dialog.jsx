import React from "react";
import { IconButton } from "../actions/IconButton.jsx";

export function Dialog({ open = true, title, description, children, footer, onClose, width = 520 }) {
  if (!open) return null;
  return (
    <div style={{ position: "fixed", inset: 0, zIndex: 60, display: "flex", alignItems: "center", justifyContent: "center", padding: "var(--space-8)", background: "var(--surface-overlay)", backdropFilter: "blur(2px)", fontFamily: "var(--font-sans)" }}>
      <div role="dialog" aria-modal="true" style={{ width, maxWidth: "100%", background: "var(--surface-card)", borderRadius: "var(--radius-lg)", boxShadow: "var(--shadow-overlay)", overflow: "hidden", animation: "none" }}>
        <div style={{ display: "flex", alignItems: "flex-start", gap: "var(--space-5)", padding: "var(--space-7) var(--space-7) var(--space-5)" }}>
          <div style={{ flex: 1, display: "flex", flexDirection: "column", gap: "var(--space-2)" }}>
            <h3 style={{ fontFamily: "var(--font-display)", fontSize: "var(--text-h3-size)", lineHeight: "var(--text-h3-lh)", color: "var(--text-strong)", margin: 0 }}>{title}</h3>
            {description && <p style={{ margin: 0, fontSize: "var(--text-body-size)", lineHeight: "var(--text-body-lh)", color: "var(--text-muted)" }}>{description}</p>}
          </div>
          {onClose && <IconButton icon="x" label="Close" variant="ghost" size="sm" onClick={onClose} />}
        </div>
        {children && <div style={{ padding: "0 var(--space-7) var(--space-7)" }}>{children}</div>}
        {footer && <div style={{ display: "flex", justifyContent: "flex-end", gap: "var(--space-4)", padding: "var(--space-5) var(--space-7)", borderTop: "1px solid var(--border-hairline)", background: "var(--warm-25)" }}>{footer}</div>}
      </div>
    </div>
  );
}
