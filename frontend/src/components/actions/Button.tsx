import { useState, type ComponentPropsWithoutRef, type CSSProperties, type ReactNode } from "react";

/* The skill also ships a `danger` variant. It is omitted here for two reasons:
 * this app is read-only and has no destructive action to hang it on, and the
 * variant hardcodes `#fff` and `#8a1b1b` — the design system has no token for a
 * red darker than --red-500, so porting it verbatim would plant the very raw hex
 * the token rules exist to prevent. Add the token first if a use ever appears. */
export type ButtonVariant = "primary" | "secondary" | "accent" | "ghost";
export type ButtonSize = "sm" | "md" | "lg";

const base: CSSProperties = {
  fontFamily: "var(--font-sans)",
  fontWeight: "var(--weight-semibold)",
  display: "inline-flex",
  alignItems: "center",
  justifyContent: "center",
  gap: "var(--space-3)",
  borderRadius: "var(--radius-sm)",
  border: "1px solid transparent",
  cursor: "pointer",
  textDecoration: "none",
  whiteSpace: "nowrap",
  transition: "var(--transition-control)",
};

const sizes: Record<ButtonSize, CSSProperties> = {
  sm: {
    height: "var(--control-h-sm)",
    padding: "0 var(--space-4)",
    fontSize: "var(--text-small-size)",
  },
  md: {
    height: "var(--control-h-md)",
    padding: "0 var(--space-6)",
    fontSize: "var(--text-body-size)",
  },
  lg: {
    height: "var(--control-h-lg)",
    padding: "0 var(--space-7)",
    fontSize: "var(--text-body-lg-size)",
  },
};

const variants: Record<ButtonVariant, CSSProperties> = {
  primary: {
    background: "var(--action-primary)",
    color: "var(--apricot-50)",
    borderColor: "var(--burgundy-700)",
    boxShadow: "var(--shadow-xs)",
  },
  secondary: {
    background: "var(--surface-card)",
    color: "var(--text-strong)",
    borderColor: "var(--border-default)",
    boxShadow: "var(--shadow-xs)",
  },
  accent: {
    background: "var(--action-secondary)",
    color: "var(--burgundy-700)",
    borderColor: "var(--apricot-300)",
  },
  ghost: { background: "transparent", color: "var(--text-accent)", borderColor: "transparent" },
};

const hovers: Record<ButtonVariant, CSSProperties> = {
  primary: { background: "var(--action-primary-hover)" },
  secondary: { background: "var(--warm-50)", borderColor: "var(--border-strong)" },
  accent: { background: "var(--action-secondary-hover)" },
  ghost: { background: "var(--apricot-50)" },
};

const DISABLED_OPACITY = 0.42;
/** Press sinks the element rather than scaling it — nothing in this system bounces.
 *  token-exempt: a sub-pixel motion offset, not spacing; the scale starts at 2px. */
const PRESS_OFFSET = "translateY(0.5px)";

export type ButtonProps = ComponentPropsWithoutRef<"button"> & {
  variant?: ButtonVariant;
  size?: ButtonSize;
  fullWidth?: boolean;
  iconLeft?: ReactNode;
  iconRight?: ReactNode;
  children?: ReactNode;
};

/** One `primary` per view; everything else is `secondary` or `ghost`. `accent` is
 *  apricot and reserved for marketing calls to action. */
export function Button({
  variant = "primary",
  size = "md",
  disabled = false,
  fullWidth = false,
  iconLeft,
  iconRight,
  children,
  style,
  ...rest
}: ButtonProps) {
  const [hover, setHover] = useState(false);
  const [press, setPress] = useState(false);

  return (
    <button
      type="button"
      disabled={disabled}
      onMouseEnter={() => setHover(true)}
      onMouseLeave={() => {
        setHover(false);
        setPress(false);
      }}
      onMouseDown={() => setPress(true)}
      onMouseUp={() => setPress(false)}
      {...rest}
      style={{
        ...base,
        ...sizes[size],
        ...variants[variant],
        ...(hover && !disabled ? hovers[variant] : null),
        ...(press && !disabled ? { transform: PRESS_OFFSET, boxShadow: "none" } : null),
        ...(disabled ? { opacity: DISABLED_OPACITY, cursor: "not-allowed", boxShadow: "none" } : null),
        ...(fullWidth ? { width: "100%" } : null),
        ...style,
      }}
    >
      {iconLeft}
      {children}
      {iconRight}
    </button>
  );
}
