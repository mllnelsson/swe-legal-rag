import { Icon } from "../../components/display/Icon";
import { Tag } from "../../components/display/Tag";
import { Combobox } from "../../components/forms/Combobox";
import { Input } from "../../components/forms/Input";
import { Select } from "../../components/forms/Select";
import { useFacets } from "../../api/queries";
import { formatCount } from "../../lib/format";
import type { FacetValue } from "../../api/types";
import { countActiveFilters, type SearchState } from "./search-params";

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

/* The one control here that does not narrow the corpus — it widens the query — so
 * it sits above the filters rather than among them. Rendered even while facets are
 * loading (or if that call fails): it needs no vocabulary, and hiding it would
 * make expansion unreachable for a reason that has nothing to do with it. */
function ExpandToggle({ state, onChange }: FacetRailProps) {
  return (
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
  );
}

/* A modest disclosure, closed by default: the filters are there to reach for once
   the reader has seen what came back, not a wall to read past first. */
const DETAILS_STYLE = {
  background: "var(--surface-card)",
  border: "1px solid var(--border-hairline)",
  borderRadius: "var(--radius-md)",
  padding: "var(--space-4) var(--space-5)",
  fontFamily: "var(--font-sans)",
} as const;

const SUMMARY_STYLE = {
  cursor: "pointer",
  display: "flex",
  alignItems: "center",
  gap: "var(--space-3)",
  fontSize: "var(--text-small-size)",
  fontWeight: "var(--weight-semibold)",
  color: "var(--text-strong)",
} as const;

const PANEL_STYLE = {
  display: "flex",
  flexDirection: "column",
  gap: "var(--space-6)",
  marginTop: "var(--space-5)",
} as const;

/* The narrowing controls flow into as many columns as the width allows, so the
   panel is a short band rather than a tall stack now that it spans the page. */
const GRID_STYLE = {
  display: "grid",
  gridTemplateColumns: "repeat(auto-fit, minmax(240px, 1fr))", // token-exempt: min filter-column width, no scale step
  gap: "var(--space-6)",
  alignItems: "start",
} as const;

/** A pill counting the active filters, so a collapsed rail still says how many are
 *  in force. Mirrors the AskBox scope pill. */
function CountBadge({ count }: { count: number }) {
  return (
    <span
      style={{
        display: "inline-flex",
        alignItems: "center",
        minWidth: "var(--space-6)",
        justifyContent: "center",
        padding: "0 var(--space-2)",
        borderRadius: "var(--radius-pill)",
        background: "var(--apricot-50)",
        border: "1px solid var(--apricot-200)",
        color: "var(--burgundy-600)",
        fontSize: "var(--text-caption-size)",
        fontWeight: "var(--weight-semibold)",
      }}
    >
      {count}
    </span>
  );
}

export function FacetRail({ state, onChange }: FacetRailProps) {
  const facets = useFacets();
  const activeCount = countActiveFilters(state);

  return (
    <details style={DETAILS_STYLE}>
      <summary style={SUMMARY_STYLE}>
        <Icon name="funnel" size={15} color="var(--text-muted)" />
        <span>Filter</span>
        {activeCount > 0 && <CountBadge count={activeCount} />}
      </summary>

      <div style={PANEL_STYLE}>
        {/* Above the filters and apart from them, because it widens the query
            rather than narrowing the corpus. */}
        <ExpandToggle state={state} onChange={onChange} />

        {facets.data !== undefined && (
          <FilterControls state={state} onChange={onChange} facets={facets.data} />
        )}
      </div>
    </details>
  );
}

type FacetsData = NonNullable<ReturnType<typeof useFacets>["data"]>;

function FilterControls({
  state,
  onChange,
  facets,
}: FacetRailProps & { facets: FacetsData }) {
  const { categories, decision_outcomes, keywords, earliest_decision_date, latest_decision_date } =
    facets;

  function toggleKeyword(keyword: string) {
    const next = state.keywords.includes(keyword)
      ? state.keywords.filter((each) => each !== keyword)
      : [...state.keywords, keyword];
    onChange({ ...state, keywords: next, page: 1 });
  }

  return (
    <div style={GRID_STYLE}>
      {/* Categories are free text lifted by regex, not a vocabulary. The live corpus
          holds both "Utlämnande av handling" and "Utlämnande av handlingar", and both
          "Avvisning" and "Avvisning m.m." — they are rendered exactly as returned and
          never merged, because we cannot know they mean the same thing. The combobox
          filters what it shows, never the value it sends. */}
      <Combobox
        label="Kategori"
        size="sm"
        placeholder="Alla kategorier"
        value={state.category ?? ANY}
        options={toOptions(categories)}
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
          and the only filter here matched exactly rather than by substring. Spans the
          whole panel so the chips wrap on one shelf rather than in a narrow column. */}
      <div
        style={{
          gridColumn: "1 / -1",
          display: "flex",
          flexDirection: "column",
          gap: "var(--space-3)",
        }}
      >
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
    </div>
  );
}
