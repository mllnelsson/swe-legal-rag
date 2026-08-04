import * as React from "react";

/**
 * The assistant's synthesized answer above a result list.
 * @startingPoint section="Research" subtitle="Answer summary on apricot wash with source chips" viewport="700x300"
 */
export interface AnswerPanelProps {
  /** Restated research question, set in the display serif. */
  question?: React.ReactNode;
  answer: React.ReactNode;
  /** Short citation labels rendered as numbered chips. */
  sources?: string[];
  onSourceClick?: (index: number) => void;
  /** Overline text; defaults to "Research summary". Use "Searching…" while streaming. */
  status?: string;
}
export declare function AnswerPanel(props: AnswerPanelProps): JSX.Element;
