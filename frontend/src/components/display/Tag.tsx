import { useState, type CSSProperties, type ReactNode } from "react";

import { Icon } from "./Icon";

/** Between the badge height and the smallest control height.
 *  token-exempt: the system has no height token below --control-h-sm (30px). */
const TAG_HEIGHT = "28px";
const REMOVE_OPACITY = 0.65;

export type TagProps = {
  children: ReactNode;
  /** Renders a remove affordance. Give this only for filters the user applied. */
  onRemove?: () => void;
  /** Apricot-filled, for an active filter. */
  selected?: boolean;
  onClick?: () => void;
  removeLabel?: string;
  style?: CSSProperties;
};

/** Interactive pill: an applied filter, or a value that becomes one when clicked.
 *  For a read-only marker use `Badge`. */
export function Tag({
  children,
  onRemove,
  selected = false,
  onClick,
  removeLabel = "Ta bort",
  style,
}: TagProps) {
  const [hover, setHover] = useState(false);
  const clickable = onClick !== undefined;

  const background = selected
    ? "var(--apricot-100)"
    : hover && clickable
      ? "var(--warm-50)"
      : "var(--surface-card)";

  const content = (
    <>
      {children}
      {onRemove !== undefined && (
        <button
          type="button"
          onClick={(event) => {
            event.stopPropagation();
            onRemove();
          }}
          aria-label={removeLabel}
          style={{
            border: "none",
            background: "transparent",
            padding: 0,
            display: "inline-flex",
            cursor: "pointer",
            color: "inherit",
            opacity: REMOVE_OPACITY,
          }}
        >
          <Icon name="x" size={13} />
        </button>
      )}
    </>
  );

  const appearance: CSSProperties = {
    display: "inline-flex",
    alignItems: "center",
    gap: "var(--space-3)",
    height: TAG_HEIGHT,
    padding: "0 var(--space-4)",
    borderRadius: "var(--radius-pill)",
    fontFamily: "var(--font-sans)",
    fontSize: "var(--text-small-size)",
    fontWeight: "var(--weight-medium)",
    background,
    border: `1px solid ${selected ? "var(--apricot-300)" : "var(--border-hairline)"}`,
    color: selected ? "var(--burgundy-600)" : "var(--text-body)",
    transition: "var(--transition-control)",
    ...style,
  };

  // A clickable tag is a button, not a span with a handler: the skill's version is
  // unreachable by keyboard, which for the primary "dig deeper" affordance in this
  // app would put the whole traversal path out of reach without a mouse.
  if (clickable) {
    return (
      <button
        type="button"
        onClick={onClick}
        onMouseEnter={() => setHover(true)}
        onMouseLeave={() => setHover(false)}
        style={{ ...appearance, cursor: "pointer" }}
      >
        {content}
      </button>
    );
  }

  return <span style={appearance}>{content}</span>;
}
