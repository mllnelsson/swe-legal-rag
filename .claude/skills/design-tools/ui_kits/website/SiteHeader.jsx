const { Button, Icon } = window.SvkBeslutsokDesignSystem_46c55d;

function SiteHeader() {
  const links = ["Product", "Coverage", "Security", "Pricing"];
  return (
    <header style={{ position: "sticky", top: 0, zIndex: 30, backdropFilter: "blur(8px)", background: "rgba(255,255,255,0.82)", borderBottom: "1px solid var(--border-hairline)" }}>
      <div style={{ maxWidth: "var(--content-max)", margin: "0 auto", height: 68, padding: "0 var(--space-8)", display: "flex", alignItems: "center", gap: "var(--space-8)" }}>
        <span style={{ fontFamily: "var(--font-display)", fontSize: 24, letterSpacing: "-0.02em", color: "var(--burgundy-600)" }}>Svk Beslutsök</span>
        <nav style={{ display: "flex", gap: "var(--space-7)" }}>
          {links.map((l) => <a key={l} href="#" style={{ fontSize: "var(--text-body-size)", color: "var(--text-body)", textDecoration: "none" }}>{l}</a>)}
        </nav>
        <div style={{ flex: 1 }} />
        <a href="#" style={{ fontSize: "var(--text-body-size)", color: "var(--text-body)", textDecoration: "none" }}>Sign in</a>
        <Button variant="primary" size="sm" iconRight={<Icon name="arrow-right" size={15} />}>Book a demo</Button>
      </div>
    </header>
  );
}

window.SiteHeader = SiteHeader;
