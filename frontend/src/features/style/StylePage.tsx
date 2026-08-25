/* The porting checklist, made visible.
 *
 * Every design-system component this app has ported, in every state it supports,
 * on one page. It exists so a visual regression is something you can see rather
 * than something you discover on a product screen, and so the next person to port
 * a component from the skill can tell at a glance what already exists.
 *
 * Dev-facing, deliberately in Swedish only where it quotes real UI copy.
 */

import { useState } from "react";

import { Button, type ButtonVariant } from "../../components/actions/Button";
import { IconButton } from "../../components/actions/IconButton";
import { Badge, type BadgeTone } from "../../components/display/Badge";
import { Card, type CardTone } from "../../components/display/Card";
import { Icon } from "../../components/display/Icon";
import { ICON_PATHS, type IconName } from "../../components/display/icon-paths";
import { Tag } from "../../components/display/Tag";
import { Input } from "../../components/forms/Input";
import { Select } from "../../components/forms/Select";
import { Switch } from "../../components/forms/Switch";
import { Tabs } from "../../components/navigation/Tabs";
import { AskBox } from "../../components/research/AskBox";
import { MatchBadge } from "../../components/research/MatchBadge";
import { SectionBadge } from "../../components/research/SectionBadge";

const COLOR_RAMPS: { name: string; steps: string[] }[] = [
  {
    name: "apricot",
    steps: ["50", "100", "200", "300", "400", "500", "600", "700"],
  },
  {
    name: "burgundy",
    steps: ["50", "100", "200", "300", "400", "500", "600", "700", "800"],
  },
  {
    name: "warm",
    steps: ["25", "50", "100", "200", "300", "400", "500", "600", "700", "800", "900"],
  },
];

const TYPE_SCALE = [
  { token: "display", sample: "Vad vill du veta?", display: true },
  { token: "h1", sample: "Obehörighet att utöva vigningstjänst", display: true },
  { token: "h2", sample: "Utlämnande av handling", display: true },
  { token: "h3", sample: "Nämndens beslut", display: true },
  { token: "body-lg", sample: "Överklagandenämnden avslår överklagandet.", display: false },
  { token: "body", sample: "Överklagandenämnden avslår överklagandet.", display: false },
  { token: "small", sample: "7 matchande stycken", display: false },
  { token: "caption", sample: "Ärendenummer 2025-0035", display: false },
];

const BUTTON_VARIANTS: ButtonVariant[] = ["primary", "secondary", "accent", "ghost"];
const BADGE_TONES: BadgeTone[] = ["neutral", "declared", "inferred", "ok", "warn", "error", "info"];
const CARD_TONES: CardTone[] = ["default", "accent", "wash", "inverse"];

export function StylePage() {
  const [tab, setTab] = useState("underline");
  const [select, setSelect] = useState("a");
  const [ask, setAsk] = useState("jäv i kyrkoråd");
  const [agentMode, setAgentMode] = useState(false);

  return (
    <main
      style={{
        maxWidth: "var(--content-max)",
        margin: "0 auto",
        padding: "var(--space-8) var(--gutter-page) var(--space-12)",
        display: "flex",
        flexDirection: "column",
        gap: "var(--section-gap)",
        fontFamily: "var(--font-sans)",
      }}
    >
      <header style={{ display: "flex", flexDirection: "column", gap: "var(--space-3)" }}>
        <h1
          style={{
            margin: 0,
            fontFamily: "var(--font-display)",
            fontSize: "var(--text-h1-size)",
            color: "var(--text-strong)",
          }}
        >
          Stil
        </h1>
        <p style={{ margin: 0, color: "var(--text-muted)", fontSize: "var(--text-body-size)" }}>
          Alla porterade komponenter och tokens. Inte en produktsida.
        </p>
      </header>

      <Section title="Typografi">
        {TYPE_SCALE.map((entry) => (
          <div
            key={entry.token}
            style={{ display: "flex", alignItems: "baseline", gap: "var(--space-6)" }}
          >
            <code
              style={{
                fontFamily: "var(--font-mono)",
                fontSize: "var(--text-caption-size)",
                color: "var(--text-faint)",
                width: "10ch",
                flex: "none",
              }}
            >
              {entry.token}
            </code>
            <span
              style={{
                fontFamily: entry.display ? "var(--font-display)" : "var(--font-sans)",
                fontSize: `var(--text-${entry.token}-size)`,
                lineHeight: `var(--text-${entry.token}-lh)`,
                color: "var(--text-strong)",
              }}
            >
              {entry.sample}
            </span>
          </div>
        ))}
        <div style={{ display: "flex", alignItems: "baseline", gap: "var(--space-6)" }}>
          <code
            style={{
              fontFamily: "var(--font-mono)",
              fontSize: "var(--text-caption-size)",
              color: "var(--text-faint)",
              width: "10ch",
              flex: "none",
            }}
          >
            mono
          </code>
          <span style={{ fontFamily: "var(--font-mono)", fontSize: "var(--text-cite-size)" }}>
            2025-0035 · 14/2026 · 57 kap. 10 § kyrkoordningen
          </span>
        </div>
      </Section>

      <Section title="Färg">
        {COLOR_RAMPS.map((ramp) => (
          <div key={ramp.name} style={{ display: "flex", flexDirection: "column", gap: "var(--space-2)" }}>
            <span style={{ fontSize: "var(--text-small-size)", color: "var(--text-muted)" }}>
              {ramp.name}
            </span>
            <div style={{ display: "flex", gap: "var(--space-2)", flexWrap: "wrap" }}>
              {ramp.steps.map((step) => (
                <div
                  key={step}
                  title={`--${ramp.name}-${step}`}
                  style={{
                    width: "var(--space-10)",
                    height: "var(--space-9)",
                    borderRadius: "var(--radius-sm)",
                    border: "1px solid var(--border-hairline)",
                    background: `var(--${ramp.name}-${step})`,
                    display: "flex",
                    alignItems: "flex-end",
                    justifyContent: "center",
                    fontSize: "var(--text-caption-size)",
                    color: "var(--text-muted)",
                  }}
                >
                  {step}
                </div>
              ))}
            </div>
          </div>
        ))}
      </Section>

      <Section title="Knappar">
        {(["md", "sm", "lg"] as const).map((size) => (
          <Row key={size}>
            {BUTTON_VARIANTS.map((variant) => (
              <Button key={variant} variant={variant} size={size}>
                {variant}
              </Button>
            ))}
            <Button disabled>disabled</Button>
          </Row>
        ))}
        <Row>
          <IconButton icon="search" label="Sök" />
          <IconButton icon="funnel" label="Filtrera" variant="ghost" />
          <IconButton icon="download" label="Ladda ner" variant="primary" />
          <IconButton icon="x" label="Stäng" disabled />
        </Row>
      </Section>

      <Section title="Märken och etiketter">
        <Row>
          {BADGE_TONES.map((tone) => (
            <Badge key={tone} tone={tone}>
              {tone}
            </Badge>
          ))}
        </Row>
        <Row>
          <Tag>oklickbar</Tag>
          <Tag onClick={() => undefined}>klickbar</Tag>
          <Tag selected onClick={() => undefined}>
            vald
          </Tag>
          <Tag selected onRemove={() => undefined}>
            borttagbar
          </Tag>
        </Row>
        <Row>
          <SectionBadge section="body" />
          <SectionBadge section="appendix" appendixLabel="Bilaga A" />
          <MatchBadge vectorRank={3} textRank={1} />
          <MatchBadge vectorRank={1} textRank={null} />
        </Row>
      </Section>

      <Section title="Kort">
        <div style={{ display: "grid", gridTemplateColumns: "repeat(2, 1fr)", gap: "var(--space-5)" }}>
          {CARD_TONES.map((tone) => (
            <Card key={tone} tone={tone} interactive={tone === "default"}>
              <strong>{tone}</strong>
            </Card>
          ))}
        </div>
      </Section>

      <Section title="Formulär">
        <div style={{ display: "grid", gridTemplateColumns: "repeat(3, 1fr)", gap: "var(--space-5)" }}>
          <Input label="Vanlig" placeholder="skriv här" />
          <Input label="Med ledtext" hint="Format ÅÅÅÅ-MM-DD" placeholder="2026-01-07" />
          <Input label="Fel" error="Ogiltigt datum" defaultValue="i går" />
          <Input label="Med ikon" iconLeft="search" placeholder="sök" />
          <Input label="Avstängd" disabled placeholder="låst" />
          <Select
            label="Val"
            value={select}
            onChange={setSelect}
            options={[
              { value: "a", label: "Alternativ a" },
              { value: "b", label: "Alternativ b" },
            ]}
          />
        </div>
        <Row>
          <Switch checked={agentMode} onChange={setAgentMode} label="Agentläge" />
          <Switch checked onChange={() => {}} label="På" />
          <Switch checked={false} onChange={() => {}} label="Avstängd" disabled />
        </Row>
      </Section>

      <Section title="Navigering">
        <Tabs
          label="Varianter"
          value={tab}
          onChange={setTab}
          tabs={[
            { value: "underline", label: "Understruken", count: 12 },
            { value: "second", label: "Andra" },
          ]}
        />
        <Tabs
          label="Piller"
          variant="pill"
          value={tab}
          onChange={setTab}
          tabs={[
            { value: "underline", label: "Ett" },
            { value: "second", label: "Två" },
          ]}
        />
      </Section>

      <Section title="Sökrutan">
        <AskBox value={ask} onChange={setAsk} onSubmit={() => undefined} />
        <AskBox value={ask} onChange={setAsk} onSubmit={() => undefined} scope="3 filter" size="lg" />
      </Section>

      <Section title={`Ikoner (${Object.keys(ICON_PATHS).length})`}>
        <div style={{ display: "flex", flexWrap: "wrap", gap: "var(--space-5)" }}>
          {(Object.keys(ICON_PATHS) as IconName[]).map((name) => (
            <div
              key={name}
              style={{
                display: "flex",
                flexDirection: "column",
                alignItems: "center",
                gap: "var(--space-2)",
                width: "12ch",
              }}
            >
              <Icon name={name} size={19} color="var(--text-body)" />
              <code
                style={{
                  fontFamily: "var(--font-mono)",
                  fontSize: "var(--text-caption-size)",
                  color: "var(--text-faint)",
                }}
              >
                {name}
              </code>
            </div>
          ))}
        </div>
      </Section>
    </main>
  );
}

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <section style={{ display: "flex", flexDirection: "column", gap: "var(--space-6)" }}>
      <h2
        style={{
          margin: 0,
          fontFamily: "var(--font-display)",
          fontSize: "var(--text-h2-size)",
          color: "var(--text-strong)",
          borderBottom: "1px solid var(--border-hairline)",
          paddingBottom: "var(--space-3)",
        }}
      >
        {title}
      </h2>
      {children}
    </section>
  );
}

function Row({ children }: { children: React.ReactNode }) {
  return (
    <div style={{ display: "flex", flexWrap: "wrap", gap: "var(--space-4)", alignItems: "center" }}>
      {children}
    </div>
  );
}
