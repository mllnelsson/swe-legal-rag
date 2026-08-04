import * as React from "react";
export interface ToastProps {
  tone?: "info" | "ok" | "warn" | "error";
  title: React.ReactNode;
  message?: React.ReactNode;
  /** Optional inline action, usually a ghost Button. */
  action?: React.ReactNode;
  onDismiss?: () => void;
}
export declare function Toast(props: ToastProps): JSX.Element;
