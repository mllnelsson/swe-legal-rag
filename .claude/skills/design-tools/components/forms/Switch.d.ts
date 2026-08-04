import * as React from "react";
export interface SwitchProps {
  checked?: boolean;
  onChange?: (checked: boolean) => void;
  label?: React.ReactNode;
  disabled?: boolean;
}
export declare function Switch(props: SwitchProps): JSX.Element;
