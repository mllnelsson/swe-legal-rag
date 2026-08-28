/* The type-to-filter single-select.
 *
 * Its one promise is that it filters what it *shows*, never what it *sends*: a
 * free-text vocabulary the corpus never merged has to reach the API byte-identical,
 * however the reader narrowed the list to find it. The rest is keyboard reach — a
 * control a keyboard cannot drive is one half the readers locked out.
 */

import { fireEvent, render, screen } from "@testing-library/react";
import { useState } from "react";
import { describe, expect, test, vi } from "vitest";

import { Combobox } from "./Combobox";

const OPTIONS = [
  { value: "Utlämnande av handling", label: "Utlämnande av handling (6)" },
  { value: "Avvisning", label: "Avvisning (4)" },
];

function Harness({ onChange = vi.fn() }: { onChange?: (value: string) => void }) {
  const [value, setValue] = useState("");
  return (
    <Combobox
      label="Kategori"
      placeholder="Alla kategorier"
      options={OPTIONS}
      value={value}
      onChange={(next) => {
        setValue(next);
        onChange(next);
      }}
    />
  );
}

describe("Combobox", () => {
  test("opens on focus and lists every option", () => {
    render(<Harness />);
    fireEvent.focus(screen.getByRole("combobox"));
    expect(screen.getAllByRole("option")).toHaveLength(2);
  });

  test("typing filters the list by label, case-insensitively", () => {
    render(<Harness />);
    const input = screen.getByRole("combobox");
    fireEvent.focus(input);
    fireEvent.change(input, { target: { value: "avv" } });
    const options = screen.getAllByRole("option");
    expect(options).toHaveLength(1);
    expect(options[0]).toHaveTextContent("Avvisning (4)");
  });

  test("selecting an option reports its exact value and closes the list", () => {
    const onChange = vi.fn();
    render(<Harness onChange={onChange} />);
    fireEvent.focus(screen.getByRole("combobox"));
    fireEvent.pointerDown(screen.getByRole("option", { name: /Utlämnande/ }));
    expect(onChange).toHaveBeenCalledWith("Utlämnande av handling");
    expect(screen.queryByRole("listbox")).not.toBeInTheDocument();
  });

  test("keyboard: arrow down then Enter selects the highlighted option", () => {
    const onChange = vi.fn();
    render(<Harness onChange={onChange} />);
    const input = screen.getByRole("combobox");
    fireEvent.focus(input);
    fireEvent.keyDown(input, { key: "ArrowDown" });
    fireEvent.keyDown(input, { key: "Enter" });
    expect(onChange).toHaveBeenCalledWith("Avvisning");
  });

  test("clearing a selection resets the value to empty", () => {
    const onChange = vi.fn();
    render(<Harness onChange={onChange} />);
    fireEvent.focus(screen.getByRole("combobox"));
    fireEvent.pointerDown(screen.getByRole("option", { name: /Avvisning/ }));
    fireEvent.click(screen.getByRole("button", { name: "Rensa" }));
    expect(onChange).toHaveBeenLastCalledWith("");
  });
});
