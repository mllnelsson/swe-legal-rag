import * as React from "react";
export interface TabItem { value: string; label: string; count?: number }
export interface TabsProps {
  tabs: Array<string | TabItem>;
  value?: string;
  onChange?: (value: string) => void;
  /** underline = page-level sections; pill = compact in-panel switch. */
  variant?: "underline" | "pill";
}
export declare function Tabs(props: TabsProps): JSX.Element;
