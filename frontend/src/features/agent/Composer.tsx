import { useState, type KeyboardEvent } from "react";

import { Icon } from "../../components/display/Icon";
import { ASK_BOX_TRANSITION_NAME } from "./ask-box-transition";

export type ComposerProps = {
  onSubmit: (question: string) => void;
  onStop: () => void;
  /** True while a turn is open: sending is closed and Stop is offered instead. */
  busy: boolean;
  autoFocus?: boolean;
};

/** token-exempt: three lines of text at the body size, before it scrolls. */
const TEXTAREA_MIN_HEIGHT = "76px";

/** The question box.
 *
 *  A textarea rather than the `AskBox` input: an agent question is a sentence or
 *  three, not a search term, and Shift+Enter has to make a newline. Like the
 *  AskBox it interprets nothing — it hands text to its caller. */
export function Composer({ onSubmit, onStop, busy, autoFocus = false }: ComposerProps) {
  const [draft, setDraft] = useState("");
  const [focus, setFocus] = useState(false);
  const empty = draft.trim() === "";

  function submit() {
    if (busy || empty) return;
    onSubmit(draft);
    setDraft("");
  }

  function onKeyDown(event: KeyboardEvent<HTMLTextAreaElement>) {
    if (event.key === "Enter" && !event.shiftKey) {
      event.preventDefault();
      submit();
    }
  }

  return (
    <form
      onSubmit={(event) => {
        event.preventDefault();
        submit();
      }}
      style={{
        display: "flex",
        flexDirection: "column",
        gap: "var(--space-4)",
        padding: "var(--space-5)",
        background: "var(--surface-card)",
        border: `1px solid ${focus ? "var(--apricot-400)" : "var(--border-hairline)"}`,
        borderRadius: "var(--radius-xl)",
        boxShadow: focus ? "var(--ring-focus), var(--shadow-md)" : "var(--shadow-md)",
        transition: "var(--transition-control)",
        // Claimed so a question asked from the home page arrives as this box
        // moving into place rather than as one control replacing another.
        viewTransitionName: ASK_BOX_TRANSITION_NAME,
      }}
    >
      <textarea
        value={draft}
        onChange={(event) => setDraft(event.target.value)}
        onKeyDown={onKeyDown}
        onFocus={() => setFocus(true)}
        onBlur={() => setFocus(false)}
        autoFocus={autoFocus}
        aria-label="Fråga agenten"
        placeholder="Fråga om Överklagandenämndens beslut"
        rows={3}
        style={{
          minHeight: TEXTAREA_MIN_HEIGHT,
          resize: "vertical",
          border: "none",
          outline: "none",
          background: "transparent",
          fontFamily: "var(--font-sans)",
          fontSize: "var(--text-body-size)",
          lineHeight: "var(--text-body-lh)",
          color: "var(--text-strong)",
        }}
      />

      <div
        style={{
          display: "flex",
          alignItems: "center",
          justifyContent: "space-between",
          gap: "var(--space-4)",
        }}
      >
        <span
          style={{
            fontFamily: "var(--font-sans)",
            fontSize: "var(--text-caption-size)",
            color: "var(--text-faint)",
          }}
        >
          Enter skickar · Skift+Enter ny rad
        </span>

        {busy ? (
          <button
            type="button"
            onClick={onStop}
            style={{ ...buttonStyle, background: "var(--surface-sunken)", color: "var(--text-body)", borderColor: "var(--border-default)" }}
          >
            <Icon name="x" size={15} />
            Avbryt
          </button>
        ) : (
          <button
            type="submit"
            disabled={empty}
            style={{
              ...buttonStyle,
              background: "var(--action-primary)",
              borderColor: "var(--burgundy-700)",
              color: "var(--apricot-50)",
              cursor: empty ? "not-allowed" : "pointer",
              opacity: empty ? 0.42 : 1,
            }}
          >
            Fråga
          </button>
        )}
      </div>
    </form>
  );
}

const buttonStyle = {
  height: "var(--control-h-md)",
  padding: "0 var(--space-6)",
  borderRadius: "var(--radius-pill)",
  border: "1px solid",
  fontFamily: "var(--font-sans)",
  fontSize: "var(--text-small-size)",
  fontWeight: "var(--weight-semibold)",
  cursor: "pointer",
  display: "inline-flex",
  alignItems: "center",
  gap: "var(--space-2)",
  transition: "var(--transition-control)",
} as const;
