import { Badge } from "../display/Badge";
import { Icon } from "../display/Icon";
import type { ChunkSection } from "../../api/types";

export type SectionBadgeProps = {
  section: ChunkSection;
  appendixLabel?: string | null;
};

/** Marks whose words an excerpt is.
 *
 *  This is the most important marker in the app. A decision PDF contains both the
 *  nämnd's decision and, as an appendix, the lower-instance decision that was
 *  appealed — frequently the one the nämnd went on to overturn. In the live corpus
 *  that appendix text is 99 of 206 chunks, so nearly half of what retrieval can
 *  return is somebody else's reasoning.
 *
 *  The API contract states the obligation directly: a client must not present such
 *  an excerpt as the nämnd's own reasoning. Nothing renders appendix text without
 *  this badge beside it. */
export function SectionBadge({ section, appendixLabel }: SectionBadgeProps) {
  if (section === "body") {
    return <Badge tone="declared">Nämndens beslut</Badge>;
  }

  return (
    <Badge tone="warn" icon={<Icon name="triangle-alert" size={13} />}>
      {appendixLabel ?? "Bilaga"} · överklagat beslut
    </Badge>
  );
}
