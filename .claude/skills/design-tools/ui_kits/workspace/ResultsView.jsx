const { SearchField, AnswerPanel, CitationCard, Tabs, Tag, Checkbox, Select, Card, Icon } = window.SvkBeslutsokDesignSystem_46c55d;

function FilterRail() {
  const [binding, setBinding] = React.useState(true);
  const [unpub, setUnpub] = React.useState(false);
  return (
    <aside style={{ width: 248, flex: "none", display: "flex", flexDirection: "column", gap: "var(--space-6)" }}>
      <Card padding="var(--space-6)">
        <div style={{ display: "flex", flexDirection: "column", gap: "var(--space-5)" }}>
          <span style={{ fontSize: "var(--text-overline-size)", letterSpacing: "var(--text-overline-ls)", textTransform: "uppercase", fontWeight: 600, color: "var(--text-faint)" }}>Filters</span>
          <Select label="Jurisdiction" size="sm" options={["9th Circuit", "All federal", "N.D. Cal."]} />
          <Select label="Date" size="sm" options={["2015 – present", "Last 3 years", "Any"]} />
          <Checkbox label="Binding only" checked={binding} onChange={setBinding} />
          <Checkbox label="Include unpublished" checked={unpub} onChange={setUnpub} />
        </div>
      </Card>
      <Card padding="var(--space-6)" tone="accent">
        <div style={{ display: "flex", flexDirection: "column", gap: "var(--space-3)" }}>
          <span style={{ fontSize: "var(--text-small-size)", fontWeight: 600, color: "var(--burgundy-700)" }}>Narrow by issue</span>
          {["Duty of care", "Carmack preemption", "Tariff allocation"].map((t) => (
            <button key={t} style={{ textAlign: "left", border: "none", background: "transparent", padding: 0, cursor: "pointer", font: "inherit", fontSize: "var(--text-small-size)", color: "var(--burgundy-600)" }}>{t}</button>
          ))}
        </div>
      </Card>
    </aside>
  );
}

function ResultsView({ query, onSearch, saved, onSave, onOpen }) {
  const [q, setQ] = React.useState(query);
  const [tab, setTab] = React.useState("all");
  React.useEffect(() => setQ(query), [query]);
  const shown = tab === "all" ? RESULTS : RESULTS.filter((r) => (tab === "cases" ? r.court && r.court !== "Statute" && r.court !== "Secondary" : tab === "statutes" ? r.court === "Statute" : r.court === "Secondary"));
  return (
    <div style={{ maxWidth: 1180, margin: "0 auto", padding: "var(--space-8)", display: "flex", flexDirection: "column", gap: "var(--space-7)" }}>
      <SearchField value={q} onChange={setQ} onSubmit={onSearch} scope="9th Cir. · 2015–present" />
      <div style={{ display: "flex", gap: "var(--space-8)", alignItems: "flex-start" }}>
        <div style={{ flex: 1, minWidth: 0, display: "flex", flexDirection: "column", gap: "var(--space-6)" }}>
          <AnswerPanel question={query} answer={<p style={{ margin: 0 }}>{ANSWER}</p>} sources={RESULTS.slice(0, 3).map((r) => r.citation)} />
          <div style={{ display: "flex", alignItems: "center", gap: "var(--space-5)" }}>
            <Tabs value={tab} onChange={setTab} style={{ flex: 1 }} tabs={[{ value: "all", label: "All", count: RESULTS.length }, { value: "cases", label: "Cases", count: 3 }, { value: "statutes", label: "Statutes", count: 1 }, { value: "secondary", label: "Secondary", count: 1 }]} />
          </div>
          <div style={{ display: "flex", flexWrap: "wrap", gap: "var(--space-3)" }}>
            <Tag selected onRemove={() => {}}>9th Cir.</Tag>
            <Tag selected onRemove={() => {}}>2015 – present</Tag>
            <span style={{ marginLeft: "auto", fontSize: "var(--text-caption-size)", color: "var(--text-faint)", alignSelf: "center" }}>Sorted by relevance</span>
          </div>
          <div style={{ display: "flex", flexDirection: "column", gap: "var(--space-4)" }}>
            {shown.map((r) => (
              <CitationCard key={r.id} {...r} saved={saved.includes(r.id)} onSave={() => onSave(r.id)} onOpen={() => onOpen(r)} />
            ))}
          </div>
        </div>
        <FilterRail />
      </div>
    </div>
  );
}

window.ResultsView = ResultsView;
