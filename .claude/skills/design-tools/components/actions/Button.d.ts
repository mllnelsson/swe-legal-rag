import * as React from "react";

/**
 * Primary action control for Svk Beslutsök.
 * @startingPoint section="Core" subtitle="Buttons in all five variants and three sizes" viewport="700x220"
 */
export interface ButtonProps extends React.ButtonHTMLAttributes<HTMLButtonElement> {
  /** primary = burgundy, the single main action per view. accent = apricot, for warm secondary CTAs. */
  variant?: "primary" | "secondary" | "accent" | "ghost" | "danger";
  size?: "sm" | "md" | "lg";
  disabled?: boolean;
  fullWidth?: boolean;
  iconLeft?: React.ReactNode;
  iconRight?: React.ReactNode;
  /** Render as another element, e.g. "a" for link buttons. */
  as?: "button" | "a";
  children?: React.ReactNode;
}
export declare function Button(props: ButtonProps): JSX.Element;
