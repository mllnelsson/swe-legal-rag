import { useId, type CSSProperties } from "react";

import { Icon } from "../display/Icon";

export type SelectOption = { value: string; label: string };

export type SelectProps = {
  label?: string;
  hint?: string;
  options: SelectOption[];
  value: string;
  onChange: (value: string) => void;
  size?: "sm" | "md";
  disabled?: boolean;
  style?: CSSProperties;
};

export function Select({
  label,
  hint,
  options,
  value,
  onChange,
  size = "md",
  disabled = false,
  style,
}: SelectProps) {
  const id = useId();

  return (
    <div
      style={{
        display: "flex",
        flexDirection: "column",
        gap: "var(--space-3)",
        fontFamily: "var(--font-sans)",
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
      <div style={{ position: "relative", display: "flex", alignItems: "center" }}>
        <select
          id={id}
          value={value}
          disabled={disabled}
          onChange={(event) => onChange(event.target.value)}
          style={{
            appearance: "none",
            width: "100%",
            height: size === "sm" ? "var(--control-h-sm)" : "var(--control-h-md)",
            padding: "0 var(--space-9) 0 var(--space-4)",
            background: disabled ? "var(--surface-sunken)" : "var(--surface-card)",
            border: "1px solid var(--border-default)",
            borderRadius: "var(--radius-sm)",
            boxShadow: "var(--shadow-xs)",
            font: "inherit",
            fontSize: "var(--text-body-size)",
            color: "var(--text-strong)",
            cursor: disabled ? "not-allowed" : "pointer",
            ...style,
          }}
        >
          {options.map((option) => (
            <option key={option.value} value={option.value}>
              {option.label}
            </option>
          ))}
        </select>
        <Icon
          name="chevron-down"
          size={15}
          color="var(--text-muted)"
          style={{ position: "absolute", right: "var(--space-4)", pointerEvents: "none" }}
        />
      </div>
      {hint !== undefined && (
        <span style={{ fontSize: "var(--text-caption-size)", color: "var(--text-muted)" }}>
          {hint}
        </span>
      )}
    </div>
  );
}
