import React from "react";

export function Tooltip({ label, children, placement = "top", style = {} }) {
  const [show, setShow] = React.useState(false);
  const pos = {
    top: { bottom: "calc(100% + 6px)", left: "50%", transform: "translateX(-50%)" },
    bottom: { top: "calc(100% + 6px)", left: "50%", transform: "translateX(-50%)" },
    left: { right: "calc(100% + 6px)", top: "50%", transform: "translateY(-50%)" },
    right: { left: "calc(100% + 6px)", top: "50%", transform: "translateY(-50%)" },
  }[placement];
  return (
    <span style={{ position: "relative", display: "inline-flex", ...style }} onMouseEnter={() => setShow(true)} onMouseLeave={() => setShow(false)}>
      {children}
      <span role="tooltip" style={{
        position: "absolute", ...pos, zIndex: 40, pointerEvents: "none", whiteSpace: "nowrap",
        padding: "var(--space-2) var(--space-4)", borderRadius: "var(--radius-xs)",
        background: "var(--warm-800)", color: "var(--apricot-50)",
        fontFamily: "var(--font-sans)", fontSize: "var(--text-caption-size)", fontWeight: "var(--weight-medium)",
        boxShadow: "var(--shadow-md)", opacity: show ? 1 : 0,
        transition: `opacity var(--dur-fast) var(--ease-standard)`,
      }}>{label}</span>
    </span>
  );
}
