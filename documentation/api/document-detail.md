---
type: API Endpoint
title: Document Detail Endpoint (GET /api/documents/{id})
description: The GET /api/documents/{id} contract — one decision's identity, section counts, legal concepts/regulations/roles/parishes, and both directions of its citation graph, in one call.
resource: GET /api/documents/{document_id}
tags: [api, documents, rest, entities, references]
timestamp: 2026-08-03T00:00:00Z
---

# Document Detail Endpoint (`GET /api/documents/{document_id}`)

One decision, with everything a reader traverses next. Deliberately one call: a
document's legal concepts, regulation references, and cited/citing cases are what a
reader looks at right after opening a decision, so they arrive with it rather than
costing four follow-up requests. Every id in the response is a valid target for another
endpoint — an entity's `entity_id` for
[`/api/concepts/{id}/documents`](/api/concept-documents.md), another decision's
`document_id` for this same endpoint.

404s when `document_id` is unknown.

## Response

```json
{
  "document": { "...": "DocumentSummary, same shape as an /api/documents item" },
  "sections": {
    "body_chunk_count": 0,
    "appendix_chunk_count": 0,
    "appendix_labels": ["Bilaga A"]
  },
  "concepts": [{"entity_id": "uuid", "name": "string", "type": "string", "relevance": "primary | mentioned"}],
  "regulations": ["... same shape ..."],
  "roles": ["... same shape ..."],
  "parishes": ["... same shape ..."],
  "other_entities": ["... same shape ..."],
  "references_out": [{"document_id": "uuid", "case_number": "string | null", "decision_number": "string | null", "decision_date": "date | null", "headline": "string | null", "reference_context": "string | null"}],
  "references_in": ["... same shape as references_out ..."],
  "unresolved_references": [{"target_case_number": "string", "reference_context": "string | null"}]
}
```

`concepts`/`regulations`/`roles`/`parishes` bucket this document's
[entities](/data-model/entities.md) by `EntityType`; `other_entities` catches any value
extraction wrote outside the enum — extraction stores `type` as free text, so an
unexpected value is surfaced here rather than silently dropped. References to church law
are already modelled as `regulations` — `Entity(type='regulation')` edges through
[document_entities](/data-model/document-entities.md) — there is no separate regulations
table.

`references_out`/`references_in` are both directions of a document's
[document_references](/data-model/document-references.md), each resolved to the other
document's identity in one query per direction (no per-edge lookup). `unresolved_references`
lists citations to a decision the corpus does not hold — this document's
[unresolved_references](/data-model/unresolved-references.md) rows — as plain text, since
there is nothing to link to yet.

`sections.appendix_labels` tells a reader an appealed decision is attached (see
[appendices are labelled, not dropped](/decisions/appendix-segmentation.md)) before they
request the [full text](/api/document-chunks.md) or the
[PDF](/api/document-pdf.md).

Implemented by `api/services/document_service.get_document_detail`, served through the
[api package](/packages/api.md).
