import { Link, useLocation, useParams } from "react-router";

import { Badge } from "../../components/display/Badge";
import { useConceptDocuments, useKeywordDocuments } from "../../api/queries";
import { decisionIdentityParts, decisionTitle, formatCount } from "../../lib/format";
import type { EntityDocumentRef } from "../../api/types";

export type EntityDocumentsPageProps = {
  kind: "keywords" | "concepts";
};

/** The name of the entity this page is about, when the link that led here knew it.
 *
 *  `/api/keywords/{id}/documents` returns the decisions and nothing about the
 *  entity itself, so the name is not derivable from the response. The vocabulary
 *  index does know it and passes it in history state — which survives a reload,
 *  because that is where the browser keeps it. A URL typed or shared cold has no
 *  state, and then the page says what kind of thing it is listing rather than
 *  guessing a name. */
function entityName(state: unknown): string | null {
  if (typeof state !== "object" || state === null) return null;
  const name = (state as { name?: unknown }).name;
  return typeof name === "string" && name !== "" ? name : null;
}

/** Every decision carrying one vocabulary entry.
 *
 *  The reverse hop of the graph: from a Sökord or an inferred concept back to the
 *  decisions it appears in. The API distinguishes "no such entity" (404) from "that
 *  entity has no decisions" (200 with an empty page), and so does this — they mean
 *  quite different things and collapsing them would hide a broken link. */
export function EntityDocumentsPage({ kind }: EntityDocumentsPageProps) {
  const { entityId } = useParams();
  const location = useLocation();
  const isKeywords = kind === "keywords";
  const name = entityName(location.state);

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
      <Link
        to={isKeywords ? "/sokord" : "/begrepp"}
        style={{ alignSelf: "flex-start", fontSize: "var(--text-small-size)" }}
      >
        {isKeywords ? "Alla sökord" : "Alla begrepp"}
      </Link>

      <header style={{ display: "flex", alignItems: "center", gap: "var(--space-3)" }}>
        <h1
          style={{
            margin: 0,
            fontFamily: "var(--font-display)",
            fontSize: "var(--text-h1-size)",
            lineHeight: "var(--text-h1-lh)",
            letterSpacing: "var(--text-h1-ls)",
            color: "var(--text-strong)",
          }}
        >
          {name ?? (isKeywords ? "Beslut med detta sökord" : "Beslut med detta begrepp")}
        </h1>
        {name !== null && (
          <Badge tone={isKeywords ? "declared" : "inferred"}>
            {isKeywords ? "Nämndens egna" : "Härledda ur texten"}
          </Badge>
        )}
      </header>

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
                  <Link
                    to={`/beslut/${reference.document_id}`}
                    style={{
                      display: "flex",
                      flexDirection: "column",
                      gap: "var(--space-2)",
                      padding: "var(--space-5) var(--space-3)",
                      borderBottom: "1px solid var(--border-hairline)",
                      color: "inherit",
                      textDecoration: "none",
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
                  </Link>
                </li>
              ))}
            </ul>
          )}
        </>
      )}
    </main>
  );
}
