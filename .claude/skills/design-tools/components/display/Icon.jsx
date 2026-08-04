import React from "react";

const CDN = "https://unpkg.com/lucide-static@0.487.0/icons/";

/** Monochrome icon rendered from the Lucide static SVG set via CSS mask,
 *  so it always inherits the current text color. */
export function Icon({ name, size = 18, color = "currentColor", title, style = {}, ...rest }) {
  const url = `url("${CDN}${name}.svg")`;
  return (
    <span
      role={title ? "img" : "presentation"}
      aria-label={title}
      {...rest}
      style={{
        display: "inline-block",
        flex: "none",
        width: size,
        height: size,
        backgroundColor: color,
        WebkitMask: `${url} center / contain no-repeat`,
        mask: `${url} center / contain no-repeat`,
        ...style,
      }}
    />
  );
}
