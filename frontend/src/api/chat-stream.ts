/* The client for `POST /api/chat`.
 *
 * `EventSource` cannot be used: the question travels in a request body, and
 * `EventSource` only issues GETs. So this is fetch plus a hand-rolled SSE
 * parser — which is also what lets the caller abort mid-answer and read the
 * `X-Interaction-Id` response header.
 *
 * The split between opening the stream and draining it is deliberate. Opening
 * awaits the response, so a 422 on an over-long message throws like any other
 * failed API call, before a single event exists. Everything after that arrives
 * in band, including failures — see `documentation/api/chat-endpoint.md`.
 */

import { ApiError } from "./client";
import type { ChatEvent, ChatRequestBody } from "./chat-events";

/** Correlates the whole turn — the orchestrator's iterations, both sub-agents
 *  and the streamed answer — in the trace store. Sent before the stream opens,
 *  so it survives a turn that ends in an `error` frame. */
const INTERACTION_ID_HEADER = "X-Interaction-Id";

export type ChatStream = {
  interactionId: string | null;
  events: AsyncGenerator<ChatEvent>;
};

/** POST the question and return the open stream.
 *
 *  Rejects with `ApiError` if the request never reached the server (`status: 0`)
 *  or the API refused it before streaming (422). Once this resolves, every
 *  further failure arrives as an `error` event instead.
 */
export async function openChatStream(
  body: ChatRequestBody,
  options: { signal?: AbortSignal } = {},
): Promise<ChatStream> {
  let response: Response;
  try {
    response = await fetch("/api/chat", {
      method: "POST",
      headers: { "Content-Type": "application/json", Accept: "text/event-stream" },
      body: JSON.stringify(body),
      signal: options.signal ?? null,
    });
  } catch (cause) {
    if (cause instanceof DOMException && cause.name === "AbortError") throw cause;
    throw new ApiError(0, "Kunde inte nå tjänsten", { cause });
  }

  if (!response.ok) {
    throw new ApiError(response.status, `${response.status} ${response.statusText}`);
  }
  if (response.body === null) {
    throw new ApiError(response.status, "Svaret innehöll ingen ström");
  }

  return {
    interactionId: response.headers.get(INTERACTION_ID_HEADER),
    events: readEvents(response.body),
  };
}

/** Yield one `ChatEvent` per SSE frame, in arrival order. */
async function* readEvents(body: ReadableStream<Uint8Array>): AsyncGenerator<ChatEvent> {
  const reader = body.getReader();
  // `stream: true` is what makes a multi-byte character split across two chunks
  // decode correctly — with Swedish prose arriving token by token, that is the
  // common case rather than an edge one.
  const decoder = new TextDecoder("utf-8");
  let buffer = "";
  let frame: RawFrame = emptyFrame();

  try {
    for (;;) {
      // Sequential by nature: the next chunk does not exist until this one has
      // been handed over. There is nothing to parallelise.
      // oxlint-disable-next-line no-await-in-loop
      const { done, value } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });

      let newline: number;
      while ((newline = buffer.indexOf("\n")) !== -1) {
        const line = stripCarriageReturn(buffer.slice(0, newline));
        buffer = buffer.slice(newline + 1);

        if (line === "") {
          const event = toChatEvent(frame);
          frame = emptyFrame();
          if (event !== null) yield event;
          continue;
        }
        frame = withLine(frame, line);
      }
    }
  } finally {
    reader.releaseLock();
  }
}

type RawFrame = { name: string; data: string[] };

function emptyFrame(): RawFrame {
  return { name: "", data: [] };
}

function stripCarriageReturn(line: string): string {
  return line.endsWith("\r") ? line.slice(0, -1) : line;
}

function withLine(frame: RawFrame, line: string): RawFrame {
  // A line starting with a colon is a comment. Nothing sends one today; keep-
  // alives would arrive this way, and ignoring them here costs nothing.
  if (line.startsWith(":")) return frame;

  const colon = line.indexOf(":");
  if (colon === -1) return frame;
  const field = line.slice(0, colon);
  // One optional space after the colon belongs to the framing, not the value.
  const value = line.slice(colon + 1).replace(/^ /, "");

  if (field === "event") return { ...frame, name: value };
  if (field === "data") return { ...frame, data: [...frame.data, value] };
  return frame;
}

/** Turn a parsed frame into an event, or `null` if it is not one we handle.
 *
 *  Unknown event names are dropped rather than thrown on: the contract says new
 *  event types may be added, and a client that only understands the old ones
 *  must keep working. */
function toChatEvent(frame: RawFrame): ChatEvent | null {
  if (frame.name === "" || frame.data.length === 0) return null;

  let payload: Record<string, unknown>;
  try {
    // Multiple data lines join with a newline, per the SSE spec.
    payload = JSON.parse(frame.data.join("\n")) as Record<string, unknown>;
  } catch {
    return null;
  }

  switch (frame.name) {
    case "tool_call":
    case "tool_result":
    case "sql":
    case "token":
    case "sources":
    case "done":
    case "error":
      // The payload is trusted to match the contract. Validating it here would
      // mean re-declaring the schema a third time, and a mismatch is a backend
      // bug that should be loud rather than silently dropped.
      return { ...payload, kind: frame.name } as ChatEvent;
    default:
      return null;
  }
}
