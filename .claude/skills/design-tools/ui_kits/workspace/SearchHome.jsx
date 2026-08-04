const { SearchField, Card, Icon, Tag } = window.SvkBeslutsokDesignSystem_46c55d;

function SearchHome({ onSearch }) {
  const [q, setQ] = React.useState("");
  return (
    <div style={{ minHeight: "100%", background: "var(--gradient-wash-soft)" }}>
      <div style={{ maxWidth: 860, margin: "0 auto", padding: "88px var(--space-8) var(--space-11)", display: "flex", flexDirection: "column", gap: "var(--space-8)" }}>
        <div style={{ display: "flex", flexDirection: "column", gap: "var(--space-4)" }}>
          <span style={{ fontSize: "var(--text-overline-size)", letterSpacing: "var(--text-overline-ls)", textTransform: "uppercase", fontWeight: 600, color: "var(--burgundy-600)" }}>Novak v. Harrow · Litigation</span>
          <h1 style={{ fontFamily: "var(--font-display)", fontSize: 44, lineHeight: 1.08, letterSpacing: "-0.02em", color: "var(--text-strong)", margin: 0 }}>What do you need to find?</h1>
          <p style={{ fontSize: "var(--text-body-lg-size)", lineHeight: 1.6, color: "var(--text-muted)", maxWidth: "var(--measure-prose)" }}>Ask in plain language or paste a citation. Every answer comes back with the authorities it rests on.</p>
        </div>
        <SearchField value={q} onChange={setQ} onSubmit={() => onSearch(q || SUGGESTED[0])} scope="9th Cir. · 2015–present" />
        <div style={{ display: "flex", flexDirection: "column", gap: "var(--space-4)" }}>
          <span style={{ fontSize: "var(--text-small-size)", color: "var(--text-muted)" }}>Try one of these</span>
          <div style={{ display: "flex", flexWrap: "wrap", gap: "var(--space-3)" }}>
            {SUGGESTED.map((s) => <Tag key={s} onClick={() => onSearch(s)}>{s}</Tag>)}
          </div>
        </div>
        <Card header="Recent searches" padding="0">
          <div style={{ display: "flex", flexDirection: "column" }}>
            {HISTORY.map((h, i) => (
              <button key={h.q} onClick={() => onSearch(h.q)} style={{ display: "flex", alignItems: "center", gap: "var(--space-5)", padding: "var(--space-5) var(--space-7)", border: "none", borderTop: i ? "1px solid var(--border-hairline)" : "none", background: "transparent", cursor: "pointer", textAlign: "left", font: "inherit" }}>
                <Icon name="history" size={16} color="var(--text-faint)" />
                <span style={{ flex: 1, fontSize: "var(--text-body-size)", color: "var(--text-strong)" }}>{h.q}</span>
                <span style={{ fontSize: "var(--text-caption-size)", color: "var(--text-faint)" }}>{h.n} results</span>
                <span style={{ fontSize: "var(--text-caption-size)", color: "var(--text-faint)", width: 90, textAlign: "right" }}>{h.when}</span>
              </button>
            ))}
          </div>
        </Card>
      </div>
    </div>
  );
}

window.SearchHome = SearchHome;
