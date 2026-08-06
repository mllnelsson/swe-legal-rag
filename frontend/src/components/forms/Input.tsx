import { useId, useState, type ComponentPropsWithoutRef, type CSSProperties } from "react";

import { Icon } from "../display/Icon";
import type { IconName } from "../display/icon-paths";

const HEIGHTS = {
  sm: "var(--control-h-sm)",
  md: "var(--control-h-md)",
  lg: "var(--control-h-lg)",
} as const;

export type InputProps = Omit<ComponentPropsWithoutRef<"input">, "size"> & {
  label?: string;
  hint?: string;
  /** Replaces the hint and turns the field red. */
  error?: string;
  iconLeft?: IconName;
  size?: keyof typeof HEIGHTS;
  wrapperStyle?: CSSProperties;
};

export function Input({
  label,
  hint,
  error,
  iconLeft,
  size = "md",
  disabled = false,
  wrapperStyle,
  style,
  ...rest
}: InputProps) {
  const [focus, setFocus] = useState(false);
  const id = useId();
  const hasError = error !== undefined;

  return (
    <div
      style={{
        display: "flex",
        flexDirection: "column",
        gap: "var(--space-3)",
        fontFamily: "var(--font-sans)",
        ...wrapperStyle,
      }}
    >
      {label !== undefined && (
        <label
          htmlFor={id}
          style={{
            fontSize: "var(--text-small-size)",
            fontWeight: "var(--weight-semibold)",
            color: "var(--text-strong)",
          }}
        >
          {label}
        </label>
      )}
      <div
        style={{
          display: "flex",
          alignItems: "center",
          gap: "var(--space-3)",
          height: HEIGHTS[size],
          padding: "0 var(--space-4)",
          background: disabled ? "var(--surface-sunken)" : "var(--surface-card)",
          border: `1px solid ${
            hasError
              ? "var(--status-error-fg)"
              : focus
                ? "var(--apricot-400)"
                : "var(--border-default)"
          }`,
          borderRadius: "var(--radius-sm)",
          boxShadow: focus ? (hasError ? "var(--ring-error)" : "var(--ring-focus)") : "var(--shadow-xs)",
          transition: "var(--transition-control)",
        }}
      >
        {iconLeft !== undefined && <Icon name={iconLeft} size={16} color="var(--text-faint)" />}
        <input
          id={id}
          disabled={disabled}
          onFocus={() => setFocus(true)}
          onBlur={() => setFocus(false)}
          {...rest}
          style={{
            flex: 1,
            minWidth: 0,
            border: "none",
            outline: "none",
            background: "transparent",
            font: "inherit",
            fontSize: "var(--text-body-size)",
            color: "var(--text-strong)",
            ...style,
          }}
        />
      </div>
      {(hint !== undefined || hasError) && (
        <span
          style={{
            fontSize: "var(--text-caption-size)",
            color: hasError ? "var(--status-error-fg)" : "var(--text-muted)",
          }}
        >
          {error ?? hint}
        </span>
      )}
    </div>
  );
}
