export interface paths {
    "/api/search": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /**
         * Search Endpoint
         * @description Hybrid search over the decision corpus.
         *
         *     POST rather than GET: the query is free text of arbitrary length and the
         *     filter is a nested object with list-valued fields.
         */
        post: operations["search_endpoint_api_search_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/filters": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * Filters Endpoint
         * @description What values the search filters will actually match.
         */
        get: operations["filters_endpoint_api_filters_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/documents": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * List Documents Endpoint
         * @description Browse decisions by metadata alone, with no query text.
         *
         *     Filters are spelled out as query parameters rather than taking a nested
         *     object, so a plain link can express a filtered view.
         */
        get: operations["list_documents_endpoint_api_documents_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/documents/{document_id}": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * Document Detail Endpoint
         * @description One decision with its concepts, regulations and citations.
         *
         *     Every id in the response is a valid traversal target for another endpoint.
         */
        get: operations["document_detail_endpoint_api_documents__document_id__get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/documents/{document_id}/chunks": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * Document Chunks Endpoint
         * @description The decision's text in reading order, chunk by chunk.
         */
        get: operations["document_chunks_endpoint_api_documents__document_id__chunks_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/documents/{document_id}/pdf": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * Document Pdf Endpoint
         * @description The original PDF, inline so a browser renders it in place.
         */
        get: operations["document_pdf_endpoint_api_documents__document_id__pdf_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/concepts": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * List Concepts Endpoint
         * @description Browse the graph's nodes — legal concepts, regulations, roles, parishes.
         */
        get: operations["list_concepts_endpoint_api_concepts_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/concepts/{entity_id}/documents": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * Concept Documents Endpoint
         * @description Every decision carrying this entity — one hop through the graph.
         */
        get: operations["concept_documents_endpoint_api_concepts__entity_id__documents_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/keywords": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * List Keywords Endpoint
         * @description Browse the nämnd's own `Sökord` classification, most-used first.
         *
         *     Unlike `/api/concepts`, these values were declared by the decisions
         *     themselves rather than inferred from their prose.
         */
        get: operations["list_keywords_endpoint_api_keywords_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/keywords/{keyword_id}/documents": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * Keyword Documents Endpoint
         * @description Every decision classified under this keyword — one hop through the graph.
         *
         *     No `relevance` parameter, unlike the concept traversal: a declared keyword is
         *     always primary, so there is nothing to narrow by.
         */
        get: operations["keyword_documents_endpoint_api_keywords__keyword_id__documents_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/chat": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /**
         * Chat Endpoint
         * @deprecated
         */
        post: operations["chat_endpoint_api_chat_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/healthz": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Healthz */
        get: operations["healthz_healthz_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
}
export type webhooks = Record<string, never>;
export interface components {
    schemas: {
        /** ChatRequest */
        ChatRequest: {
            /** Session Id */
            session_id?: string | null;
            /** Message */
            message: string;
        };
        /**
         * ChunkSection
         * @description Which part of the source PDF a chunk was cut from.
         *
         *     Decision PDFs carry the appealed decision as an appendix, so an ``APPENDIX``
         *     chunk holds the *lower instance's* words — often the reasoning Överklagande-
         *     nämnden went on to overturn. Retrieval defaults to ``BODY`` for that reason.
         * @enum {string}
         */
        ChunkSection: "body" | "appendix";
        /**
         * DocumentChunk
         * @description A chunk as a reader sees it.
         *
         *     Projected from ``ChunkRead`` to drop the embedding vector and the
         *     context-enriched text, neither of which is meaningful outside retrieval.
         */
        DocumentChunk: {
            /**
             * Chunk Id
             * Format: uuid
             */
            chunk_id: string;
            /** Chunk Index */
            chunk_index: number;
            /** Text */
            text: string;
            section: components["schemas"]["ChunkSection"];
            /** Appendix Label */
            appendix_label: string | null;
        };
        /** DocumentDetail */
        DocumentDetail: {
            document: components["schemas"]["DocumentSummary"];
            sections: components["schemas"]["DocumentSections"];
            /** Keywords */
            keywords: components["schemas"]["DocumentEntityDetail"][];
            /** Concepts */
            concepts: components["schemas"]["DocumentEntityDetail"][];
            /** Regulations */
            regulations: components["schemas"]["DocumentEntityDetail"][];
            /** Roles */
            roles: components["schemas"]["DocumentEntityDetail"][];
            /** Parishes */
            parishes: components["schemas"]["DocumentEntityDetail"][];
            /** Other Entities */
            other_entities: components["schemas"]["DocumentEntityDetail"][];
            /** References Out */
            references_out: components["schemas"]["ReferenceEdge"][];
            /** References In */
            references_in: components["schemas"]["ReferenceEdge"][];
            /** Unresolved References */
            unresolved_references: components["schemas"]["UnresolvedCitation"][];
        };
        /**
         * DocumentEntityDetail
         * @description One edge with the entity resolved — what a reader of a document needs.
         *
         *     ``DocumentEntityRead`` carries bare ids, so rendering a document's concepts
         *     from it would cost a lookup per edge.
         */
        DocumentEntityDetail: {
            /**
             * Entity Id
             * Format: uuid
             */
            entity_id: string;
            /** Name */
            name: string;
            /** Type */
            type: string;
            /** Relevance */
            relevance: string;
        };
        /**
         * DocumentFacets
         * @description The values the metadata filters will actually match.
         *
         *     ``category`` and ``decision_outcome`` are free text lifted off the PDFs by
         *     regex, not a controlled vocabulary, so a client has no way to guess valid
         *     values — it has to be told.
         *
         *     ``keywords`` is the exception and the strongest of the four: it is the nämnd's
         *     own ``Sökord`` classification, so its values are a real vocabulary rather than
         *     whatever the regexes happened to lift.
         */
        DocumentFacets: {
            /** Categories */
            categories: components["schemas"]["FacetValue"][];
            /** Decision Outcomes */
            decision_outcomes: components["schemas"]["FacetValue"][];
            /** Entity Types */
            entity_types: components["schemas"]["FacetValue"][];
            /** Keywords */
            keywords: components["schemas"]["FacetValue"][];
            /** Earliest Decision Date */
            earliest_decision_date: string | null;
            /** Latest Decision Date */
            latest_decision_date: string | null;
            /** Document Count */
            document_count: number;
        };
        /** DocumentFilter */
        DocumentFilter: {
            /** Date From */
            date_from?: string | null;
            /** Date To */
            date_to?: string | null;
            /** Category */
            category?: string | null;
            /** Decision Outcome */
            decision_outcome?: string | null;
            /** Case Number */
            case_number?: string | null;
            /** Decision Number */
            decision_number?: string | null;
            /**
             * Entity Names
             * @default []
             */
            entity_names: string[];
            /**
             * Entity Types
             * @default []
             */
            entity_types: string[];
            /**
             * Keywords
             * @default []
             */
            keywords: string[];
            /** References Case Number */
            references_case_number?: string | null;
        };
        /**
         * DocumentSections
         * @description What parts the source PDF was cut into.
         *
         *     Appendix labels are listed so a reader knows an appealed decision is attached
         *     before asking for its text.
         */
        DocumentSections: {
            /** Body Chunk Count */
            body_chunk_count: number;
            /** Appendix Chunk Count */
            appendix_chunk_count: number;
            /** Appendix Labels */
            appendix_labels: string[];
        };
        /**
         * DocumentSummary
         * @description A decision's identity — enough to list it or link to it.
         */
        DocumentSummary: {
            /**
             * Document Id
             * Format: uuid
             */
            document_id: string;
            /** Case Number */
            case_number: string | null;
            /** Decision Number */
            decision_number: string | null;
            /** Decision Date */
            decision_date: string | null;
            /** Category */
            category: string | null;
            /** Decision Outcome */
            decision_outcome: string | null;
            /** Headline */
            headline: string | null;
            /** Summary */
            summary: string | null;
            /** Source Url */
            source_url: string;
            /** Source Published At */
            source_published_at: string | null;
            /** Has Pdf */
            has_pdf: boolean;
        };
        /**
         * EntityDocumentRef
         * @description One edge with the document resolved — the reverse traversal hop.
         */
        EntityDocumentRef: {
            /**
             * Document Id
             * Format: uuid
             */
            document_id: string;
            /** Case Number */
            case_number: string | null;
            /** Decision Number */
            decision_number: string | null;
            /** Decision Date */
            decision_date: string | null;
            /** Headline */
            headline: string | null;
            /** Category */
            category: string | null;
            /** Decision Outcome */
            decision_outcome: string | null;
            /** Relevance */
            relevance: string;
        };
        /**
         * EntityRelevance
         * @description How central an entity is to the document it was found in.
         * @enum {string}
         */
        EntityRelevance: "primary" | "mentioned";
        /**
         * EntityType
         * @description Category of a legal entity extracted from a document.
         *
         *     ``KEYWORD`` differs in provenance from the rest: the other members are
         *     *inferred* from the decision's prose by regex or LLM, while a keyword is
         *     *declared* by Överklagandenämnden itself on the trailer's ``Sökord:`` line.
         *     That makes it the one type the corpus vouches for, and the reason extraction
         *     reads it deterministically rather than through a strategy.
         * @enum {string}
         */
        EntityType: "legal_concept" | "role" | "parish" | "regulation" | "keyword";
        /**
         * EntityWithCount
         * @description An entity plus how many documents carry it.
         *
         *     Browsing concepts without the count is not navigable — the count is what
         *     separates a recurring legal concept from a one-off extraction artefact.
         */
        EntityWithCount: {
            /**
             * Id
             * Format: uuid
             */
            id: string;
            /** Name */
            name: string;
            /** Type */
            type: string;
            /** Document Count */
            document_count: number;
        };
        /** FacetValue */
        FacetValue: {
            /** Value */
            value: string;
            /** Count */
            count: number;
        };
        /** HTTPValidationError */
        HTTPValidationError: {
            /** Detail */
            detail?: components["schemas"]["ValidationError"][];
        };
        /** Page[DocumentSummary] */
        Page_DocumentSummary_: {
            /** Items */
            items: components["schemas"]["DocumentSummary"][];
            /** Total */
            total: number;
            /** Limit */
            limit: number;
            /** Offset */
            offset: number;
        };
        /** Page[EntityDocumentRef] */
        Page_EntityDocumentRef_: {
            /** Items */
            items: components["schemas"]["EntityDocumentRef"][];
            /** Total */
            total: number;
            /** Limit */
            limit: number;
            /** Offset */
            offset: number;
        };
        /** Page[EntityWithCount] */
        Page_EntityWithCount_: {
            /** Items */
            items: components["schemas"]["EntityWithCount"][];
            /** Total */
            total: number;
            /** Limit */
            limit: number;
            /** Offset */
            offset: number;
        };
        /**
         * ReferenceEdge
         * @description A citation with the *other* document resolved, ready to render as a link.
         *
         *     Which document ``document_id`` names depends on which side of
         *     ``ReferenceEdges`` the edge sits on.
         */
        ReferenceEdge: {
            /**
             * Document Id
             * Format: uuid
             */
            document_id: string;
            /** Case Number */
            case_number: string | null;
            /** Decision Number */
            decision_number: string | null;
            /** Decision Date */
            decision_date: string | null;
            /** Headline */
            headline: string | null;
            /** Reference Context */
            reference_context: string | null;
        };
        /**
         * SearchChunk
         * @description A matched passage, verbatim, with how each arm scored and ranked it.
         */
        SearchChunk: {
            /**
             * Chunk Id
             * Format: uuid
             */
            chunk_id: string;
            /** Chunk Index */
            chunk_index: number;
            /** Text */
            text: string;
            section: components["schemas"]["ChunkSection"];
            /** Appendix Label */
            appendix_label: string | null;
            /** Score */
            score: number;
            /** Vector Rank */
            vector_rank: number | null;
            /** Text Rank */
            text_rank: number | null;
            /** Vector Similarity */
            vector_similarity: number | null;
            /** Text Score */
            text_score: number | null;
        };
        /**
         * SearchDiagnostics
         * @description What the search actually did, so a caller can trust or debug the result.
         */
        SearchDiagnostics: {
            /** Filter Applied */
            filter_applied: boolean;
            /** Candidate Document Count */
            candidate_document_count: number | null;
            /** Vector Hit Count */
            vector_hit_count: number;
            /** Text Hit Counts */
            text_hit_counts: {
                [key: string]: number;
            };
            /** Fused Chunk Count */
            fused_chunk_count: number;
            /** Expanded */
            expanded: boolean;
            /** Widened To Appendices */
            widened_to_appendices: boolean;
            /** Vector Similarity Floor */
            vector_similarity_floor: number;
            /** Top Vector Similarity */
            top_vector_similarity: number | null;
        };
        /**
         * SearchHit
         * @description One decision, with the passages that matched it.
         *
         *     ``score`` is the best chunk's fused rank score and carries the same caveat:
         *     it orders decisions, it does not grade them. Read ``chunks[0]`` for relevance.
         */
        SearchHit: {
            /**
             * Document Id
             * Format: uuid
             */
            document_id: string;
            /** Case Number */
            case_number: string | null;
            /** Decision Number */
            decision_number: string | null;
            /** Decision Date */
            decision_date: string | null;
            /** Category */
            category: string | null;
            /** Decision Outcome */
            decision_outcome: string | null;
            /** Headline */
            headline: string | null;
            /** Summary */
            summary: string | null;
            /** Source Url */
            source_url: string;
            /** Score */
            score: number;
            /** Matched Chunk Count */
            matched_chunk_count: number;
            /** Chunks */
            chunks: components["schemas"]["SearchChunk"][];
        };
        /**
         * SearchQuery
         * @description Everything the search path needs, independent of how it arrived.
         *
         *     Deliberately free of FastAPI types: the same model serves an HTTP route, an
         *     MCP tool call, or a direct call from a test.
         */
        SearchQuery: {
            /** Query */
            query: string;
            /** Queries */
            queries?: string[] | null;
            /**
             * Expand
             * @default false
             */
            expand: boolean;
            /**
             * @default {
             *       "entity_names": [],
             *       "entity_types": [],
             *       "keywords": []
             *     }
             */
            filter: components["schemas"]["DocumentFilter"];
            /** Limit */
            limit?: number | null;
            /**
             * Offset
             * @default 0
             */
            offset: number;
            /**
             * Include Appendices
             * @default false
             */
            include_appendices: boolean;
            /** Chunks Per Document */
            chunks_per_document?: number | null;
        };
        /** SearchResponse */
        SearchResponse: {
            /** Items */
            items: components["schemas"]["SearchHit"][];
            /** Total */
            total: number;
            /** Limit */
            limit: number;
            /** Offset */
            offset: number;
            /** Effective Queries */
            effective_queries: string[];
            diagnostics: components["schemas"]["SearchDiagnostics"];
        };
        /**
         * UnresolvedCitation
         * @description A citation to a decision the corpus does not hold — text, not a link.
         */
        UnresolvedCitation: {
            /** Target Case Number */
            target_case_number: string;
            /** Reference Context */
            reference_context: string | null;
        };
        /** ValidationError */
        ValidationError: {
            /** Location */
            loc: (string | number)[];
            /** Message */
            msg: string;
            /** Error Type */
            type: string;
            /** Input */
            input?: unknown;
            /** Context */
            ctx?: Record<string, never>;
        };
    };
    responses: never;
    parameters: never;
    requestBodies: never;
    headers: never;
    pathItems: never;
}
export type $defs = Record<string, never>;
export interface operations {
    search_endpoint_api_search_post: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["SearchQuery"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["SearchResponse"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    filters_endpoint_api_filters_get: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["DocumentFacets"];
                };
            };
        };
    };
    list_documents_endpoint_api_documents_get: {
        parameters: {
            query?: {
                date_from?: string | null;
                date_to?: string | null;
                category?: string | null;
                decision_outcome?: string | null;
                case_number?: string | null;
                decision_number?: string | null;
                entity_name?: string[];
                entity_type?: string[];
                keyword?: string[];
                references_case_number?: string | null;
                newest_first?: boolean;
                limit?: number | null;
                offset?: number;
            };
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["Page_DocumentSummary_"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    document_detail_endpoint_api_documents__document_id__get: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                document_id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["DocumentDetail"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    document_chunks_endpoint_api_documents__document_id__chunks_get: {
        parameters: {
            query?: {
                section?: components["schemas"]["ChunkSection"] | null;
            };
            header?: never;
            path: {
                document_id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["DocumentChunk"][];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    document_pdf_endpoint_api_documents__document_id__pdf_get: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                document_id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": unknown;
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    list_concepts_endpoint_api_concepts_get: {
        parameters: {
            query?: {
                entity_type?: components["schemas"]["EntityType"] | null;
                q?: string | null;
                limit?: number | null;
                offset?: number;
            };
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["Page_EntityWithCount_"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    concept_documents_endpoint_api_concepts__entity_id__documents_get: {
        parameters: {
            query?: {
                relevance?: components["schemas"]["EntityRelevance"] | null;
                limit?: number | null;
                offset?: number;
            };
            header?: never;
            path: {
                entity_id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["Page_EntityDocumentRef_"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    list_keywords_endpoint_api_keywords_get: {
        parameters: {
            query?: {
                q?: string | null;
                limit?: number | null;
                offset?: number;
            };
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["Page_EntityWithCount_"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    keyword_documents_endpoint_api_keywords__keyword_id__documents_get: {
        parameters: {
            query?: {
                limit?: number | null;
                offset?: number;
            };
            header?: never;
            path: {
                keyword_id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["Page_EntityDocumentRef_"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    chat_endpoint_api_chat_post: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["ChatRequest"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": unknown;
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    healthz_healthz_get: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": {
                        [key: string]: string;
                    };
                };
            };
        };
    };
}
