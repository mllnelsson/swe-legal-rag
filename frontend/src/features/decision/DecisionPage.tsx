import { useState } from "react";
import { useNavigate, useParams } from "react-router";

import { Badge } from "../../components/display/Badge";
import { Icon } from "../../components/display/Icon";
import { Tag } from "../../components/display/Tag";
import { Tabs } from "../../components/navigation/Tabs";
import { SectionBadge } from "../../components/research/SectionBadge";
import { documentPdfUrl } from "../../api/client";
import { useDocument, useDocumentChunks } from "../../api/queries";
import { decisionIdentityParts, decisionTitle } from "../../lib/format";
import { EMPTY_SEARCH, toSearchParams } from "../search/search-params";
import { CitationGraph } from "./CitationGraph";
import type { DocumentEntityDetail } from "../../api/types";

const PDF_TAB = "pdf";
const BODY_TAB = "body";

/** token-exempt: a reading-height pane, not spacing. */
const PDF_HEIGHT = "820px";

/** Sits directly below the sticky app header, which the design system fixes at 56px.
 *  token-exempt: mirrors that header height; there is no token for it. */
const STICKY_MARKER_TOP = "56px";

export function DecisionPage() {
  const { documentId } = useParams();
  const navigate = useNavigate();
  const detail = useDocument(documentId);
  const [tab, setTab] = useState(BODY_TAB);

  const chunks = useDocumentChunks(documentId);

  if (detail.isPending) {
    return <PageMessage>Hämtar beslutet…</PageMessage>;
  }
  if (detail.isError || detail.data === undefined) {
    return <PageMessage>Beslutet kunde inte hämtas.</PageMessage>;
  }

  const { document, sections, keywords, concepts, regulations, roles, parishes } = detail.data;
  const identity = decisionIdentityParts({
    caseNumber: document.case_number,
    decisionNumber: document.decision_number,
    decisionDate: document.decision_date,
  });

  const appendixTabs = sections.appendix_labels.map((label) => ({ value: label, label }));
  const tabs = [
    { value: BODY_TAB, label: "Nämndens beslut", count: sections.body_chunk_count },
    ...appendixTabs,
    ...(document.has_pdf ? [{ value: PDF_TAB, label: "PDF" }] : []),
  ];

  const visibleChunks = (chunks.data ?? []).filter((chunk) =>
    tab === BODY_TAB ? chunk.section === "body" : chunk.appendix_label === tab,
  );

  function searchByKeyword(keyword: string) {
    navigate(
      `/sok?${toSearchParams({ ...EMPTY_SEARCH, query: keyword, keywords: [keyword] }).toString()}`,
    );
  }

  return (
    <main
      className="layout-columns"
      style={{
        maxWidth: "var(--content-max)",
        margin: "0 auto",
        padding: "var(--space-8) var(--gutter-page) var(--space-11)",
        fontFamily: "var(--font-sans)",
      }}
    >
      <div
        className="layout-main"
        style={{ display: "flex", flexDirection: "column", gap: "var(--space-6)" }}
      >
        <header style={{ display: "flex", flexDirection: "column", gap: "var(--space-4)" }}>
          {/* A decision is arrived at from a search, and going back to that search
              is the next thing a reader wants. `-1` rather than a link to `/sok`:
              the whole search — query, filters, page — lives in the URL that was
              left, and no reconstruction here could be as faithful. */}
          <button
            type="button"
            onClick={() => navigate(-1)}
            style={{
              display: "inline-flex",
              alignItems: "center",
              gap: "var(--space-2)",
              width: "fit-content",
              padding: 0,
              border: "none",
              background: "transparent",
              fontFamily: "var(--font-sans)",
              fontSize: "var(--text-small-size)",
              color: "var(--text-muted)",
              cursor: "pointer",
            }}
          >
            <Icon name="arrow-left" size={14} color="var(--text-muted)" />
            Tillbaka
          </button>

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
            {decisionTitle(document.headline, document.category)}
          </h1>

          <div
            style={{
              display: "flex",
              flexWrap: "wrap",
              gap: "var(--space-4)",
              fontSize: "var(--text-cite-size)",
              color: "var(--text-muted)",
            }}
          >
            {identity.map((part) => (
              <span key={part.label} style={{ display: "inline-flex", gap: "var(--space-2)" }}>
                <span>{part.label}</span>
                <span style={{ fontFamily: "var(--font-mono)", color: "var(--text-body)" }}>
                  {part.value}
                </span>
              </span>
            ))}
          </div>

          <a
            href={document.source_url}
            target="_blank"
            rel="noreferrer"
            style={{
              display: "inline-flex",
              alignItems: "center",
              gap: "var(--space-2)",
              fontSize: "var(--text-small-size)",
              width: "fit-content",
            }}
          >
            <Icon name="external-link" size={14} />
            Källa på svenskakyrkan.se
          </a>
        </header>

        {document.decision_outcome !== null && (
          <section style={{ display: "flex", flexDirection: "column", gap: "var(--space-3)" }}>
            <span
              style={{
                fontSize: "var(--text-overline-size)",
                letterSpacing: "var(--text-overline-ls)",
                textTransform: "uppercase",
                fontWeight: "var(--text-overline-weight)",
                color: "var(--text-faint)",
              }}
            >
              Beslut
            </span>
            <p
              style={{
                margin: 0,
                paddingLeft: "var(--space-5)",
                borderLeft: "2px solid var(--apricot-300)",
                fontFamily: "var(--font-display)",
                fontSize: "var(--text-body-lg-size)",
                lineHeight: 1.55,
                color: "var(--text-strong)",
                maxWidth: "var(--measure-prose)",
              }}
            >
              {document.decision_outcome}
            </p>
          </section>
        )}

        <Tabs tabs={tabs} value={tab} onChange={setTab} label="Delar av beslutet" />

        {tab === PDF_TAB ? (
          /* No sandbox attribute, deliberately — verified in Chrome, which renders
             the "cannot display" placeholder when one is set: the built-in PDF
             viewer needs privileges `sandbox="allow-same-origin"` withholds.
             `allow-same-origin allow-scripts` would restore rendering, but that
             pair on same-origin content lets the frame clear its own sandbox — it
             reads as protection while providing none, which is worse than being
             plain about it.
             What actually contains a hostile PDF here is Chrome itself: PDFium runs
             in its own OS-level sandbox regardless of this attribute, and the iframe
             sandbox governs HTML documents. The bytes are ours, served same-origin
             by our API from decisions our crawler fetched, not user uploads. */
          // oxlint-disable-next-line react/iframe-missing-sandbox
          <iframe
            title="Beslutet som PDF"
            src={documentPdfUrl(document.document_id)}
            style={{
              width: "100%",
              height: PDF_HEIGHT,
              border: "1px solid var(--border-hairline)",
              borderRadius: "var(--radius-md)",
            }}
          />
        ) : (
          <div style={{ display: "flex", flexDirection: "column", gap: "var(--space-5)" }}>
            {tab !== BODY_TAB && (
              // Sticky, not static. An appendix runs to eleven chunks here, so a
              // marker at the top of the tab is off-screen for most of the reading
              // — and this is the one marker that must not be missable: everything
              // below it is the appealed decision's words, which the nämnd may have
              // overturned.
              <div
                style={{
                  position: "sticky",
                  top: STICKY_MARKER_TOP,
                  zIndex: 5,
                  display: "flex",
                  padding: "var(--space-3) 0",
                  background: "var(--surface-page)",
                }}
              >
                <SectionBadge section="appendix" appendixLabel={tab} />
              </div>
            )}
            {chunks.isPending && <p style={{ margin: 0, color: "var(--text-muted)" }}>Hämtar text…</p>}
            {visibleChunks.map((chunk) => (
              <p
                key={chunk.chunk_id}
                style={{
                  margin: 0,
                  fontSize: "var(--text-body-size)",
                  lineHeight: 1.62,
                  color: "var(--text-body)",
                  maxWidth: "var(--measure-prose)",
                  textWrap: "pretty",
                }}
              >
                {chunk.text}
              </p>
            ))}
          </div>
        )}
      </div>

      <aside
        className="layout-rail"
        style={{
          display: "flex",
          flexDirection: "column",
          gap: "var(--space-7)",
        }}
      >
        {/* Declared by the nämnd on the decision's own Sökord line — the one
            classification the corpus vouches for. Styled apart from the inferred
            vocabularies below, which extraction guessed from prose. */}
        <EntityGroup
          title="Sökord"
          note="Nämndens egna"
          tone="declared"
          entities={keywords}
          onSelect={searchByKeyword}
        />
        <EntityGroup title="Lagrum" note="Härledda ur texten" tone="inferred" entities={regulations} />
        <EntityGroup title="Begrepp" note="Härledda ur texten" tone="inferred" entities={concepts} />
        <EntityGroup title="Roller" note="Härledda ur texten" tone="inferred" entities={roles} />
        <EntityGroup title="Församlingar" note="Härledda ur texten" tone="inferred" entities={parishes} />

        <CitationGraph
          referencesOut={detail.data.references_out}
          referencesIn={detail.data.references_in}
          unresolved={detail.data.unresolved_references}
          onOpen={(id) => navigate(`/beslut/${id}`)}
        />
      </aside>
    </main>
  );
}

type EntityGroupProps = {
  title: string;
  note: string;
  tone: "declared" | "inferred";
  entities: DocumentEntityDetail[];
  onSelect?: (name: string) => void;
};

function EntityGroup({ title, note, tone, entities, onSelect }: EntityGroupProps) {
  if (entities.length === 0) return null;

  return (
    <section style={{ display: "flex", flexDirection: "column", gap: "var(--space-3)" }}>
      <div style={{ display: "flex", alignItems: "center", gap: "var(--space-3)" }}>
        <span
          style={{
            fontSize: "var(--text-overline-size)",
            letterSpacing: "var(--text-overline-ls)",
            textTransform: "uppercase",
            fontWeight: "var(--text-overline-weight)",
            color: "var(--text-faint)",
          }}
        >
          {title}
        </span>
        <Badge tone={tone}>{note}</Badge>
      </div>
      <div style={{ display: "flex", flexWrap: "wrap", gap: "var(--space-3)" }}>
        {entities.map((entity) =>
          onSelect === undefined ? (
            <Tag key={entity.entity_id}>{entity.name}</Tag>
          ) : (
            <Tag key={entity.entity_id} onClick={() => onSelect(entity.name)}>
              {entity.name}
            </Tag>
          ),
        )}
      </div>
    </section>
  );
}

function PageMessage({ children }: { children: string }) {
  return (
    <main
      style={{
        maxWidth: "var(--content-max)",
        margin: "0 auto",
        padding: "var(--space-10) var(--gutter-page)",
        fontFamily: "var(--font-sans)",
        color: "var(--text-muted)",
      }}
    >
      {children}
    </main>
  );
}
