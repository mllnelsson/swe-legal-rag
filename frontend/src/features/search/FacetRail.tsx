import { Icon } from "../../components/display/Icon";
import type { IconName } from "../../components/display/icon-paths";
import { Tag } from "../../components/display/Tag";
import { Input } from "../../components/forms/Input";
import { Select } from "../../components/forms/Select";
import { useFacets } from "../../api/queries";
import { formatCount } from "../../lib/format";
import type { FacetValue } from "../../api/types";
import type { SearchState } from "./search-params";

export type FacetRailProps = {
  state: SearchState;
  onChange: (next: SearchState) => void;
};

/** How many Sökord to show before the rail becomes a wall of chips. */
const VISIBLE_KEYWORDS = 12;

/* `decision_outcome` values are the holding itself, verbatim — in the live corpus
 * they run from 41 to 378 characters. A 378-character option is not a control, so
 * the *label* is shortened for display while the value sent to the API stays
 * byte-identical and the full text is available on hover. That is display
 * truncation, not normalisation: nothing is merged, rewritten or guessed. */
const OUTCOME_LABEL_MAX = 60;

function shortenOutcome(value: string): string {
  return value.length <= OUTCOME_LABEL_MAX ? value : `${value.slice(0, OUTCOME_LABEL_MAX)}…`;
}

function toOptions(values: FacetValue[], shorten?: (value: string) => string) {
  return values.map((facet) => ({
    value: facet.value,
    label: `${shorten === undefined ? facet.value : shorten(facet.value)} (${facet.count})`,
  }));
}

const ANY = "";

function RailHeading({ icon, children }: { icon: IconName; children: string }) {
  return (
    <div style={{ display: "flex", alignItems: "center", gap: "var(--space-3)" }}>
      <Icon name={icon} size={15} color="var(--text-muted)" />
      <span
        style={{
          fontSize: "var(--text-overline-size)",
          letterSpacing: "var(--text-overline-ls)",
          textTransform: "uppercase",
          fontWeight: "var(--text-overline-weight)",
          color: "var(--text-faint)",
        }}
      >
        {children}
      </span>
    </div>
  );
}

/* The one control here that does not come from `/facets`. Rendered outside the
 * `facets.data` gate on purpose: it needs no vocabulary, and hiding it while the
 * facets load — or for good, if that call fails — would make expansion
 * unreachable for a reason that has nothing to do with it. */
function ExpandToggle({ state, onChange }: FacetRailProps) {
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: "var(--space-3)" }}>
      <RailHeading icon="search">Sökning</RailHeading>
      <label
        style={{
          display: "flex",
          gap: "var(--space-3)",
          fontSize: "var(--text-small-size)",
          color: "var(--text-body)",
          cursor: "pointer",
        }}
      >
        <input
          type="checkbox"
          checked={state.expand}
          onChange={(event) => onChange({ ...state, expand: event.target.checked, page: 1 })}
        />
        Sök även på omformuleringar av frågan
      </label>
    </div>
  );
}

/* Width and flex come from the `layout-rail` class, which is what lets the rail
   go full width when the columns stack. */
const RAIL_STYLE = {
  display: "flex",
  flexDirection: "column",
  gap: "var(--space-7)",
  fontFamily: "var(--font-sans)",
} as const;

export function FacetRail({ state, onChange }: FacetRailProps) {
  const facets = useFacets();

  if (facets.data === undefined) {
    return (
      <aside className="layout-rail" style={RAIL_STYLE}>
        <ExpandToggle state={state} onChange={onChange} />
      </aside>
    );
  }

  const { categories, decision_outcomes, keywords, earliest_decision_date, latest_decision_date } =
    facets.data;

  function toggleKeyword(keyword: string) {
    const next = state.keywords.includes(keyword)
      ? state.keywords.filter((each) => each !== keyword)
      : [...state.keywords, keyword];
    onChange({ ...state, keywords: next, page: 1 });
  }

  return (
    <aside className="layout-rail" style={RAIL_STYLE}>
      {/* Above "Avgränsa" and outside it, because it is not a filter: everything
          below narrows the corpus, this widens the query. */}
      <ExpandToggle state={state} onChange={onChange} />

      <RailHeading icon="funnel">Avgränsa</RailHeading>

      {/* Categories are free text lifted by regex, not a vocabulary. The live corpus
          holds both "Utlämnande av handling" and "Utlämnande av handlingar", and both
          "Avvisning" and "Avvisning m.m." — they are rendered exactly as returned and
          never merged, because we cannot know they mean the same thing. */}
      <Select
        label="Kategori"
        size="sm"
        value={state.category ?? ANY}
        options={[{ value: ANY, label: "Alla kategorier" }, ...toOptions(categories)]}
        onChange={(value) =>
          onChange({ ...state, category: value === ANY ? null : value, page: 1 })
        }
      />

      <Select
        label="Utfall"
        size="sm"
        value={state.outcome ?? ANY}
        options={[{ value: ANY, label: "Alla utfall" }, ...toOptions(decision_outcomes, shortenOutcome)]}
        onChange={(value) => onChange({ ...state, outcome: value === ANY ? null : value, page: 1 })}
      />

      <div style={{ display: "flex", flexDirection: "column", gap: "var(--space-4)" }}>
        <Input
          label="Från"
          type="date"
          size="sm"
          value={state.dateFrom ?? ""}
          min={earliest_decision_date ?? undefined}
          max={latest_decision_date ?? undefined}
          onChange={(event) =>
            onChange({ ...state, dateFrom: event.target.value || null, page: 1 })
          }
        />
        <Input
          label="Till"
          type="date"
          size="sm"
          value={state.dateTo ?? ""}
          min={earliest_decision_date ?? undefined}
          max={latest_decision_date ?? undefined}
          onChange={(event) => onChange({ ...state, dateTo: event.target.value || null, page: 1 })}
        />
      </div>

      {/* The nämnd's own Sökord line — the one classification the corpus vouches for,
          and the only filter here matched exactly rather than by substring. */}
      <div style={{ display: "flex", flexDirection: "column", gap: "var(--space-3)" }}>
        <span
          style={{
            fontSize: "var(--text-small-size)",
            fontWeight: "var(--weight-semibold)",
            color: "var(--text-strong)",
          }}
        >
          Sökord
        </span>
        <div style={{ display: "flex", flexWrap: "wrap", gap: "var(--space-3)" }}>
          {keywords.slice(0, VISIBLE_KEYWORDS).map((keyword) => (
            <Tag
              key={keyword.value}
              selected={state.keywords.includes(keyword.value)}
              onClick={() => toggleKeyword(keyword.value)}
            >
              {`${keyword.value} ${formatCount(keyword.count)}`}
            </Tag>
          ))}
        </div>
      </div>
    </aside>
  );
}
