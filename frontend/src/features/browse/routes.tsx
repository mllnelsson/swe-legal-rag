import { useSearchParams } from "react-router";

import { EntityDocumentsPage } from "./EntityDocumentsPage";
import { VocabularyPage } from "./VocabularyPage";
import type { EntityType } from "../../api/types";

const CONCEPT_TYPES: EntityType[] = ["regulation", "legal_concept", "role", "parish"];
const DEFAULT_CONCEPT_TYPE: EntityType = "regulation";

function readConceptType(raw: string | null): EntityType {
  return CONCEPT_TYPES.find((type) => type === raw) ?? DEFAULT_CONCEPT_TYPE;
}

export function KeywordIndexRoute() {
  return <VocabularyPage kind="keywords" />;
}

/** The chosen type lives in the URL, so a concept list is as shareable as a search. */
export function ConceptIndexRoute() {
  const [params, setParams] = useSearchParams();
  return (
    <VocabularyPage
      kind="concepts"
      entityType={readConceptType(params.get("typ"))}
      onEntityTypeChange={(entityType) => setParams({ typ: entityType })}
    />
  );
}

export function KeywordDocumentsRoute() {
  return <EntityDocumentsPage kind="keywords" />;
}

export function ConceptDocumentsRoute() {
  return <EntityDocumentsPage kind="concepts" />;
}
