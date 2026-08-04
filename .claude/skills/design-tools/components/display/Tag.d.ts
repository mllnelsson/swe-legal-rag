import * as React from "react";
export interface TagProps {
  children?: React.ReactNode;
  /** Renders a trailing ✕; omit for non-removable tags. */
  onRemove?: () => void;
  /** Apricot-filled state, for active filters. */
  selected?: boolean;
  onClick?: () => void;
}
export declare function Tag(props: TagProps): JSX.Element;
