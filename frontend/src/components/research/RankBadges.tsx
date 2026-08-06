import { Badge } from "../display/Badge";

export type RankBadgesProps = {
  /** Rank in the vector arm, or null when that arm never returned this chunk. */
  vectorRank: number | null;
  /** Rank in the Swedish full-text arm, same null meaning. */
  textRank: number | null;
};

/** Why a result placed where it did.
 *
 *  Deliberately shown instead of the score. `score` is a raw reciprocal-rank-fusion
 *  value: it sits around 0.016–0.033, the differences between hits are tiny, and it
 *  carries no meaning on its own — rendering it as a percentage or a star rating
 *  would invent a precision the number does not have.
 *
 *  A null arm is ordinary rather than exceptional. Multi-word Swedish queries often
 *  return nothing from the tsvector arm while the vector arm answers well, so most
 *  hits legitimately carry one badge. */
export function RankBadges({ vectorRank, textRank }: RankBadgesProps) {
  if (vectorRank === null && textRank === null) return null;

  return (
    <span style={{ display: "inline-flex", gap: "var(--space-2)" }}>
      {vectorRank !== null && <Badge tone="neutral">{`Vektor #${vectorRank}`}</Badge>}
      {textRank !== null && <Badge tone="neutral">{`Text #${textRank}`}</Badge>}
    </span>
  );
}
