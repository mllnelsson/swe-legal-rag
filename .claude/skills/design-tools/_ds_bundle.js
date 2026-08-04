/* @ds-bundle: {"format":4,"namespace":"SvkBeslutsokDesignSystem_46c55d","components":[{"name":"Button","sourcePath":"components/actions/Button.jsx"},{"name":"IconButton","sourcePath":"components/actions/IconButton.jsx"},{"name":"Badge","sourcePath":"components/display/Badge.jsx"},{"name":"Card","sourcePath":"components/display/Card.jsx"},{"name":"Icon","sourcePath":"components/display/Icon.jsx"},{"name":"Tag","sourcePath":"components/display/Tag.jsx"},{"name":"Dialog","sourcePath":"components/feedback/Dialog.jsx"},{"name":"Toast","sourcePath":"components/feedback/Toast.jsx"},{"name":"Tooltip","sourcePath":"components/feedback/Tooltip.jsx"},{"name":"Checkbox","sourcePath":"components/forms/Checkbox.jsx"},{"name":"Input","sourcePath":"components/forms/Input.jsx"},{"name":"Radio","sourcePath":"components/forms/Radio.jsx"},{"name":"SearchField","sourcePath":"components/forms/SearchField.jsx"},{"name":"Select","sourcePath":"components/forms/Select.jsx"},{"name":"Switch","sourcePath":"components/forms/Switch.jsx"},{"name":"SidebarNav","sourcePath":"components/navigation/SidebarNav.jsx"},{"name":"Tabs","sourcePath":"components/navigation/Tabs.jsx"},{"name":"AnswerPanel","sourcePath":"components/research/AnswerPanel.jsx"},{"name":"CitationCard","sourcePath":"components/research/CitationCard.jsx"}],"sourceHashes":{"components/actions/Button.jsx":"d2c53dddc56b","components/actions/IconButton.jsx":"1a71b13b25e6","components/display/Badge.jsx":"d4beb7eb58b5","components/display/Card.jsx":"1289222e1aac","components/display/Icon.jsx":"acc4debd11da","components/display/Tag.jsx":"43efb33ea4f6","components/feedback/Dialog.jsx":"3a32244c3cbd","components/feedback/Toast.jsx":"2021b0c3041f","components/feedback/Tooltip.jsx":"f11a8a50d893","components/forms/Checkbox.jsx":"722d5c86a541","components/forms/Input.jsx":"6ae65b0b3132","components/forms/Radio.jsx":"2473a8aa0261","components/forms/SearchField.jsx":"c79fa36ca0e8","components/forms/Select.jsx":"383350d90eaa","components/forms/Switch.jsx":"8d9f99084dab","components/navigation/SidebarNav.jsx":"15be0897ef66","components/navigation/Tabs.jsx":"3175342e4041","components/research/AnswerPanel.jsx":"06164ff62ac8","components/research/CitationCard.jsx":"336b55f1601e","ui_kits/website/Hero.jsx":"2da4e3cc57cc","ui_kits/website/Sections.jsx":"27139c6275cc","ui_kits/website/SiteHeader.jsx":"1545990583ad","ui_kits/workspace/AppShell.jsx":"f2435b9d4ba6","ui_kits/workspace/DocumentView.jsx":"0bcb741265ad","ui_kits/workspace/MatterView.jsx":"1a1e6d47bfa0","ui_kits/workspace/ResultsView.jsx":"2cd54fec65d6","ui_kits/workspace/SearchHome.jsx":"d366db130671","ui_kits/workspace/data.js":"916b2a3a56c0"},"inlinedExternals":[],"unexposedExports":[]} */

(() => {

const __ds_ns = (window.SvkBeslutsokDesignSystem_46c55d = window.SvkBeslutsokDesignSystem_46c55d || {});

const __ds_scope = {};

(__ds_ns.__errors = __ds_ns.__errors || []);

// components/actions/Button.jsx
try { (() => {
function _extends() { return _extends = Object.assign ? Object.assign.bind() : function (n) { for (var e = 1; e < arguments.length; e++) { var t = arguments[e]; for (var r in t) ({}).hasOwnProperty.call(t, r) && (n[r] = t[r]); } return n; }, _extends.apply(null, arguments); }
const base = {
  fontFamily: "var(--font-sans)",
  fontWeight: "var(--weight-semibold)",
  display: "inline-flex",
  alignItems: "center",
  justifyContent: "center",
  gap: "var(--space-3)",
  borderRadius: "var(--radius-sm)",
  border: "1px solid transparent",
  cursor: "pointer",
  textDecoration: "none",
  whiteSpace: "nowrap",
  transition: "var(--transition-control)"
};
const sizes = {
  sm: {
    height: "var(--control-h-sm)",
    padding: "0 var(--space-4)",
    fontSize: "var(--text-small-size)"
  },
  md: {
    height: "var(--control-h-md)",
    padding: "0 var(--space-6)",
    fontSize: "var(--text-body-size)"
  },
  lg: {
    height: "var(--control-h-lg)",
    padding: "0 var(--space-7)",
    fontSize: "var(--text-body-lg-size)"
  }
};
const variants = {
  primary: {
    background: "var(--action-primary)",
    color: "var(--apricot-50)",
    borderColor: "var(--burgundy-700)",
    boxShadow: "var(--shadow-xs)"
  },
  secondary: {
    background: "var(--surface-card)",
    color: "var(--text-strong)",
    borderColor: "var(--border-default)",
    boxShadow: "var(--shadow-xs)"
  },
  accent: {
    background: "var(--action-secondary)",
    color: "var(--burgundy-700)",
    borderColor: "var(--apricot-300)"
  },
  ghost: {
    background: "transparent",
    color: "var(--text-accent)",
    borderColor: "transparent"
  },
  danger: {
    background: "var(--status-error-fg)",
    color: "#fff",
    borderColor: "#8a1b1b"
  }
};
const hovers = {
  primary: {
    background: "var(--action-primary-hover)"
  },
  secondary: {
    background: "var(--warm-50)",
    borderColor: "var(--border-strong)"
  },
  accent: {
    background: "var(--action-secondary-hover)"
  },
  ghost: {
    background: "var(--apricot-50)"
  },
  danger: {
    background: "#8a1b1b"
  }
};
function Button({
  variant = "primary",
  size = "md",
  disabled = false,
  fullWidth = false,
  iconLeft,
  iconRight,
  as = "button",
  children,
  style = {},
  ...rest
}) {
  const [hover, setHover] = React.useState(false);
  const [press, setPress] = React.useState(false);
  const Tag = as;
  return /*#__PURE__*/React.createElement(Tag, _extends({
    disabled: Tag === "button" ? disabled : undefined,
    onMouseEnter: () => setHover(true),
    onMouseLeave: () => {
      setHover(false);
      setPress(false);
    },
    onMouseDown: () => setPress(true),
    onMouseUp: () => setPress(false)
  }, rest, {
    style: {
      ...base,
      ...sizes[size],
      ...variants[variant],
      ...(hover && !disabled ? hovers[variant] : null),
      ...(press && !disabled ? {
        transform: "translateY(0.5px)",
        boxShadow: "none"
      } : null),
      ...(disabled ? {
        opacity: 0.42,
        cursor: "not-allowed",
        boxShadow: "none"
      } : null),
      width: fullWidth ? "100%" : undefined,
      ...style
    }
  }), iconLeft, children, iconRight);
}
Object.assign(__ds_scope, { Button });
})(); } catch (e) { __ds_ns.__errors.push({ path: "components/actions/Button.jsx", error: String((e && e.message) || e) }); }

// components/display/Badge.jsx
try { (() => {
const tones = {
  neutral: {
    background: "var(--warm-100)",
    color: "var(--text-body)",
    border: "var(--border-hairline)"
  },
  binding: {
    background: "var(--burgundy-50)",
    color: "var(--burgundy-600)",
    border: "var(--burgundy-200)"
  },
  persuasive: {
    background: "var(--apricot-100)",
    color: "var(--apricot-700)",
    border: "var(--apricot-200)"
  },
  ok: {
    background: "var(--status-ok-bg)",
    color: "var(--status-ok-fg)",
    border: "var(--status-ok-bg)"
  },
  warn: {
    background: "var(--status-warn-bg)",
    color: "var(--status-warn-fg)",
    border: "var(--status-warn-bg)"
  },
  error: {
    background: "var(--status-error-bg)",
    color: "var(--status-error-fg)",
    border: "var(--status-error-bg)"
  },
  info: {
    background: "var(--status-info-bg)",
    color: "var(--status-info-fg)",
    border: "var(--status-info-bg)"
  }
};
function Badge({
  children,
  tone = "neutral",
  icon,
  style = {}
}) {
  const t = tones[tone];
  return /*#__PURE__*/React.createElement("span", {
    style: {
      display: "inline-flex",
      alignItems: "center",
      gap: "var(--space-2)",
      height: 21,
      padding: "0 var(--space-3)",
      borderRadius: "var(--radius-xs)",
      background: t.background,
      color: t.color,
      border: `1px solid ${t.border}`,
      fontFamily: "var(--font-sans)",
      fontSize: "var(--text-caption-size)",
      fontWeight: "var(--weight-semibold)",
      letterSpacing: "0.01em",
      whiteSpace: "nowrap",
      ...style
    }
  }, icon, children);
}
Object.assign(__ds_scope, { Badge });
})(); } catch (e) { __ds_ns.__errors.push({ path: "components/display/Badge.jsx", error: String((e && e.message) || e) }); }

// components/display/Card.jsx
try { (() => {
function _extends() { return _extends = Object.assign ? Object.assign.bind() : function (n) { for (var e = 1; e < arguments.length; e++) { var t = arguments[e]; for (var r in t) ({}).hasOwnProperty.call(t, r) && (n[r] = t[r]); } return n; }, _extends.apply(null, arguments); }
function Card({
  children,
  padding = "var(--space-7)",
  tone = "default",
  interactive = false,
  header,
  footer,
  style = {},
  ...rest
}) {
  const [hover, setHover] = React.useState(false);
  const tones = {
    default: {
      background: "var(--surface-card)",
      border: "1px solid var(--border-hairline)"
    },
    accent: {
      background: "var(--surface-accent)",
      border: "1px solid var(--apricot-200)"
    },
    wash: {
      background: "var(--gradient-wash-soft)",
      border: "1px solid var(--apricot-200)"
    },
    inverse: {
      background: "var(--gradient-authority)",
      border: "1px solid var(--burgundy-800)",
      color: "var(--apricot-100)"
    }
  };
  return /*#__PURE__*/React.createElement("div", _extends({
    onMouseEnter: () => setHover(true),
    onMouseLeave: () => setHover(false)
  }, rest, {
    style: {
      borderRadius: "var(--radius-lg)",
      boxShadow: hover && interactive ? "var(--shadow-md)" : "var(--shadow-sm)",
      transition: "box-shadow var(--dur-base) var(--ease-standard), border-color var(--dur-base) var(--ease-standard)",
      cursor: interactive ? "pointer" : undefined,
      overflow: "hidden",
      fontFamily: "var(--font-sans)",
      ...tones[tone],
      ...(hover && interactive ? {
        borderColor: "var(--apricot-300)"
      } : null),
      ...style
    }
  }), header && /*#__PURE__*/React.createElement("div", {
    style: {
      padding: `var(--space-5) ${padding}`,
      borderBottom: "1px solid var(--border-hairline)",
      fontWeight: "var(--weight-semibold)",
      color: "var(--text-strong)",
      fontSize: "var(--text-small-size)"
    }
  }, header), /*#__PURE__*/React.createElement("div", {
    style: {
      padding
    }
  }, children), footer && /*#__PURE__*/React.createElement("div", {
    style: {
      padding: `var(--space-5) ${padding}`,
      borderTop: "1px solid var(--border-hairline)",
      background: "var(--warm-25)"
    }
  }, footer));
}
Object.assign(__ds_scope, { Card });
})(); } catch (e) { __ds_ns.__errors.push({ path: "components/display/Card.jsx", error: String((e && e.message) || e) }); }

// components/display/Icon.jsx
try { (() => {
function _extends() { return _extends = Object.assign ? Object.assign.bind() : function (n) { for (var e = 1; e < arguments.length; e++) { var t = arguments[e]; for (var r in t) ({}).hasOwnProperty.call(t, r) && (n[r] = t[r]); } return n; }, _extends.apply(null, arguments); }
const CDN = "https://unpkg.com/lucide-static@0.487.0/icons/";

/** Monochrome icon rendered from the Lucide static SVG set via CSS mask,
 *  so it always inherits the current text color. */
function Icon({
  name,
  size = 18,
  color = "currentColor",
  title,
  style = {},
  ...rest
}) {
  const url = `url("${CDN}${name}.svg")`;
  return /*#__PURE__*/React.createElement("span", _extends({
    role: title ? "img" : "presentation",
    "aria-label": title
  }, rest, {
    style: {
      display: "inline-block",
      flex: "none",
      width: size,
      height: size,
      backgroundColor: color,
      WebkitMask: `${url} center / contain no-repeat`,
      mask: `${url} center / contain no-repeat`,
      ...style
    }
  }));
}
Object.assign(__ds_scope, { Icon });
})(); } catch (e) { __ds_ns.__errors.push({ path: "components/display/Icon.jsx", error: String((e && e.message) || e) }); }

// components/actions/IconButton.jsx
try { (() => {
function _extends() { return _extends = Object.assign ? Object.assign.bind() : function (n) { for (var e = 1; e < arguments.length; e++) { var t = arguments[e]; for (var r in t) ({}).hasOwnProperty.call(t, r) && (n[r] = t[r]); } return n; }, _extends.apply(null, arguments); }
const sizes = {
  sm: 30,
  md: 38,
  lg: 46
};
function IconButton({
  icon,
  label,
  variant = "secondary",
  size = "md",
  disabled = false,
  style = {},
  ...rest
}) {
  const [hover, setHover] = React.useState(false);
  const px = sizes[size];
  const skin = {
    secondary: {
      background: "var(--surface-card)",
      border: "1px solid var(--border-default)",
      color: "var(--text-body)"
    },
    ghost: {
      background: "transparent",
      border: "1px solid transparent",
      color: "var(--text-muted)"
    },
    primary: {
      background: "var(--action-primary)",
      border: "1px solid var(--burgundy-700)",
      color: "var(--apricot-50)"
    }
  }[variant];
  const hoverSkin = {
    secondary: {
      background: "var(--warm-50)",
      borderColor: "var(--border-strong)",
      color: "var(--text-strong)"
    },
    ghost: {
      background: "var(--apricot-50)",
      color: "var(--text-accent)"
    },
    primary: {
      background: "var(--action-primary-hover)"
    }
  }[variant];
  return /*#__PURE__*/React.createElement("button", _extends({
    "aria-label": label,
    title: label,
    disabled: disabled,
    onMouseEnter: () => setHover(true),
    onMouseLeave: () => setHover(false)
  }, rest, {
    style: {
      width: px,
      height: px,
      display: "inline-flex",
      alignItems: "center",
      justifyContent: "center",
      borderRadius: "var(--radius-sm)",
      cursor: disabled ? "not-allowed" : "pointer",
      transition: "var(--transition-control)",
      opacity: disabled ? 0.42 : 1,
      ...skin,
      ...(hover && !disabled ? hoverSkin : null),
      ...style
    }
  }), typeof icon === "string" ? /*#__PURE__*/React.createElement(__ds_scope.Icon, {
    name: icon,
    size: size === "sm" ? 15 : 17
  }) : icon);
}
Object.assign(__ds_scope, { IconButton });
})(); } catch (e) { __ds_ns.__errors.push({ path: "components/actions/IconButton.jsx", error: String((e && e.message) || e) }); }

// components/display/Tag.jsx
try { (() => {
function Tag({
  children,
  onRemove,
  selected = false,
  onClick,
  style = {}
}) {
  const [hover, setHover] = React.useState(false);
  return /*#__PURE__*/React.createElement("span", {
    onClick: onClick,
    onMouseEnter: () => setHover(true),
    onMouseLeave: () => setHover(false),
    style: {
      display: "inline-flex",
      alignItems: "center",
      gap: "var(--space-3)",
      height: 28,
      padding: "0 var(--space-4)",
      borderRadius: "var(--radius-pill)",
      fontFamily: "var(--font-sans)",
      fontSize: "var(--text-small-size)",
      fontWeight: "var(--weight-medium)",
      cursor: onClick ? "pointer" : "default",
      background: selected ? "var(--apricot-100)" : hover && onClick ? "var(--warm-50)" : "var(--surface-card)",
      border: `1px solid ${selected ? "var(--apricot-300)" : "var(--border-hairline)"}`,
      color: selected ? "var(--burgundy-600)" : "var(--text-body)",
      transition: "var(--transition-control)",
      ...style
    }
  }, children, onRemove && /*#__PURE__*/React.createElement("button", {
    onClick: e => {
      e.stopPropagation();
      onRemove();
    },
    "aria-label": "Remove",
    style: {
      border: "none",
      background: "transparent",
      padding: 0,
      display: "inline-flex",
      cursor: "pointer",
      color: "inherit",
      opacity: 0.65
    }
  }, /*#__PURE__*/React.createElement(__ds_scope.Icon, {
    name: "x",
    size: 13
  })));
}
Object.assign(__ds_scope, { Tag });
})(); } catch (e) { __ds_ns.__errors.push({ path: "components/display/Tag.jsx", error: String((e && e.message) || e) }); }

// components/feedback/Dialog.jsx
try { (() => {
function Dialog({
  open = true,
  title,
  description,
  children,
  footer,
  onClose,
  width = 520
}) {
  if (!open) return null;
  return /*#__PURE__*/React.createElement("div", {
    style: {
      position: "fixed",
      inset: 0,
      zIndex: 60,
      display: "flex",
      alignItems: "center",
      justifyContent: "center",
      padding: "var(--space-8)",
      background: "var(--surface-overlay)",
      backdropFilter: "blur(2px)",
      fontFamily: "var(--font-sans)"
    }
  }, /*#__PURE__*/React.createElement("div", {
    role: "dialog",
    "aria-modal": "true",
    style: {
      width,
      maxWidth: "100%",
      background: "var(--surface-card)",
      borderRadius: "var(--radius-lg)",
      boxShadow: "var(--shadow-overlay)",
      overflow: "hidden",
      animation: "none"
    }
  }, /*#__PURE__*/React.createElement("div", {
    style: {
      display: "flex",
      alignItems: "flex-start",
      gap: "var(--space-5)",
      padding: "var(--space-7) var(--space-7) var(--space-5)"
    }
  }, /*#__PURE__*/React.createElement("div", {
    style: {
      flex: 1,
      display: "flex",
      flexDirection: "column",
      gap: "var(--space-2)"
    }
  }, /*#__PURE__*/React.createElement("h3", {
    style: {
      fontFamily: "var(--font-display)",
      fontSize: "var(--text-h3-size)",
      lineHeight: "var(--text-h3-lh)",
      color: "var(--text-strong)",
      margin: 0
    }
  }, title), description && /*#__PURE__*/React.createElement("p", {
    style: {
      margin: 0,
      fontSize: "var(--text-body-size)",
      lineHeight: "var(--text-body-lh)",
      color: "var(--text-muted)"
    }
  }, description)), onClose && /*#__PURE__*/React.createElement(__ds_scope.IconButton, {
    icon: "x",
    label: "Close",
    variant: "ghost",
    size: "sm",
    onClick: onClose
  })), children && /*#__PURE__*/React.createElement("div", {
    style: {
      padding: "0 var(--space-7) var(--space-7)"
    }
  }, children), footer && /*#__PURE__*/React.createElement("div", {
    style: {
      display: "flex",
      justifyContent: "flex-end",
      gap: "var(--space-4)",
      padding: "var(--space-5) var(--space-7)",
      borderTop: "1px solid var(--border-hairline)",
      background: "var(--warm-25)"
    }
  }, footer)));
}
Object.assign(__ds_scope, { Dialog });
})(); } catch (e) { __ds_ns.__errors.push({ path: "components/feedback/Dialog.jsx", error: String((e && e.message) || e) }); }

// components/feedback/Toast.jsx
try { (() => {
const tones = {
  info: {
    icon: "info",
    fg: "var(--status-info-fg)",
    bg: "var(--surface-card)"
  },
  ok: {
    icon: "check",
    fg: "var(--status-ok-fg)",
    bg: "var(--surface-card)"
  },
  warn: {
    icon: "triangle-alert",
    fg: "var(--status-warn-fg)",
    bg: "var(--surface-card)"
  },
  error: {
    icon: "circle-alert",
    fg: "var(--status-error-fg)",
    bg: "var(--surface-card)"
  }
};
function Toast({
  tone = "info",
  title,
  message,
  action,
  onDismiss,
  style = {}
}) {
  const t = tones[tone];
  return /*#__PURE__*/React.createElement("div", {
    role: "status",
    style: {
      display: "flex",
      alignItems: "flex-start",
      gap: "var(--space-4)",
      width: 380,
      maxWidth: "100%",
      padding: "var(--space-5)",
      background: t.bg,
      border: "1px solid var(--border-hairline)",
      borderRadius: "var(--radius-md)",
      boxShadow: "var(--shadow-lg)",
      fontFamily: "var(--font-sans)",
      ...style
    }
  }, /*#__PURE__*/React.createElement(__ds_scope.Icon, {
    name: t.icon,
    size: 17,
    color: t.fg,
    style: {
      marginTop: 1
    }
  }), /*#__PURE__*/React.createElement("div", {
    style: {
      flex: 1,
      display: "flex",
      flexDirection: "column",
      gap: 2
    }
  }, /*#__PURE__*/React.createElement("span", {
    style: {
      fontSize: "var(--text-body-size)",
      fontWeight: "var(--weight-semibold)",
      color: "var(--text-strong)"
    }
  }, title), message && /*#__PURE__*/React.createElement("span", {
    style: {
      fontSize: "var(--text-small-size)",
      color: "var(--text-muted)"
    }
  }, message), action && /*#__PURE__*/React.createElement("span", {
    style: {
      marginTop: "var(--space-3)"
    }
  }, action)), onDismiss && /*#__PURE__*/React.createElement("button", {
    onClick: onDismiss,
    "aria-label": "Dismiss",
    style: {
      border: "none",
      background: "transparent",
      cursor: "pointer",
      padding: 0,
      color: "var(--text-faint)"
    }
  }, /*#__PURE__*/React.createElement(__ds_scope.Icon, {
    name: "x",
    size: 15
  })));
}
Object.assign(__ds_scope, { Toast });
})(); } catch (e) { __ds_ns.__errors.push({ path: "components/feedback/Toast.jsx", error: String((e && e.message) || e) }); }

// components/feedback/Tooltip.jsx
try { (() => {
function Tooltip({
  label,
  children,
  placement = "top",
  style = {}
}) {
  const [show, setShow] = React.useState(false);
  const pos = {
    top: {
      bottom: "calc(100% + 6px)",
      left: "50%",
      transform: "translateX(-50%)"
    },
    bottom: {
      top: "calc(100% + 6px)",
      left: "50%",
      transform: "translateX(-50%)"
    },
    left: {
      right: "calc(100% + 6px)",
      top: "50%",
      transform: "translateY(-50%)"
    },
    right: {
      left: "calc(100% + 6px)",
      top: "50%",
      transform: "translateY(-50%)"
    }
  }[placement];
  return /*#__PURE__*/React.createElement("span", {
    style: {
      position: "relative",
      display: "inline-flex",
      ...style
    },
    onMouseEnter: () => setShow(true),
    onMouseLeave: () => setShow(false)
  }, children, /*#__PURE__*/React.createElement("span", {
    role: "tooltip",
    style: {
      position: "absolute",
      ...pos,
      zIndex: 40,
      pointerEvents: "none",
      whiteSpace: "nowrap",
      padding: "var(--space-2) var(--space-4)",
      borderRadius: "var(--radius-xs)",
      background: "var(--warm-800)",
      color: "var(--apricot-50)",
      fontFamily: "var(--font-sans)",
      fontSize: "var(--text-caption-size)",
      fontWeight: "var(--weight-medium)",
      boxShadow: "var(--shadow-md)",
      opacity: show ? 1 : 0,
      transition: `opacity var(--dur-fast) var(--ease-standard)`
    }
  }, label));
}
Object.assign(__ds_scope, { Tooltip });
})(); } catch (e) { __ds_ns.__errors.push({ path: "components/feedback/Tooltip.jsx", error: String((e && e.message) || e) }); }

// components/forms/Checkbox.jsx
try { (() => {
function Checkbox({
  label,
  description,
  checked = false,
  onChange,
  disabled,
  style = {}
}) {
  return /*#__PURE__*/React.createElement("label", {
    style: {
      display: "flex",
      gap: "var(--space-4)",
      alignItems: "flex-start",
      cursor: disabled ? "not-allowed" : "pointer",
      opacity: disabled ? 0.5 : 1,
      fontFamily: "var(--font-sans)",
      ...style
    }
  }, /*#__PURE__*/React.createElement("span", {
    onClick: () => !disabled && onChange && onChange(!checked),
    style: {
      width: 17,
      height: 17,
      marginTop: 1,
      flex: "none",
      display: "inline-flex",
      alignItems: "center",
      justifyContent: "center",
      borderRadius: "var(--radius-xs)",
      border: `1px solid ${checked ? "var(--burgundy-600)" : "var(--border-strong)"}`,
      background: checked ? "var(--action-primary)" : "var(--surface-card)",
      transition: "var(--transition-control)"
    }
  }, checked && /*#__PURE__*/React.createElement(__ds_scope.Icon, {
    name: "check",
    size: 12,
    color: "var(--apricot-50)"
  })), /*#__PURE__*/React.createElement("span", {
    style: {
      display: "flex",
      flexDirection: "column",
      gap: 2
    }
  }, /*#__PURE__*/React.createElement("span", {
    style: {
      fontSize: "var(--text-body-size)",
      color: "var(--text-strong)"
    }
  }, label), description && /*#__PURE__*/React.createElement("span", {
    style: {
      fontSize: "var(--text-caption-size)",
      color: "var(--text-muted)"
    }
  }, description)));
}
Object.assign(__ds_scope, { Checkbox });
})(); } catch (e) { __ds_ns.__errors.push({ path: "components/forms/Checkbox.jsx", error: String((e && e.message) || e) }); }

// components/forms/Input.jsx
try { (() => {
function _extends() { return _extends = Object.assign ? Object.assign.bind() : function (n) { for (var e = 1; e < arguments.length; e++) { var t = arguments[e]; for (var r in t) ({}).hasOwnProperty.call(t, r) && (n[r] = t[r]); } return n; }, _extends.apply(null, arguments); }
function Input({
  label,
  hint,
  error,
  iconLeft,
  size = "md",
  disabled,
  id,
  style = {},
  ...rest
}) {
  const [focus, setFocus] = React.useState(false);
  const uid = id || React.useId();
  return /*#__PURE__*/React.createElement("div", {
    style: {
      display: "flex",
      flexDirection: "column",
      gap: "var(--space-3)",
      fontFamily: "var(--font-sans)"
    }
  }, label && /*#__PURE__*/React.createElement("label", {
    htmlFor: uid,
    style: {
      fontSize: "var(--text-small-size)",
      fontWeight: "var(--weight-semibold)",
      color: "var(--text-strong)"
    }
  }, label), /*#__PURE__*/React.createElement("div", {
    style: {
      display: "flex",
      alignItems: "center",
      gap: "var(--space-3)",
      height: size === "sm" ? "var(--control-h-sm)" : size === "lg" ? "var(--control-h-lg)" : "var(--control-h-md)",
      padding: "0 var(--space-4)",
      background: disabled ? "var(--surface-sunken)" : "var(--surface-card)",
      border: `1px solid ${error ? "var(--status-error-fg)" : focus ? "var(--apricot-400)" : "var(--border-default)"}`,
      borderRadius: "var(--radius-sm)",
      boxShadow: focus ? error ? "var(--ring-error)" : "var(--ring-focus)" : "var(--shadow-xs)",
      transition: "var(--transition-control)",
      ...style
    }
  }, iconLeft && (typeof iconLeft === "string" ? /*#__PURE__*/React.createElement(__ds_scope.Icon, {
    name: iconLeft,
    size: 16,
    color: "var(--text-faint)"
  }) : iconLeft), /*#__PURE__*/React.createElement("input", _extends({
    id: uid,
    disabled: disabled,
    onFocus: () => setFocus(true),
    onBlur: () => setFocus(false)
  }, rest, {
    style: {
      flex: 1,
      minWidth: 0,
      border: "none",
      outline: "none",
      background: "transparent",
      font: "inherit",
      fontSize: "var(--text-body-size)",
      color: "var(--text-strong)"
    }
  }))), (hint || error) && /*#__PURE__*/React.createElement("span", {
    style: {
      fontSize: "var(--text-caption-size)",
      color: error ? "var(--status-error-fg)" : "var(--text-muted)"
    }
  }, error || hint));
}
Object.assign(__ds_scope, { Input });
})(); } catch (e) { __ds_ns.__errors.push({ path: "components/forms/Input.jsx", error: String((e && e.message) || e) }); }

// components/forms/Radio.jsx
try { (() => {
function Radio({
  label,
  description,
  checked = false,
  onChange,
  name,
  disabled,
  style = {}
}) {
  return /*#__PURE__*/React.createElement("label", {
    style: {
      display: "flex",
      gap: "var(--space-4)",
      alignItems: "flex-start",
      cursor: disabled ? "not-allowed" : "pointer",
      opacity: disabled ? 0.5 : 1,
      fontFamily: "var(--font-sans)",
      ...style
    }
  }, /*#__PURE__*/React.createElement("input", {
    type: "radio",
    name: name,
    checked: checked,
    disabled: disabled,
    onChange: () => onChange && onChange(true),
    style: {
      position: "absolute",
      opacity: 0,
      width: 0,
      height: 0
    }
  }), /*#__PURE__*/React.createElement("span", {
    style: {
      width: 17,
      height: 17,
      marginTop: 1,
      flex: "none",
      borderRadius: "var(--radius-pill)",
      border: `1px solid ${checked ? "var(--burgundy-600)" : "var(--border-strong)"}`,
      background: "var(--surface-card)",
      display: "inline-flex",
      alignItems: "center",
      justifyContent: "center",
      transition: "var(--transition-control)"
    }
  }, checked && /*#__PURE__*/React.createElement("span", {
    style: {
      width: 8,
      height: 8,
      borderRadius: "var(--radius-pill)",
      background: "var(--action-primary)"
    }
  })), /*#__PURE__*/React.createElement("span", {
    style: {
      display: "flex",
      flexDirection: "column",
      gap: 2
    }
  }, /*#__PURE__*/React.createElement("span", {
    style: {
      fontSize: "var(--text-body-size)",
      color: "var(--text-strong)"
    }
  }, label), description && /*#__PURE__*/React.createElement("span", {
    style: {
      fontSize: "var(--text-caption-size)",
      color: "var(--text-muted)"
    }
  }, description)));
}
Object.assign(__ds_scope, { Radio });
})(); } catch (e) { __ds_ns.__errors.push({ path: "components/forms/Radio.jsx", error: String((e && e.message) || e) }); }

// components/forms/SearchField.jsx
try { (() => {
/** The product's signature control: a wide, calm question box. */
function SearchField({
  value,
  onChange,
  onSubmit,
  placeholder = "Ask a research question, or paste a citation",
  scope,
  submitLabel = "Search",
  disabled,
  style = {}
}) {
  const [focus, setFocus] = React.useState(false);
  return /*#__PURE__*/React.createElement("form", {
    onSubmit: e => {
      e.preventDefault();
      onSubmit && onSubmit(value);
    },
    style: {
      display: "flex",
      alignItems: "center",
      gap: "var(--space-4)",
      padding: "var(--space-3) var(--space-3) var(--space-3) var(--space-6)",
      background: "var(--surface-card)",
      border: `1px solid ${focus ? "var(--apricot-400)" : "var(--border-hairline)"}`,
      borderRadius: "var(--radius-xl)",
      boxShadow: focus ? "var(--ring-focus), var(--shadow-md)" : "var(--shadow-md)",
      transition: "var(--transition-control)",
      fontFamily: "var(--font-sans)",
      ...style
    }
  }, /*#__PURE__*/React.createElement(__ds_scope.Icon, {
    name: "search",
    size: 20,
    color: "var(--burgundy-600)"
  }), /*#__PURE__*/React.createElement("input", {
    value: value,
    disabled: disabled,
    placeholder: placeholder,
    onChange: e => onChange && onChange(e.target.value),
    onFocus: () => setFocus(true),
    onBlur: () => setFocus(false),
    style: {
      flex: 1,
      minWidth: 0,
      border: "none",
      outline: "none",
      background: "transparent",
      font: "inherit",
      fontSize: "var(--text-body-lg-size)",
      color: "var(--text-strong)"
    }
  }), scope && /*#__PURE__*/React.createElement("span", {
    style: {
      display: "inline-flex",
      alignItems: "center",
      gap: "var(--space-2)",
      padding: "0 var(--space-4)",
      height: 28,
      borderRadius: "var(--radius-pill)",
      background: "var(--apricot-50)",
      border: "1px solid var(--apricot-200)",
      color: "var(--burgundy-600)",
      fontSize: "var(--text-caption-size)",
      fontWeight: "var(--weight-semibold)",
      whiteSpace: "nowrap"
    }
  }, /*#__PURE__*/React.createElement(__ds_scope.Icon, {
    name: "scale",
    size: 13
  }), scope), /*#__PURE__*/React.createElement("button", {
    type: "submit",
    disabled: disabled,
    style: {
      height: "var(--control-h-md)",
      padding: "0 var(--space-6)",
      borderRadius: "var(--radius-pill)",
      border: "1px solid var(--burgundy-700)",
      background: "var(--action-primary)",
      color: "var(--apricot-50)",
      font: "inherit",
      fontSize: "var(--text-small-size)",
      fontWeight: "var(--weight-semibold)",
      cursor: "pointer",
      transition: "var(--transition-control)"
    }
  }, submitLabel));
}
Object.assign(__ds_scope, { SearchField });
})(); } catch (e) { __ds_ns.__errors.push({ path: "components/forms/SearchField.jsx", error: String((e && e.message) || e) }); }

// components/forms/Select.jsx
try { (() => {
function _extends() { return _extends = Object.assign ? Object.assign.bind() : function (n) { for (var e = 1; e < arguments.length; e++) { var t = arguments[e]; for (var r in t) ({}).hasOwnProperty.call(t, r) && (n[r] = t[r]); } return n; }, _extends.apply(null, arguments); }
function Select({
  label,
  hint,
  options = [],
  value,
  onChange,
  size = "md",
  disabled,
  id,
  style = {},
  ...rest
}) {
  const uid = id || React.useId();
  return /*#__PURE__*/React.createElement("div", {
    style: {
      display: "flex",
      flexDirection: "column",
      gap: "var(--space-3)",
      fontFamily: "var(--font-sans)"
    }
  }, label && /*#__PURE__*/React.createElement("label", {
    htmlFor: uid,
    style: {
      fontSize: "var(--text-small-size)",
      fontWeight: "var(--weight-semibold)",
      color: "var(--text-strong)"
    }
  }, label), /*#__PURE__*/React.createElement("div", {
    style: {
      position: "relative",
      display: "flex",
      alignItems: "center"
    }
  }, /*#__PURE__*/React.createElement("select", _extends({
    id: uid,
    value: value,
    disabled: disabled,
    onChange: e => onChange && onChange(e.target.value)
  }, rest, {
    style: {
      appearance: "none",
      width: "100%",
      height: size === "sm" ? "var(--control-h-sm)" : "var(--control-h-md)",
      padding: "0 var(--space-9) 0 var(--space-4)",
      background: disabled ? "var(--surface-sunken)" : "var(--surface-card)",
      border: "1px solid var(--border-default)",
      borderRadius: "var(--radius-sm)",
      boxShadow: "var(--shadow-xs)",
      font: "inherit",
      fontSize: "var(--text-body-size)",
      color: "var(--text-strong)",
      cursor: disabled ? "not-allowed" : "pointer",
      ...style
    }
  }), options.map(o => {
    const opt = typeof o === "string" ? {
      value: o,
      label: o
    } : o;
    return /*#__PURE__*/React.createElement("option", {
      key: opt.value,
      value: opt.value
    }, opt.label);
  })), /*#__PURE__*/React.createElement(__ds_scope.Icon, {
    name: "chevron-down",
    size: 15,
    color: "var(--text-muted)",
    style: {
      position: "absolute",
      right: "var(--space-4)",
      pointerEvents: "none"
    }
  })), hint && /*#__PURE__*/React.createElement("span", {
    style: {
      fontSize: "var(--text-caption-size)",
      color: "var(--text-muted)"
    }
  }, hint));
}
Object.assign(__ds_scope, { Select });
})(); } catch (e) { __ds_ns.__errors.push({ path: "components/forms/Select.jsx", error: String((e && e.message) || e) }); }

// components/forms/Switch.jsx
try { (() => {
function Switch({
  checked = false,
  onChange,
  label,
  disabled,
  style = {}
}) {
  return /*#__PURE__*/React.createElement("label", {
    style: {
      display: "inline-flex",
      alignItems: "center",
      gap: "var(--space-4)",
      cursor: disabled ? "not-allowed" : "pointer",
      opacity: disabled ? 0.5 : 1,
      fontFamily: "var(--font-sans)",
      ...style
    }
  }, /*#__PURE__*/React.createElement("span", {
    onClick: () => !disabled && onChange && onChange(!checked),
    style: {
      width: 36,
      height: 20,
      flex: "none",
      padding: 2,
      borderRadius: "var(--radius-pill)",
      background: checked ? "var(--action-primary)" : "var(--warm-300)",
      transition: "background-color var(--dur-base) var(--ease-standard)",
      display: "flex",
      alignItems: "center"
    }
  }, /*#__PURE__*/React.createElement("span", {
    style: {
      width: 16,
      height: 16,
      borderRadius: "var(--radius-pill)",
      background: "#fff",
      boxShadow: "var(--shadow-sm)",
      transform: `translateX(${checked ? 16 : 0}px)`,
      transition: "transform var(--dur-base) var(--ease-standard)"
    }
  })), label && /*#__PURE__*/React.createElement("span", {
    style: {
      fontSize: "var(--text-body-size)",
      color: "var(--text-strong)"
    }
  }, label));
}
Object.assign(__ds_scope, { Switch });
})(); } catch (e) { __ds_ns.__errors.push({ path: "components/forms/Switch.jsx", error: String((e && e.message) || e) }); }

// components/navigation/SidebarNav.jsx
try { (() => {
function SidebarNav({
  items = [],
  value,
  onChange,
  footer,
  title,
  style = {}
}) {
  return /*#__PURE__*/React.createElement("nav", {
    style: {
      width: "var(--sidebar-w)",
      flex: "none",
      display: "flex",
      flexDirection: "column",
      gap: "var(--space-3)",
      padding: "var(--space-6)",
      background: "var(--warm-25)",
      borderRight: "1px solid var(--border-hairline)",
      fontFamily: "var(--font-sans)",
      ...style
    }
  }, title && /*#__PURE__*/React.createElement("div", {
    style: {
      fontSize: "var(--text-overline-size)",
      letterSpacing: "var(--text-overline-ls)",
      textTransform: "uppercase",
      fontWeight: "var(--weight-semibold)",
      color: "var(--text-faint)",
      padding: "var(--space-3) var(--space-4)"
    }
  }, title), items.map(item => {
    const active = item.value === value;
    return /*#__PURE__*/React.createElement("button", {
      key: item.value,
      onClick: () => onChange && onChange(item.value),
      style: {
        display: "flex",
        alignItems: "center",
        gap: "var(--space-4)",
        height: 34,
        padding: "0 var(--space-4)",
        border: "none",
        borderRadius: "var(--radius-sm)",
        cursor: "pointer",
        textAlign: "left",
        background: active ? "var(--apricot-100)" : "transparent",
        color: active ? "var(--burgundy-600)" : "var(--text-body)",
        font: "inherit",
        fontSize: "var(--text-body-size)",
        fontWeight: active ? "var(--weight-semibold)" : "var(--weight-regular)",
        transition: "var(--transition-control)"
      }
    }, item.icon && /*#__PURE__*/React.createElement(__ds_scope.Icon, {
      name: item.icon,
      size: 16
    }), /*#__PURE__*/React.createElement("span", {
      style: {
        flex: 1,
        overflow: "hidden",
        textOverflow: "ellipsis",
        whiteSpace: "nowrap"
      }
    }, item.label), item.count != null && /*#__PURE__*/React.createElement("span", {
      style: {
        fontSize: "var(--text-caption-size)",
        color: "var(--text-faint)"
      }
    }, item.count));
  }), footer && /*#__PURE__*/React.createElement("div", {
    style: {
      marginTop: "auto"
    }
  }, footer));
}
Object.assign(__ds_scope, { SidebarNav });
})(); } catch (e) { __ds_ns.__errors.push({ path: "components/navigation/SidebarNav.jsx", error: String((e && e.message) || e) }); }

// components/navigation/Tabs.jsx
try { (() => {
function Tabs({
  tabs = [],
  value,
  onChange,
  variant = "underline",
  style = {}
}) {
  const items = tabs.map(t => typeof t === "string" ? {
    value: t,
    label: t
  } : t);
  const active = value ?? items[0]?.value;
  if (variant === "pill") {
    return /*#__PURE__*/React.createElement("div", {
      style: {
        display: "inline-flex",
        gap: "var(--space-1)",
        padding: 3,
        background: "var(--surface-sunken)",
        borderRadius: "var(--radius-pill)",
        fontFamily: "var(--font-sans)",
        ...style
      }
    }, items.map(t => /*#__PURE__*/React.createElement("button", {
      key: t.value,
      onClick: () => onChange && onChange(t.value),
      style: {
        height: 30,
        padding: "0 var(--space-5)",
        border: "none",
        borderRadius: "var(--radius-pill)",
        cursor: "pointer",
        background: t.value === active ? "var(--surface-card)" : "transparent",
        boxShadow: t.value === active ? "var(--shadow-xs)" : "none",
        color: t.value === active ? "var(--text-strong)" : "var(--text-muted)",
        font: "inherit",
        fontSize: "var(--text-small-size)",
        fontWeight: "var(--weight-semibold)",
        transition: "var(--transition-control)"
      }
    }, t.label)));
  }
  return /*#__PURE__*/React.createElement("div", {
    style: {
      display: "flex",
      gap: "var(--space-7)",
      borderBottom: "1px solid var(--border-hairline)",
      fontFamily: "var(--font-sans)",
      ...style
    }
  }, items.map(t => /*#__PURE__*/React.createElement("button", {
    key: t.value,
    onClick: () => onChange && onChange(t.value),
    style: {
      position: "relative",
      padding: "0 0 var(--space-4)",
      border: "none",
      background: "transparent",
      cursor: "pointer",
      color: t.value === active ? "var(--text-strong)" : "var(--text-muted)",
      font: "inherit",
      fontSize: "var(--text-body-size)",
      fontWeight: "var(--weight-semibold)",
      boxShadow: t.value === active ? "inset 0 -2px 0 var(--burgundy-600)" : "none",
      transition: "var(--transition-control)"
    }
  }, t.label, t.count != null && /*#__PURE__*/React.createElement("span", {
    style: {
      marginLeft: "var(--space-3)",
      color: "var(--text-faint)",
      fontWeight: "var(--weight-regular)"
    }
  }, t.count))));
}
Object.assign(__ds_scope, { Tabs });
})(); } catch (e) { __ds_ns.__errors.push({ path: "components/navigation/Tabs.jsx", error: String((e && e.message) || e) }); }

// components/research/AnswerPanel.jsx
try { (() => {
/** The assistant's synthesized answer, with inline superscript source markers. */
function AnswerPanel({
  question,
  answer,
  sources = [],
  onSourceClick,
  status,
  style = {}
}) {
  return /*#__PURE__*/React.createElement("section", {
    style: {
      display: "flex",
      flexDirection: "column",
      gap: "var(--space-5)",
      padding: "var(--space-7) var(--space-8)",
      background: "var(--gradient-wash-soft)",
      border: "1px solid var(--apricot-200)",
      borderRadius: "var(--radius-lg)",
      boxShadow: "var(--shadow-sm)",
      fontFamily: "var(--font-sans)",
      ...style
    }
  }, /*#__PURE__*/React.createElement("div", {
    style: {
      display: "flex",
      alignItems: "center",
      gap: "var(--space-3)",
      fontSize: "var(--text-overline-size)",
      letterSpacing: "var(--text-overline-ls)",
      textTransform: "uppercase",
      fontWeight: "var(--weight-semibold)",
      color: "var(--burgundy-600)"
    }
  }, /*#__PURE__*/React.createElement(__ds_scope.Icon, {
    name: "sparkles",
    size: 13,
    color: "var(--burgundy-600)"
  }), status || "Research summary"), question && /*#__PURE__*/React.createElement("h2", {
    style: {
      fontFamily: "var(--font-display)",
      fontSize: "var(--text-h2-size)",
      lineHeight: "var(--text-h2-lh)",
      letterSpacing: "var(--text-h2-ls)",
      color: "var(--text-strong)",
      margin: 0,
      maxWidth: "var(--measure-prose)"
    }
  }, question), /*#__PURE__*/React.createElement("div", {
    style: {
      fontSize: "var(--text-body-lg-size)",
      lineHeight: "var(--text-body-lg-lh)",
      color: "var(--text-body)",
      maxWidth: "var(--measure-prose)",
      textWrap: "pretty"
    }
  }, answer), sources.length > 0 && /*#__PURE__*/React.createElement("div", {
    style: {
      display: "flex",
      flexWrap: "wrap",
      gap: "var(--space-3)",
      paddingTop: "var(--space-4)",
      borderTop: "1px solid var(--apricot-200)"
    }
  }, /*#__PURE__*/React.createElement("span", {
    style: {
      fontSize: "var(--text-caption-size)",
      color: "var(--text-muted)",
      alignSelf: "center",
      marginRight: "var(--space-2)"
    }
  }, "Sources"), sources.map((s, i) => /*#__PURE__*/React.createElement("button", {
    key: s,
    onClick: () => onSourceClick && onSourceClick(i),
    style: {
      display: "inline-flex",
      alignItems: "center",
      gap: "var(--space-2)",
      height: 26,
      padding: "0 var(--space-4)",
      borderRadius: "var(--radius-pill)",
      border: "1px solid var(--apricot-300)",
      background: "rgba(255,255,255,0.72)",
      color: "var(--burgundy-600)",
      font: "inherit",
      fontSize: "var(--text-caption-size)",
      fontWeight: "var(--weight-semibold)",
      cursor: "pointer",
      transition: "var(--transition-control)"
    }
  }, /*#__PURE__*/React.createElement("span", {
    style: {
      fontFamily: "var(--font-mono)",
      opacity: 0.65
    }
  }, i + 1), s))));
}
Object.assign(__ds_scope, { AnswerPanel });
})(); } catch (e) { __ds_ns.__errors.push({ path: "components/research/AnswerPanel.jsx", error: String((e && e.message) || e) }); }

// components/research/CitationCard.jsx
try { (() => {
const authorityTone = {
  binding: "binding",
  persuasive: "persuasive",
  secondary: "neutral"
};

/** A single search result: case name, citation line, held-passage excerpt, authority signal. */
function CitationCard({
  title,
  citation,
  court,
  year,
  authority = "binding",
  treatment,
  excerpt,
  matchTerms = [],
  onOpen,
  onSave,
  saved = false,
  style = {}
}) {
  const [hover, setHover] = React.useState(false);
  return /*#__PURE__*/React.createElement("article", {
    onMouseEnter: () => setHover(true),
    onMouseLeave: () => setHover(false),
    onClick: onOpen,
    style: {
      display: "flex",
      flexDirection: "column",
      gap: "var(--space-4)",
      padding: "var(--space-6) var(--space-7)",
      background: "var(--surface-card)",
      border: `1px solid ${hover ? "var(--apricot-300)" : "var(--border-hairline)"}`,
      borderRadius: "var(--radius-lg)",
      boxShadow: hover ? "var(--shadow-md)" : "var(--shadow-sm)",
      cursor: onOpen ? "pointer" : "default",
      fontFamily: "var(--font-sans)",
      transition: "box-shadow var(--dur-base) var(--ease-standard), border-color var(--dur-base) var(--ease-standard)",
      ...style
    }
  }, /*#__PURE__*/React.createElement("div", {
    style: {
      display: "flex",
      alignItems: "flex-start",
      gap: "var(--space-5)"
    }
  }, /*#__PURE__*/React.createElement("div", {
    style: {
      flex: 1,
      minWidth: 0
    }
  }, /*#__PURE__*/React.createElement("h3", {
    style: {
      fontFamily: "var(--font-display)",
      fontSize: "var(--text-h3-size)",
      lineHeight: "var(--text-h3-lh)",
      color: "var(--text-strong)",
      margin: 0
    }
  }, title), /*#__PURE__*/React.createElement("div", {
    style: {
      display: "flex",
      alignItems: "center",
      gap: "var(--space-3)",
      marginTop: "var(--space-2)",
      fontFamily: "var(--font-mono)",
      fontSize: "var(--text-cite-size)",
      color: "var(--text-muted)"
    }
  }, /*#__PURE__*/React.createElement("span", null, citation), court && /*#__PURE__*/React.createElement("span", {
    style: {
      color: "var(--text-faint)"
    }
  }, "\xB7"), court && /*#__PURE__*/React.createElement("span", null, court, year ? ` ${year}` : ""))), /*#__PURE__*/React.createElement("div", {
    style: {
      display: "flex",
      alignItems: "center",
      gap: "var(--space-3)"
    }
  }, /*#__PURE__*/React.createElement(__ds_scope.Badge, {
    tone: authorityTone[authority]
  }, authority[0].toUpperCase() + authority.slice(1)), treatment && /*#__PURE__*/React.createElement(__ds_scope.Badge, {
    tone: treatment === "Criticized" || treatment === "Overruled" ? "warn" : "ok"
  }, treatment), onSave && /*#__PURE__*/React.createElement(__ds_scope.IconButton, {
    icon: saved ? "bookmark-check" : "bookmark",
    label: saved ? "Saved" : "Save to matter",
    variant: "ghost",
    size: "sm",
    onClick: e => {
      e.stopPropagation();
      onSave();
    }
  }))), excerpt && /*#__PURE__*/React.createElement("p", {
    style: {
      margin: 0,
      paddingLeft: "var(--space-5)",
      borderLeft: "2px solid var(--apricot-300)",
      fontSize: "var(--text-body-size)",
      lineHeight: 1.62,
      color: "var(--text-body)",
      textWrap: "pretty"
    }
  }, excerpt), matchTerms.length > 0 && /*#__PURE__*/React.createElement("div", {
    style: {
      display: "flex",
      flexWrap: "wrap",
      gap: "var(--space-3)",
      alignItems: "center",
      fontSize: "var(--text-caption-size)",
      color: "var(--text-faint)"
    }
  }, /*#__PURE__*/React.createElement(__ds_scope.Icon, {
    name: "search",
    size: 12,
    color: "var(--text-faint)"
  }), matchTerms.map(t => /*#__PURE__*/React.createElement("span", {
    key: t,
    style: {
      padding: "1px var(--space-3)",
      background: "var(--apricot-50)",
      border: "1px solid var(--apricot-100)",
      borderRadius: "var(--radius-xs)",
      color: "var(--apricot-700)"
    }
  }, t))));
}
Object.assign(__ds_scope, { CitationCard });
})(); } catch (e) { __ds_ns.__errors.push({ path: "components/research/CitationCard.jsx", error: String((e && e.message) || e) }); }

// ui_kits/website/Hero.jsx
try { (() => {
const {
  Button,
  Icon,
  AnswerPanel,
  Badge
} = window.SvkBeslutsokDesignSystem_46c55d;
function Hero() {
  return /*#__PURE__*/React.createElement("section", {
    style: {
      background: "var(--gradient-wash)",
      borderBottom: "1px solid var(--apricot-200)"
    }
  }, /*#__PURE__*/React.createElement("div", {
    style: {
      maxWidth: "var(--content-max)",
      margin: "0 auto",
      padding: "var(--space-13) var(--space-8) var(--space-12)",
      display: "grid",
      gridTemplateColumns: "1.05fr 1fr",
      gap: "var(--space-11)",
      alignItems: "center"
    }
  }, /*#__PURE__*/React.createElement("div", {
    style: {
      display: "flex",
      flexDirection: "column",
      gap: "var(--space-6)"
    }
  }, /*#__PURE__*/React.createElement("span", {
    style: {
      fontSize: "var(--text-overline-size)",
      letterSpacing: "var(--text-overline-ls)",
      textTransform: "uppercase",
      fontWeight: 600,
      color: "var(--burgundy-600)"
    }
  }, "For litigation teams"), /*#__PURE__*/React.createElement("h1", {
    style: {
      fontFamily: "var(--font-display)",
      fontSize: 56,
      lineHeight: 1.04,
      letterSpacing: "-0.022em",
      color: "var(--text-strong)",
      margin: 0,
      maxWidth: "14ch"
    }
  }, "Legal research that cites itself"), /*#__PURE__*/React.createElement("p", {
    style: {
      fontSize: "var(--text-body-lg-size)",
      lineHeight: 1.62,
      color: "var(--text-body)",
      maxWidth: "48ch",
      margin: 0
    }
  }, "Ask a question the way you would ask a colleague. Svk Beslutsök answers with the cases, statutes and passages behind every sentence, so the check takes minutes instead of an afternoon."), /*#__PURE__*/React.createElement("div", {
    style: {
      display: "flex",
      gap: "var(--space-4)",
      marginTop: "var(--space-2)"
    }
  }, /*#__PURE__*/React.createElement(Button, {
    size: "lg"
  }, "Book a demo"), /*#__PURE__*/React.createElement(Button, {
    size: "lg",
    variant: "secondary",
    iconLeft: /*#__PURE__*/React.createElement(Icon, {
      name: "play",
      size: 16
    })
  }, "Watch the 3-minute tour")), /*#__PURE__*/React.createElement("div", {
    style: {
      display: "flex",
      alignItems: "center",
      gap: "var(--space-5)",
      marginTop: "var(--space-4)",
      fontSize: "var(--text-small-size)",
      color: "var(--text-muted)"
    }
  }, /*#__PURE__*/React.createElement("span", null, "Federal and all 50 states"), /*#__PURE__*/React.createElement("span", {
    style: {
      color: "var(--apricot-300)"
    }
  }, "\xB7"), /*#__PURE__*/React.createElement("span", null, "SOC 2 Type II"), /*#__PURE__*/React.createElement("span", {
    style: {
      color: "var(--apricot-300)"
    }
  }, "\xB7"), /*#__PURE__*/React.createElement("span", null, "No client data used for training"))), /*#__PURE__*/React.createElement("div", {
    style: {
      background: "var(--surface-card)",
      border: "1px solid var(--apricot-200)",
      borderRadius: "var(--radius-xl)",
      boxShadow: "var(--shadow-lg)",
      padding: "var(--space-6)",
      display: "flex",
      flexDirection: "column",
      gap: "var(--space-5)"
    }
  }, /*#__PURE__*/React.createElement("div", {
    style: {
      display: "flex",
      alignItems: "center",
      gap: "var(--space-4)",
      padding: "var(--space-4) var(--space-5)",
      border: "1px solid var(--border-hairline)",
      borderRadius: "var(--radius-pill)",
      color: "var(--text-muted)",
      fontSize: "var(--text-body-size)"
    }
  }, /*#__PURE__*/React.createElement(Icon, {
    name: "search",
    size: 17,
    color: "var(--burgundy-600)"
  }), "Does a carrier owe a duty to a downstream consignee?"), /*#__PURE__*/React.createElement(AnswerPanel, {
    status: "Research summary",
    answer: /*#__PURE__*/React.createElement("p", {
      style: {
        margin: 0,
        fontSize: "var(--text-body-size)"
      }
    }, "In the Ninth Circuit the duty runs past the named consignee where the delivery chain was foreseeable. The Sixth Circuit disagrees where a tariff fixes the risk."),
    sources: ["812 F.3d 1044", "49 U.S.C. § 14706"],
    style: {
      padding: "var(--space-6)"
    }
  }), /*#__PURE__*/React.createElement("div", {
    style: {
      display: "flex",
      gap: "var(--space-3)"
    }
  }, /*#__PURE__*/React.createElement(Badge, {
    tone: "binding"
  }, "2 binding"), /*#__PURE__*/React.createElement(Badge, {
    tone: "persuasive"
  }, "2 persuasive"), /*#__PURE__*/React.createElement(Badge, {
    tone: "warn"
  }, "1 criticized")))));
}
window.Hero = Hero;
})(); } catch (e) { __ds_ns.__errors.push({ path: "ui_kits/website/Hero.jsx", error: String((e && e.message) || e) }); }

// ui_kits/website/Sections.jsx
try { (() => {
const {
  Card,
  Icon,
  Button
} = window.SvkBeslutsokDesignSystem_46c55d;
const FEATURES = [{
  icon: "quote",
  title: "Every sentence sourced",
  body: "Answers are assembled from passages, not paraphrase. Click any clause to land on the paragraph it came from."
}, {
  icon: "scale",
  title: "Authority, ranked honestly",
  body: "Binding, persuasive and secondary are separated on the page, with subsequent history flagged before you cite."
}, {
  icon: "folder",
  title: "Work lives in the matter",
  body: "Save authorities as you go and export a memo that already carries the passages and the citations."
}];
const STEPS = [["Ask", "Plain language or a citation. Scope to a court and a date range."], ["Read", "A summary with numbered sources, then the authorities in weight order."], ["File", "Save what matters and export a memo in Word, PDF or a Bluebook list."]];
function Sections() {
  return /*#__PURE__*/React.createElement(React.Fragment, null, /*#__PURE__*/React.createElement("section", {
    style: {
      maxWidth: "var(--content-max)",
      margin: "0 auto",
      padding: "var(--space-12) var(--space-8)",
      display: "flex",
      flexDirection: "column",
      gap: "var(--space-9)"
    }
  }, /*#__PURE__*/React.createElement("div", {
    style: {
      display: "flex",
      flexDirection: "column",
      gap: "var(--space-4)",
      maxWidth: "56ch"
    }
  }, /*#__PURE__*/React.createElement("span", {
    style: {
      fontSize: "var(--text-overline-size)",
      letterSpacing: "var(--text-overline-ls)",
      textTransform: "uppercase",
      fontWeight: 600,
      color: "var(--burgundy-600)"
    }
  }, "What you get"), /*#__PURE__*/React.createElement("h2", {
    style: {
      fontFamily: "var(--font-display)",
      fontSize: "var(--text-h1-size)",
      lineHeight: "var(--text-h1-lh)",
      letterSpacing: "var(--text-h1-ls)",
      color: "var(--text-strong)",
      margin: 0
    }
  }, "Built for the part of the job that has to be right")), /*#__PURE__*/React.createElement("div", {
    style: {
      display: "grid",
      gridTemplateColumns: "repeat(3, 1fr)",
      gap: "var(--space-6)"
    }
  }, FEATURES.map(f => /*#__PURE__*/React.createElement(Card, {
    key: f.title,
    padding: "var(--space-8)"
  }, /*#__PURE__*/React.createElement("div", {
    style: {
      display: "flex",
      flexDirection: "column",
      gap: "var(--space-4)"
    }
  }, /*#__PURE__*/React.createElement("span", {
    style: {
      width: 38,
      height: 38,
      borderRadius: "var(--radius-md)",
      background: "var(--apricot-50)",
      border: "1px solid var(--apricot-200)",
      display: "grid",
      placeItems: "center"
    }
  }, /*#__PURE__*/React.createElement(Icon, {
    name: f.icon,
    size: 18,
    color: "var(--burgundy-600)"
  })), /*#__PURE__*/React.createElement("h3", {
    style: {
      fontFamily: "var(--font-display)",
      fontSize: "var(--text-h3-size)",
      color: "var(--text-strong)",
      margin: 0
    }
  }, f.title), /*#__PURE__*/React.createElement("p", {
    style: {
      margin: 0,
      fontSize: "var(--text-body-size)",
      lineHeight: 1.6,
      color: "var(--text-muted)",
      textWrap: "pretty"
    }
  }, f.body)))))), /*#__PURE__*/React.createElement("section", {
    style: {
      background: "var(--warm-50)",
      borderTop: "1px solid var(--border-hairline)",
      borderBottom: "1px solid var(--border-hairline)"
    }
  }, /*#__PURE__*/React.createElement("div", {
    style: {
      maxWidth: "var(--content-max)",
      margin: "0 auto",
      padding: "var(--space-12) var(--space-8)",
      display: "grid",
      gridTemplateColumns: "repeat(3, 1fr)",
      gap: "var(--space-9)"
    }
  }, STEPS.map(([t, b], i) => /*#__PURE__*/React.createElement("div", {
    key: t,
    style: {
      display: "flex",
      flexDirection: "column",
      gap: "var(--space-4)"
    }
  }, /*#__PURE__*/React.createElement("span", {
    style: {
      fontFamily: "var(--font-mono)",
      fontSize: "var(--text-caption-size)",
      color: "var(--apricot-600)"
    }
  }, "0", i + 1), /*#__PURE__*/React.createElement("div", {
    style: {
      height: 3,
      background: "var(--gradient-rule)",
      borderRadius: 2
    }
  }), /*#__PURE__*/React.createElement("h3", {
    style: {
      fontFamily: "var(--font-display)",
      fontSize: "var(--text-h2-size)",
      color: "var(--text-strong)",
      margin: 0
    }
  }, t), /*#__PURE__*/React.createElement("p", {
    style: {
      margin: 0,
      fontSize: "var(--text-body-size)",
      lineHeight: 1.6,
      color: "var(--text-muted)"
    }
  }, b))))), /*#__PURE__*/React.createElement("section", {
    style: {
      maxWidth: "var(--content-max)",
      margin: "0 auto",
      padding: "var(--space-12) var(--space-8)"
    }
  }, /*#__PURE__*/React.createElement("div", {
    style: {
      background: "var(--gradient-authority)",
      borderRadius: "var(--radius-xl)",
      padding: "var(--space-11) var(--space-10)",
      display: "flex",
      alignItems: "center",
      gap: "var(--space-9)"
    }
  }, /*#__PURE__*/React.createElement("div", {
    style: {
      flex: 1,
      display: "flex",
      flexDirection: "column",
      gap: "var(--space-5)"
    }
  }, /*#__PURE__*/React.createElement("blockquote", {
    style: {
      margin: 0,
      fontFamily: "var(--font-display)",
      fontSize: 30,
      lineHeight: 1.28,
      letterSpacing: "-0.01em",
      color: "var(--apricot-100)",
      maxWidth: "26ch"
    }
  }, "The associates stopped starting from a blank page. The citations were already there."), /*#__PURE__*/React.createElement("span", {
    style: {
      fontSize: "var(--text-small-size)",
      color: "var(--apricot-200)"
    }
  }, "Partner, 40-attorney litigation firm")), /*#__PURE__*/React.createElement("div", {
    style: {
      flex: "none",
      display: "flex",
      flexDirection: "column",
      gap: "var(--space-4)"
    }
  }, /*#__PURE__*/React.createElement(Button, {
    size: "lg",
    variant: "accent"
  }, "Book a demo"), /*#__PURE__*/React.createElement(Button, {
    size: "lg",
    variant: "ghost",
    style: {
      color: "var(--apricot-200)"
    }
  }, "Talk to sales")))), /*#__PURE__*/React.createElement("footer", {
    style: {
      borderTop: "1px solid var(--border-hairline)",
      background: "var(--warm-25)"
    }
  }, /*#__PURE__*/React.createElement("div", {
    style: {
      maxWidth: "var(--content-max)",
      margin: "0 auto",
      padding: "var(--space-10) var(--space-8)",
      display: "grid",
      gridTemplateColumns: "1.4fr repeat(3, 1fr)",
      gap: "var(--space-8)"
    }
  }, /*#__PURE__*/React.createElement("div", {
    style: {
      display: "flex",
      flexDirection: "column",
      gap: "var(--space-4)"
    }
  }, /*#__PURE__*/React.createElement("span", {
    style: {
      fontFamily: "var(--font-display)",
      fontSize: 22,
      letterSpacing: "-0.02em",
      color: "var(--burgundy-600)"
    }
  }, "Svk Beslutsök"), /*#__PURE__*/React.createElement("p", {
    style: {
      margin: 0,
      fontSize: "var(--text-small-size)",
      color: "var(--text-muted)",
      maxWidth: "34ch"
    }
  }, "Legal research that cites itself. Not a substitute for professional judgment.")), [["Product", ["Search", "Matters", "Memos", "Coverage"]], ["Company", ["About", "Careers", "Contact"]], ["Legal", ["Terms", "Privacy", "Security"]]].map(([h, items]) => /*#__PURE__*/React.createElement("div", {
    key: h,
    style: {
      display: "flex",
      flexDirection: "column",
      gap: "var(--space-4)"
    }
  }, /*#__PURE__*/React.createElement("span", {
    style: {
      fontSize: "var(--text-overline-size)",
      letterSpacing: "var(--text-overline-ls)",
      textTransform: "uppercase",
      fontWeight: 600,
      color: "var(--text-faint)"
    }
  }, h), items.map(i => /*#__PURE__*/React.createElement("a", {
    key: i,
    href: "#",
    style: {
      fontSize: "var(--text-small-size)",
      color: "var(--text-body)",
      textDecoration: "none"
    }
  }, i)))))));
}
window.Sections = Sections;
})(); } catch (e) { __ds_ns.__errors.push({ path: "ui_kits/website/Sections.jsx", error: String((e && e.message) || e) }); }

// ui_kits/website/SiteHeader.jsx
try { (() => {
const {
  Button,
  Icon
} = window.SvkBeslutsokDesignSystem_46c55d;
function SiteHeader() {
  const links = ["Product", "Coverage", "Security", "Pricing"];
  return /*#__PURE__*/React.createElement("header", {
    style: {
      position: "sticky",
      top: 0,
      zIndex: 30,
      backdropFilter: "blur(8px)",
      background: "rgba(255,255,255,0.82)",
      borderBottom: "1px solid var(--border-hairline)"
    }
  }, /*#__PURE__*/React.createElement("div", {
    style: {
      maxWidth: "var(--content-max)",
      margin: "0 auto",
      height: 68,
      padding: "0 var(--space-8)",
      display: "flex",
      alignItems: "center",
      gap: "var(--space-8)"
    }
  }, /*#__PURE__*/React.createElement("span", {
    style: {
      fontFamily: "var(--font-display)",
      fontSize: 24,
      letterSpacing: "-0.02em",
      color: "var(--burgundy-600)"
    }
  }, "Svk Beslutsök"), /*#__PURE__*/React.createElement("nav", {
    style: {
      display: "flex",
      gap: "var(--space-7)"
    }
  }, links.map(l => /*#__PURE__*/React.createElement("a", {
    key: l,
    href: "#",
    style: {
      fontSize: "var(--text-body-size)",
      color: "var(--text-body)",
      textDecoration: "none"
    }
  }, l))), /*#__PURE__*/React.createElement("div", {
    style: {
      flex: 1
    }
  }), /*#__PURE__*/React.createElement("a", {
    href: "#",
    style: {
      fontSize: "var(--text-body-size)",
      color: "var(--text-body)",
      textDecoration: "none"
    }
  }, "Sign in"), /*#__PURE__*/React.createElement(Button, {
    variant: "primary",
    size: "sm",
    iconRight: /*#__PURE__*/React.createElement(Icon, {
      name: "arrow-right",
      size: 15
    })
  }, "Book a demo")));
}
window.SiteHeader = SiteHeader;
})(); } catch (e) { __ds_ns.__errors.push({ path: "ui_kits/website/SiteHeader.jsx", error: String((e && e.message) || e) }); }

// ui_kits/workspace/AppShell.jsx
try { (() => {
const {
  SidebarNav,
  Button,
  IconButton,
  Icon,
  Toast,
  Dialog
} = window.SvkBeslutsokDesignSystem_46c55d;
function TopBar({
  view,
  onHome,
  matter
}) {
  return /*#__PURE__*/React.createElement("header", {
    style: {
      display: "flex",
      alignItems: "center",
      gap: "var(--space-5)",
      height: 56,
      padding: "0 var(--space-7)",
      background: "var(--surface-card)",
      borderBottom: "1px solid var(--border-hairline)",
      flex: "none"
    }
  }, /*#__PURE__*/React.createElement("button", {
    onClick: onHome,
    style: {
      border: "none",
      background: "transparent",
      cursor: "pointer",
      padding: 0,
      fontFamily: "var(--font-display)",
      fontSize: 22,
      letterSpacing: "-0.02em",
      color: "var(--burgundy-600)"
    }
  }, "Svk Beslutsök"), /*#__PURE__*/React.createElement("div", {
    style: {
      width: 1,
      height: 22,
      background: "var(--border-hairline)"
    }
  }), /*#__PURE__*/React.createElement("span", {
    style: {
      fontSize: "var(--text-small-size)",
      color: "var(--text-muted)"
    }
  }, matter), /*#__PURE__*/React.createElement("div", {
    style: {
      flex: 1
    }
  }), /*#__PURE__*/React.createElement(IconButton, {
    icon: "history",
    label: "Search history",
    variant: "ghost"
  }), /*#__PURE__*/React.createElement(IconButton, {
    icon: "circle-help",
    label: "Help",
    variant: "ghost"
  }), /*#__PURE__*/React.createElement("span", {
    style: {
      width: 30,
      height: 30,
      borderRadius: "var(--radius-pill)",
      background: "var(--apricot-200)",
      color: "var(--burgundy-700)",
      display: "grid",
      placeItems: "center",
      fontSize: 12,
      fontWeight: 600
    }
  }, "RM"));
}
function AppShell() {
  const [view, setView] = React.useState("home");
  const [nav, setNav] = React.useState("novak");
  const [query, setQuery] = React.useState("");
  const [doc, setDoc] = React.useState(null);
  const [saved, setSaved] = React.useState(["novak"]);
  const [toast, setToast] = React.useState(null);
  const [exporting, setExporting] = React.useState(false);
  const run = q => {
    setQuery(q);
    setView("results");
  };
  const toggleSave = id => {
    setSaved(s => s.includes(id) ? s.filter(x => x !== id) : [...s, id]);
    setToast(saved.includes(id) ? null : {
      title: "Saved to Novak v. Harrow",
      message: "1 authority added to the matter."
    });
    setTimeout(() => setToast(null), 2600);
  };
  return /*#__PURE__*/React.createElement("div", {
    style: {
      display: "flex",
      flexDirection: "column",
      height: "100%",
      fontFamily: "var(--font-sans)"
    }
  }, /*#__PURE__*/React.createElement(TopBar, {
    onHome: () => setView("home"),
    matter: "Novak v. Harrow \xB7 Litigation"
  }), /*#__PURE__*/React.createElement("div", {
    style: {
      display: "flex",
      flex: 1,
      minHeight: 0
    }
  }, /*#__PURE__*/React.createElement(SidebarNav, {
    title: "Workspace",
    value: nav,
    onChange: v => {
      setNav(v);
      setView(v === "history" ? "home" : "matter");
    },
    items: [...MATTERS, {
      value: "history",
      label: "Search history",
      icon: "history"
    }, {
      value: "library",
      label: "Saved authorities",
      icon: "bookmark",
      count: saved.length
    }],
    footer: /*#__PURE__*/React.createElement(Button, {
      variant: "secondary",
      size: "sm",
      fullWidth: true,
      iconLeft: /*#__PURE__*/React.createElement(Icon, {
        name: "plus",
        size: 14
      })
    }, "New matter")
  }), /*#__PURE__*/React.createElement("main", {
    style: {
      flex: 1,
      minWidth: 0,
      overflow: "auto",
      background: "var(--warm-50)"
    }
  }, view === "home" && /*#__PURE__*/React.createElement(SearchHome, {
    onSearch: run
  }), view === "results" && /*#__PURE__*/React.createElement(ResultsView, {
    query: query,
    onSearch: run,
    saved: saved,
    onSave: toggleSave,
    onOpen: r => {
      setDoc(r);
      setView("doc");
    }
  }), view === "doc" && /*#__PURE__*/React.createElement(DocumentView, {
    result: doc,
    onBack: () => setView("results"),
    saved: saved.includes(doc?.id),
    onSave: () => toggleSave(doc.id)
  }), view === "matter" && /*#__PURE__*/React.createElement(MatterView, {
    saved: saved,
    onExport: () => setExporting(true),
    onOpen: r => {
      setDoc(r);
      setView("doc");
    }
  }))), toast && /*#__PURE__*/React.createElement("div", {
    style: {
      position: "fixed",
      right: 24,
      bottom: 24,
      zIndex: 50
    }
  }, /*#__PURE__*/React.createElement(Toast, {
    tone: "ok",
    title: toast.title,
    message: toast.message,
    onDismiss: () => setToast(null)
  })), /*#__PURE__*/React.createElement(Dialog, {
    open: exporting,
    onClose: () => setExporting(false),
    title: "Export research memo",
    description: "Includes the summary, every saved authority and its held passage, formatted for filing.",
    footer: /*#__PURE__*/React.createElement(React.Fragment, null, /*#__PURE__*/React.createElement(Button, {
      variant: "secondary",
      onClick: () => setExporting(false)
    }, "Cancel"), /*#__PURE__*/React.createElement(Button, {
      onClick: () => {
        setExporting(false);
        setToast({
          title: "Memo exported",
          message: "Novak-v-Harrow-memo.docx"
        });
        setTimeout(() => setToast(null), 2600);
      }
    }, "Export"))
  }, /*#__PURE__*/React.createElement("div", {
    style: {
      display: "flex",
      flexDirection: "column",
      gap: "var(--space-4)"
    }
  }, ["Word (.docx)", "PDF", "Copy as Bluebook list"].map((o, i) => /*#__PURE__*/React.createElement("label", {
    key: o,
    style: {
      display: "flex",
      gap: "var(--space-4)",
      alignItems: "center",
      padding: "var(--space-4) var(--space-5)",
      border: `1px solid ${i === 0 ? "var(--apricot-300)" : "var(--border-hairline)"}`,
      background: i === 0 ? "var(--apricot-50)" : "var(--surface-card)",
      borderRadius: "var(--radius-md)",
      cursor: "pointer",
      fontSize: "var(--text-body-size)",
      color: "var(--text-strong)"
    }
  }, /*#__PURE__*/React.createElement("input", {
    type: "radio",
    name: "fmt",
    defaultChecked: i === 0
  }), o)))));
}
window.AppShell = AppShell;
})(); } catch (e) { __ds_ns.__errors.push({ path: "ui_kits/workspace/AppShell.jsx", error: String((e && e.message) || e) }); }

// ui_kits/workspace/DocumentView.jsx
try { (() => {
const {
  Button,
  IconButton,
  Badge,
  Card,
  Icon,
  Tabs,
  Tooltip
} = window.SvkBeslutsokDesignSystem_46c55d;
const BODY = ["Harrow Logistics contracted with Meridian Foods to move refrigerated produce from Fresno to Portland. The bill of lading named Meridian's Portland warehouse as consignee. Harrow's dispatch records show the load was scheduled for transfer to Novak Provisions the same afternoon.", "A carrier that accepts goods for delivery assumes a duty of reasonable care toward every party it knows will take possession downstream, not merely the consignee named on the bill of lading. The district court's contrary reading would leave a foreseeable plaintiff without recourse whenever a shipper's paperwork lags its practice.", "We do not disturb the rule that claims for loss or damage occurring in transit are preempted by the Carmack Amendment. The duty we recognize today is narrower: it governs the carrier's conduct toward known downstream recipients, and it does not create a parallel remedy for cargo loss."];
function DocumentView({
  result,
  onBack,
  saved,
  onSave
}) {
  const [tab, setTab] = React.useState("opinion");
  if (!result) return null;
  return /*#__PURE__*/React.createElement("div", {
    style: {
      maxWidth: 1180,
      margin: "0 auto",
      padding: "var(--space-8)",
      display: "flex",
      flexDirection: "column",
      gap: "var(--space-6)"
    }
  }, /*#__PURE__*/React.createElement("div", {
    style: {
      display: "flex",
      alignItems: "center",
      gap: "var(--space-4)"
    }
  }, /*#__PURE__*/React.createElement(Button, {
    variant: "ghost",
    size: "sm",
    iconLeft: /*#__PURE__*/React.createElement(Icon, {
      name: "arrow-left",
      size: 15
    }),
    onClick: onBack
  }, "Back to results"), /*#__PURE__*/React.createElement("div", {
    style: {
      flex: 1
    }
  }), /*#__PURE__*/React.createElement(Tooltip, {
    label: "Copy Bluebook citation"
  }, /*#__PURE__*/React.createElement(IconButton, {
    icon: "quote",
    label: "Copy citation"
  })), /*#__PURE__*/React.createElement(IconButton, {
    icon: "link-2",
    label: "Copy link"
  }), /*#__PURE__*/React.createElement(Button, {
    variant: saved ? "accent" : "secondary",
    size: "sm",
    iconLeft: /*#__PURE__*/React.createElement(Icon, {
      name: saved ? "bookmark-check" : "bookmark",
      size: 15
    }),
    onClick: onSave
  }, saved ? "Saved" : "Save to matter")), /*#__PURE__*/React.createElement("div", {
    style: {
      display: "flex",
      gap: "var(--space-8)",
      alignItems: "flex-start"
    }
  }, /*#__PURE__*/React.createElement("article", {
    style: {
      flex: 1,
      minWidth: 0,
      background: "var(--surface-card)",
      border: "1px solid var(--border-hairline)",
      borderRadius: "var(--radius-lg)",
      boxShadow: "var(--shadow-sm)",
      padding: "var(--space-9) var(--space-10)"
    }
  }, /*#__PURE__*/React.createElement("div", {
    style: {
      display: "flex",
      alignItems: "center",
      gap: "var(--space-3)",
      marginBottom: "var(--space-4)"
    }
  }, /*#__PURE__*/React.createElement(Badge, {
    tone: result.authority === "binding" ? "binding" : result.authority === "persuasive" ? "persuasive" : "neutral"
  }, result.authority[0].toUpperCase() + result.authority.slice(1)), result.treatment && /*#__PURE__*/React.createElement(Badge, {
    tone: result.treatment === "Followed" ? "ok" : "warn"
  }, result.treatment)), /*#__PURE__*/React.createElement("h1", {
    style: {
      fontFamily: "var(--font-display)",
      fontSize: "var(--text-h1-size)",
      lineHeight: "var(--text-h1-lh)",
      letterSpacing: "var(--text-h1-ls)",
      color: "var(--text-strong)",
      margin: 0
    }
  }, result.title), /*#__PURE__*/React.createElement("div", {
    style: {
      fontFamily: "var(--font-mono)",
      fontSize: "var(--text-cite-size)",
      color: "var(--text-muted)",
      marginTop: "var(--space-3)"
    }
  }, result.citation, result.court ? ` · ${result.court} ${result.year}` : ""), /*#__PURE__*/React.createElement("div", {
    style: {
      height: 3,
      background: "var(--gradient-rule)",
      borderRadius: 2,
      margin: "var(--space-6) 0"
    }
  }), /*#__PURE__*/React.createElement(Tabs, {
    value: tab,
    onChange: setTab,
    tabs: [{
      value: "opinion",
      label: "Opinion"
    }, {
      value: "history",
      label: "Subsequent history"
    }, {
      value: "citing",
      label: "Citing references",
      count: 143
    }],
    style: {
      marginBottom: "var(--space-6)"
    }
  }), /*#__PURE__*/React.createElement("div", {
    style: {
      display: "flex",
      flexDirection: "column",
      gap: "var(--space-5)",
      maxWidth: "var(--measure-prose)"
    }
  }, BODY.map((p, i) => /*#__PURE__*/React.createElement("p", {
    key: i,
    style: {
      fontSize: "var(--text-body-lg-size)",
      lineHeight: 1.68,
      color: "var(--text-body)",
      textWrap: "pretty",
      background: i === 1 ? "var(--apricot-50)" : "transparent",
      boxShadow: i === 1 ? "0 0 0 6px var(--apricot-50)" : "none",
      borderRadius: i === 1 ? 2 : 0
    }
  }, p)))), /*#__PURE__*/React.createElement("aside", {
    style: {
      width: 288,
      flex: "none",
      display: "flex",
      flexDirection: "column",
      gap: "var(--space-5)"
    }
  }, /*#__PURE__*/React.createElement(Card, {
    padding: "var(--space-6)",
    header: "Why this matched"
  }, /*#__PURE__*/React.createElement("p", {
    style: {
      fontSize: "var(--text-small-size)",
      lineHeight: 1.55,
      color: "var(--text-body)",
      margin: 0
    }
  }, "Holding paragraph states the duty extends beyond the named consignee \u2014 directly on point for the question asked.")), /*#__PURE__*/React.createElement(Card, {
    padding: "var(--space-6)",
    header: "Cited by (143)"
  }, /*#__PURE__*/React.createElement("div", {
    style: {
      display: "flex",
      flexDirection: "column",
      gap: "var(--space-5)"
    }
  }, [["Delgado Bros. Trucking", "2019 WL 3821194", "Followed"], ["Marchand Produce Co.", "704 F. App'x 512", "Criticized"], ["Pacific Cold Storage", "2021 WL 118844", "Followed"]].map(([n, c, t]) => /*#__PURE__*/React.createElement("div", {
    key: n,
    style: {
      display: "flex",
      flexDirection: "column",
      gap: 3
    }
  }, /*#__PURE__*/React.createElement("span", {
    style: {
      fontSize: "var(--text-small-size)",
      fontWeight: 600,
      color: "var(--text-strong)"
    }
  }, n), /*#__PURE__*/React.createElement("span", {
    style: {
      fontFamily: "var(--font-mono)",
      fontSize: "var(--text-caption-size)",
      color: "var(--text-muted)"
    }
  }, c), /*#__PURE__*/React.createElement(Badge, {
    tone: t === "Followed" ? "ok" : "warn",
    style: {
      alignSelf: "flex-start",
      marginTop: 3
    }
  }, t))))))));
}
window.DocumentView = DocumentView;
})(); } catch (e) { __ds_ns.__errors.push({ path: "ui_kits/workspace/DocumentView.jsx", error: String((e && e.message) || e) }); }

// ui_kits/workspace/MatterView.jsx
try { (() => {
function _extends() { return _extends = Object.assign ? Object.assign.bind() : function (n) { for (var e = 1; e < arguments.length; e++) { var t = arguments[e]; for (var r in t) ({}).hasOwnProperty.call(t, r) && (n[r] = t[r]); } return n; }, _extends.apply(null, arguments); }
const {
  Button,
  Card,
  CitationCard,
  Icon,
  Badge,
  Tabs
} = window.SvkBeslutsokDesignSystem_46c55d;
function MatterView({
  saved,
  onExport,
  onOpen
}) {
  const [tab, setTab] = React.useState("authorities");
  const items = RESULTS.filter(r => saved.includes(r.id));
  return /*#__PURE__*/React.createElement("div", {
    style: {
      maxWidth: 1180,
      margin: "0 auto",
      padding: "var(--space-8)",
      display: "flex",
      flexDirection: "column",
      gap: "var(--space-7)"
    }
  }, /*#__PURE__*/React.createElement("div", {
    style: {
      display: "flex",
      alignItems: "flex-end",
      gap: "var(--space-6)"
    }
  }, /*#__PURE__*/React.createElement("div", {
    style: {
      flex: 1,
      display: "flex",
      flexDirection: "column",
      gap: "var(--space-3)"
    }
  }, /*#__PURE__*/React.createElement("span", {
    style: {
      fontSize: "var(--text-overline-size)",
      letterSpacing: "var(--text-overline-ls)",
      textTransform: "uppercase",
      fontWeight: 600,
      color: "var(--text-faint)"
    }
  }, "Matter"), /*#__PURE__*/React.createElement("h1", {
    style: {
      fontFamily: "var(--font-display)",
      fontSize: "var(--text-h1-size)",
      lineHeight: "var(--text-h1-lh)",
      letterSpacing: "var(--text-h1-ls)",
      color: "var(--text-strong)",
      margin: 0
    }
  }, "Novak v. Harrow Logistics"), /*#__PURE__*/React.createElement("div", {
    style: {
      display: "flex",
      gap: "var(--space-4)",
      fontSize: "var(--text-small-size)",
      color: "var(--text-muted)"
    }
  }, /*#__PURE__*/React.createElement("span", null, "Opened 14 Mar"), /*#__PURE__*/React.createElement("span", null, "\xB7"), /*#__PURE__*/React.createElement("span", null, "R. Mahoney, lead"), /*#__PURE__*/React.createElement("span", null, "\xB7"), /*#__PURE__*/React.createElement("span", null, items.length, " saved authorities"))), /*#__PURE__*/React.createElement(Button, {
    variant: "secondary",
    iconLeft: /*#__PURE__*/React.createElement(Icon, {
      name: "download",
      size: 16
    }),
    onClick: onExport
  }, "Export memo")), /*#__PURE__*/React.createElement(Tabs, {
    value: tab,
    onChange: setTab,
    tabs: [{
      value: "authorities",
      label: "Authorities",
      count: items.length
    }, {
      value: "notes",
      label: "Notes"
    }, {
      value: "team",
      label: "Team"
    }]
  }), tab === "authorities" && /*#__PURE__*/React.createElement("div", {
    style: {
      display: "flex",
      gap: "var(--space-8)",
      alignItems: "flex-start"
    }
  }, /*#__PURE__*/React.createElement("div", {
    style: {
      flex: 1,
      minWidth: 0,
      display: "flex",
      flexDirection: "column",
      gap: "var(--space-4)"
    }
  }, items.length === 0 ? /*#__PURE__*/React.createElement(Card, {
    tone: "accent"
  }, /*#__PURE__*/React.createElement("span", {
    style: {
      fontSize: "var(--text-body-size)",
      color: "var(--burgundy-700)"
    }
  }, "Nothing saved yet. Save an authority from any result to build the memo.")) : items.map(r => /*#__PURE__*/React.createElement(CitationCard, _extends({
    key: r.id
  }, r, {
    saved: true,
    onOpen: () => onOpen(r)
  })))), /*#__PURE__*/React.createElement("aside", {
    style: {
      width: 288,
      flex: "none",
      display: "flex",
      flexDirection: "column",
      gap: "var(--space-5)"
    }
  }, /*#__PURE__*/React.createElement(Card, {
    padding: "var(--space-6)",
    header: "Coverage"
  }, /*#__PURE__*/React.createElement("div", {
    style: {
      display: "flex",
      flexDirection: "column",
      gap: "var(--space-4)"
    }
  }, [["Binding", "binding", 2], ["Persuasive", "persuasive", 1], ["Secondary", "neutral", 1]].map(([l, t, n]) => /*#__PURE__*/React.createElement("div", {
    key: l,
    style: {
      display: "flex",
      alignItems: "center",
      gap: "var(--space-4)"
    }
  }, /*#__PURE__*/React.createElement(Badge, {
    tone: t
  }, l), /*#__PURE__*/React.createElement("span", {
    style: {
      marginLeft: "auto",
      fontFamily: "var(--font-mono)",
      fontSize: "var(--text-caption-size)",
      color: "var(--text-muted)"
    }
  }, n))))), /*#__PURE__*/React.createElement(Card, {
    padding: "var(--space-6)",
    tone: "wash"
  }, /*#__PURE__*/React.createElement("div", {
    style: {
      display: "flex",
      flexDirection: "column",
      gap: "var(--space-3)"
    }
  }, /*#__PURE__*/React.createElement("span", {
    style: {
      fontSize: "var(--text-small-size)",
      fontWeight: 600,
      color: "var(--burgundy-700)"
    }
  }, "Gap check"), /*#__PURE__*/React.createElement("p", {
    style: {
      margin: 0,
      fontSize: "var(--text-small-size)",
      lineHeight: 1.55,
      color: "var(--text-body)"
    }
  }, "No out-of-circuit contrary authority saved. Consider adding Ellery Freight before filing."))))), tab !== "authorities" && /*#__PURE__*/React.createElement(Card, null, /*#__PURE__*/React.createElement("span", {
    style: {
      fontSize: "var(--text-body-size)",
      color: "var(--text-muted)"
    }
  }, "Not part of the supplied source material \u2014 left intentionally blank.")));
}
window.MatterView = MatterView;
})(); } catch (e) { __ds_ns.__errors.push({ path: "ui_kits/workspace/MatterView.jsx", error: String((e && e.message) || e) }); }

// ui_kits/workspace/ResultsView.jsx
try { (() => {
function _extends() { return _extends = Object.assign ? Object.assign.bind() : function (n) { for (var e = 1; e < arguments.length; e++) { var t = arguments[e]; for (var r in t) ({}).hasOwnProperty.call(t, r) && (n[r] = t[r]); } return n; }, _extends.apply(null, arguments); }
const {
  SearchField,
  AnswerPanel,
  CitationCard,
  Tabs,
  Tag,
  Checkbox,
  Select,
  Card,
  Icon
} = window.SvkBeslutsokDesignSystem_46c55d;
function FilterRail() {
  const [binding, setBinding] = React.useState(true);
  const [unpub, setUnpub] = React.useState(false);
  return /*#__PURE__*/React.createElement("aside", {
    style: {
      width: 248,
      flex: "none",
      display: "flex",
      flexDirection: "column",
      gap: "var(--space-6)"
    }
  }, /*#__PURE__*/React.createElement(Card, {
    padding: "var(--space-6)"
  }, /*#__PURE__*/React.createElement("div", {
    style: {
      display: "flex",
      flexDirection: "column",
      gap: "var(--space-5)"
    }
  }, /*#__PURE__*/React.createElement("span", {
    style: {
      fontSize: "var(--text-overline-size)",
      letterSpacing: "var(--text-overline-ls)",
      textTransform: "uppercase",
      fontWeight: 600,
      color: "var(--text-faint)"
    }
  }, "Filters"), /*#__PURE__*/React.createElement(Select, {
    label: "Jurisdiction",
    size: "sm",
    options: ["9th Circuit", "All federal", "N.D. Cal."]
  }), /*#__PURE__*/React.createElement(Select, {
    label: "Date",
    size: "sm",
    options: ["2015 – present", "Last 3 years", "Any"]
  }), /*#__PURE__*/React.createElement(Checkbox, {
    label: "Binding only",
    checked: binding,
    onChange: setBinding
  }), /*#__PURE__*/React.createElement(Checkbox, {
    label: "Include unpublished",
    checked: unpub,
    onChange: setUnpub
  }))), /*#__PURE__*/React.createElement(Card, {
    padding: "var(--space-6)",
    tone: "accent"
  }, /*#__PURE__*/React.createElement("div", {
    style: {
      display: "flex",
      flexDirection: "column",
      gap: "var(--space-3)"
    }
  }, /*#__PURE__*/React.createElement("span", {
    style: {
      fontSize: "var(--text-small-size)",
      fontWeight: 600,
      color: "var(--burgundy-700)"
    }
  }, "Narrow by issue"), ["Duty of care", "Carmack preemption", "Tariff allocation"].map(t => /*#__PURE__*/React.createElement("button", {
    key: t,
    style: {
      textAlign: "left",
      border: "none",
      background: "transparent",
      padding: 0,
      cursor: "pointer",
      font: "inherit",
      fontSize: "var(--text-small-size)",
      color: "var(--burgundy-600)"
    }
  }, t)))));
}
function ResultsView({
  query,
  onSearch,
  saved,
  onSave,
  onOpen
}) {
  const [q, setQ] = React.useState(query);
  const [tab, setTab] = React.useState("all");
  React.useEffect(() => setQ(query), [query]);
  const shown = tab === "all" ? RESULTS : RESULTS.filter(r => tab === "cases" ? r.court && r.court !== "Statute" && r.court !== "Secondary" : tab === "statutes" ? r.court === "Statute" : r.court === "Secondary");
  return /*#__PURE__*/React.createElement("div", {
    style: {
      maxWidth: 1180,
      margin: "0 auto",
      padding: "var(--space-8)",
      display: "flex",
      flexDirection: "column",
      gap: "var(--space-7)"
    }
  }, /*#__PURE__*/React.createElement(SearchField, {
    value: q,
    onChange: setQ,
    onSubmit: onSearch,
    scope: "9th Cir. \xB7 2015\u2013present"
  }), /*#__PURE__*/React.createElement("div", {
    style: {
      display: "flex",
      gap: "var(--space-8)",
      alignItems: "flex-start"
    }
  }, /*#__PURE__*/React.createElement("div", {
    style: {
      flex: 1,
      minWidth: 0,
      display: "flex",
      flexDirection: "column",
      gap: "var(--space-6)"
    }
  }, /*#__PURE__*/React.createElement(AnswerPanel, {
    question: query,
    answer: /*#__PURE__*/React.createElement("p", {
      style: {
        margin: 0
      }
    }, ANSWER),
    sources: RESULTS.slice(0, 3).map(r => r.citation)
  }), /*#__PURE__*/React.createElement("div", {
    style: {
      display: "flex",
      alignItems: "center",
      gap: "var(--space-5)"
    }
  }, /*#__PURE__*/React.createElement(Tabs, {
    value: tab,
    onChange: setTab,
    style: {
      flex: 1
    },
    tabs: [{
      value: "all",
      label: "All",
      count: RESULTS.length
    }, {
      value: "cases",
      label: "Cases",
      count: 3
    }, {
      value: "statutes",
      label: "Statutes",
      count: 1
    }, {
      value: "secondary",
      label: "Secondary",
      count: 1
    }]
  })), /*#__PURE__*/React.createElement("div", {
    style: {
      display: "flex",
      flexWrap: "wrap",
      gap: "var(--space-3)"
    }
  }, /*#__PURE__*/React.createElement(Tag, {
    selected: true,
    onRemove: () => {}
  }, "9th Cir."), /*#__PURE__*/React.createElement(Tag, {
    selected: true,
    onRemove: () => {}
  }, "2015 \u2013 present"), /*#__PURE__*/React.createElement("span", {
    style: {
      marginLeft: "auto",
      fontSize: "var(--text-caption-size)",
      color: "var(--text-faint)",
      alignSelf: "center"
    }
  }, "Sorted by relevance")), /*#__PURE__*/React.createElement("div", {
    style: {
      display: "flex",
      flexDirection: "column",
      gap: "var(--space-4)"
    }
  }, shown.map(r => /*#__PURE__*/React.createElement(CitationCard, _extends({
    key: r.id
  }, r, {
    saved: saved.includes(r.id),
    onSave: () => onSave(r.id),
    onOpen: () => onOpen(r)
  }))))), /*#__PURE__*/React.createElement(FilterRail, null)));
}
window.ResultsView = ResultsView;
})(); } catch (e) { __ds_ns.__errors.push({ path: "ui_kits/workspace/ResultsView.jsx", error: String((e && e.message) || e) }); }

// ui_kits/workspace/SearchHome.jsx
try { (() => {
const {
  SearchField,
  Card,
  Icon,
  Tag
} = window.SvkBeslutsokDesignSystem_46c55d;
function SearchHome({
  onSearch
}) {
  const [q, setQ] = React.useState("");
  return /*#__PURE__*/React.createElement("div", {
    style: {
      minHeight: "100%",
      background: "var(--gradient-wash-soft)"
    }
  }, /*#__PURE__*/React.createElement("div", {
    style: {
      maxWidth: 860,
      margin: "0 auto",
      padding: "88px var(--space-8) var(--space-11)",
      display: "flex",
      flexDirection: "column",
      gap: "var(--space-8)"
    }
  }, /*#__PURE__*/React.createElement("div", {
    style: {
      display: "flex",
      flexDirection: "column",
      gap: "var(--space-4)"
    }
  }, /*#__PURE__*/React.createElement("span", {
    style: {
      fontSize: "var(--text-overline-size)",
      letterSpacing: "var(--text-overline-ls)",
      textTransform: "uppercase",
      fontWeight: 600,
      color: "var(--burgundy-600)"
    }
  }, "Novak v. Harrow \xB7 Litigation"), /*#__PURE__*/React.createElement("h1", {
    style: {
      fontFamily: "var(--font-display)",
      fontSize: 44,
      lineHeight: 1.08,
      letterSpacing: "-0.02em",
      color: "var(--text-strong)",
      margin: 0
    }
  }, "What do you need to find?"), /*#__PURE__*/React.createElement("p", {
    style: {
      fontSize: "var(--text-body-lg-size)",
      lineHeight: 1.6,
      color: "var(--text-muted)",
      maxWidth: "var(--measure-prose)"
    }
  }, "Ask in plain language or paste a citation. Every answer comes back with the authorities it rests on.")), /*#__PURE__*/React.createElement(SearchField, {
    value: q,
    onChange: setQ,
    onSubmit: () => onSearch(q || SUGGESTED[0]),
    scope: "9th Cir. \xB7 2015\u2013present"
  }), /*#__PURE__*/React.createElement("div", {
    style: {
      display: "flex",
      flexDirection: "column",
      gap: "var(--space-4)"
    }
  }, /*#__PURE__*/React.createElement("span", {
    style: {
      fontSize: "var(--text-small-size)",
      color: "var(--text-muted)"
    }
  }, "Try one of these"), /*#__PURE__*/React.createElement("div", {
    style: {
      display: "flex",
      flexWrap: "wrap",
      gap: "var(--space-3)"
    }
  }, SUGGESTED.map(s => /*#__PURE__*/React.createElement(Tag, {
    key: s,
    onClick: () => onSearch(s)
  }, s)))), /*#__PURE__*/React.createElement(Card, {
    header: "Recent searches",
    padding: "0"
  }, /*#__PURE__*/React.createElement("div", {
    style: {
      display: "flex",
      flexDirection: "column"
    }
  }, HISTORY.map((h, i) => /*#__PURE__*/React.createElement("button", {
    key: h.q,
    onClick: () => onSearch(h.q),
    style: {
      display: "flex",
      alignItems: "center",
      gap: "var(--space-5)",
      padding: "var(--space-5) var(--space-7)",
      border: "none",
      borderTop: i ? "1px solid var(--border-hairline)" : "none",
      background: "transparent",
      cursor: "pointer",
      textAlign: "left",
      font: "inherit"
    }
  }, /*#__PURE__*/React.createElement(Icon, {
    name: "history",
    size: 16,
    color: "var(--text-faint)"
  }), /*#__PURE__*/React.createElement("span", {
    style: {
      flex: 1,
      fontSize: "var(--text-body-size)",
      color: "var(--text-strong)"
    }
  }, h.q), /*#__PURE__*/React.createElement("span", {
    style: {
      fontSize: "var(--text-caption-size)",
      color: "var(--text-faint)"
    }
  }, h.n, " results"), /*#__PURE__*/React.createElement("span", {
    style: {
      fontSize: "var(--text-caption-size)",
      color: "var(--text-faint)",
      width: 90,
      textAlign: "right"
    }
  }, h.when)))))));
}
window.SearchHome = SearchHome;
})(); } catch (e) { __ds_ns.__errors.push({ path: "ui_kits/workspace/SearchHome.jsx", error: String((e && e.message) || e) }); }

// ui_kits/workspace/data.js
try { (() => {
const RESULTS = [{
  id: "novak",
  title: "Novak v. Harrow Logistics, Inc.",
  citation: "812 F.3d 1044",
  court: "9th Cir.",
  year: "2016",
  authority: "binding",
  treatment: "Followed",
  excerpt: "A carrier that accepts goods for delivery assumes a duty of reasonable care toward every party it knows will take possession downstream, not merely the consignee named on the bill of lading.",
  matchTerms: ["duty of care", "consignee", "bill of lading"]
}, {
  id: "carmack",
  title: "49 U.S.C. § 14706 — Liability of carriers under receipts and bills of lading",
  citation: "49 U.S.C. § 14706",
  court: "Statute",
  year: "",
  authority: "binding",
  excerpt: "A carrier is liable to the person entitled to recover under the receipt or bill of lading for the actual loss or injury to the property caused by it or by any other carrier over whose line the property is transported.",
  matchTerms: ["actual loss", "bill of lading"]
}, {
  id: "ellery",
  title: "Ellery Freight Sys. v. Marchand Produce Co.",
  citation: "704 F. App'x 512",
  court: "6th Cir.",
  year: "2017",
  authority: "persuasive",
  treatment: "Criticized",
  excerpt: "Foreseeability alone does not create a duty where the parties' allocation of risk is fixed by the tariff; the consignee's remedy lies in contract.",
  matchTerms: ["foreseeability", "tariff"]
}, {
  id: "restatement",
  title: "Restatement (Second) of Torts § 324A",
  citation: "Restatement (2d) Torts § 324A",
  court: "Secondary",
  year: "1965",
  authority: "secondary",
  excerpt: "One who undertakes to render services to another which he should recognize as necessary for the protection of a third person is subject to liability to the third person for physical harm resulting from failure to exercise reasonable care.",
  matchTerms: ["third person", "reasonable care"]
}, {
  id: "delgado",
  title: "Delgado Bros. Trucking v. Pacific Cold Storage",
  citation: "2019 WL 3821194",
  court: "N.D. Cal.",
  year: "2019",
  authority: "persuasive",
  excerpt: "Applying Novak, the court held that a cold-storage consignee not named on the bill of lading could nonetheless recover where the carrier's dispatch records showed the delivery chain.",
  matchTerms: ["consignee", "delivery chain"]
}];
const MATTERS = [{
  value: "novak",
  label: "Novak v. Harrow",
  icon: "folder",
  count: 12
}, {
  value: "delaney",
  label: "Delaney acquisition",
  icon: "folder",
  count: 4
}, {
  value: "kessler",
  label: "Kessler arbitration",
  icon: "folder",
  count: 7
}];
const SUGGESTED = ["Does a motor carrier owe a duty of care to a downstream consignee?", "Ninth Circuit standard for Carmack Amendment preemption", "When is an unpublished disposition citable in the 9th Circuit?"];
const HISTORY = [{
  q: "Carmack preemption of state negligence claims",
  when: "Today, 09:14",
  n: 31
}, {
  q: "Duty of care to downstream consignee",
  when: "Yesterday",
  n: 48
}, {
  q: "Tariff allocation of risk — 6th Cir.",
  when: "Mon",
  n: 12
}];
const ANSWER = "Within the Ninth Circuit, a carrier's duty of reasonable care runs to the consignee named on the bill of lading, and Novak extends it to a downstream consignee whose possession was reasonably foreseeable. District courts have applied that reading where dispatch records establish the delivery chain. The Sixth Circuit takes the narrower view that a tariff's allocation of risk forecloses a tort duty, so the analysis turns on where the claim is filed. Claims for loss or damage in transit remain preempted by the Carmack Amendment regardless of circuit.";
Object.assign(window, {
  RESULTS,
  MATTERS,
  SUGGESTED,
  HISTORY,
  ANSWER
});
})(); } catch (e) { __ds_ns.__errors.push({ path: "ui_kits/workspace/data.js", error: String((e && e.message) || e) }); }

__ds_ns.Button = __ds_scope.Button;

__ds_ns.IconButton = __ds_scope.IconButton;

__ds_ns.Badge = __ds_scope.Badge;

__ds_ns.Card = __ds_scope.Card;

__ds_ns.Icon = __ds_scope.Icon;

__ds_ns.Tag = __ds_scope.Tag;

__ds_ns.Dialog = __ds_scope.Dialog;

__ds_ns.Toast = __ds_scope.Toast;

__ds_ns.Tooltip = __ds_scope.Tooltip;

__ds_ns.Checkbox = __ds_scope.Checkbox;

__ds_ns.Input = __ds_scope.Input;

__ds_ns.Radio = __ds_scope.Radio;

__ds_ns.SearchField = __ds_scope.SearchField;

__ds_ns.Select = __ds_scope.Select;

__ds_ns.Switch = __ds_scope.Switch;

__ds_ns.SidebarNav = __ds_scope.SidebarNav;

__ds_ns.Tabs = __ds_scope.Tabs;

__ds_ns.AnswerPanel = __ds_scope.AnswerPanel;

__ds_ns.CitationCard = __ds_scope.CitationCard;

})();
