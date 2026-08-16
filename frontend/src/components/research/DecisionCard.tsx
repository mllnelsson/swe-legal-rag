import { useState } from "react";
import { Link } from "react-router";

import { Icon } from "../display/Icon";
import { MatchBadge } from "./MatchBadge";
import { SectionBadge } from "./SectionBadge";
import { decisionIdentityParts, decisionTitle } from "../../lib/format";
import type { SearchHit } from "../../api/types";

export type DecisionCardProps = {
  hit: SearchHit;
  /** Where the title goes. A real `href` rather than a click handler, so the
   *  title behaves like the link it looks like: middle-click and Cmd+click open
   *  a decision in its own tab, and the browser shows where it leads on hover. */
  to: string;
};

/** Enough excerpt to judge relevance, few enough that ten results fit a page. */
const EXCERPT_LINES = 5;

/* Reshaped from the skill's CitationCard. Dropped: `authority`
 * (binding/persuasive/secondary) and `treatment` (Followed/Criticized) — those are
 * US litigation concepts with no counterpart in this data model, and inventing a
 * mapping would put a claim on screen the corpus does not make. The provenance
 * distinction that *is* real here — the nämnd's words versus the appealed
 * decision's — is carried by SectionBadge instead. Also dropped: onSave, since no
 * backend surface exists for saved matters. */

export function DecisionCard({ hit, to }: DecisionCardProps) {
  const [hover, setHover] = useState(false);

  const identity = decisionIdentityParts({
    caseNumber: hit.case_number,
    decisionNumber: hit.decision_number,
    decisionDate: hit.decision_date,
  });

  // Lead with the summary when there is one, and fall back to the holding. Both
  // are real text written about this decision; neither is generated here.
  const lede = hit.summary ?? hit.decision_outcome;
  const bestChunk = hit.chunks[0];

  return (
    <article
      onMouseEnter={() => setHover(true)}
      onMouseLeave={() => setHover(false)}
      style={{
        display: "flex",
        flexDirection: "column",
        gap: "var(--space-4)",
        padding: "var(--space-6) var(--space-7)",
        background: "var(--surface-card)",
        border: `1px solid ${hover ? "var(--apricot-300)" : "var(--border-hairline)"}`,
        borderRadius: "var(--radius-lg)",
        boxShadow: hover ? "var(--shadow-md)" : "var(--shadow-sm)",
        fontFamily: "var(--font-sans)",
        transition:
          "box-shadow var(--dur-base) var(--ease-standard), border-color var(--dur-base) var(--ease-standard)",
      }}
    >
      <div style={{ display: "flex", alignItems: "flex-start", gap: "var(--space-5)" }}>
        <div style={{ flex: 1, minWidth: 0 }}>
          <h3
            style={{
              fontFamily: "var(--font-display)",
              fontSize: "var(--text-h3-size)",
              lineHeight: "var(--text-h3-lh)",
              color: "var(--text-strong)",
              margin: 0,
            }}
          >
            <Link
              to={to}
              style={{
                color: "inherit",
                textDecoration: hover ? "underline" : "none",
                textUnderlineOffset: "0.12em",
              }}
            >
              {decisionTitle(hit.headline, hit.category)}
            </Link>
          </h3>

          <div
            style={{
              display: "flex",
              flexWrap: "wrap",
              alignItems: "center",
              gap: "var(--space-3)",
              marginTop: "var(--space-2)",
              fontSize: "var(--text-cite-size)",
              color: "var(--text-muted)",
            }}
          >
            {identity.map((part, index) => (
              <span key={part.label} style={{ display: "inline-flex", gap: "var(--space-2)" }}>
                {index > 0 && <span style={{ color: "var(--text-faint)" }}>·</span>}
                <span>{part.label}</span>
                <span style={{ fontFamily: "var(--font-mono)", color: "var(--text-body)" }}>
                  {part.value}
                </span>
              </span>
            ))}
          </div>
        </div>

        <MatchBadge vectorRank={bestChunk?.vector_rank ?? null} textRank={bestChunk?.text_rank ?? null} />
      </div>

      {lede !== null && (
        <p
          style={{
            margin: 0,
            fontSize: "var(--text-body-size)",
            lineHeight: 1.6,
            color: "var(--text-body)",
            maxWidth: "var(--measure-prose)",
            textWrap: "pretty",
          }}
        >
          {lede}
        </p>
      )}

      {bestChunk !== undefined && (
        <div style={{ display: "flex", flexDirection: "column", gap: "var(--space-3)" }}>
          <SectionBadge section={bestChunk.section} appendixLabel={bestChunk.appendix_label} />
          {/* The API returns whole chunks and never truncates, which is right for a
              contract but makes one result 637px tall — a full screen per hit, so a
              page of ten cannot be scanned. Clamped for display only: the text stays
              in the DOM, and the decision page renders every chunk in full. */}
          <p
            style={{
              margin: 0,
              paddingLeft: "var(--space-5)",
              borderLeft: "2px solid var(--apricot-300)",
              fontSize: "var(--text-body-size)",
              lineHeight: 1.62,
              color: "var(--text-body)",
              maxWidth: "var(--measure-prose)",
              textWrap: "pretty",
              display: "-webkit-box",
              WebkitBoxOrient: "vertical",
              WebkitLineClamp: EXCERPT_LINES,
              overflow: "hidden",
            }}
          >
            {bestChunk.text}
          </p>
        </div>
      )}

      <div
        style={{
          display: "flex",
          alignItems: "center",
          gap: "var(--space-3)",
          fontSize: "var(--text-caption-size)",
          color: "var(--text-faint)",
        }}
      >
        <Icon name="file-text" size={13} color="var(--text-faint)" />
        <span>
          {hit.matched_chunk_count === 1
            ? "1 matchande stycke"
            : `${hit.matched_chunk_count} matchande stycken`}
        </span>
      </div>
    </article>
  );
}
