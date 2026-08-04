import React from "react";
import { Icon } from "../display/Icon.jsx";

/** The product's signature control: a wide, calm question box. */
export function SearchField({ value, onChange, onSubmit, placeholder = "Ask a research question, or paste a citation", scope, submitLabel = "Search", disabled, style = {} }) {
  const [focus, setFocus] = React.useState(false);
  return (
    <form
      onSubmit={(e) => { e.preventDefault(); onSubmit && onSubmit(value); }}
      style={{
        display: "flex", alignItems: "center", gap: "var(--space-4)",
        padding: "var(--space-3) var(--space-3) var(--space-3) var(--space-6)",
        background: "var(--surface-card)",
        border: `1px solid ${focus ? "var(--apricot-400)" : "var(--border-hairline)"}`,
        borderRadius: "var(--radius-xl)",
        boxShadow: focus ? "var(--ring-focus), var(--shadow-md)" : "var(--shadow-md)",
        transition: "var(--transition-control)", fontFamily: "var(--font-sans)", ...style,
      }}
    >
      <Icon name="search" size={20} color="var(--burgundy-600)" />
      <input
        value={value}
        disabled={disabled}
        placeholder={placeholder}
        onChange={(e) => onChange && onChange(e.target.value)}
        onFocus={() => setFocus(true)}
        onBlur={() => setFocus(false)}
        style={{ flex: 1, minWidth: 0, border: "none", outline: "none", background: "transparent", font: "inherit", fontSize: "var(--text-body-lg-size)", color: "var(--text-strong)" }}
      />
      {scope && (
        <span style={{ display: "inline-flex", alignItems: "center", gap: "var(--space-2)", padding: "0 var(--space-4)", height: 28, borderRadius: "var(--radius-pill)", background: "var(--apricot-50)", border: "1px solid var(--apricot-200)", color: "var(--burgundy-600)", fontSize: "var(--text-caption-size)", fontWeight: "var(--weight-semibold)", whiteSpace: "nowrap" }}>
          <Icon name="scale" size={13} />{scope}
        </span>
      )}
      <button
        type="submit"
        disabled={disabled}
        style={{ height: "var(--control-h-md)", padding: "0 var(--space-6)", borderRadius: "var(--radius-pill)", border: "1px solid var(--burgundy-700)", background: "var(--action-primary)", color: "var(--apricot-50)", font: "inherit", fontSize: "var(--text-small-size)", fontWeight: "var(--weight-semibold)", cursor: "pointer", transition: "var(--transition-control)" }}
      >
        {submitLabel}
      </button>
    </form>
  );
}
