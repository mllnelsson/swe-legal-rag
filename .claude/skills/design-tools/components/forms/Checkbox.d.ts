import * as React from "react";
export interface CheckboxProps {
  label: React.ReactNode;
  /** Optional second line of explanatory text. */
  description?: string;
  checked?: boolean;
  onChange?: (checked: boolean) => void;
  disabled?: boolean;
}
export declare function Checkbox(props: CheckboxProps): JSX.Element;
