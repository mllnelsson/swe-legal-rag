/* Presentation helpers. Pure: they take API values and return strings.
 *
 * The corpus carries two identifier spaces that look alike and are not:
 *
 *   case_number     "2025-0035"  ärendenummer — identifies the *case*
 *   decision_number "14/2026"    beslutsnummer — identifies the *decision*
 *
 * They genuinely disagree: a case opened in 2025 can be decided in 2026, and the
 * live corpus contains exactly that. Neither is a formatting of the other, so
 * every rendering labels which one it is showing.
 */

const SWEDISH_DATE = new Intl.DateTimeFormat("sv-SE", {
  year: "numeric",
  month: "long",
  day: "numeric",
});

const SWEDISH_NUMBER = new Intl.NumberFormat("sv-SE");

/** ISO date from the API to a readable Swedish one. */
export function formatDecisionDate(isoDate: string | null): string | null {
  if (isoDate === null) return null;
  const parsed = new Date(isoDate);
  if (Number.isNaN(parsed.getTime())) return null;
  return SWEDISH_DATE.format(parsed);
}

/** Digits with Swedish grouping, per the design system's "counts are digits". */
export function formatCount(value: number): string {
  return SWEDISH_NUMBER.format(value);
}

export type DecisionIdentity = {
  caseNumber: string | null;
  decisionNumber: string | null;
  decisionDate: string | null;
};

export type IdentityPart = { label: string; value: string };

/** The labelled parts of a decision's identity line, in reading order.
 *
 * Returns parts rather than a joined string so the caller can set the two
 * identifiers in the mono citation face and keep the labels in the UI face. */
export function decisionIdentityParts(identity: DecisionIdentity): IdentityPart[] {
  const parts: IdentityPart[] = [];
  if (identity.caseNumber !== null) {
    parts.push({ label: "Ärendenummer", value: identity.caseNumber });
  }
  if (identity.decisionNumber !== null) {
    parts.push({ label: "Beslut", value: identity.decisionNumber });
  }
  const date = formatDecisionDate(identity.decisionDate);
  if (date !== null) {
    parts.push({ label: "Meddelat", value: date });
  }
  return parts;
}

/** A decision with no case number and no decision number still needs a name. */
export function decisionTitle(headline: string | null, category: string | null): string {
  return headline ?? category ?? "Beslut utan rubrik";
}
