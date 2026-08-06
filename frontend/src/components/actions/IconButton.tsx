import { useState, type ComponentPropsWithoutRef, type CSSProperties } from "react";

import { Icon, type IconProps } from "../display/Icon";

export type IconButtonVariant = "secondary" | "ghost" | "primary";
export type IconButtonSize = "sm" | "md" | "lg";

/** Matches the control heights in the spacing tokens. */
const BUTTON_SIZES: Record<IconButtonSize, string> = {
  sm: "var(--control-h-sm)",
  md: "var(--control-h-md)",
  lg: "var(--control-h-lg)",
};

const GLYPH_SIZES: Record<IconButtonSize, number> = { sm: 15, md: 17, lg: 19 };

const skins: Record<IconButtonVariant, CSSProperties> = {
  secondary: {
    background: "var(--surface-card)",
    border: "1px solid var(--border-default)",
    color: "var(--text-body)",
  },
  ghost: { background: "transparent", border: "1px solid transparent", color: "var(--text-muted)" },
  primary: {
    background: "var(--action-primary)",
    border: "1px solid var(--burgundy-700)",
    color: "var(--apricot-50)",
  },
};

const hoverSkins: Record<IconButtonVariant, CSSProperties> = {
  secondary: {
    background: "var(--warm-50)",
    borderColor: "var(--border-strong)",
    color: "var(--text-strong)",
  },
  ghost: { background: "var(--apricot-50)", color: "var(--text-accent)" },
  primary: { background: "var(--action-primary-hover)" },
};

const DISABLED_OPACITY = 0.42;

export type IconButtonProps = Omit<ComponentPropsWithoutRef<"button">, "aria-label"> & {
  icon: IconProps["name"];
  /** Required: it is the accessible name and the tooltip. An icon-only control
   *  without one is unusable by anything that cannot see it. */
  label: string;
  variant?: IconButtonVariant;
  size?: IconButtonSize;
};

export function IconButton({
  icon,
  label,
  variant = "secondary",
  size = "md",
  disabled = false,
  style,
  ...rest
}: IconButtonProps) {
  const [hover, setHover] = useState(false);

  return (
    <button
      type="button"
      aria-label={label}
      title={label}
      disabled={disabled}
      onMouseEnter={() => setHover(true)}
      onMouseLeave={() => setHover(false)}
      {...rest}
      style={{
        width: BUTTON_SIZES[size],
        height: BUTTON_SIZES[size],
        display: "inline-flex",
        alignItems: "center",
        justifyContent: "center",
        borderRadius: "var(--radius-sm)",
        cursor: disabled ? "not-allowed" : "pointer",
        transition: "var(--transition-control)",
        opacity: disabled ? DISABLED_OPACITY : 1,
        ...skins[variant],
        ...(hover && !disabled ? hoverSkins[variant] : null),
        ...style,
      }}
    >
      <Icon name={icon} size={GLYPH_SIZES[size]} />
    </button>
  );
}
