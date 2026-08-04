import * as React from "react";
export interface SelectOption { value: string; label: string }
export interface SelectProps {
  label?: string;
  hint?: string;
  options: Array<string | SelectOption>;
  value?: string;
  onChange?: (value: string) => void;
  size?: "sm" | "md";
  disabled?: boolean;
}
export declare function Select(props: SelectProps): JSX.Element;
