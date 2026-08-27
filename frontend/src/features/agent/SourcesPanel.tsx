import { useEffect } from "react";
import { Link } from "react-router";

import { Icon } from "../../components/display/Icon";
import { SectionBadge } from "../../components/research/SectionBadge";
import { decisionIdentityParts } from "../../lib/format";
import type { SourceReference } from "../../api/chat-events";

/** token-exempt: wide enough to hold an excerpt without wrapping every line,
 *  and capped to the viewport on a phone. */
const PANEL_WIDTH = "min(30rem, 100%)";

export type SourcesPanelProps = {
  open: boolean;
  onClose: () => void;
  /** Cited passages, numbered by the order the answer first referred to them. */
  sources: SourceReference[];
  /** Selected by the agent but never cited. Rendered after, unnumbered. */
  uncited: SourceReference[];
};

/** The passages an answer rests on, on request.
 *
 *  They used to sit in a stack of full cards below every answer, which put the
 *  provenance — the thing a reader reaches for to verify, not the thing they
 *  came for — ahead of the next question. Behind a button the answer keeps the
 *  column to itself, and the sources are one click away in full. The pattern is
 *  the one `ConversationPanel` already uses: a right-hand aside over an overlay,
 *  dismissed by the overlay, the close button, or Escape. */
export function SourcesPanel({ open, onClose, sources, uncited }: SourcesPanelProps) {
  // Escape closes it. A panel over the page that only a mouse can dismiss is one
  // a keyboard reader is stuck behind.
  useEffect(() => {
    if (!open) return;
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") onClose();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open, onClose]);

  if (!open) return null;

  const total = sources.length + uncited.length;

  return (
    <>
      <div
        onClick={onClose}
        aria-hidden="true"
        style={{
          position: "fixed",
          inset: 0,
          zIndex: 20,
          background: "var(--surface-overlay)",
        }}
      />
      <aside
        aria-label="Källor"
        style={{
          position: "fixed",
          top: 0,
          right: 0,
          bottom: 0,
          zIndex: 21,
          width: PANEL_WIDTH,
          maxWidth: "100%",
          overflowY: "auto",
          padding: "var(--space-7) var(--gutter-page)",
          background: "var(--surface-card)",
          boxShadow: "var(--shadow-overlay)",
        }}
      >
        <div
          style={{
            display: "flex",
            alignItems: "center",
            justifyContent: "space-between",
            gap: "var(--space-4)",
            marginBottom: "var(--space-6)",
          }}
        >
          <h2
            style={{
              margin: 0,
              fontFamily: "var(--font-sans)",
              fontSize: "var(--text-overline-size)",
              letterSpacing: "var(--text-overline-ls)",
              fontWeight: "var(--text-overline-weight)",
              textTransform: "uppercase",
              color: "var(--text-faint)",
            }}
          >
            {total === 1 ? "Källa" : "Källor"}
          </h2>
          <button
            type="button"
            onClick={onClose}
            aria-label="Stäng"
            style={{
              display: "inline-flex",
              alignItems: "center",
              justifyContent: "center",
              height: "var(--control-h-sm)",
              width: "var(--control-h-sm)",
              borderRadius: "var(--radius-sm)",
              border: "1px solid var(--border-default)",
              background: "var(--surface-card)",
              color: "var(--text-body)",
              cursor: "pointer",
            }}
          >
            <Icon name="x" size={15} />
          </button>
        </div>

        <ul
          style={{
            listStyle: "none",
            margin: 0,
            padding: 0,
            display: "flex",
            flexDirection: "column",
            gap: "var(--space-4)",
          }}
        >
          {sources.map((source, index) => (
            <SourceCard key={source.handle} source={source} number={index + 1} />
          ))}
          {/* Selected but never cited. Unnumbered on purpose: the answer did not
              lean on them, and a number would say a superscript pointed here. */}
          {uncited.map((source) => (
            <SourceCard key={source.handle} source={source} number={null} />
          ))}
        </ul>
      </aside>
    </>
  );
}

/** One passage the answer rests on.
 *
 *  One entry per cited passage, not per decision, so two passages of the same
 *  decision are two entries — the superscript in the prose points at a passage,
 *  and collapsing them would leave one of those marks pointing at nothing. The
 *  excerpt is a label rather than the whole evidence: the passage reached the
 *  model in full, and this is the first 200 characters of it. */
function SourceCard({
  source,
  number,
}: {
  source: SourceReference;
  number: number | null;
}) {
  const identity = decisionIdentityParts({
    caseNumber: source.case_number,
    // The chat contract carries no beslutsnummer — the two identifier spaces
    // stay apart, so nothing here presents the ärendenummer as one.
    decisionNumber: null,
    decisionDate: source.decision_date,
  });

  return (
    <li
      style={{
        background: "var(--surface-card)",
        border: "1px solid var(--border-hairline)",
        borderRadius: "var(--radius-lg)",
        padding: "var(--space-5) var(--space-6)",
        display: "flex",
        flexDirection: "column",
        gap: "var(--space-3)",
      }}
    >
      <div
        style={{
          display: "flex",
          flexWrap: "wrap",
          alignItems: "center",
          gap: "var(--space-4)",
        }}
      >
        {number !== null && (
          <span
            aria-label={`Källa ${number}`}
            style={{
              fontFamily: "var(--font-mono)",
              fontSize: "var(--text-caption-size)",
              fontWeight: "var(--weight-semibold)",
              color: "var(--text-strong)",
              background: "var(--surface-sunken)",
              borderRadius: "var(--radius-sm)",
              padding: "0 var(--space-2)",
            }}
          >
            {number}
          </span>
        )}
        {/* Never omitted. An appendix excerpt is the appealed decision — the
            lower instance's own words, which the nämnd may have overturned. */}
        <SectionBadge section={source.section} appendixLabel={source.appendix_label} />
        {identity.map((part) => (
          <span
            key={part.label}
            style={{
              fontFamily: "var(--font-sans)",
              fontSize: "var(--text-caption-size)",
              color: "var(--text-muted)",
            }}
          >
            {part.label}{" "}
            <span style={{ fontFamily: "var(--font-mono)", color: "var(--text-strong)" }}>
              {part.value}
            </span>
          </span>
        ))}
      </div>

      {source.excerpt !== "" && (
        <blockquote
          style={{
            margin: 0,
            paddingLeft: "var(--space-4)",
            borderLeft: "2px solid var(--apricot-300)",
            fontFamily: "var(--font-display)",
            fontSize: "var(--text-cite-size)",
            lineHeight: "var(--text-cite-lh)",
            color: "var(--text-body)",
          }}
        >
          {source.excerpt}
        </blockquote>
      )}

      <div style={{ display: "flex", gap: "var(--space-5)", flexWrap: "wrap" }}>
        <Link
          to={`/beslut/${source.document_id}`}
          style={{
            fontFamily: "var(--font-sans)",
            fontSize: "var(--text-small-size)",
            fontWeight: "var(--weight-semibold)",
            color: "var(--text-link)",
          }}
        >
          Öppna beslutet
        </Link>
        {/* The API path, not a storage URL — the backend proxies the bytes so
            one URL shape works for both local and bucket storage. */}
        <a
          href={source.pdf_url}
          target="_blank"
          rel="noreferrer"
          style={{
            fontFamily: "var(--font-sans)",
            fontSize: "var(--text-small-size)",
            color: "var(--text-muted)",
            display: "inline-flex",
            alignItems: "center",
            gap: "var(--space-2)",
          }}
        >
          <Icon name="file-text" size={14} />
          PDF
        </a>
      </div>
    </li>
  );
}
