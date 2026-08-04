import * as React from "react";
export interface CardProps extends React.HTMLAttributes<HTMLDivElement> {
  /** CSS length for the body padding. Default var(--space-7). */
  padding?: string;
  /** default = white; accent = apricot tint; wash = apricot gradient; inverse = burgundy gradient. */
  tone?: "default" | "accent" | "wash" | "inverse";
  /** Adds hover lift + pointer cursor. */
  interactive?: boolean;
  header?: React.ReactNode;
  footer?: React.ReactNode;
  children?: React.ReactNode;
}
export declare function Card(props: CardProps): JSX.Element;
