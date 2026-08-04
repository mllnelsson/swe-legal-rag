import * as React from "react";
export interface SidebarNavItem { value: string; label: string; icon?: string; count?: number }
export interface SidebarNavProps {
  items: SidebarNavItem[];
  value?: string;
  onChange?: (value: string) => void;
  /** Small uppercase label above the list. */
  title?: string;
  footer?: React.ReactNode;
}
export declare function SidebarNav(props: SidebarNavProps): JSX.Element;
