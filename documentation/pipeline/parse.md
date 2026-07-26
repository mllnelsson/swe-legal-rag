---
type: Service
title: Parse Worker
description: Subscriber worker that extracts raw text from stored PDFs with pypdfium2 and enqueues metadata tasks.
resource: packages/worker-parse
tags: [pipeline, worker, parse, pdf]
timestamp: 2026-07-24T00:00:00Z
---

# Parse Worker (`packages/worker-parse/`)

Long-running subscriber. Consumes parse tasks, retrieves the stored PDF bytes from the
[storage backend](/packages/shared.md), extracts text using pypdfium2, stores it in
[`documents.raw_text`](/data-model/documents.md), and enqueues metadata tasks.

## Module layout

| Module | Role |
|---|---|
| `config.py` | `ParseSettings(BaseSettings)` — `PARSE_TOPIC` (`parse`), `PARSE_NEXT_TOPIC` (`metadata`). `get_parse_settings()` is `@lru_cache`. |
| `parser.py` | `Parser` Protocol + `parse_pdf_with_pypdfium2()` function. `ParseError` is the domain exception. |
| `service.py` | `process_parse()` async function — orchestration via functional dependency injection. |
| `__main__.py` | Entry point. Loads `.env`, wires dependencies, registers the handler, installs signal handlers, calls `subscriber.start()`. |

## Parser abstraction

`Parser` is a `typing.Protocol` with a single `__call__(pdf_bytes: bytes) -> str`
signature — any function of that shape satisfies it without inheritance, so the
underlying library is swappable without touching the service layer. The concrete
`parse_pdf_with_pypdfium2` loads the PDF via `pypdfium2.PdfDocument(pdf_bytes)`, extracts
each page via `page.get_textpage().get_text_range()`, joins pages with `"\n\n---\n\n"`
separators, and wraps pypdfium2 exceptions in `ParseError`.

`raw_text` is a faithful flattening of the PDF, appendices included — the citation flow
depends on it matching what the user opens. Downstream steps that need only
Överklagandenämndens own text derive it with
[`shared.segmentation`](/reference/document-structure.md) rather than the parser
withholding it.

**`pypdfium2` uses the Apache 2.0 license** (permissive), unlike PyMuPDF/pymupdf4llm
which is AGPL — see the [architectural register](/decisions/architectural-register.md).

## Service layer

`process_parse(document_id, task_id, storage, document_repo, task_repo, queue_publisher,
parser, session, next_topic)` is a module-level async function; all dependencies are
passed as arguments. Its `body()` fetches and validates the document, then extracts and
stores text. Storage retrieval uses the deterministic key
`documents/{document_id}/original.pdf`, matching the download worker's key. The task
lifecycle is owned by the shared task envelope (see
[worker patterns](/pipeline/worker-patterns.md)); `body()` raises `StepInputError` when
the document is missing or has no stored PDF (`document.gcs_uri is None`).
