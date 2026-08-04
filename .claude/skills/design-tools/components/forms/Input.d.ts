import * as React from "react";
export interface InputProps extends React.InputHTMLAttributes<HTMLInputElement> {
  label?: string;
  /** Helper text below the field. */
  hint?: string;
  /** Error message; replaces the hint and turns the field red. */
  error?: string;
  /** Lucide icon name or node rendered inside the field, left of the text. */
  iconLeft?: string | React.ReactNode;
  size?: "sm" | "md" | "lg";
}
export declare function Input(props: InputProps): JSX.Element;
