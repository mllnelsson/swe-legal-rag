# Frontend

* [Frontend](overview.md) - The React SPA at frontend/ — two surfaces over the same corpus: deterministic search, and agent mode, an SSE client for the conversational agent. No LLM call is made from the browser; both surfaces go through the API.
* [Honesty rules](honesty-rules.md) - The frontend's tested constraints on what it claims — twelve about a search result, eight more about an answer a language model wrote. Each exists because the data does not support the more convenient alternative.
* [Generated API types](generated-types.md) - How src/api/schema.d.ts is generated from the FastAPI app's OpenAPI schema, and why a backend contract change surfaces as a TypeScript error rather than a runtime surprise.
