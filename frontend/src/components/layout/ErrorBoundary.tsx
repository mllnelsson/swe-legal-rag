import { Component, type ErrorInfo, type ReactNode } from "react";

/* The app's only class component, because an error boundary has to be one.
 *
 * It exists for the same reason the honesty rules do: a surface that cannot say
 * what went wrong says nothing, and a blank white page is the least honest
 * failure this app can produce. A render that throws — a malformed frame folded
 * into a turn, a field the API stopped sending — used to take the whole document
 * with it, which is what a reader experienced as "it crashed".
 */

export type ErrorBoundaryProps = {
  children: ReactNode;
};

type ErrorBoundaryState = {
  failed: boolean;
};

export class ErrorBoundary extends Component<ErrorBoundaryProps, ErrorBoundaryState> {
  override state: ErrorBoundaryState = { failed: false };

  static getDerivedStateFromError(): ErrorBoundaryState {
    return { failed: true };
  }

  /** The reader gets a statement; the console gets the cause. Putting the
   *  message on screen would tell them a stack trace instead of a next step,
   *  and the cause is a developer's to read. */
  override componentDidCatch(error: Error, info: ErrorInfo): void {
    // oxlint-disable-next-line no-console -- the only place a render failure is recoverable from
    console.error("Rendering failed", error, info.componentStack);
  }

  override render(): ReactNode {
    if (!this.state.failed) return this.props.children;

    return (
      <main
        style={{
          display: "flex",
          flexDirection: "column",
          alignItems: "center",
          justifyContent: "center",
          gap: "var(--space-5)",
          minHeight: "calc(100vh - var(--section-gap))",
          padding: "var(--space-9) var(--gutter-page)",
          textAlign: "center",
          fontFamily: "var(--font-sans)",
        }}
      >
        <h1
          style={{
            margin: 0,
            fontFamily: "var(--font-display)",
            fontSize: "var(--text-h1-size)",
            lineHeight: "var(--text-h1-lh)",
            letterSpacing: "var(--text-h1-ls)",
            fontWeight: "var(--weight-regular)",
            color: "var(--text-strong)",
          }}
        >
          Sidan kunde inte visas
        </h1>
        <p
          style={{
            margin: 0,
            maxWidth: "var(--measure-narrow)",
            fontSize: "var(--text-body-size)",
            lineHeight: "var(--text-body-lh)",
            color: "var(--text-muted)",
          }}
        >
          Något gick fel när innehållet skulle ritas upp. Inget har sparats eller
          ändrats — ladda om sidan och pröva igen.
        </p>
        {/* A full reload, not a router navigation: the component tree that threw
            is still mounted above this, and only a reload is certain to clear it. */}
        <a
          href="/"
          style={{
            height: "var(--control-h-md)",
            display: "inline-flex",
            alignItems: "center",
            padding: "0 var(--space-6)",
            borderRadius: "var(--radius-pill)",
            border: "1px solid var(--burgundy-700)",
            background: "var(--action-primary)",
            color: "var(--apricot-50)",
            fontSize: "var(--text-small-size)",
            fontWeight: "var(--weight-semibold)",
            textDecoration: "none",
          }}
        >
          Till startsidan
        </a>
      </main>
    );
  }
}
