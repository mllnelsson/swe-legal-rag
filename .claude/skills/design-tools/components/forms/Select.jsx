import React from "react";
import { Icon } from "../display/Icon.jsx";

export function Select({ label, hint, options = [], value, onChange, size = "md", disabled, id, style = {}, ...rest }) {
  const uid = id || React.useId();
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: "var(--space-3)", fontFamily: "var(--font-sans)" }}>
      {label && <label htmlFor={uid} style={{ fontSize: "var(--text-small-size)", fontWeight: "var(--weight-semibold)", color: "var(--text-strong)" }}>{label}</label>}
      <div style={{ position: "relative", display: "flex", alignItems: "center" }}>
        <select
          id={uid} value={value} disabled={disabled}
          onChange={(e) => onChange && onChange(e.target.value)}
          {...rest}
          style={{
            appearance: "none", width: "100%",
            height: size === "sm" ? "var(--control-h-sm)" : "var(--control-h-md)",
            padding: "0 var(--space-9) 0 var(--space-4)",
            background: disabled ? "var(--surface-sunken)" : "var(--surface-card)",
            border: "1px solid var(--border-default)", borderRadius: "var(--radius-sm)",
            boxShadow: "var(--shadow-xs)", font: "inherit", fontSize: "var(--text-body-size)",
            color: "var(--text-strong)", cursor: disabled ? "not-allowed" : "pointer", ...style,
          }}
        >
          {options.map((o) => {
            const opt = typeof o === "string" ? { value: o, label: o } : o;
            return <option key={opt.value} value={opt.value}>{opt.label}</option>;
          })}
        </select>
        <Icon name="chevron-down" size={15} color="var(--text-muted)" style={{ position: "absolute", right: "var(--space-4)", pointerEvents: "none" }} />
      </div>
      {hint && <span style={{ fontSize: "var(--text-caption-size)", color: "var(--text-muted)" }}>{hint}</span>}
    </div>
  );
}
