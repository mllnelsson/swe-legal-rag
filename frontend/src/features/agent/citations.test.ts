import { describe, expect, it } from "vitest";

import { parseAnswer } from "./citations";
import { makeSource } from "../../test/factories";

const c1 = makeSource({ handle: "c1", case_number: "12/2023" });
const c2 = makeSource({ handle: "c2", case_number: "7/2022" });

const textOf = (segments: ReturnType<typeof parseAnswer>["segments"]) =>
  segments.map((s) => (s.kind === "text" ? s.text : `[${s.number}]`)).join("");

describe("parseAnswer", () => {
  it("turns a marker into a citation and keeps the prose around it", () => {
    const { segments } = parseAnswer("Fristen löper från delgivning[c1].", [c1], false);

    expect(textOf(segments)).toBe("Fristen löper från delgivning[1].");
  });

  it("numbers by first appearance in the prose, not by the order sources arrived", () => {
    const { segments, citedSources } = parseAnswer("Först[c2], sedan[c1].", [c1, c2], false);

    expect(textOf(segments)).toBe("Först[1], sedan[2].");
    // The list renders in this order, so the reader counting to 1 lands on c2.
    expect(citedSources.map((s) => s.handle)).toEqual(["c2", "c1"]);
  });

  it("gives one passage one number however often it is cited", () => {
    const { segments, citedSources } = parseAnswer("A[c1]. B[c1]. C[c2].", [c1, c2], false);

    expect(textOf(segments)).toBe("A[1]. B[1]. C[2].");
    expect(citedSources).toHaveLength(2);
  });

  it("reads adjacent markers as two citations", () => {
    const { segments } = parseAnswer("Båda gäller[c1][c2].", [c1, c2], false);

    expect(textOf(segments)).toBe("Båda gäller[1][2].");
  });

  it("removes a marker it cannot resolve rather than showing it", () => {
    // The model named a handle it never selected. `[c9]` on screen is a
    // reference to nothing.
    const { segments, citedSources } = parseAnswer("Detta gäller[c9].", [c1], false);

    expect(textOf(segments)).toBe("Detta gäller.");
    expect(citedSources).toEqual([]);
  });

  it("strips every marker from a restored turn, which kept no sources", () => {
    const { segments, citedSources } = parseAnswer("Fristen löper[c1] och[c2].", [], false);

    expect(textOf(segments)).toBe("Fristen löper och.");
    expect(citedSources).toEqual([]);
  });

  it("hides a marker the stream has not finished writing", () => {
    // A token boundary can fall anywhere; the accumulated string is re-parsed
    // on every one of them.
    for (const partial of ["Fristen löper[", "Fristen löper[c", "Fristen löper[c1"]) {
      expect(textOf(parseAnswer(partial, [c1], true).segments)).toBe("Fristen löper");
    }
  });

  it("keeps a trailing bracket once the answer is finished", () => {
    expect(textOf(parseAnswer("Se not [", [c1], false).segments)).toBe("Se not [");
  });

  it("reports selected passages the answer never cited", () => {
    const { citedSources, uncitedSources } = parseAnswer("Bara detta[c1].", [c1, c2], false);

    expect(citedSources.map((s) => s.handle)).toEqual(["c1"]);
    expect(uncitedSources.map((s) => s.handle)).toEqual(["c2"]);
  });
});
