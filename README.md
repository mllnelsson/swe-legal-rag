# RAG Toolset Swedish Church Law
RAG toolset for searching through previous decisions made by the Church of Sweden Appeals Board (Överklagandenämnden)

## Goal
Creating a modern RAG stack with focus on optimisations in each step. Avoiding generic SDKs and implementing much of the functionality 'by hand'.

## Features
 - Built bottom up with robust hybrid search
 - Custom text-to-SQL agent for more advanced queries
 - Graph-like traversal of documents
 - Simple Front End
 - Possible for easy abstraction of toolset as MCP
 - Query Expansion
 - Using Swedish hosted LLMs

## Documentation
Architecture, data model, ingestion pipeline, retrieval design and the
architectural decision register live in [`documentation/`](documentation/index.md).

## Installation
See the [local dev playbook](documentation/playbooks/local-dev.md).

## TODO List
 - Complete chat interface
 - Summarization of search query by user
 - Agentic assistance in queries

## License
Apache-2.0 — see [LICENSE](LICENSE).
