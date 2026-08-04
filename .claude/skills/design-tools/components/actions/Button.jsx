import React from "react";

const base = {
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

const sizes = {
  sm: { height: "var(--control-h-sm)", padding: "0 var(--space-4)", fontSize: "var(--text-small-size)" },
  md: { height: "var(--control-h-md)", padding: "0 var(--space-6)", fontSize: "var(--text-body-size)" },
  lg: { height: "var(--control-h-lg)", padding: "0 var(--space-7)", fontSize: "var(--text-body-lg-size)" },
};

const variants = {
  primary: { background: "var(--action-primary)", color: "var(--apricot-50)", borderColor: "var(--burgundy-700)", boxShadow: "var(--shadow-xs)" },
  secondary: { background: "var(--surface-card)", color: "var(--text-strong)", borderColor: "var(--border-default)", boxShadow: "var(--shadow-xs)" },
  accent: { background: "var(--action-secondary)", color: "var(--burgundy-700)", borderColor: "var(--apricot-300)" },
  ghost: { background: "transparent", color: "var(--text-accent)", borderColor: "transparent" },
  danger: { background: "var(--status-error-fg)", color: "#fff", borderColor: "#8a1b1b" },
};

const hovers = {
  primary: { background: "var(--action-primary-hover)" },
  secondary: { background: "var(--warm-50)", borderColor: "var(--border-strong)" },
  accent: { background: "var(--action-secondary-hover)" },
  ghost: { background: "var(--apricot-50)" },
  danger: { background: "#8a1b1b" },
};

export function Button({
  variant = "primary",
  size = "md",
  disabled = false,
  fullWidth = false,
  iconLeft,
  iconRight,
  as = "button",
  children,
  style = {},
  ...rest
}) {
  const [hover, setHover] = React.useState(false);
  const [press, setPress] = React.useState(false);
  const Tag = as;
  return (
    <Tag
      disabled={Tag === "button" ? disabled : undefined}
      onMouseEnter={() => setHover(true)}
      onMouseLeave={() => { setHover(false); setPress(false); }}
      onMouseDown={() => setPress(true)}
      onMouseUp={() => setPress(false)}
      {...rest}
      style={{
        ...base,
        ...sizes[size],
        ...variants[variant],
        ...(hover && !disabled ? hovers[variant] : null),
        ...(press && !disabled ? { transform: "translateY(0.5px)", boxShadow: "none" } : null),
        ...(disabled ? { opacity: 0.42, cursor: "not-allowed", boxShadow: "none" } : null),
        width: fullWidth ? "100%" : undefined,
        ...style,
      }}
    >
      {iconLeft}
      {children}
      {iconRight}
    </Tag>
  );
}
