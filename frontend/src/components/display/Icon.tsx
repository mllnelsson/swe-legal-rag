import type { CSSProperties } from "react";

import { ICON_PATHS, type IconName } from "./icon-paths";

export type IconProps = {
  name: IconName;
  /** Design system caps icons at 20 in the app: 13 in chips, 15-16 in dense rows,
   *  17-19 in toolbars. */
  size?: number;
  color?: string;
  /** Give this only when the icon carries meaning on its own. Without it the icon
   *  is presentational and hidden from assistive tech, which is right whenever it
   *  sits beside a text label. */
  title?: string;
  style?: CSSProperties;
};

const DEFAULT_SIZE = 18;

/** Monochrome Lucide icon, rendered inline so it inherits `currentColor`.
 *
 *  The design skill masks these from a CDN at runtime; the geometry is vendored
 *  into `icon-paths.ts` instead so no third-party request happens on render. */
export function Icon({ name, size = DEFAULT_SIZE, color = "currentColor", title, style }: IconProps) {
  return (
    <svg
      xmlns="http://www.w3.org/2000/svg"
      width={size}
      height={size}
      viewBox="0 0 24 24"
      fill="none"
      stroke={color}
      strokeWidth={2}
      strokeLinecap="round"
      strokeLinejoin="round"
      role={title === undefined ? "presentation" : "img"}
      aria-hidden={title === undefined}
      aria-label={title}
      focusable="false"
      style={{ display: "inline-block", flex: "none", verticalAlign: "middle", ...style }}
      dangerouslySetInnerHTML={{ __html: ICON_PATHS[name] }}
    />
  );
}
