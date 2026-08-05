import { useState, type ComponentPropsWithoutRef, type CSSProperties, type ReactNode } from "react";

export type CardTone = "default" | "accent" | "wash" | "inverse";

const tones: Record<CardTone, CSSProperties> = {
  default: { background: "var(--surface-card)", border: "1px solid var(--border-hairline)" },
  accent: { background: "var(--surface-accent)", border: "1px solid var(--apricot-200)" },
  wash: { background: "var(--gradient-wash-soft)", border: "1px solid var(--apricot-200)" },
  inverse: {
    background: "var(--gradient-authority)",
    border: "1px solid var(--burgundy-800)",
    color: "var(--apricot-100)",
  },
};

export type CardProps = ComponentPropsWithoutRef<"div"> & {
  padding?: string;
  tone?: CardTone;
  interactive?: boolean;
  header?: ReactNode;
  footer?: ReactNode;
};

/** Cards never carry a coloured left border — quoted matter uses a 2px apricot
 *  rule and no box instead. Interactive cards raise on hover and warm their
 *  border; nothing scales. */
export function Card({
  children,
  padding = "var(--space-7)",
  tone = "default",
  interactive = false,
  header,
  footer,
  style,
  ...rest
}: CardProps) {
  const [hover, setHover] = useState(false);
  const raised = hover && interactive;

  return (
    <div
      onMouseEnter={() => setHover(true)}
      onMouseLeave={() => setHover(false)}
      {...rest}
      style={{
        borderRadius: "var(--radius-lg)",
        boxShadow: raised ? "var(--shadow-md)" : "var(--shadow-sm)",
        transition:
          "box-shadow var(--dur-base) var(--ease-standard), border-color var(--dur-base) var(--ease-standard)",
        overflow: "hidden",
        fontFamily: "var(--font-sans)",
        ...tones[tone],
        ...(interactive ? { cursor: "pointer" } : null),
        ...(raised ? { borderColor: "var(--apricot-300)" } : null),
        ...style,
      }}
    >
      {header !== undefined && (
        <div
          style={{
            padding: `var(--space-5) ${padding}`,
            borderBottom: "1px solid var(--border-hairline)",
            fontWeight: "var(--weight-semibold)",
            color: "var(--text-strong)",
            fontSize: "var(--text-small-size)",
          }}
        >
          {header}
        </div>
      )}
      <div style={{ padding }}>{children}</div>
      {footer !== undefined && (
        <div
          style={{
            padding: `var(--space-5) ${padding}`,
            borderTop: "1px solid var(--border-hairline)",
            background: "var(--warm-25)",
          }}
        >
          {footer}
        </div>
      )}
    </div>
  );
}
