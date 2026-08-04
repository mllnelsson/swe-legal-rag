import React from "react";

export function Card({ children, padding = "var(--space-7)", tone = "default", interactive = false, header, footer, style = {}, ...rest }) {
  const [hover, setHover] = React.useState(false);
  const tones = {
    default: { background: "var(--surface-card)", border: "1px solid var(--border-hairline)" },
    accent: { background: "var(--surface-accent)", border: "1px solid var(--apricot-200)" },
    wash: { background: "var(--gradient-wash-soft)", border: "1px solid var(--apricot-200)" },
    inverse: { background: "var(--gradient-authority)", border: "1px solid var(--burgundy-800)", color: "var(--apricot-100)" },
  };
  return (
    <div
      onMouseEnter={() => setHover(true)}
      onMouseLeave={() => setHover(false)}
      {...rest}
      style={{
        borderRadius: "var(--radius-lg)", boxShadow: hover && interactive ? "var(--shadow-md)" : "var(--shadow-sm)",
        transition: "box-shadow var(--dur-base) var(--ease-standard), border-color var(--dur-base) var(--ease-standard)",
        cursor: interactive ? "pointer" : undefined, overflow: "hidden",
        fontFamily: "var(--font-sans)", ...tones[tone],
        ...(hover && interactive ? { borderColor: "var(--apricot-300)" } : null),
        ...style,
      }}
    >
      {header && <div style={{ padding: `var(--space-5) ${padding}`, borderBottom: "1px solid var(--border-hairline)", fontWeight: "var(--weight-semibold)", color: "var(--text-strong)", fontSize: "var(--text-small-size)" }}>{header}</div>}
      <div style={{ padding }}>{children}</div>
      {footer && <div style={{ padding: `var(--space-5) ${padding}`, borderTop: "1px solid var(--border-hairline)", background: "var(--warm-25)" }}>{footer}</div>}
    </div>
  );
}
