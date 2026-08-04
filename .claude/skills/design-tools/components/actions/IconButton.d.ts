import * as React from "react";
export interface IconButtonProps extends React.ButtonHTMLAttributes<HTMLButtonElement> {
  /** Lucide icon name, or a node. */
  icon: string | React.ReactNode;
  /** Required accessible label; also used as the tooltip title. */
  label: string;
  variant?: "secondary" | "ghost" | "primary";
  size?: "sm" | "md" | "lg";
  disabled?: boolean;
}
export declare function IconButton(props: IconButtonProps): JSX.Element;
