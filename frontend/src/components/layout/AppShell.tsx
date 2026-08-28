import { Link, NavLink, Outlet, useLocation } from "react-router";

import { ErrorBoundary } from "./ErrorBoundary";

/** token-exempt: the design system fixes the app header at 56px. */
const HEADER_HEIGHT = "56px";

/** The home page carries its own wordmark at display size, as the one thing on
 *  the screen. A second one in the header would say the name twice and put a
 *  band of chrome above a page whose whole point is that there is nothing above
 *  the box. So on `/` the header keeps its links and gives up everything else. */
const BARE_HEADER_PATH = "/";

export function AppShell() {
  const bare = useLocation().pathname === BARE_HEADER_PATH;

  return (
    <div style={{ minHeight: "100vh", background: "var(--surface-page)" }}>
      <header
        style={{
          position: bare ? "absolute" : "sticky",
          top: 0,
          left: 0,
          right: 0,
          zIndex: 10,
          height: HEADER_HEIGHT,
          display: "flex",
          alignItems: "center",
          gap: "var(--space-7)",
          padding: "0 var(--gutter-page)",
          background: bare ? "transparent" : "var(--surface-card)",
          boxShadow: bare ? "none" : "var(--shadow-inset-hairline)",
        }}
      >
        {/* Sentence case, never letterspaced — the wordmark is the display serif. */}
        {!bare && (
          <Link
            to="/"
            style={{
              fontFamily: "var(--font-display)",
              fontSize: "var(--text-h3-size)",
              letterSpacing: "-0.02em",
              color: "var(--burgundy-600)",
              textDecoration: "none",
            }}
          >
            Svk Beslutsök
          </Link>
        )}

        <nav
          style={{
            display: "flex",
            gap: "var(--space-6)",
            // Pushed to the trailing edge on the home page, where there is no
            // wordmark to sit beside.
            marginLeft: bare ? "auto" : undefined,
          }}
        >
          <ShellLink to="/agent">Agent</ShellLink>
          <ShellLink to="/sokord">Sökord</ShellLink>
          <ShellLink to="/begrepp">Referenser</ShellLink>
        </nav>
      </header>

      {/* Inside the shell rather than around it, so a page that throws still
          leaves the reader somewhere to go. */}
      <ErrorBoundary>
        <Outlet />
      </ErrorBoundary>
    </div>
  );
}

function ShellLink({ to, children }: { to: string; children: string }) {
  return (
    <NavLink
      to={to}
      style={({ isActive }) => ({
        fontFamily: "var(--font-sans)",
        fontSize: "var(--text-small-size)",
        fontWeight: "var(--weight-semibold)",
        color: isActive ? "var(--text-strong)" : "var(--text-muted)",
        textDecoration: "none",
      })}
    >
      {children}
    </NavLink>
  );
}
