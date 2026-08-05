import { Icon } from "../../components/display/Icon";
import type { ReferenceEdge, UnresolvedCitation } from "../../api/types";

export type CitationGraphProps = {
  referencesOut: ReferenceEdge[];
  referencesIn: ReferenceEdge[];
  unresolved: UnresolvedCitation[];
  onOpen: (documentId: string) => void;
};

/** The citation graph around one decision, in both directions.
 *
 *  `unresolved` gets equal billing rather than a footnote. Those are decisions this
 *  one cites that the corpus does not hold, and at the current ingested slice they
 *  outnumber the resolved edges — so "we don't have that one" is the ordinary case,
 *  not an edge case. They render as plain text: making them look like links would
 *  promise a destination that does not exist. */
export function CitationGraph({
  referencesOut,
  referencesIn,
  unresolved,
  onOpen,
}: CitationGraphProps) {
  const empty =
    referencesOut.length === 0 && referencesIn.length === 0 && unresolved.length === 0;
  if (empty) return null;

  return (
    <section style={{ display: "flex", flexDirection: "column", gap: "var(--space-5)" }}>
      <EdgeList title="Hänvisar till" edges={referencesOut} onOpen={onOpen} />
      <EdgeList title="Hänvisas av" edges={referencesIn} onOpen={onOpen} />

      {unresolved.length > 0 && (
        <div style={{ display: "flex", flexDirection: "column", gap: "var(--space-3)" }}>
          <GroupTitle>Ej i samlingen</GroupTitle>
          <ul style={{ margin: 0, padding: 0, listStyle: "none" }}>
            {unresolved.map((citation) => (
              <li
                key={citation.target_case_number}
                style={{
                  display: "flex",
                  alignItems: "center",
                  gap: "var(--space-2)",
                  padding: "var(--space-2) 0",
                  fontSize: "var(--text-small-size)",
                  color: "var(--text-muted)",
                }}
              >
                <span style={{ fontFamily: "var(--font-mono)" }}>
                  {citation.target_case_number}
                </span>
                <span style={{ color: "var(--text-faint)" }}>·</span>
                <span>finns inte i samlingen</span>
              </li>
            ))}
          </ul>
        </div>
      )}
    </section>
  );
}

function EdgeList({
  title,
  edges,
  onOpen,
}: {
  title: string;
  edges: ReferenceEdge[];
  onOpen: (documentId: string) => void;
}) {
  if (edges.length === 0) return null;

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: "var(--space-3)" }}>
      <GroupTitle>{title}</GroupTitle>
      <ul style={{ margin: 0, padding: 0, listStyle: "none" }}>
        {edges.map((edge) => (
          <li key={edge.document_id} style={{ padding: "var(--space-2) 0" }}>
            <button
              type="button"
              onClick={() => onOpen(edge.document_id)}
              style={{
                display: "flex",
                alignItems: "center",
                gap: "var(--space-2)",
                border: "none",
                background: "transparent",
                padding: 0,
                font: "inherit",
                fontSize: "var(--text-small-size)",
                color: "var(--text-link)",
                cursor: "pointer",
                textAlign: "left",
              }}
            >
              <Icon name="link-2" size={13} />
              <span style={{ fontFamily: "var(--font-mono)" }}>
                {edge.decision_number ?? edge.case_number ?? "Okänt beslut"}
              </span>
              {edge.headline !== null && <span>{edge.headline}</span>}
            </button>
          </li>
        ))}
      </ul>
    </div>
  );
}

function GroupTitle({ children }: { children: string }) {
  return (
    <span
      style={{
        fontSize: "var(--text-overline-size)",
        letterSpacing: "var(--text-overline-ls)",
        textTransform: "uppercase",
        fontWeight: "var(--text-overline-weight)",
        color: "var(--text-faint)",
      }}
    >
      {children}
    </span>
  );
}
