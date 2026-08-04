import * as React from "react";
export interface DialogProps {
  open?: boolean;
  title: React.ReactNode;
  description?: React.ReactNode;
  children?: React.ReactNode;
  /** Right-aligned action row. */
  footer?: React.ReactNode;
  onClose?: () => void;
  /** Pixel width of the panel. Default 520. */
  width?: number;
}
export declare function Dialog(props: DialogProps): JSX.Element | null;
