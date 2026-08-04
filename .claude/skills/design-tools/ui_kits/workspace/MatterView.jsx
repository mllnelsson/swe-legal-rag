const { Button, Card, CitationCard, Icon, Badge, Tabs } = window.SvkBeslutsokDesignSystem_46c55d;

function MatterView({ saved, onExport, onOpen }) {
  const [tab, setTab] = React.useState("authorities");
  const items = RESULTS.filter((r) => saved.includes(r.id));
  return (
    <div style={{ maxWidth: 1180, margin: "0 auto", padding: "var(--space-8)", display: "flex", flexDirection: "column", gap: "var(--space-7)" }}>
      <div style={{ display: "flex", alignItems: "flex-end", gap: "var(--space-6)" }}>
        <div style={{ flex: 1, display: "flex", flexDirection: "column", gap: "var(--space-3)" }}>
          <span style={{ fontSize: "var(--text-overline-size)", letterSpacing: "var(--text-overline-ls)", textTransform: "uppercase", fontWeight: 600, color: "var(--text-faint)" }}>Matter</span>
          <h1 style={{ fontFamily: "var(--font-display)", fontSize: "var(--text-h1-size)", lineHeight: "var(--text-h1-lh)", letterSpacing: "var(--text-h1-ls)", color: "var(--text-strong)", margin: 0 }}>Novak v. Harrow Logistics</h1>
          <div style={{ display: "flex", gap: "var(--space-4)", fontSize: "var(--text-small-size)", color: "var(--text-muted)" }}>
            <span>Opened 14 Mar</span><span>·</span><span>R. Mahoney, lead</span><span>·</span><span>{items.length} saved authorities</span>
          </div>
        </div>
        <Button variant="secondary" iconLeft={<Icon name="download" size={16} />} onClick={onExport}>Export memo</Button>
      </div>
      <Tabs value={tab} onChange={setTab} tabs={[{ value: "authorities", label: "Authorities", count: items.length }, { value: "notes", label: "Notes" }, { value: "team", label: "Team" }]} />
      {tab === "authorities" && (
        <div style={{ display: "flex", gap: "var(--space-8)", alignItems: "flex-start" }}>
          <div style={{ flex: 1, minWidth: 0, display: "flex", flexDirection: "column", gap: "var(--space-4)" }}>
            {items.length === 0 ? (
              <Card tone="accent"><span style={{ fontSize: "var(--text-body-size)", color: "var(--burgundy-700)" }}>Nothing saved yet. Save an authority from any result to build the memo.</span></Card>
            ) : items.map((r) => <CitationCard key={r.id} {...r} saved onOpen={() => onOpen(r)} />)}
          </div>
          <aside style={{ width: 288, flex: "none", display: "flex", flexDirection: "column", gap: "var(--space-5)" }}>
            <Card padding="var(--space-6)" header="Coverage">
              <div style={{ display: "flex", flexDirection: "column", gap: "var(--space-4)" }}>
                {[["Binding", "binding", 2], ["Persuasive", "persuasive", 1], ["Secondary", "neutral", 1]].map(([l, t, n]) => (
                  <div key={l} style={{ display: "flex", alignItems: "center", gap: "var(--space-4)" }}>
                    <Badge tone={t}>{l}</Badge>
                    <span style={{ marginLeft: "auto", fontFamily: "var(--font-mono)", fontSize: "var(--text-caption-size)", color: "var(--text-muted)" }}>{n}</span>
                  </div>
                ))}
              </div>
            </Card>
            <Card padding="var(--space-6)" tone="wash">
              <div style={{ display: "flex", flexDirection: "column", gap: "var(--space-3)" }}>
                <span style={{ fontSize: "var(--text-small-size)", fontWeight: 600, color: "var(--burgundy-700)" }}>Gap check</span>
                <p style={{ margin: 0, fontSize: "var(--text-small-size)", lineHeight: 1.55, color: "var(--text-body)" }}>No out-of-circuit contrary authority saved. Consider adding Ellery Freight before filing.</p>
              </div>
            </Card>
          </aside>
        </div>
      )}
      {tab !== "authorities" && (
        <Card><span style={{ fontSize: "var(--text-body-size)", color: "var(--text-muted)" }}>Not part of the supplied source material — left intentionally blank.</span></Card>
      )}
    </div>
  );
}

window.MatterView = MatterView;
