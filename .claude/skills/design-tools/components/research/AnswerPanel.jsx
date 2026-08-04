import React from "react";
import { Icon } from "../display/Icon.jsx";

/** The assistant's synthesized answer, with inline superscript source markers. */
export function AnswerPanel({ question, answer, sources = [], onSourceClick, status, style = {} }) {
  return (
    <section style={{
      display: "flex", flexDirection: "column", gap: "var(--space-5)", padding: "var(--space-7) var(--space-8)",
      background: "var(--gradient-wash-soft)", border: "1px solid var(--apricot-200)", borderRadius: "var(--radius-lg)",
      boxShadow: "var(--shadow-sm)", fontFamily: "var(--font-sans)", ...style,
    }}>
      <div style={{ display: "flex", alignItems: "center", gap: "var(--space-3)", fontSize: "var(--text-overline-size)", letterSpacing: "var(--text-overline-ls)", textTransform: "uppercase", fontWeight: "var(--weight-semibold)", color: "var(--burgundy-600)" }}>
        <Icon name="sparkles" size={13} color="var(--burgundy-600)" />
        {status || "Research summary"}
      </div>
      {question && <h2 style={{ fontFamily: "var(--font-display)", fontSize: "var(--text-h2-size)", lineHeight: "var(--text-h2-lh)", letterSpacing: "var(--text-h2-ls)", color: "var(--text-strong)", margin: 0, maxWidth: "var(--measure-prose)" }}>{question}</h2>}
      <div style={{ fontSize: "var(--text-body-lg-size)", lineHeight: "var(--text-body-lg-lh)", color: "var(--text-body)", maxWidth: "var(--measure-prose)", textWrap: "pretty" }}>{answer}</div>
      {sources.length > 0 && (
        <div style={{ display: "flex", flexWrap: "wrap", gap: "var(--space-3)", paddingTop: "var(--space-4)", borderTop: "1px solid var(--apricot-200)" }}>
          <span style={{ fontSize: "var(--text-caption-size)", color: "var(--text-muted)", alignSelf: "center", marginRight: "var(--space-2)" }}>Sources</span>
          {sources.map((s, i) => (
            <button key={s} onClick={() => onSourceClick && onSourceClick(i)} style={{
              display: "inline-flex", alignItems: "center", gap: "var(--space-2)", height: 26, padding: "0 var(--space-4)",
              borderRadius: "var(--radius-pill)", border: "1px solid var(--apricot-300)", background: "rgba(255,255,255,0.72)",
              color: "var(--burgundy-600)", font: "inherit", fontSize: "var(--text-caption-size)", fontWeight: "var(--weight-semibold)",
              cursor: "pointer", transition: "var(--transition-control)",
            }}>
              <span style={{ fontFamily: "var(--font-mono)", opacity: 0.65 }}>{i + 1}</span>{s}
            </button>
          ))}
        </div>
      )}
    </section>
  );
}
