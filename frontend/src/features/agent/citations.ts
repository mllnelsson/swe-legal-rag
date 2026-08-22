/* Resolving the citation markers the answer carries.
 *
 * The synthesis prompt marks each claim with the handle of the passage it
 * rests on — `[c3]`, or `[c3][c7]` where several do. This turns that prose
 * into segments a component can render, and assigns the numbers the reader
 * actually sees.
 *
 * Three rules, all of them about not showing the reader something untrue:
 *
 *  - **Numbers come from the prose, not the source list.** The first handle
 *    cited is 1, whatever order the backend sent its sources in. A reader
 *    counting down the Källor list has to land on the passage the superscript
 *    pointed at.
 *  - **An unresolvable marker is removed, never shown raw.** It happens two
 *    ways: the model names a handle it did not select, and a reopened
 *    conversation has prose but no sources (they are not persisted). `[c3]` on
 *    screen is a reference to nothing.
 *  - **A half-written marker is not a marker.** Tokens arrive mid-`[c1`, and
 *    the accumulated string is re-parsed on every one of them.
 */

import type { SourceReference } from "../../api/chat-events";

/** Append prose, merging into the previous run rather than starting a new one.
 *
 *  A dropped marker leaves prose on both sides of it, and two adjacent spans
 *  would split a sentence across DOM nodes — invisible on screen, but it means
 *  a reader's text search, and any test, no longer sees one sentence. */
function pushText(segments: AnswerSegment[], text: string): void {
  const last = segments.at(-1);
  if (last !== undefined && last.kind === "text") {
    segments[segments.length - 1] = { kind: "text", text: last.text + text };
    return;
  }
  segments.push({ kind: "text", text });
}

/** A complete marker: `[c`, digits, `]`. */
const MARKER = /\[c(\d+)\]/g;

/** A marker the stream has not finished writing, at the very end of the text. */
const PARTIAL_MARKER = /\[c?\d*$/;

export type TextSegment = { kind: "text"; text: string };

export type CitationSegment = {
  kind: "citation";
  /** What the reader sees, and the position in `citedSources`. */
  number: number;
  source: SourceReference;
};

export type AnswerSegment = TextSegment | CitationSegment;

export type ParsedAnswer = {
  segments: AnswerSegment[];
  /** The cited passages in citation order — the order Källor renders them. */
  citedSources: SourceReference[];
  /** Selected but never cited. Shown after, unnumbered: the answer did not
   *  lean on them, and numbering them would imply it did. */
  uncitedSources: SourceReference[];
};

/** Split `text` into prose and resolved citations.
 *
 *  `streaming` suppresses a trailing partial marker; pass false for a finished
 *  answer so a literal `[c` at the very end survives as text.
 */
export function parseAnswer(
  text: string,
  sources: readonly SourceReference[],
  streaming: boolean,
): ParsedAnswer {
  const byHandle = new Map(sources.map((source) => [source.handle, source]));
  const body = streaming ? text.replace(PARTIAL_MARKER, "") : text;

  const segments: AnswerSegment[] = [];
  const citedSources: SourceReference[] = [];
  const numberByHandle = new Map<string, number>();

  let cursor = 0;
  for (const match of body.matchAll(MARKER)) {
    const handle = `c${match[1]}`;
    const source = byHandle.get(handle);
    const at = match.index;

    // The prose before this marker is kept whether the marker resolves or not;
    // only the marker itself disappears when it does not.
    if (at > cursor) pushText(segments, body.slice(cursor, at));
    cursor = at + match[0].length;

    if (source === undefined) continue;

    let number = numberByHandle.get(handle);
    if (number === undefined) {
      number = citedSources.length + 1;
      numberByHandle.set(handle, number);
      citedSources.push(source);
    }
    segments.push({ kind: "citation", number, source });
  }

  if (cursor < body.length) pushText(segments, body.slice(cursor));

  return {
    segments,
    citedSources,
    uncitedSources: sources.filter((source) => !numberByHandle.has(source.handle)),
  };
}
