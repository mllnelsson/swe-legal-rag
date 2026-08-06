/* Swedish display formatting, shared by every surface that names a decision.
 *
 * Lives here rather than in a component because the same decision appears as a
 * search hit, a citation edge and a page heading, and the three must not drift
 * into naming it three different ways.
 *
 * Nothing here invents text. Each function picks between values the API already
 * returned, or formats a number for a Swedish reader; where the API returned
 * nothing, these produce nothing rather than a placeholder.
 */

/** Grouped with the Swedish thousands separator (a non-breaking space). */
export function formatCount(count: number): string {
  return new Intl.NumberFormat("sv-SE").format(count);
}

/** What to call a decision in a heading.
 *
 *  `headline` is the nämnd's own published title and is preferred whenever it
 *  exists. `category` is a regex-lifted field — opaque free text, per honesty
 *  rule 10 — so it is a fallback, not an equal. When neither exists the caller
 *  still needs something clickable, and "Beslut" is the one word that is true of
 *  every document in the corpus.
 */
export function decisionTitle(
  headline: string | null,
  category: string | null,
): string {
  return headline ?? category ?? "Beslut";
}

export type DecisionIdentityInput = {
  caseNumber: string | null;
  decisionNumber: string | null;
  decisionDate: string | null;
};

export type DecisionIdentityPart = {
  label: string;
  value: string;
};

/** The labelled identifiers of a decision, in reading order.
 *
 *  Always labelled and never concatenated: `case_number` and `decision_number`
 *  are two different identifier spaces, and the corpus contains cases opened in
 *  one year and decided in another (2025-0035 decided as 14/2026), so an
 *  unlabelled "2025-0035 · 14/2026" would read as one number twice. See honesty
 *  rule 8.
 *
 *  A missing identifier is dropped rather than rendered as a dash — the parts
 *  are keyed by `label` at every call site, so each label appears at most once.
 */
export function decisionIdentityParts(
  input: DecisionIdentityInput,
): DecisionIdentityPart[] {
  const parts: DecisionIdentityPart[] = [];

  if (input.caseNumber !== null) {
    parts.push({ label: "Ärendenummer", value: input.caseNumber });
  }
  if (input.decisionNumber !== null) {
    parts.push({ label: "Beslut", value: input.decisionNumber });
  }
  if (input.decisionDate !== null) {
    // Already ISO from the API, which is also how Swedish writes a date, so
    // there is nothing to convert — only to label.
    parts.push({ label: "Beslutsdatum", value: input.decisionDate });
  }

  return parts;
}
