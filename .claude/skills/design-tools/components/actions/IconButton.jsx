import React from "react";
import { Icon } from "../display/Icon.jsx";

const sizes = { sm: 30, md: 38, lg: 46 };

export function IconButton({ icon, label, variant = "secondary", size = "md", disabled = false, style = {}, ...rest }) {
  const [hover, setHover] = React.useState(false);
  const px = sizes[size];
  const skin = {
    secondary: { background: "var(--surface-card)", border: "1px solid var(--border-default)", color: "var(--text-body)" },
    ghost: { background: "transparent", border: "1px solid transparent", color: "var(--text-muted)" },
    primary: { background: "var(--action-primary)", border: "1px solid var(--burgundy-700)", color: "var(--apricot-50)" },
  }[variant];
  const hoverSkin = {
    secondary: { background: "var(--warm-50)", borderColor: "var(--border-strong)", color: "var(--text-strong)" },
    ghost: { background: "var(--apricot-50)", color: "var(--text-accent)" },
    primary: { background: "var(--action-primary-hover)" },
  }[variant];
  return (
    <button
      aria-label={label}
      title={label}
      disabled={disabled}
      onMouseEnter={() => setHover(true)}
      onMouseLeave={() => setHover(false)}
      {...rest}
      style={{
        width: px, height: px, display: "inline-flex", alignItems: "center", justifyContent: "center",
        borderRadius: "var(--radius-sm)", cursor: disabled ? "not-allowed" : "pointer",
        transition: "var(--transition-control)", opacity: disabled ? 0.42 : 1,
        ...skin, ...(hover && !disabled ? hoverSkin : null), ...style,
      }}
    >
      {typeof icon === "string" ? <Icon name={icon} size={size === "sm" ? 15 : 17} /> : icon}
    </button>
  );
}
