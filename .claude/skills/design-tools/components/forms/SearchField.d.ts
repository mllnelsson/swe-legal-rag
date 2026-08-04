import * as React from "react";

/**
 * The product's signature search control.
 * @startingPoint section="Research" subtitle="Signature question box with jurisdiction scope" viewport="700x160"
 */
export interface SearchFieldProps {
  value?: string;
  onChange?: (value: string) => void;
  onSubmit?: (value: string) => void;
  placeholder?: string;
  /** Jurisdiction / corpus pill shown at the right, e.g. "9th Cir." */
  scope?: string;
  submitLabel?: string;
  disabled?: boolean;
}
export declare function SearchField(props: SearchFieldProps): JSX.Element;
