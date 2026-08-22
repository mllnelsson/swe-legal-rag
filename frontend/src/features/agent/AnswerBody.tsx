import { parseAnswer, type AnswerSegment } from "./citations";
import type { SourceReference } from "../../api/chat-events";

export type AnswerBodyProps = {
  text: string;
  /** The cited passages, so a marker in the prose can be resolved. Sources
   *  arrive before the first token, so this is populated while streaming. */
  sources: readonly SourceReference[];
  /** True while tokens are still arriving. */
  streaming: boolean;
};

/** The agent's prose, with its citations resolved.
 *
 *  Rendered as plain paragraphs, not markdown. The synthesis prompt asks for
 *  "löpande text, inga rubriker", so there is nothing to parse — and a markdown
 *  renderer would be a fifth runtime dependency for a corpus of running Swedish
 *  sentences. Text goes in as text, so nothing the model writes can become
 *  markup.
 *
 *  The one thing that is parsed is the citation marker. `[c3]` becomes the
 *  superscript number of that passage in the source list below; a marker
 *  pointing at a passage that is not there is removed rather than shown, which
 *  is what a reopened conversation needs — the prose is kept, the citations
 *  were not.
 *
 *  While it streams, the trailing marker says so. A half-written answer
 *  presented as a finished one is the easiest thing to get wrong here: the
 *  sentence on screen may be about to be qualified by the next one. */
export function AnswerBody({ text, sources, streaming }: AnswerBodyProps) {
  const { segments } = parseAnswer(text, sources, streaming);
  const paragraphs = splitParagraphs(segments);

  return (
    <div
      style={{
        fontFamily: "var(--font-sans)",
        fontSize: "var(--text-body-lg-size)",
        lineHeight: "var(--text-body-lg-lh)",
        color: "var(--text-body)",
        display: "flex",
        flexDirection: "column",
        gap: "var(--space-4)",
      }}
    >
      {paragraphs.map((paragraph, index) => (
        // Paragraphs have no identity beyond their position, and the last one
        // grows as tokens arrive — an index is the honest key here. A
        // content-derived key would change on every token and remount the
        // paragraph being written.
        // oxlint-disable-next-line react/no-array-index-key
        <p key={index} style={{ margin: 0, whiteSpace: "pre-wrap" }}>
          {paragraph.map((segment, part) =>
            segment.kind === "text" ? (
              // oxlint-disable-next-line react/no-array-index-key
              <span key={part}>{segment.text}</span>
            ) : (
              <sup
                // oxlint-disable-next-line react/no-array-index-key
                key={part}
                aria-label={`Källa ${segment.number}`}
                style={{
                  fontFamily: "var(--font-mono)",
                  fontSize: "var(--text-caption-size)",
                  color: "var(--text-link)",
                  paddingLeft: "var(--space-1)",
                }}
              >
                {segment.number}
              </sup>
            ),
          )}
        </p>
      ))}

      {streaming && (
        <p
          aria-live="polite"
          style={{
            margin: 0,
            fontSize: "var(--text-small-size)",
            color: "var(--text-faint)",
            fontStyle: "italic",
          }}
        >
          {paragraphs.length === 0 ? "Skriver svaret…" : "Skriver vidare…"}
        </p>
      )}
    </div>
  );
}

/** Break the segment run on blank lines, the way the plain-text render did.
 *
 *  A paragraph break can only fall inside a text segment — a citation carries
 *  no newlines — so the split happens there and citations ride along in
 *  whichever paragraph they landed in. */
function splitParagraphs(segments: AnswerSegment[]): AnswerSegment[][] {
  const paragraphs: AnswerSegment[][] = [];
  let current: AnswerSegment[] = [];

  const flush = () => {
    if (current.some((s) => s.kind === "citation" || s.text.trim() !== "")) {
      paragraphs.push(current);
    }
    current = [];
  };

  for (const segment of segments) {
    if (segment.kind === "citation") {
      current.push(segment);
      continue;
    }
    const [first = "", ...rest] = segment.text.split(/\n{2,}/);
    if (first !== "") current.push({ kind: "text", text: first });
    for (const part of rest) {
      flush();
      if (part !== "") current.push({ kind: "text", text: part });
    }
  }
  flush();

  return paragraphs;
}
