import { Icon } from "../display/Icon";
import { formatCount } from "../../lib/format";
import type { SearchDiagnostics } from "../../api/types";

export type SearchSummaryProps = {
  effectiveQueries: string[];
  total: number;
  diagnostics: SearchDiagnostics;
  /** What the caller asked for, against which `diagnostics.expanded` says what
   *  happened. The two differ when the model call failed and search fell open.
   *  Omitted means not asked for, and then the summary says nothing about it. */
  expandRequested?: boolean;
};

/* Occupies the slot the skill gives AnswerPanel, and keeps its apricot wash — the
 * design system allows that wash in exactly three places and this is the app's one.
 *
 * What it is NOT is an answer. The skill's panel renders synthesised prose with
 * numbered source chips; this renders only facts about the query that was just
 * run. Nothing here is generated: the queries are what was sent, the count is what
 * came back, the diagnostics are the API's own. */

/** What to say about an expansion the caller asked for.
 *
 *  The phrasing line above this one is every query that was searched, and all but
 *  the first were written by a model rather than by the user. Saying so is the
 *  point: unattributed, the summary presents generated text as the question the
 *  user typed.
 *
 *  Three outcomes, not two. Expansion fails open — a model error costs recall, not
 *  the request — so a search asked to expand and unable to looks identical to one
 *  never asked; and a model that ran and proposed nothing leaves a single phrasing
 *  with no "omformuleringar ovan" to point at. */
function describeExpansion(expanded: boolean, queryCount: number): string {
  if (!expanded) {
    return "Omformuleringar kunde inte hämtas. Sökningen kördes på frågan som den skrevs.";
  }
  if (queryCount < 2) {
    return "Språkmodellen föreslog inga andra formuleringar av frågan.";
  }
  return "Frågan söktes också som omformuleringarna ovan, föreslagna av en språkmodell.";
}

export function SearchSummary({
  effectiveQueries,
  total,
  diagnostics,
  expandRequested = false,
}: SearchSummaryProps) {
  const wordMatches = Object.values(diagnostics.text_hit_counts).reduce(
    (sum, count) => sum + count,
    0,
  );

  return (
    <section
      style={{
        display: "flex",
        flexDirection: "column",
        gap: "var(--space-4)",
        padding: "var(--space-6) var(--space-7)",
        background: "var(--gradient-wash-soft)",
        border: "1px solid var(--apricot-200)",
        borderRadius: "var(--radius-lg)",
        fontFamily: "var(--font-sans)",
      }}
    >
      <span
        style={{
          fontSize: "var(--text-overline-size)",
          letterSpacing: "var(--text-overline-ls)",
          textTransform: "uppercase",
          fontWeight: "var(--text-overline-weight)",
          color: "var(--text-faint)",
        }}
      >
        Sökning
      </span>

      <p
        style={{
          margin: 0,
          fontFamily: "var(--font-display)",
          fontSize: "var(--text-h2-size)",
          lineHeight: "var(--text-h2-lh)",
          letterSpacing: "var(--text-h2-ls)",
          color: "var(--text-strong)",
          maxWidth: "var(--measure-prose)",
        }}
      >
        {effectiveQueries.join(" · ")}
      </p>

      {expandRequested && (
        <p style={{ margin: 0, fontSize: "var(--text-small-size)", color: "var(--text-muted)" }}>
          {describeExpansion(diagnostics.expanded, effectiveQueries.length)}
        </p>
      )}

      <p style={{ margin: 0, fontSize: "var(--text-body-size)", color: "var(--text-body)" }}>
        {/* `total` is the size of the fused candidate pool, not a corpus-wide count,
            so it is stated bare rather than as "1-10 av N". */}
        {total === 1 ? "1 träff" : `${formatCount(total)} träffar`}
      </p>

      {/* Not a warning that the hits are bad — the vector arm applies
          `diagnostics.vector_similarity_floor`, so anything that reached this list
          cleared it. It is a warning about what kind of hit these are: matched by
          meaning alone, with not one word of the query occurring in the text. The
          fused `score` cannot express that distinction (RRF derives it from rank,
          so rank 1 is ~0.0164 either way) — `text_hit_counts` is what does.

          Gated on having results: "träffarna nedan" is a claim about a list, and
          below an empty state there is no list to make it about. */}
      {wordMatches === 0 && total > 0 && (
        <p
          style={{
            display: "flex",
            gap: "var(--space-3)",
            margin: 0,
            fontSize: "var(--text-small-size)",
            color: "var(--text-muted)",
            maxWidth: "var(--measure-prose)",
          }}
        >
          <Icon name="info" size={15} color="var(--text-faint)" />
          <span>
            Inga ord ur frågan finns i besluten. Träffarna nedan är de som ligger
            närmast i betydelse — läs dem som förslag, inte som svar.
          </span>
        </p>
      )}

      {/* Same gate, same reason: since the similarity floor landed, a widened
          search can also come back with nothing, and this banner speaks about
          results that would not be there. */}
      {diagnostics.widened_to_appendices && total > 0 && (
        <p
          style={{
            display: "flex",
            gap: "var(--space-3)",
            margin: 0,
            padding: "var(--space-4) var(--space-5)",
            background: "var(--status-warn-bg)",
            color: "var(--status-warn-fg)",
            borderRadius: "var(--radius-sm)",
            fontSize: "var(--text-small-size)",
            maxWidth: "var(--measure-prose)",
          }}
        >
          <Icon name="triangle-alert" size={16} />
          <span>
            Inget matchade i besluten själva. Träffarna nedan kommer från bilagor — de
            överklagade besluten, som nämnden i flera fall har ändrat.
          </span>
        </p>
      )}
    </section>
  );
}
