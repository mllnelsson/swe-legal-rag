import { useNavigate, useParams } from "react-router";

import { Badge } from "../../components/display/Badge";
import { useConceptDocuments, useKeywordDocuments } from "../../api/queries";
import { decisionIdentityParts, decisionTitle, formatCount } from "../../lib/format";
import type { EntityDocumentRef } from "../../api/types";

export type EntityDocumentsPageProps = {
  kind: "keywords" | "concepts";
};

/** Every decision carrying one vocabulary entry.
 *
 *  The reverse hop of the graph: from a Sökord or an inferred concept back to the
 *  decisions it appears in. The API distinguishes "no such entity" (404) from "that
 *  entity has no decisions" (200 with an empty page), and so does this — they mean
 *  quite different things and collapsing them would hide a broken link. */
export function EntityDocumentsPage({ kind }: EntityDocumentsPageProps) {
  const { entityId } = useParams();
  const navigate = useNavigate();
  const isKeywords = kind === "keywords";

  const keywordDocs = useKeywordDocuments(isKeywords ? entityId : undefined);
  const conceptDocs = useConceptDocuments(isKeywords ? undefined : entityId);
  const query = isKeywords ? keywordDocs : conceptDocs;

  return (
    <main
      style={{
        maxWidth: "var(--content-max)",
        margin: "0 auto",
        padding: "var(--space-8) var(--gutter-page) var(--space-11)",
        display: "flex",
        flexDirection: "column",
        gap: "var(--space-6)",
        fontFamily: "var(--font-sans)",
      }}
    >
      <button
        type="button"
        onClick={() => navigate(isKeywords ? "/sokord" : "/begrepp")}
        style={{
          alignSelf: "flex-start",
          border: "none",
          background: "transparent",
          padding: 0,
          font: "inherit",
          fontSize: "var(--text-small-size)",
          color: "var(--text-link)",
          cursor: "pointer",
        }}
      >
        {isKeywords ? "Alla sökord" : "Alla begrepp"}
      </button>

      {query.isPending && <p style={{ margin: 0, color: "var(--text-muted)" }}>Hämtar…</p>}

      {query.isError && (
        <p style={{ margin: 0, color: "var(--status-error-fg)" }}>
          {/* A 404 here means the id names nothing — or, for keywords, names an
              entity of another type. Either way the link was wrong, which is not
              the same as an entity that simply has no decisions. */}
          Det finns ingen sådan post.
        </p>
      )}

      {query.data !== undefined && (
        <>
          <p style={{ margin: 0, fontSize: "var(--text-body-size)", color: "var(--text-body)" }}>
            {query.data.total === 1
              ? "1 beslut"
              : `${formatCount(query.data.total)} beslut`}
          </p>

          {query.data.items.length === 0 ? (
            <p style={{ margin: 0, color: "var(--text-muted)" }}>
              Posten finns, men inga beslut är kopplade till den.
            </p>
          ) : (
            <ul style={{ margin: 0, padding: 0, listStyle: "none" }}>
              {query.data.items.map((reference: EntityDocumentRef) => (
                <li key={reference.document_id}>
                  <button
                    type="button"
                    onClick={() => navigate(`/beslut/${reference.document_id}`)}
                    style={{
                      width: "100%",
                      display: "flex",
                      flexDirection: "column",
                      gap: "var(--space-2)",
                      padding: "var(--space-5) var(--space-3)",
                      border: "none",
                      borderBottom: "1px solid var(--border-hairline)",
                      background: "transparent",
                      font: "inherit",
                      textAlign: "left",
                      cursor: "pointer",
                    }}
                  >
                    <span
                      style={{
                        display: "flex",
                        alignItems: "center",
                        gap: "var(--space-4)",
                        fontFamily: "var(--font-display)",
                        fontSize: "var(--text-h3-size)",
                        color: "var(--text-strong)",
                      }}
                    >
                      {decisionTitle(reference.headline, reference.category)}
                      {/* Primary means the entity is central to the decision;
                          mentioned means it merely appears. Appendix-sourced
                          entities are always "mentioned". */}
                      {reference.relevance === "primary" && <Badge tone="declared">Central</Badge>}
                    </span>
                    <span
                      style={{
                        display: "flex",
                        flexWrap: "wrap",
                        gap: "var(--space-3)",
                        fontSize: "var(--text-cite-size)",
                        color: "var(--text-muted)",
                      }}
                    >
                      {decisionIdentityParts({
                        caseNumber: reference.case_number,
                        decisionNumber: reference.decision_number,
                        decisionDate: reference.decision_date,
                      }).map((part) => (
                        <span key={part.label} style={{ display: "inline-flex", gap: "var(--space-2)" }}>
                          <span>{part.label}</span>
                          <span style={{ fontFamily: "var(--font-mono)", color: "var(--text-body)" }}>
                            {part.value}
                          </span>
                        </span>
                      ))}
                    </span>
                  </button>
                </li>
              ))}
            </ul>
          )}
        </>
      )}
    </main>
  );
}
