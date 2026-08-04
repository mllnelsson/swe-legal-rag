const { Button, IconButton, Badge, Card, Icon, Tabs, Tooltip } = window.SvkBeslutsokDesignSystem_46c55d;

const BODY = [
  "Harrow Logistics contracted with Meridian Foods to move refrigerated produce from Fresno to Portland. The bill of lading named Meridian's Portland warehouse as consignee. Harrow's dispatch records show the load was scheduled for transfer to Novak Provisions the same afternoon.",
  "A carrier that accepts goods for delivery assumes a duty of reasonable care toward every party it knows will take possession downstream, not merely the consignee named on the bill of lading. The district court's contrary reading would leave a foreseeable plaintiff without recourse whenever a shipper's paperwork lags its practice.",
  "We do not disturb the rule that claims for loss or damage occurring in transit are preempted by the Carmack Amendment. The duty we recognize today is narrower: it governs the carrier's conduct toward known downstream recipients, and it does not create a parallel remedy for cargo loss.",
];

function DocumentView({ result, onBack, saved, onSave }) {
  const [tab, setTab] = React.useState("opinion");
  if (!result) return null;
  return (
    <div style={{ maxWidth: 1180, margin: "0 auto", padding: "var(--space-8)", display: "flex", flexDirection: "column", gap: "var(--space-6)" }}>
      <div style={{ display: "flex", alignItems: "center", gap: "var(--space-4)" }}>
        <Button variant="ghost" size="sm" iconLeft={<Icon name="arrow-left" size={15} />} onClick={onBack}>Back to results</Button>
        <div style={{ flex: 1 }} />
        <Tooltip label="Copy Bluebook citation"><IconButton icon="quote" label="Copy citation" /></Tooltip>
        <IconButton icon="link-2" label="Copy link" />
        <Button variant={saved ? "accent" : "secondary"} size="sm" iconLeft={<Icon name={saved ? "bookmark-check" : "bookmark"} size={15} />} onClick={onSave}>{saved ? "Saved" : "Save to matter"}</Button>
      </div>
      <div style={{ display: "flex", gap: "var(--space-8)", alignItems: "flex-start" }}>
        <article style={{ flex: 1, minWidth: 0, background: "var(--surface-card)", border: "1px solid var(--border-hairline)", borderRadius: "var(--radius-lg)", boxShadow: "var(--shadow-sm)", padding: "var(--space-9) var(--space-10)" }}>
          <div style={{ display: "flex", alignItems: "center", gap: "var(--space-3)", marginBottom: "var(--space-4)" }}>
            <Badge tone={result.authority === "binding" ? "binding" : result.authority === "persuasive" ? "persuasive" : "neutral"}>{result.authority[0].toUpperCase() + result.authority.slice(1)}</Badge>
            {result.treatment && <Badge tone={result.treatment === "Followed" ? "ok" : "warn"}>{result.treatment}</Badge>}
          </div>
          <h1 style={{ fontFamily: "var(--font-display)", fontSize: "var(--text-h1-size)", lineHeight: "var(--text-h1-lh)", letterSpacing: "var(--text-h1-ls)", color: "var(--text-strong)", margin: 0 }}>{result.title}</h1>
          <div style={{ fontFamily: "var(--font-mono)", fontSize: "var(--text-cite-size)", color: "var(--text-muted)", marginTop: "var(--space-3)" }}>{result.citation}{result.court ? ` · ${result.court} ${result.year}` : ""}</div>
          <div style={{ height: 3, background: "var(--gradient-rule)", borderRadius: 2, margin: "var(--space-6) 0" }} />
          <Tabs value={tab} onChange={setTab} tabs={[{ value: "opinion", label: "Opinion" }, { value: "history", label: "Subsequent history" }, { value: "citing", label: "Citing references", count: 143 }]} style={{ marginBottom: "var(--space-6)" }} />
          <div style={{ display: "flex", flexDirection: "column", gap: "var(--space-5)", maxWidth: "var(--measure-prose)" }}>
            {BODY.map((p, i) => (
              <p key={i} style={{ fontSize: "var(--text-body-lg-size)", lineHeight: 1.68, color: "var(--text-body)", textWrap: "pretty", background: i === 1 ? "var(--apricot-50)" : "transparent", boxShadow: i === 1 ? "0 0 0 6px var(--apricot-50)" : "none", borderRadius: i === 1 ? 2 : 0 }}>{p}</p>
            ))}
          </div>
        </article>
        <aside style={{ width: 288, flex: "none", display: "flex", flexDirection: "column", gap: "var(--space-5)" }}>
          <Card padding="var(--space-6)" header="Why this matched">
            <p style={{ fontSize: "var(--text-small-size)", lineHeight: 1.55, color: "var(--text-body)", margin: 0 }}>Holding paragraph states the duty extends beyond the named consignee — directly on point for the question asked.</p>
          </Card>
          <Card padding="var(--space-6)" header="Cited by (143)">
            <div style={{ display: "flex", flexDirection: "column", gap: "var(--space-5)" }}>
              {[["Delgado Bros. Trucking", "2019 WL 3821194", "Followed"], ["Marchand Produce Co.", "704 F. App'x 512", "Criticized"], ["Pacific Cold Storage", "2021 WL 118844", "Followed"]].map(([n, c, t]) => (
                <div key={n} style={{ display: "flex", flexDirection: "column", gap: 3 }}>
                  <span style={{ fontSize: "var(--text-small-size)", fontWeight: 600, color: "var(--text-strong)" }}>{n}</span>
                  <span style={{ fontFamily: "var(--font-mono)", fontSize: "var(--text-caption-size)", color: "var(--text-muted)" }}>{c}</span>
                  <Badge tone={t === "Followed" ? "ok" : "warn"} style={{ alignSelf: "flex-start", marginTop: 3 }}>{t}</Badge>
                </div>
              ))}
            </div>
          </Card>
        </aside>
      </div>
    </div>
  );
}

window.DocumentView = DocumentView;
