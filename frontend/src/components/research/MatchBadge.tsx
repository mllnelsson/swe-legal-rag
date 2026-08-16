import { Badge } from "../display/Badge";

export type MatchBadgeProps = {
  /** Rank in the vector arm, or null when that arm never returned this chunk. */
  vectorRank: number | null;
  /** Rank in the Swedish full-text arm, same null meaning. */
  textRank: number | null;
};

/** How the search found this decision, in words rather than in arm names.
 *
 *  Deliberately shown instead of the score. `score` is a raw reciprocal-rank-fusion
 *  value: it sits around 0.016–0.033, the differences between hits are tiny, and it
 *  carries no meaning on its own — rendering it as a percentage or a star rating
 *  would invent a precision the number does not have.
 *
 *  What the reader gets instead is the one distinction they can act on: whether the
 *  words they typed actually occur in this decision, or whether it came back on
 *  meaning alone and may use quite different language. The rank *numbers* behind
 *  that are not shown — the list is already in rank order, so a "#3" beside the
 *  third card restates the position and reads as a score to anyone who does not
 *  know what a retrieval arm is.
 *
 *  A hit with no arm at all cannot happen — fusion is built from the arms — so the
 *  null/null case renders nothing rather than a third, inventive label. */
export function MatchBadge({ vectorRank, textRank }: MatchBadgeProps) {
  if (textRank !== null) {
    return <Badge tone="neutral">Innehåller dina ord</Badge>;
  }
  if (vectorRank !== null) {
    return <Badge tone="neutral">Träff på betydelse</Badge>;
  }
  return null;
}
