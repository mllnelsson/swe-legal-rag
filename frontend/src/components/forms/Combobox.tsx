import { useEffect, useId, useRef, useState } from "react";

import { Icon } from "../display/Icon";
import type { SelectOption } from "./Select";

const HEIGHTS = {
  sm: "var(--control-h-sm)",
  md: "var(--control-h-md)",
} as const;

// How tall the option list may grow before it scrolls, so a long free-text
// vocabulary never runs off the page. token-exempt: no scroll-height step in the scale.
const LISTBOX_MAX_HEIGHT = "260px";

export type ComboboxProps = {
  label?: string;
  options: SelectOption[];
  /** The selected option's value; `""` means nothing is selected. */
  value: string;
  /** Called with an option's value, or `""` when cleared. */
  onChange: (value: string) => void;
  size?: keyof typeof HEIGHTS;
  placeholder?: string;
};

/** A type-to-filter single-select, for a list too long for a plain dropdown.
 *
 *  It filters what it shows, never what it sends: option values pass through
 *  untouched, so a free-text vocabulary the corpus never merged stays exactly as
 *  it arrived. Built as a real `role="combobox"` with keyboard selection because
 *  a control a keyboard cannot drive is one half the readers of a legal-research
 *  tool cannot use. */
export function Combobox({
  label,
  options,
  value,
  onChange,
  size = "md",
  placeholder,
}: ComboboxProps) {
  const inputId = useId();
  const listboxId = useId();
  const containerRef = useRef<HTMLDivElement>(null);

  const selectedOption = options.find((option) => option.value === value);
  const selectedLabel = selectedOption?.label ?? "";

  const [text, setText] = useState(selectedLabel);
  const [open, setOpen] = useState(false);
  const [activeIndex, setActiveIndex] = useState(0);

  // The closed input mirrors the current selection, including changes made
  // elsewhere (a shared URL, the removable filter tag on the results page).
  useEffect(() => {
    if (!open) setText(selectedLabel);
  }, [selectedLabel, open]);

  // Until the reader types something other than the selected label, show the
  // whole list so it can be browsed; a real query narrows it.
  const query = text.trim().toLowerCase();
  const filtering = open && text !== selectedLabel && query !== "";
  const visibleOptions = filtering
    ? options.filter((option) => option.label.toLowerCase().includes(query))
    : options;

  useEffect(() => setActiveIndex(0), [text, open]);

  // Keep the highlighted option in view as it moves past the fold.
  const optionId = (index: number) => `${listboxId}-option-${index}`;
  useEffect(() => {
    if (!open) return;
    document.getElementById(optionId(activeIndex))?.scrollIntoView({ block: "nearest" });
  });

  useEffect(() => {
    if (!open) return;
    function handlePointerDown(event: PointerEvent) {
      if (containerRef.current !== null && !containerRef.current.contains(event.target as Node)) {
        setOpen(false);
        setText(selectedLabel);
      }
    }
    document.addEventListener("pointerdown", handlePointerDown);
    return () => document.removeEventListener("pointerdown", handlePointerDown);
  }, [open, selectedLabel]);

  function select(option: SelectOption) {
    onChange(option.value);
    setText(option.label);
    setOpen(false);
  }

  function clear() {
    onChange("");
    setText("");
    setOpen(false);
  }

  function handleKeyDown(event: React.KeyboardEvent<HTMLInputElement>) {
    if (event.key === "ArrowDown") {
      event.preventDefault();
      if (!open) {
        setOpen(true);
        return;
      }
      setActiveIndex((index) => Math.min(index + 1, visibleOptions.length - 1));
    } else if (event.key === "ArrowUp") {
      event.preventDefault();
      setActiveIndex((index) => Math.max(index - 1, 0));
    } else if (event.key === "Enter") {
      const option = visibleOptions[activeIndex];
      if (open && option !== undefined) {
        event.preventDefault();
        select(option);
      }
    } else if (event.key === "Escape") {
      setOpen(false);
      setText(selectedLabel);
    }
  }

  return (
    <div
      ref={containerRef}
      style={{
        position: "relative",
        display: "flex",
        flexDirection: "column",
        gap: "var(--space-3)",
        fontFamily: "var(--font-sans)",
      }}
    >
      {label !== undefined && (
        <label
          htmlFor={inputId}
          style={{
            fontSize: "var(--text-small-size)",
            fontWeight: "var(--weight-semibold)",
            color: "var(--text-strong)",
          }}
        >
          {label}
        </label>
      )}

      <div
        style={{
          display: "flex",
          alignItems: "center",
          gap: "var(--space-3)",
          height: HEIGHTS[size],
          padding: "0 var(--space-4)",
          background: "var(--surface-card)",
          border: `1px solid ${open ? "var(--apricot-400)" : "var(--border-default)"}`,
          borderRadius: "var(--radius-sm)",
          boxShadow: open ? "var(--ring-focus)" : "var(--shadow-xs)",
          transition: "var(--transition-control)",
        }}
      >
        <input
          id={inputId}
          role="combobox"
          aria-expanded={open}
          aria-controls={listboxId}
          aria-autocomplete="list"
          aria-activedescendant={open ? optionId(activeIndex) : undefined}
          value={text}
          placeholder={placeholder}
          onChange={(event) => {
            setText(event.target.value);
            setOpen(true);
          }}
          onFocus={(event) => {
            setOpen(true);
            event.target.select();
          }}
          onKeyDown={handleKeyDown}
          style={{
            flex: 1,
            minWidth: 0,
            border: "none",
            outline: "none",
            background: "transparent",
            font: "inherit",
            fontSize: "var(--text-body-size)",
            color: "var(--text-strong)",
          }}
        />
        {value === "" ? (
          <Icon name="chevron-down" size={15} color="var(--text-muted)" />
        ) : (
          <button
            type="button"
            aria-label="Rensa"
            onClick={clear}
            style={{
              display: "inline-flex",
              alignItems: "center",
              padding: 0,
              border: "none",
              background: "transparent",
              color: "var(--text-muted)",
              cursor: "pointer",
            }}
          >
            <Icon name="x" size={15} />
          </button>
        )}
      </div>

      {open && (
        <ul
          id={listboxId}
          role="listbox"
          style={{
            position: "absolute",
            top: "100%",
            left: 0,
            right: 0,
            zIndex: 20,
            margin: "var(--space-2) 0 0",
            padding: "var(--space-2)",
            listStyle: "none",
            maxHeight: LISTBOX_MAX_HEIGHT,
            overflowY: "auto",
            background: "var(--surface-card)",
            border: "1px solid var(--border-default)",
            borderRadius: "var(--radius-sm)",
            boxShadow: "var(--shadow-md)",
          }}
        >
          {visibleOptions.length === 0 ? (
            <li
              style={{
                padding: "var(--space-3) var(--space-4)",
                fontSize: "var(--text-small-size)",
                color: "var(--text-muted)",
              }}
            >
              Inga träffar
            </li>
          ) : (
            visibleOptions.map((option, index) => {
              const active = index === activeIndex;
              const selected = option.value === value;
              return (
                <li
                  key={option.value}
                  id={optionId(index)}
                  role="option"
                  aria-selected={selected}
                  // Pointer down rather than click: click fires after the input's
                  // blur, which would close the list before the selection lands.
                  onPointerDown={(event) => {
                    event.preventDefault();
                    select(option);
                  }}
                  onMouseEnter={() => setActiveIndex(index)}
                  style={{
                    display: "flex",
                    alignItems: "center",
                    justifyContent: "space-between",
                    gap: "var(--space-3)",
                    padding: "var(--space-3) var(--space-4)",
                    borderRadius: "var(--radius-sm)",
                    fontSize: "var(--text-body-size)",
                    color: "var(--text-strong)",
                    background: active ? "var(--surface-sunken)" : "transparent",
                    cursor: "pointer",
                  }}
                >
                  <span>{option.label}</span>
                  {selected && <Icon name="check" size={15} color="var(--action-primary)" />}
                </li>
              );
            })
          )}
        </ul>
      )}
    </div>
  );
}
