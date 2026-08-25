import { useEffect } from "react";

import { Icon } from "../../components/display/Icon";
import { ConversationRail } from "./ConversationRail";

export type ConversationPanelProps = {
  open: boolean;
  onClose: () => void;
  /** The conversation currently open, so the rail can mark it. */
  openSessionId: string | undefined;
};

/** token-exempt: the panel is the rail's width plus a gutter on each side. */
const PANEL_WIDTH = "328px";

/** Earlier conversations, on request.
 *
 *  They used to be a 264px column beside every answer, which pushed the prose
 *  off-centre for the whole of a reader's time here in exchange for a list most
 *  of them never touch. Behind a button the answer sits in the middle of the
 *  screen, which is where a page whose entire content is one column belongs. */
export function ConversationPanel({ open, onClose, openSessionId }: ConversationPanelProps) {
  // Escape closes it. A panel over the page that only a mouse can dismiss is one
  // a keyboard reader is stuck behind.
  useEffect(() => {
    if (!open) return;
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") onClose();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open, onClose]);

  if (!open) return null;

  return (
    <>
      <div
        onClick={onClose}
        aria-hidden="true"
        style={{
          position: "fixed",
          inset: 0,
          zIndex: 20,
          background: "var(--surface-overlay)",
        }}
      />
      <aside
        aria-label="Tidigare samtal"
        style={{
          position: "fixed",
          top: 0,
          right: 0,
          bottom: 0,
          zIndex: 21,
          width: PANEL_WIDTH,
          maxWidth: "100%",
          overflowY: "auto",
          padding: "var(--space-7) var(--gutter-page)",
          background: "var(--surface-card)",
          boxShadow: "var(--shadow-overlay)",
        }}
      >
        <div
          style={{
            display: "flex",
            justifyContent: "flex-end",
            marginBottom: "var(--space-5)",
          }}
        >
          <button
            type="button"
            onClick={onClose}
            aria-label="Stäng"
            style={{
              display: "inline-flex",
              alignItems: "center",
              justifyContent: "center",
              height: "var(--control-h-sm)",
              width: "var(--control-h-sm)",
              borderRadius: "var(--radius-sm)",
              border: "1px solid var(--border-default)",
              background: "var(--surface-card)",
              color: "var(--text-body)",
              cursor: "pointer",
            }}
          >
            <Icon name="x" size={15} />
          </button>
        </div>

        {/* The page header offers "Nytt samtal" whether or not this is open. */}
        <ConversationRail openSessionId={openSessionId} offerNewConversation={false} />
      </aside>
    </>
  );
}
