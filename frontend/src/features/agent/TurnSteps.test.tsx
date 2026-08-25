/* The wait, as the reader experiences it.
 *
 * Roughly eighteen seconds pass before an answer starts. These tests are about
 * the difference between that wait being legible and it being noticeable, which
 * is the whole reason this component was rewritten.
 */

import { act, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, test, vi } from "vitest";

import { TurnSteps } from "./TurnSteps";
import type { Step } from "./conversation";

function step(overrides: Partial<Step> = {}): Step {
  return { id: "s-1", label: "search.broad", status: null, detail: {}, ...overrides };
}

beforeEach(() => {
  vi.useFakeTimers({ shouldAdvanceTime: true });
});

afterEach(() => {
  vi.useRealTimers();
});

describe("while the agent is working", () => {
  test("the steps are announced as their own region, not buried in the turn", () => {
    render(<TurnSteps steps={[step()]} streaming />);
    expect(screen.getByRole("region", { name: "Agenten arbetar" })).toBeInTheDocument();
  });

  test("something is on screen before the first tool call arrives", () => {
    // The first step is itself a model round trip away. An empty region here
    // is the blank the progress events exist to prevent.
    render(<TurnSteps steps={[]} streaming />);
    expect(screen.getByText("Läser frågan")).toBeInTheDocument();
  });

  test("the elapsed seconds count up against the stated one-minute ceiling", () => {
    render(<TurnSteps steps={[step()]} streaming />);
    expect(screen.getByText("0 s")).toBeInTheDocument();

    // Wrapped, because the counter ticks through React state.
    act(() => vi.advanceTimersByTime(3000));
    expect(screen.getByText("3 s")).toBeInTheDocument();
  });

  test("the running step is marked as the one happening now", () => {
    const { container } = render(
      <TurnSteps steps={[step({ id: "done", status: "ok" }), step({ id: "now" })]} streaming />,
    );
    // One running step, so exactly one animated label.
    expect(container.querySelectorAll(".step-active-label")).toHaveLength(1);
  });
});

describe("once the answer starts arriving", () => {
  test("the block folds to a summary so the prose has the attention", () => {
    render(<TurnSteps steps={[step({ status: "ok" }), step({ id: "s-2", status: "ok" })]} streaming writing />);

    expect(screen.getByText(/2 steg/)).toBeInTheDocument();
    expect(screen.queryByRole("region", { name: "Agenten arbetar" })).not.toBeInTheDocument();
  });

  test("folded is not gone — the steps are still there to open", () => {
    // What the agent did is the reader's only account of where an answer came
    // from. It may move out of the way; it may not disappear.
    render(<TurnSteps steps={[step({ status: "ok" })]} streaming writing />);
    expect(screen.getByText("Sökte i besluten")).toBeInTheDocument();
  });
});

describe("a finished turn", () => {
  test("shows nothing at all when it took no steps", () => {
    const { container } = render(<TurnSteps steps={[]} streaming={false} />);
    expect(container).toBeEmptyDOMElement();
  });

  test("stops counting", () => {
    render(<TurnSteps steps={[step({ status: "ok" })]} streaming={false} />);
    expect(screen.queryByText(/ s$/)).not.toBeInTheDocument();
  });
});
