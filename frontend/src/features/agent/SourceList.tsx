import { Link } from "react-router";

import { Icon } from "../../components/display/Icon";
import { SectionBadge } from "../../components/research/SectionBadge";
import { decisionIdentityParts } from "../../lib/format";
import type { SourceReference } from "../../api/chat-events";

/** A stable reference, so the default does not remount the list each render. */
const NO_SOURCES: SourceReference[] = [];

export type SourceListProps = {
  /** Cited passages, in the order the answer first referred to them. Their
   *  position here is the superscript number the prose carries. */
  sources: SourceReference[];
  /** Selected by the agent but never cited. Rendered after, unnumbered. */
  uncited?: SourceReference[];
  /** True once the `sources` frame has arrived, whatever it contained. */
  received: boolean;
};

/** The passages an answer rests on.
 *
 *  One entry per cited passage, not per decision, so two passages of the same
 *  decision are two entries — the superscript in the prose points at a
 *  passage, and collapsing them would leave one of those marks pointing at
 *  nothing. The excerpt is a label rather than the whole evidence: the passage
 *  reached the model in full, and this is 200 characters of it.
 *
 *  An empty list is a real answer and is said out loud: a turn that found
 *  nothing, and a turn that needed nothing (a greeting, a follow-up), both send
 *  one. Rendering nothing at all would leave the reader to assume the prose was
 *  sourced when it was not. */
export function SourceList({
  sources,
  uncited = NO_SOURCES,
  received,
}: SourceListProps) {
  if (!received) return null;

  if (sources.length === 0 && uncited.length === 0) {
    return (
      <p
        style={{
          margin: 0,
          fontFamily: "var(--font-sans)",
          fontSize: "var(--text-small-size)",
          color: "var(--text-muted)",
          display: "flex",
          alignItems: "center",
          gap: "var(--space-2)",
        }}
      >
        <Icon name="info" size={14} />
        Svaret vilar inte på något citerat beslut.
      </p>
    );
  }

  return (
    <section style={{ display: "flex", flexDirection: "column", gap: "var(--space-4)" }}>
      <h3
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
        {sources.length + uncited.length === 1 ? "Källa" : "Källor"}
      </h3>

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
    </section>
  );
}

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
