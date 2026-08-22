/* The `POST /api/chat` event contract, by hand.
 *
 * Every other type in this folder comes from `schema.d.ts`, which is generated
 * from the API's OpenAPI document. These cannot: the endpoint returns a
 * `StreamingResponse`, so FastAPI publishes its request body and nothing about
 * what comes back. Regenerating the schema will never produce these, and a
 * contract change here will never show up as a compile error — so treat
 * `documentation/api/chat-endpoint.md` as the authority and keep this file in
 * step with `packages/agents/src/agents/chat/_dtos.py` by hand.
 *
 * Frames are discriminated by the **SSE event name**, not by `data.type`. The
 * route dumps whole models for `tool_call`, `tool_result` and `sql` (which
 * therefore carry `type`) but reshapes `token`, `sources`, `done` and `error`
 * (which do not). Dispatching on the event name is the one rule that holds for
 * all seven.
 */

/** Tools the orchestrator may call. The API owns this list. */
export type ChatTool =
  | "list_vocabulary"
  | "search_decisions"
  | "read_decision"
  | "inspect_decision"
  | "query_corpus"
  | "answer";

/** What a client may say is happening — a key, never a sentence.
 *
 *  Finer-grained than `ChatTool` on purpose: one tool reports more than one kind
 *  of step, so a client never has to inspect `detail` to decide what to show.
 *  The Swedish words live in `features/agent/progress-text.ts`. */
export type ProgressLabel =
  | "vocabulary.list"
  | "search.broad"
  | "search.filtered"
  | "search.refused"
  | "sql.query"
  | "decision.read"
  | "decision.inspect"
  | "answer.compose";

/** `refused` is a policy decline the agent repairs from on its next iteration —
 *  an ungrounded filter, a spent reading budget. It is a step, not a failure. */
export type ToolStatus = "ok" | "refused" | "error";

/** Structured facts about a step, never prose. Optional for a client: it exists
 *  so a label can be enriched ("7 beslut") without a contract change. */
export type ProgressDetail = {
  has_filter?: boolean;
  filter_fields?: string[];
  include_appendices?: boolean;
  document_id?: string;
  cited_chunks?: number;
  decision_count?: number;
  widened_to_appendices?: boolean;
  answered?: boolean;
  row_count?: number;
};

export type ToolCallEvent = {
  kind: "tool_call";
  id: string;
  tool: ChatTool;
  label: ProgressLabel;
  detail: ProgressDetail;
};

export type ToolResultEvent = {
  kind: "tool_result";
  id: string;
  tool: ChatTool;
  label: ProgressLabel;
  status: ToolStatus;
  detail: ProgressDetail;
};

/** One attempt the SQL sub-agent made, successful or not. The trail is what
 *  shows a reader the agent grounded a predicate before committing to a query. */
export type SqlAttempt = {
  sql: string;
  ok: boolean;
  error: string | null;
  row_count: number | null;
};

export type SqlCell = string | number | boolean | null;

/** The query behind a count, sent before the answer that rests on it.
 *  Not decorative: a count reads as authoritative and carries no excerpt to
 *  check it against, so surfacing it is the caller's stated obligation. */
export type SqlEvent = {
  kind: "sql";
  answered: boolean;
  sql: string | null;
  columns: string[];
  rows: SqlCell[][];
  row_count: number;
  truncated: boolean;
  assumptions: string[];
  attempts: SqlAttempt[];
};

export type TokenEvent = { kind: "token"; text: string };

/** One entry per cited decision, first selected passage winning.
 *
 *  `section: "appendix"` means the appealed decision — the lower instance's
 *  words, which Överklagandenämnden may have overturned. A client must not
 *  present such an excerpt as the nämnd's own reasoning. */
export type SourceReference = {
  document_id: string;
  case_number: string | null;
  decision_date: string | null;
  decision_outcome: string | null;
  category: string | null;
  excerpt: string;
  section: "body" | "appendix";
  appendix_label: string | null;
  pdf_url: string;
};

export type SourcesEvent = { kind: "sources"; sources: SourceReference[] };

export type DoneEvent = { kind: "done"; session_id: string };

/** Terminal. No `done` follows an error — a client that waits for one hangs. */
export type ErrorEvent = { kind: "error"; message: string };

export type ChatEvent =
  | ToolCallEvent
  | ToolResultEvent
  | SqlEvent
  | TokenEvent
  | SourcesEvent
  | DoneEvent
  | ErrorEvent;

export type ChatRequestBody = {
  session_id: string | null;
  message: string;
};
