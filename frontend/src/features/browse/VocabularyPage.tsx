import { Link } from "react-router";

import { Badge } from "../../components/display/Badge";
import { Tabs } from "../../components/navigation/Tabs";
import { useConcepts, useKeywords } from "../../api/queries";
import { formatCount } from "../../lib/format";
import type { EntityType, EntityWithCount } from "../../api/types";

/** The vocabularies a user can browse, and what each one is worth trusting.
 *
 *  `keyword` is the only one the corpus declares: it comes off each decision's own
 *  `Sökord:` line, written by the nämnd. The other four are inferred from prose by
 *  the extraction step. Both are useful; only one is authoritative, and the UI says
 *  which is which rather than presenting one undifferentiated tag cloud. */
const CONCEPT_TABS: { value: EntityType; label: string }[] = [
  { value: "regulation", label: "Lagrum" },
  { value: "legal_concept", label: "Begrepp" },
  { value: "role", label: "Roller" },
  { value: "parish", label: "Församlingar" },
];

/** The API clamps to 50; ask for it so a vocabulary fits on one page. */
const PAGE_SIZE = 50;

export type VocabularyPageProps = {
  kind: "keywords" | "concepts";
  /** Only meaningful for `concepts`; the keyword vocabulary has a single type. */
  entityType?: EntityType;
  onEntityTypeChange?: (entityType: EntityType) => void;
};

export function VocabularyPage({ kind, entityType, onEntityTypeChange }: VocabularyPageProps) {
  const isKeywords = kind === "keywords";

  const keywords = useKeywords(isKeywords ? { limit: PAGE_SIZE } : {});
  const concepts = useConcepts(
    isKeywords ? {} : { entity_type: entityType ?? "regulation", limit: PAGE_SIZE },
  );
  const query = isKeywords ? keywords : concepts;

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
      <header style={{ display: "flex", flexDirection: "column", gap: "var(--space-3)" }}>
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
          {isKeywords ? "Sökord" : "Begrepp i besluten"}
        </h1>
        <div style={{ display: "flex", alignItems: "center", gap: "var(--space-3)" }}>
          <Badge tone={isKeywords ? "declared" : "inferred"}>
            {isKeywords ? "Nämndens egna" : "Härledda ur texten"}
          </Badge>
          <p style={{ margin: 0, fontSize: "var(--text-small-size)", color: "var(--text-muted)" }}>
            {isKeywords
              ? "Skrivna av nämnden på varje besluts egen sökordsrad."
              : "Utvunna ur beslutens text, inte klassificerade av nämnden."}
          </p>
        </div>
      </header>

      {!isKeywords && onEntityTypeChange !== undefined && (
        <Tabs
          tabs={CONCEPT_TABS}
          value={entityType ?? "regulation"}
          onChange={(value) => onEntityTypeChange(value as EntityType)}
          label="Typ av begrepp"
        />
      )}

      {query.isPending && <p style={{ margin: 0, color: "var(--text-muted)" }}>Hämtar…</p>}
      {query.isError && (
        <p style={{ margin: 0, color: "var(--status-error-fg)" }}>Kunde inte hämta listan.</p>
      )}

      {query.data !== undefined && (
        <ul
          style={{
            margin: 0,
            padding: 0,
            listStyle: "none",
            display: "flex",
            flexDirection: "column",
          }}
        >
          {query.data.items.map((entity: EntityWithCount) => (
            <li key={entity.id}>
              {/* A row is a link, not a button that navigates: it goes somewhere,
                  so it should behave like it — hoverable URL, middle-click, and a
                  new tab for a reader comparing two vocabularies. */}
              <Link
                to={`${isKeywords ? "/sokord" : "/begrepp"}/${entity.id}`}
                // The target page's API call returns decisions and nothing about
                // the entity, so the name travels with the navigation instead.
                state={{ name: entity.name }}
                style={{
                  display: "flex",
                  alignItems: "baseline",
                  justifyContent: "space-between",
                  gap: "var(--space-5)",
                  padding: "var(--space-4) var(--space-3)",
                  borderBottom: "1px solid var(--border-hairline)",
                  fontSize: "var(--text-body-size)",
                  color: "var(--text-strong)",
                  textDecoration: "none",
                }}
              >
                <span>{entity.name}</span>
                <span style={{ color: "var(--text-faint)", fontSize: "var(--text-small-size)" }}>
                  {entity.document_count === 1
                    ? "1 beslut"
                    : `${formatCount(entity.document_count)} beslut`}
                </span>
              </Link>
            </li>
          ))}
        </ul>
      )}
    </main>
  );
}
