import { useState } from "react";

import { Icon } from "../../components/display/Icon";
import { SourcesPanel } from "./SourcesPanel";
import type { SourceReference } from "../../api/chat-events";

/** A stable reference, so the default does not remount the panel each render. */
const NO_SOURCES: SourceReference[] = [];

export type SourceListProps = {
  /** Cited passages, in the order the answer first referred to them. Their
   *  position here is the superscript number the prose carries. */
  sources: SourceReference[];
  /** Selected by the agent but never cited. Rendered after, unnumbered. */
  uncited?: SourceReference[];
  /** True once the `sources` frame has arrived, whatever it contained. */
  received: boolean;
};

/** The discreet handle to an answer's sources.
 *
 *  The passages themselves live in a side panel — provenance a reader opens to
 *  verify, not the thing they came for. What stays under the answer is one quiet
 *  line: a button that says how many there are and opens them, and nothing when
 *  there are none to open.
 *
 *  An empty list is still said out loud, and inline rather than behind the
 *  button: a turn that found nothing and a turn that needed nothing both send an
 *  empty `sources` frame, and rendering nothing at all would let the reader
 *  assume the prose was sourced when it was not. That is a claim about the
 *  answer, so it belongs on the page, not one click away. */
export function SourceList({
  sources,
  uncited = NO_SOURCES,
  received,
}: SourceListProps) {
  const [open, setOpen] = useState(false);

  if (!received) return null;

  const total = sources.length + uncited.length;

  if (total === 0) {
    return (
      <p
        style={{
          margin: 0,
          fontFamily: "var(--font-sans)",
          fontSize: "var(--text-small-size)",
          color: "var(--text-muted)",
          display: "flex",
          alignItems: "center",
          gap: "var(--space-2)",
        }}
      >
        <Icon name="info" size={14} />
        Svaret vilar inte på något citerat beslut.
      </p>
    );
  }

  return (
    <div>
      <button
        type="button"
        onClick={() => setOpen(true)}
        style={{
          display: "inline-flex",
          alignItems: "center",
          gap: "var(--space-2)",
          height: "var(--control-h-sm)",
          padding: "0 var(--space-4)",
          borderRadius: "var(--radius-sm)",
          border: "1px solid var(--border-default)",
          background: "var(--surface-card)",
          fontFamily: "var(--font-sans)",
          fontSize: "var(--text-small-size)",
          fontWeight: "var(--weight-semibold)",
          color: "var(--text-strong)",
          cursor: "pointer",
        }}
      >
        <Icon name="book-open" size={14} />
        {total === 1 ? "1 källa" : `${total} källor`}
      </button>

      <SourcesPanel
        open={open}
        onClose={() => setOpen(false)}
        sources={sources}
        uncited={uncited}
      />
    </div>
  );
}
