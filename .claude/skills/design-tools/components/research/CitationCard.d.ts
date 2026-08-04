import * as React from "react";

/**
 * One authority in a result list.
 * @startingPoint section="Research" subtitle="Case result with authority signal and excerpt" viewport="700x230"
 */
export interface CitationCardProps {
  /** Case or statute name, e.g. "Novak v. Harrow Logistics, Inc." */
  title: string;
  /** Reporter citation, set in mono, e.g. "812 F.3d 1044". */
  citation: string;
  court?: string;
  year?: string | number;
  /** Drives the authority badge color. */
  authority?: "binding" | "persuasive" | "secondary";
  /** Subsequent-history signal, e.g. "Followed", "Criticized". */
  treatment?: string;
  /** The held passage, shown with an apricot rule on the left. */
  excerpt?: string;
  /** Matched query terms, shown as small apricot chips. */
  matchTerms?: string[];
  onOpen?: () => void;
  onSave?: () => void;
  saved?: boolean;
}
export declare function CitationCard(props: CitationCardProps): JSX.Element;
