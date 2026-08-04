import React from "react";
import { Icon } from "./Icon.jsx";

export function Tag({ children, onRemove, selected = false, onClick, style = {} }) {
  const [hover, setHover] = React.useState(false);
  return (
    <span
      onClick={onClick}
      onMouseEnter={() => setHover(true)}
      onMouseLeave={() => setHover(false)}
      style={{
        display: "inline-flex", alignItems: "center", gap: "var(--space-3)", height: 28, padding: "0 var(--space-4)",
        borderRadius: "var(--radius-pill)", fontFamily: "var(--font-sans)", fontSize: "var(--text-small-size)",
        fontWeight: "var(--weight-medium)", cursor: onClick ? "pointer" : "default",
        background: selected ? "var(--apricot-100)" : hover && onClick ? "var(--warm-50)" : "var(--surface-card)",
        border: `1px solid ${selected ? "var(--apricot-300)" : "var(--border-hairline)"}`,
        color: selected ? "var(--burgundy-600)" : "var(--text-body)",
        transition: "var(--transition-control)", ...style,
      }}
    >
      {children}
      {onRemove && (
        <button onClick={(e) => { e.stopPropagation(); onRemove(); }} aria-label="Remove" style={{ border: "none", background: "transparent", padding: 0, display: "inline-flex", cursor: "pointer", color: "inherit", opacity: 0.65 }}>
          <Icon name="x" size={13} />
        </button>
      )}
    </span>
  );
}
