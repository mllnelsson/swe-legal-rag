# Frontend

* [Frontend](overview.md) - The React SPA at frontend/ — a filtered, browsable, traversable interface over the deterministic retrieval API only. No chat, no SSE, no LLM call from the browser.
* [Search result honesty rules](honesty-rules.md) - The frontend's tested constraints on what it claims about a search result — each one exists because the data does not support the more convenient alternative.
* [Generated API types](generated-types.md) - How src/api/schema.d.ts is generated from the FastAPI app's OpenAPI schema, and why a backend contract change surfaces as a TypeScript error rather than a runtime surprise.
