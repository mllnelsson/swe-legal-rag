const { Card, Icon, Button } = window.SvkBeslutsokDesignSystem_46c55d;

const FEATURES = [
  { icon: "quote", title: "Every sentence sourced", body: "Answers are assembled from passages, not paraphrase. Click any clause to land on the paragraph it came from." },
  { icon: "scale", title: "Authority, ranked honestly", body: "Binding, persuasive and secondary are separated on the page, with subsequent history flagged before you cite." },
  { icon: "folder", title: "Work lives in the matter", body: "Save authorities as you go and export a memo that already carries the passages and the citations." },
];

const STEPS = [
  ["Ask", "Plain language or a citation. Scope to a court and a date range."],
  ["Read", "A summary with numbered sources, then the authorities in weight order."],
  ["File", "Save what matters and export a memo in Word, PDF or a Bluebook list."],
];

function Sections() {
  return (
    <>
      <section style={{ maxWidth: "var(--content-max)", margin: "0 auto", padding: "var(--space-12) var(--space-8)", display: "flex", flexDirection: "column", gap: "var(--space-9)" }}>
        <div style={{ display: "flex", flexDirection: "column", gap: "var(--space-4)", maxWidth: "56ch" }}>
          <span style={{ fontSize: "var(--text-overline-size)", letterSpacing: "var(--text-overline-ls)", textTransform: "uppercase", fontWeight: 600, color: "var(--burgundy-600)" }}>What you get</span>
          <h2 style={{ fontFamily: "var(--font-display)", fontSize: "var(--text-h1-size)", lineHeight: "var(--text-h1-lh)", letterSpacing: "var(--text-h1-ls)", color: "var(--text-strong)", margin: 0 }}>Built for the part of the job that has to be right</h2>
        </div>
        <div style={{ display: "grid", gridTemplateColumns: "repeat(3, 1fr)", gap: "var(--space-6)" }}>
          {FEATURES.map((f) => (
            <Card key={f.title} padding="var(--space-8)">
              <div style={{ display: "flex", flexDirection: "column", gap: "var(--space-4)" }}>
                <span style={{ width: 38, height: 38, borderRadius: "var(--radius-md)", background: "var(--apricot-50)", border: "1px solid var(--apricot-200)", display: "grid", placeItems: "center" }}><Icon name={f.icon} size={18} color="var(--burgundy-600)" /></span>
                <h3 style={{ fontFamily: "var(--font-display)", fontSize: "var(--text-h3-size)", color: "var(--text-strong)", margin: 0 }}>{f.title}</h3>
                <p style={{ margin: 0, fontSize: "var(--text-body-size)", lineHeight: 1.6, color: "var(--text-muted)", textWrap: "pretty" }}>{f.body}</p>
              </div>
            </Card>
          ))}
        </div>
      </section>

      <section style={{ background: "var(--warm-50)", borderTop: "1px solid var(--border-hairline)", borderBottom: "1px solid var(--border-hairline)" }}>
        <div style={{ maxWidth: "var(--content-max)", margin: "0 auto", padding: "var(--space-12) var(--space-8)", display: "grid", gridTemplateColumns: "repeat(3, 1fr)", gap: "var(--space-9)" }}>
          {STEPS.map(([t, b], i) => (
            <div key={t} style={{ display: "flex", flexDirection: "column", gap: "var(--space-4)" }}>
              <span style={{ fontFamily: "var(--font-mono)", fontSize: "var(--text-caption-size)", color: "var(--apricot-600)" }}>0{i + 1}</span>
              <div style={{ height: 3, background: "var(--gradient-rule)", borderRadius: 2 }} />
              <h3 style={{ fontFamily: "var(--font-display)", fontSize: "var(--text-h2-size)", color: "var(--text-strong)", margin: 0 }}>{t}</h3>
              <p style={{ margin: 0, fontSize: "var(--text-body-size)", lineHeight: 1.6, color: "var(--text-muted)" }}>{b}</p>
            </div>
          ))}
        </div>
      </section>

      <section style={{ maxWidth: "var(--content-max)", margin: "0 auto", padding: "var(--space-12) var(--space-8)" }}>
        <div style={{ background: "var(--gradient-authority)", borderRadius: "var(--radius-xl)", padding: "var(--space-11) var(--space-10)", display: "flex", alignItems: "center", gap: "var(--space-9)" }}>
          <div style={{ flex: 1, display: "flex", flexDirection: "column", gap: "var(--space-5)" }}>
            <blockquote style={{ margin: 0, fontFamily: "var(--font-display)", fontSize: 30, lineHeight: 1.28, letterSpacing: "-0.01em", color: "var(--apricot-100)", maxWidth: "26ch" }}>The associates stopped starting from a blank page. The citations were already there.</blockquote>
            <span style={{ fontSize: "var(--text-small-size)", color: "var(--apricot-200)" }}>Partner, 40-attorney litigation firm</span>
          </div>
          <div style={{ flex: "none", display: "flex", flexDirection: "column", gap: "var(--space-4)" }}>
            <Button size="lg" variant="accent">Book a demo</Button>
            <Button size="lg" variant="ghost" style={{ color: "var(--apricot-200)" }}>Talk to sales</Button>
          </div>
        </div>
      </section>

      <footer style={{ borderTop: "1px solid var(--border-hairline)", background: "var(--warm-25)" }}>
        <div style={{ maxWidth: "var(--content-max)", margin: "0 auto", padding: "var(--space-10) var(--space-8)", display: "grid", gridTemplateColumns: "1.4fr repeat(3, 1fr)", gap: "var(--space-8)" }}>
          <div style={{ display: "flex", flexDirection: "column", gap: "var(--space-4)" }}>
            <span style={{ fontFamily: "var(--font-display)", fontSize: 22, letterSpacing: "-0.02em", color: "var(--burgundy-600)" }}>Svk Beslutsök</span>
            <p style={{ margin: 0, fontSize: "var(--text-small-size)", color: "var(--text-muted)", maxWidth: "34ch" }}>Legal research that cites itself. Not a substitute for professional judgment.</p>
          </div>
          {[["Product", ["Search", "Matters", "Memos", "Coverage"]], ["Company", ["About", "Careers", "Contact"]], ["Legal", ["Terms", "Privacy", "Security"]]].map(([h, items]) => (
            <div key={h} style={{ display: "flex", flexDirection: "column", gap: "var(--space-4)" }}>
              <span style={{ fontSize: "var(--text-overline-size)", letterSpacing: "var(--text-overline-ls)", textTransform: "uppercase", fontWeight: 600, color: "var(--text-faint)" }}>{h}</span>
              {items.map((i) => <a key={i} href="#" style={{ fontSize: "var(--text-small-size)", color: "var(--text-body)", textDecoration: "none" }}>{i}</a>)}
            </div>
          ))}
        </div>
      </footer>
    </>
  );
}

window.Sections = Sections;
