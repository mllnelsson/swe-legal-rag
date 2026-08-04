import * as React from "react";
export interface IconProps extends React.HTMLAttributes<HTMLSpanElement> {
  /** Lucide icon name, kebab-case. e.g. "search", "book-open", "scale". */
  name: string;
  /** Pixel size of the square glyph. Default 18. */
  size?: number;
  /** Any CSS color. Defaults to currentColor. */
  color?: string;
  /** Accessible label; omit for decorative icons. */
  title?: string;
}
export declare function Icon(props: IconProps): JSX.Element;
