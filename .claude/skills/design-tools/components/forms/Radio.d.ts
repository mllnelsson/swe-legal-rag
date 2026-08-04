import * as React from "react";
export interface RadioProps {
  label: React.ReactNode;
  description?: string;
  checked?: boolean;
  onChange?: (checked: boolean) => void;
  /** Group name shared by all radios in the set. */
  name?: string;
  disabled?: boolean;
}
export declare function Radio(props: RadioProps): JSX.Element;
