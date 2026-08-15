/* Cross-language parity for a closed, API-owned enum.
 *
 * `documentation/api/chat-endpoint.md` states the split plainly: the API emits
 * keys and the client owns the words. That only holds while the client has a
 * word for every key — and nothing else checks it, because the two halves are
 * written in different languages and the frames are untyped JSON on the wire.
 *
 * So this reads the Python enum and asserts the Swedish table covers it. When
 * the backend adds a label, this fails here rather than putting `decision.audit`
 * in front of a user.
 */

import { describe, expect, it } from "vitest";

// The backend enum itself, as text. `?raw` rather than reading the file at
// runtime so the dependency is one the bundler resolves: move or rename
// `_dtos.py` and this fails to import rather than silently finding nothing.
import dtosSource from "../../../../packages/agents/src/agents/chat/_dtos.py?raw";
import { progressText } from "./progress-text";

/** The values of `class ProgressLabel(StrEnum)`, read out of the source. */
function backendLabels(): string[] {
  const block = /class ProgressLabel\(StrEnum\):([\s\S]*?)\n\nclass /.exec(dtosSource);
  if (block === null) throw new Error("ProgressLabel not found in _dtos.py");
  const body = block[1] ?? "";
  return [...body.matchAll(/^\s{4}[A-Z_]+ = "([a-z._]+)"$/gm)].flatMap((match) =>
    match[1] === undefined ? [] : [match[1]],
  );
}

describe("the label vocabulary the API owns", () => {
  const labels = backendLabels();

  it("is found, and is not empty", () => {
    // Guards the regex itself: an empty list would make every test below pass.
    expect(labels.length).toBeGreaterThan(5);
    expect(labels).toContain("search.broad");
    expect(labels).toContain("answer.direct");
  });

  it.each(labels)("has Swedish words for %s while it runs", (label) => {
    const text = progressText(label, "running");
    expect(text).not.toBe("Arbetar");
    expect(text).not.toContain(".");
  });

  it.each(labels)("has Swedish words for %s once it has finished", (label) => {
    const text = progressText(label, "finished");
    expect(text).not.toBe("Klart");
    expect(text).not.toContain(".");
  });
});

describe("a label this client has never heard of", () => {
  it("renders neutral prose, never the raw key", () => {
    // A frontend deployed before a backend must not put an identifier on
    // screen. Dropping the step entirely would be worse: the reader would see
    // an answer arrive with a gap in the work behind it.
    expect(progressText("decision.audit", "running")).toBe("Arbetar");
    expect(progressText("decision.audit", "finished")).toBe("Klart");
  });
});
