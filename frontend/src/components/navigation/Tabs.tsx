import type { CSSProperties } from "react";

export type TabItem = {
  value: string;
  label: string;
  /** Rendered beside the label in a lighter weight. */
  count?: number;
};

export type TabsProps = {
  tabs: TabItem[];
  value: string;
  onChange: (value: string) => void;
  /** `underline` for page-level navigation, `pill` for switching within a panel. */
  variant?: "underline" | "pill";
  /** Names the tablist for assistive tech. */
  label: string;
  style?: CSSProperties;
};

export function Tabs({ tabs, value, onChange, variant = "underline", label, style }: TabsProps) {
  const isPill = variant === "pill";

  return (
    <div
      role="tablist"
      aria-label={label}
      style={
        isPill
          ? {
              display: "inline-flex",
              gap: "var(--space-1)",
              padding: "var(--space-1)",
              background: "var(--surface-sunken)",
              borderRadius: "var(--radius-pill)",
              fontFamily: "var(--font-sans)",
              ...style,
            }
          : {
              display: "flex",
              gap: "var(--space-7)",
              borderBottom: "1px solid var(--border-hairline)",
              fontFamily: "var(--font-sans)",
              ...style,
            }
      }
    >
      {tabs.map((tab) => {
        const active = tab.value === value;
        return (
          <button
            key={tab.value}
            type="button"
            role="tab"
            aria-selected={active}
            onClick={() => onChange(tab.value)}
            style={
              isPill
                ? {
                    height: "var(--control-h-sm)",
                    padding: "0 var(--space-5)",
                    border: "none",
                    borderRadius: "var(--radius-pill)",
                    cursor: "pointer",
                    background: active ? "var(--surface-card)" : "transparent",
                    boxShadow: active ? "var(--shadow-xs)" : "none",
                    color: active ? "var(--text-strong)" : "var(--text-muted)",
                    font: "inherit",
                    fontSize: "var(--text-small-size)",
                    fontWeight: "var(--weight-semibold)",
                    transition: "var(--transition-control)",
                  }
                : {
                    position: "relative",
                    padding: "0 0 var(--space-4)",
                    border: "none",
                    background: "transparent",
                    cursor: "pointer",
                    color: active ? "var(--text-strong)" : "var(--text-muted)",
                    font: "inherit",
                    fontSize: "var(--text-body-size)",
                    fontWeight: "var(--weight-semibold)",
                    // token-exempt: a 2px rule width, the same class as a border;
                    // the system has no width token for rules.
                    boxShadow: active ? "inset 0 -2px 0 var(--burgundy-600)" : "none",
                    transition: "var(--transition-control)",
                  }
            }
          >
            {tab.label}
            {tab.count !== undefined && (
              <span
                style={{
                  marginLeft: "var(--space-3)",
                  color: "var(--text-faint)",
                  fontWeight: "var(--weight-regular)",
                }}
              >
                {tab.count}
              </span>
            )}
          </button>
        );
      })}
    </div>
  );
}
