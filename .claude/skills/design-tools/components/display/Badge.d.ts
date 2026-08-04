import * as React from "react";
export interface BadgeProps {
  /** binding / persuasive mirror the citation-authority colors. */
  tone?: "neutral" | "binding" | "persuasive" | "ok" | "warn" | "error" | "info";
  icon?: React.ReactNode;
  children?: React.ReactNode;
}
export declare function Badge(props: BadgeProps): JSX.Element;
