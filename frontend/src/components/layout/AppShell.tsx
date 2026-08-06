import { Link, NavLink, Outlet } from "react-router";

/** token-exempt: the design system fixes the app header at 56px. */
const HEADER_HEIGHT = "56px";

export function AppShell() {
  return (
    <div style={{ minHeight: "100vh", background: "var(--surface-page)" }}>
      <header
        style={{
          position: "sticky",
          top: 0,
          zIndex: 10,
          height: HEADER_HEIGHT,
          display: "flex",
          alignItems: "center",
          gap: "var(--space-7)",
          padding: "0 var(--gutter-page)",
          background: "var(--surface-card)",
          boxShadow: "var(--shadow-inset-hairline)",
        }}
      >
        {/* Sentence case, never letterspaced — the wordmark is the display serif. */}
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

        <nav style={{ display: "flex", gap: "var(--space-6)" }}>
          <ShellLink to="/sokord">Sökord</ShellLink>
          <ShellLink to="/begrepp">Begrepp</ShellLink>
        </nav>
      </header>

      <Outlet />
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
