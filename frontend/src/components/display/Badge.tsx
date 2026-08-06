import type { CSSProperties, ReactNode } from "react";

/* The skill ships `binding` and `persuasive` tones for US citation authority.
 * That concept has no counterpart in this corpus — the nearest real distinction
 * is chunk provenance, body versus appendix — so those two are renamed to what
 * they actually mark here and the rest carry over unchanged. */
export type BadgeTone =
  | "neutral"
  /** The nämnd's own words, or a value the corpus itself declares. */
  | "declared"
  /** Inferred from prose by extraction, not vouched for by the nämnd. */
  | "inferred"
  | "ok"
  | "warn"
  | "error"
  | "info";

type ToneStyle = { background: string; color: string; border: string };

const tones: Record<BadgeTone, ToneStyle> = {
  neutral: { background: "var(--warm-100)", color: "var(--text-body)", border: "var(--border-hairline)" },
  declared: { background: "var(--burgundy-50)", color: "var(--burgundy-600)", border: "var(--burgundy-200)" },
  inferred: { background: "var(--apricot-100)", color: "var(--apricot-700)", border: "var(--apricot-200)" },
  ok: { background: "var(--status-ok-bg)", color: "var(--status-ok-fg)", border: "var(--status-ok-bg)" },
  warn: { background: "var(--status-warn-bg)", color: "var(--status-warn-fg)", border: "var(--status-warn-bg)" },
  error: { background: "var(--status-error-bg)", color: "var(--status-error-fg)", border: "var(--status-error-bg)" },
  info: { background: "var(--status-info-bg)", color: "var(--status-info-fg)", border: "var(--status-info-bg)" },
};

/** Shorter than the smallest control height, sized to sit on one text line.
 *  token-exempt: the system has no height token below --control-h-sm (30px). */
const BADGE_HEIGHT = "21px";

export type BadgeProps = {
  children: ReactNode;
  tone?: BadgeTone;
  icon?: ReactNode;
  style?: CSSProperties;
};

/** Read-only status marker. Never make it clickable — use `Tag` for anything the
 *  user can select or remove. */
export function Badge({ children, tone = "neutral", icon, style }: BadgeProps) {
  const { background, color, border } = tones[tone];
  return (
    <span
      style={{
        display: "inline-flex",
        // A badge is intrinsically sized. Without this it becomes a flex item in
        // any column layout and stretches to the full container width, which turns
        // the provenance marker into a full-bleed bar.
        alignSelf: "flex-start",
        alignItems: "center",
        gap: "var(--space-2)",
        height: BADGE_HEIGHT,
        padding: "0 var(--space-3)",
        borderRadius: "var(--radius-xs)",
        background,
        color,
        border: `1px solid ${border}`,
        fontFamily: "var(--font-sans)",
        fontSize: "var(--text-caption-size)",
        fontWeight: "var(--weight-semibold)",
        letterSpacing: "0.01em",
        whiteSpace: "nowrap",
        ...style,
      }}
    >
      {icon}
      {children}
    </span>
  );
}
