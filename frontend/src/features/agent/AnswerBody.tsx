export type AnswerBodyProps = {
  text: string;
  /** True while tokens are still arriving. */
  streaming: boolean;
};

/** The agent's prose.
 *
 *  Rendered as plain paragraphs, not markdown. The synthesis prompt asks for
 *  "löpande text, inga rubriker", so there is nothing to parse — and a markdown
 *  renderer would be a fifth runtime dependency for a corpus of running Swedish
 *  sentences. Text goes in as text, so nothing the model writes can become
 *  markup.
 *
 *  While it streams, the trailing marker says so. A half-written answer
 *  presented as a finished one is the easiest thing to get wrong here: the
 *  sentence on screen may be about to be qualified by the next one. */
export function AnswerBody({ text, streaming }: AnswerBodyProps) {
  const paragraphs = text.split(/\n{2,}/).filter((part) => part.trim() !== "");

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
          {paragraph}
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
