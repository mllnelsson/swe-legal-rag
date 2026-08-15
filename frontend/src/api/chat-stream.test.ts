/* The SSE parser, against the framing the API actually writes.
 *
 * Worth testing on its own because none of it is checked by the type system:
 * the frames arrive as bytes, the boundaries fall wherever the network puts
 * them, and a parser that quietly drops the last frame looks exactly like an
 * agent that stopped talking.
 */

import { afterEach, describe, expect, it, vi } from "vitest";

import { ApiError } from "./client";
import { openChatStream } from "./chat-stream";
import type { ChatEvent } from "./chat-events";

const encoder = new TextEncoder();

/** A response body that hands over exactly these byte chunks, in order. */
function streamOf(...chunks: string[]): ReadableStream<Uint8Array> {
  return new ReadableStream({
    start(controller) {
      for (const chunk of chunks) controller.enqueue(encoder.encode(chunk));
      controller.close();
    },
  });
}

function respondWith(
  body: ReadableStream<Uint8Array>,
  init: { status?: number; headers?: Record<string, string> } = {},
) {
  const response = new Response(body, {
    status: init.status ?? 200,
    headers: init.headers ?? {},
  });
  vi.stubGlobal("fetch", vi.fn().mockResolvedValue(response));
}

async function collect(...chunks: string[]): Promise<ChatEvent[]> {
  respondWith(streamOf(...chunks));
  const stream = await openChatStream({ session_id: null, message: "Vad gäller?" });
  const events: ChatEvent[] = [];
  for await (const event of stream.events) events.push(event);
  return events;
}

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("frame parsing", () => {
  it("reads one event per frame, in order", async () => {
    const events = await collect(
      'event: token\ndata: {"text":"Hej"}\n\n',
      'event: token\ndata: {"text":" världen"}\n\n',
      'event: done\ndata: {"session_id":"s-1"}\n\n',
    );

    expect(events.map((e) => e.kind)).toEqual(["token", "token", "done"]);
    expect(events[0]).toEqual({ kind: "token", text: "Hej" });
    expect(events[2]).toEqual({ kind: "done", session_id: "s-1" });
  });

  it("reassembles a frame split across chunk boundaries", async () => {
    // The common case, not an edge one: the API flushes one token at a time and
    // the network splits wherever it likes.
    const events = await collect("event: tok", 'en\ndata: {"te', 'xt":"Hej"}\n', "\n");

    expect(events).toEqual([{ kind: "token", text: "Hej" }]);
  });

  it("decodes a multi-byte character split across chunks", async () => {
    const bytes = encoder.encode('event: token\ndata: {"text":"åäö"}\n\n');
    const split = 22; // lands mid-character in the JSON payload
    respondWith(
      new ReadableStream({
        start(controller) {
          controller.enqueue(bytes.slice(0, split));
          controller.enqueue(bytes.slice(split));
          controller.close();
        },
      }),
    );

    const stream = await openChatStream({ session_id: null, message: "hej" });
    const events: ChatEvent[] = [];
    for await (const event of stream.events) events.push(event);

    expect(events).toEqual([{ kind: "token", text: "åäö" }]);
  });

  it("joins multiple data lines with a newline, per the SSE spec", async () => {
    const events = await collect('event: token\ndata: {"text":\ndata: "Hej"}\n\n');

    expect(events).toEqual([{ kind: "token", text: "Hej" }]);
  });

  it("ignores comment lines", async () => {
    // Nothing sends keep-alives today. When something does, it must not read as
    // an event, and it must not swallow the frame after it.
    const events = await collect(': ping\n\nevent: token\ndata: {"text":"Hej"}\n\n');

    expect(events).toEqual([{ kind: "token", text: "Hej" }]);
  });

  it("tolerates CRLF framing", async () => {
    const events = await collect('event: token\r\ndata: {"text":"Hej"}\r\n\r\n');

    expect(events).toEqual([{ kind: "token", text: "Hej" }]);
  });
});

describe("forward compatibility", () => {
  it("skips an event type it does not know", async () => {
    // The contract says new event types may be added; a client that only
    // understands today's must keep working rather than throw.
    const events = await collect(
      'event: heartbeat\ndata: {"at":1}\n\n',
      'event: token\ndata: {"text":"Hej"}\n\n',
    );

    expect(events).toEqual([{ kind: "token", text: "Hej" }]);
  });

  it("skips a frame whose data is not JSON", async () => {
    const events = await collect(
      "event: token\ndata: not json\n\n",
      'event: token\ndata: {"text":"Hej"}\n\n',
    );

    expect(events).toEqual([{ kind: "token", text: "Hej" }]);
  });
});

describe("what a truncated stream looks like", () => {
  it("ends without a done event rather than inventing one", async () => {
    // The hook turns this into "avbruten". Silently succeeding here would make
    // a half-written answer look finished.
    const events = await collect('event: token\ndata: {"text":"Hej"}\n\n');

    expect(events.some((e) => e.kind === "done")).toBe(false);
  });

  it("drops a frame that never got its blank line", async () => {
    const events = await collect('event: token\ndata: {"text":"Hej"}\n\nevent: token\n');

    expect(events).toEqual([{ kind: "token", text: "Hej" }]);
  });
});

describe("failures before the stream opens", () => {
  it("raises ApiError on a 422 rather than yielding events", async () => {
    respondWith(streamOf(""), { status: 422 });

    await expect(
      openChatStream({ session_id: null, message: "x" }),
    ).rejects.toBeInstanceOf(ApiError);
  });

  it("reports a request that never reached the server as status 0", async () => {
    vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new TypeError("offline")));

    await expect(openChatStream({ session_id: null, message: "x" })).rejects.toMatchObject(
      { status: 0 },
    );
  });
});

describe("correlation", () => {
  it("hands back the interaction id from the response header", async () => {
    respondWith(streamOf('event: done\ndata: {"session_id":"s-1"}\n\n'), {
      headers: { "X-Interaction-Id": "11111111-1111-4111-8111-111111111111" },
    });

    const stream = await openChatStream({ session_id: null, message: "hej" });

    expect(stream.interactionId).toBe("11111111-1111-4111-8111-111111111111");
  });

  it("is null when the header is absent rather than throwing", async () => {
    respondWith(streamOf('event: done\ndata: {"session_id":"s-1"}\n\n'));

    const stream = await openChatStream({ session_id: null, message: "hej" });

    expect(stream.interactionId).toBeNull();
  });
});
