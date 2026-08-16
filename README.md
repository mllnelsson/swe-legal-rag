# RAG Toolset Swedish Church Law
RAG toolset for searching through previous decisions made by the Church of Sweden Appeals Board (Överklagandenämnden)

## Goal
Creating a modern RAG stack with focus on optimisations in each step. Avoiding generic SDKs and implementing much of the functionality 'by hand'.

## Features
 - Built bottom up with robust hybrid search
 - Custom text-to-SQL agent for more advanced queries
 - Graph-like traversal of documents
 - Conversational agent over SSE, with a rail of past conversations
 - React front end: deterministic search and agent mode
 - Possible for easy abstraction of toolset as MCP
 - Query Expansion
 - Using Swedish hosted LLMs

## Documentation
Architecture, data model, ingestion pipeline, retrieval design and the
architectural decision register live in [`documentation/`](documentation/index.md).

## Installation
See the [local dev playbook](documentation/playbooks/local-dev.md).

## Status
Feature-complete against the initial vision, and **not yet deployed** — see
[deployment state](documentation/reference/deployment-state.md). The complete
system has deliberately not been tested end-to-end by a human yet.

## TODO List
 - End-to-end acceptance test of the running system
 - Deployment to GCP
 - Mobile-optimised layout

## License
Apache-2.0 — see [LICENSE](LICENSE).
