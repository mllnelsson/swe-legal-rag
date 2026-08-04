import * as React from "react";
export interface TooltipProps {
  label: React.ReactNode;
  placement?: "top" | "bottom" | "left" | "right";
  children?: React.ReactNode;
}
export declare function Tooltip(props: TooltipProps): JSX.Element;
