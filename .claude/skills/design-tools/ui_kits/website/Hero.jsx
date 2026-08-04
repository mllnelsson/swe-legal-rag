const { Button, Icon, AnswerPanel, Badge } = window.SvkBeslutsokDesignSystem_46c55d;

function Hero() {
  return (
    <section style={{ background: "var(--gradient-wash)", borderBottom: "1px solid var(--apricot-200)" }}>
      <div style={{ maxWidth: "var(--content-max)", margin: "0 auto", padding: "var(--space-13) var(--space-8) var(--space-12)", display: "grid", gridTemplateColumns: "1.05fr 1fr", gap: "var(--space-11)", alignItems: "center" }}>
        <div style={{ display: "flex", flexDirection: "column", gap: "var(--space-6)" }}>
          <span style={{ fontSize: "var(--text-overline-size)", letterSpacing: "var(--text-overline-ls)", textTransform: "uppercase", fontWeight: 600, color: "var(--burgundy-600)" }}>For litigation teams</span>
          <h1 style={{ fontFamily: "var(--font-display)", fontSize: 56, lineHeight: 1.04, letterSpacing: "-0.022em", color: "var(--text-strong)", margin: 0, maxWidth: "14ch" }}>Legal research that cites itself</h1>
          <p style={{ fontSize: "var(--text-body-lg-size)", lineHeight: 1.62, color: "var(--text-body)", maxWidth: "48ch", margin: 0 }}>Ask a question the way you would ask a colleague. Svk Beslutsök answers with the cases, statutes and passages behind every sentence, so the check takes minutes instead of an afternoon.</p>
          <div style={{ display: "flex", gap: "var(--space-4)", marginTop: "var(--space-2)" }}>
            <Button size="lg">Book a demo</Button>
            <Button size="lg" variant="secondary" iconLeft={<Icon name="play" size={16} />}>Watch the 3-minute tour</Button>
          </div>
          <div style={{ display: "flex", alignItems: "center", gap: "var(--space-5)", marginTop: "var(--space-4)", fontSize: "var(--text-small-size)", color: "var(--text-muted)" }}>
            <span>Federal and all 50 states</span><span style={{ color: "var(--apricot-300)" }}>·</span><span>SOC 2 Type II</span><span style={{ color: "var(--apricot-300)" }}>·</span><span>No client data used for training</span>
          </div>
        </div>
        <div style={{ background: "var(--surface-card)", border: "1px solid var(--apricot-200)", borderRadius: "var(--radius-xl)", boxShadow: "var(--shadow-lg)", padding: "var(--space-6)", display: "flex", flexDirection: "column", gap: "var(--space-5)" }}>
          <div style={{ display: "flex", alignItems: "center", gap: "var(--space-4)", padding: "var(--space-4) var(--space-5)", border: "1px solid var(--border-hairline)", borderRadius: "var(--radius-pill)", color: "var(--text-muted)", fontSize: "var(--text-body-size)" }}>
            <Icon name="search" size={17} color="var(--burgundy-600)" />Does a carrier owe a duty to a downstream consignee?
          </div>
          <AnswerPanel status="Research summary" answer={<p style={{ margin: 0, fontSize: "var(--text-body-size)" }}>In the Ninth Circuit the duty runs past the named consignee where the delivery chain was foreseeable. The Sixth Circuit disagrees where a tariff fixes the risk.</p>} sources={["812 F.3d 1044", "49 U.S.C. § 14706"]} style={{ padding: "var(--space-6)" }} />
          <div style={{ display: "flex", gap: "var(--space-3)" }}>
            <Badge tone="binding">2 binding</Badge><Badge tone="persuasive">2 persuasive</Badge><Badge tone="warn">1 criticized</Badge>
          </div>
        </div>
      </div>
    </section>
  );
}

window.Hero = Hero;
