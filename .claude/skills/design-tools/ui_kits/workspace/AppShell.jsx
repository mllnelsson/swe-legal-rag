const { SidebarNav, Button, IconButton, Icon, Toast, Dialog } = window.SvkBeslutsokDesignSystem_46c55d;

function TopBar({ view, onHome, matter }) {
  return (
    <header style={{ display: "flex", alignItems: "center", gap: "var(--space-5)", height: 56, padding: "0 var(--space-7)", background: "var(--surface-card)", borderBottom: "1px solid var(--border-hairline)", flex: "none" }}>
      <button onClick={onHome} style={{ border: "none", background: "transparent", cursor: "pointer", padding: 0, fontFamily: "var(--font-display)", fontSize: 22, letterSpacing: "-0.02em", color: "var(--burgundy-600)" }}>Svk Beslutsök</button>
      <div style={{ width: 1, height: 22, background: "var(--border-hairline)" }} />
      <span style={{ fontSize: "var(--text-small-size)", color: "var(--text-muted)" }}>{matter}</span>
      <div style={{ flex: 1 }} />
      <IconButton icon="history" label="Search history" variant="ghost" />
      <IconButton icon="circle-help" label="Help" variant="ghost" />
      <span style={{ width: 30, height: 30, borderRadius: "var(--radius-pill)", background: "var(--apricot-200)", color: "var(--burgundy-700)", display: "grid", placeItems: "center", fontSize: 12, fontWeight: 600 }}>RM</span>
    </header>
  );
}

function AppShell() {
  const [view, setView] = React.useState("home");
  const [nav, setNav] = React.useState("novak");
  const [query, setQuery] = React.useState("");
  const [doc, setDoc] = React.useState(null);
  const [saved, setSaved] = React.useState(["novak"]);
  const [toast, setToast] = React.useState(null);
  const [exporting, setExporting] = React.useState(false);

  const run = (q) => { setQuery(q); setView("results"); };
  const toggleSave = (id) => {
    setSaved((s) => s.includes(id) ? s.filter((x) => x !== id) : [...s, id]);
    setToast(saved.includes(id) ? null : { title: "Saved to Novak v. Harrow", message: "1 authority added to the matter." });
    setTimeout(() => setToast(null), 2600);
  };

  return (
    <div style={{ display: "flex", flexDirection: "column", height: "100%", fontFamily: "var(--font-sans)" }}>
      <TopBar onHome={() => setView("home")} matter="Novak v. Harrow · Litigation" />
      <div style={{ display: "flex", flex: 1, minHeight: 0 }}>
        <SidebarNav
          title="Workspace"
          value={nav}
          onChange={(v) => { setNav(v); setView(v === "history" ? "home" : "matter"); }}
          items={[...MATTERS, { value: "history", label: "Search history", icon: "history" }, { value: "library", label: "Saved authorities", icon: "bookmark", count: saved.length }]}
          footer={<Button variant="secondary" size="sm" fullWidth iconLeft={<Icon name="plus" size={14} />}>New matter</Button>}
        />
        <main style={{ flex: 1, minWidth: 0, overflow: "auto", background: "var(--warm-50)" }}>
          {view === "home" && <SearchHome onSearch={run} />}
          {view === "results" && <ResultsView query={query} onSearch={run} saved={saved} onSave={toggleSave} onOpen={(r) => { setDoc(r); setView("doc"); }} />}
          {view === "doc" && <DocumentView result={doc} onBack={() => setView("results")} saved={saved.includes(doc?.id)} onSave={() => toggleSave(doc.id)} />}
          {view === "matter" && <MatterView saved={saved} onExport={() => setExporting(true)} onOpen={(r) => { setDoc(r); setView("doc"); }} />}
        </main>
      </div>
      {toast && <div style={{ position: "fixed", right: 24, bottom: 24, zIndex: 50 }}><Toast tone="ok" title={toast.title} message={toast.message} onDismiss={() => setToast(null)} /></div>}
      <Dialog open={exporting} onClose={() => setExporting(false)} title="Export research memo"
        description="Includes the summary, every saved authority and its held passage, formatted for filing."
        footer={<><Button variant="secondary" onClick={() => setExporting(false)}>Cancel</Button><Button onClick={() => { setExporting(false); setToast({ title: "Memo exported", message: "Novak-v-Harrow-memo.docx" }); setTimeout(() => setToast(null), 2600); }}>Export</Button></>}>
        <div style={{ display: "flex", flexDirection: "column", gap: "var(--space-4)" }}>
          {["Word (.docx)", "PDF", "Copy as Bluebook list"].map((o, i) => (
            <label key={o} style={{ display: "flex", gap: "var(--space-4)", alignItems: "center", padding: "var(--space-4) var(--space-5)", border: `1px solid ${i === 0 ? "var(--apricot-300)" : "var(--border-hairline)"}`, background: i === 0 ? "var(--apricot-50)" : "var(--surface-card)", borderRadius: "var(--radius-md)", cursor: "pointer", fontSize: "var(--text-body-size)", color: "var(--text-strong)" }}>
              <input type="radio" name="fmt" defaultChecked={i === 0} />{o}
            </label>
          ))}
        </div>
      </Dialog>
    </div>
  );
}

window.AppShell = AppShell;
