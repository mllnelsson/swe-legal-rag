import React from "react";
import { Icon } from "../display/Icon.jsx";

export function SidebarNav({ items = [], value, onChange, footer, title, style = {} }) {
  return (
    <nav style={{ width: "var(--sidebar-w)", flex: "none", display: "flex", flexDirection: "column", gap: "var(--space-3)", padding: "var(--space-6)", background: "var(--warm-25)", borderRight: "1px solid var(--border-hairline)", fontFamily: "var(--font-sans)", ...style }}>
      {title && <div style={{ fontSize: "var(--text-overline-size)", letterSpacing: "var(--text-overline-ls)", textTransform: "uppercase", fontWeight: "var(--weight-semibold)", color: "var(--text-faint)", padding: "var(--space-3) var(--space-4)" }}>{title}</div>}
      {items.map((item) => {
        const active = item.value === value;
        return (
          <button key={item.value} onClick={() => onChange && onChange(item.value)} style={{
            display: "flex", alignItems: "center", gap: "var(--space-4)", height: 34, padding: "0 var(--space-4)",
            border: "none", borderRadius: "var(--radius-sm)", cursor: "pointer", textAlign: "left",
            background: active ? "var(--apricot-100)" : "transparent",
            color: active ? "var(--burgundy-600)" : "var(--text-body)",
            font: "inherit", fontSize: "var(--text-body-size)", fontWeight: active ? "var(--weight-semibold)" : "var(--weight-regular)",
            transition: "var(--transition-control)",
          }}>
            {item.icon && <Icon name={item.icon} size={16} />}
            <span style={{ flex: 1, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{item.label}</span>
            {item.count != null && <span style={{ fontSize: "var(--text-caption-size)", color: "var(--text-faint)" }}>{item.count}</span>}
          </button>
        );
      })}
      {footer && <div style={{ marginTop: "auto" }}>{footer}</div>}
    </nav>
  );
}
