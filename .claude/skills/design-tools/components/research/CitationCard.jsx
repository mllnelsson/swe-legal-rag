import React from "react";
import { Badge } from "../display/Badge.jsx";
import { Icon } from "../display/Icon.jsx";
import { IconButton } from "../actions/IconButton.jsx";

const authorityTone = { binding: "binding", persuasive: "persuasive", secondary: "neutral" };

/** A single search result: case name, citation line, held-passage excerpt, authority signal. */
export function CitationCard({ title, citation, court, year, authority = "binding", treatment, excerpt, matchTerms = [], onOpen, onSave, saved = false, style = {} }) {
  const [hover, setHover] = React.useState(false);
  return (
    <article
      onMouseEnter={() => setHover(true)}
      onMouseLeave={() => setHover(false)}
      onClick={onOpen}
      style={{
        display: "flex", flexDirection: "column", gap: "var(--space-4)", padding: "var(--space-6) var(--space-7)",
        background: "var(--surface-card)", border: `1px solid ${hover ? "var(--apricot-300)" : "var(--border-hairline)"}`,
        borderRadius: "var(--radius-lg)", boxShadow: hover ? "var(--shadow-md)" : "var(--shadow-sm)",
        cursor: onOpen ? "pointer" : "default", fontFamily: "var(--font-sans)",
        transition: "box-shadow var(--dur-base) var(--ease-standard), border-color var(--dur-base) var(--ease-standard)", ...style,
      }}
    >
      <div style={{ display: "flex", alignItems: "flex-start", gap: "var(--space-5)" }}>
        <div style={{ flex: 1, minWidth: 0 }}>
          <h3 style={{ fontFamily: "var(--font-display)", fontSize: "var(--text-h3-size)", lineHeight: "var(--text-h3-lh)", color: "var(--text-strong)", margin: 0 }}>{title}</h3>
          <div style={{ display: "flex", alignItems: "center", gap: "var(--space-3)", marginTop: "var(--space-2)", fontFamily: "var(--font-mono)", fontSize: "var(--text-cite-size)", color: "var(--text-muted)" }}>
            <span>{citation}</span>
            {court && <span style={{ color: "var(--text-faint)" }}>·</span>}
            {court && <span>{court}{year ? ` ${year}` : ""}</span>}
          </div>
        </div>
        <div style={{ display: "flex", alignItems: "center", gap: "var(--space-3)" }}>
          <Badge tone={authorityTone[authority]}>{authority[0].toUpperCase() + authority.slice(1)}</Badge>
          {treatment && <Badge tone={treatment === "Criticized" || treatment === "Overruled" ? "warn" : "ok"}>{treatment}</Badge>}
          {onSave && <IconButton icon={saved ? "bookmark-check" : "bookmark"} label={saved ? "Saved" : "Save to matter"} variant="ghost" size="sm" onClick={(e) => { e.stopPropagation(); onSave(); }} />}
        </div>
      </div>
      {excerpt && (
        <p style={{
          margin: 0, paddingLeft: "var(--space-5)", borderLeft: "2px solid var(--apricot-300)",
          fontSize: "var(--text-body-size)", lineHeight: 1.62, color: "var(--text-body)", textWrap: "pretty",
        }}>{excerpt}</p>
      )}
      {matchTerms.length > 0 && (
        <div style={{ display: "flex", flexWrap: "wrap", gap: "var(--space-3)", alignItems: "center", fontSize: "var(--text-caption-size)", color: "var(--text-faint)" }}>
          <Icon name="search" size={12} color="var(--text-faint)" />
          {matchTerms.map((t) => <span key={t} style={{ padding: "1px var(--space-3)", background: "var(--apricot-50)", border: "1px solid var(--apricot-100)", borderRadius: "var(--radius-xs)", color: "var(--apricot-700)" }}>{t}</span>)}
        </div>
      )}
    </article>
  );
}
