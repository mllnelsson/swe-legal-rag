/* The Swedish words for the agent's progress keys.
 *
 * The API emits keys; the client owns the words. That split is deliberate on
 * both sides: no translation lives in the backend, and this file never has to
 * parse tool arguments to work out what to say.
 *
 * `ProgressLabel` is a closed enum owned by the API, so every member needs an
 * entry here — `progress-labels.test.ts` reads the Python enum and fails if one
 * is missing. An unknown key still renders neutral prose rather than a raw
 * `decision.inspect`, because a client from before a backend deploy must not
 * put an identifier on screen.
 */

import type { ProgressDetail, ProgressLabel, ToolStatus } from "../../api/chat-events";

/** What is happening, while it happens. */
const RUNNING: Record<ProgressLabel, string> = {
  "vocabulary.list": "Läser vilka kategorier och sökord som finns",
  "search.broad": "Söker i besluten",
  "search.filtered": "Söker i ett avgränsat urval",
  "search.refused": "Söker i ett avgränsat urval",
  "sql.query": "Räknar i hela samlingen",
  "decision.read": "Läser ett beslut i sin helhet",
  "decision.inspect": "Följer begrepp och hänvisningar",
  "answer.compose": "Väljer ut underlaget",
};

/** What happened, once it has. */
const FINISHED: Record<ProgressLabel, string> = {
  "vocabulary.list": "Läste kategorier och sökord",
  "search.broad": "Sökte i besluten",
  "search.filtered": "Sökte i ett avgränsat urval",
  // Not a failure: the agent asked to filter on a value it had not looked up,
  // and the API declined until it does. The next step is that lookup.
  "search.refused": "Avvaktade med filtret tills värdena var kända",
  "sql.query": "Räknade i hela samlingen",
  "decision.read": "Läste ett beslut i sin helhet",
  "decision.inspect": "Följde begrepp och hänvisningar",
  "answer.compose": "Valde ut underlaget",
};

const UNKNOWN_RUNNING = "Arbetar";
const UNKNOWN_FINISHED = "Klart";

export type StepPhase = "running" | "finished";

/** The sentence for one step. Never returns the key itself. */
export function progressText(label: string, phase: StepPhase): string {
  const table = phase === "running" ? RUNNING : FINISHED;
  return (
    table[label as ProgressLabel] ??
    (phase === "running" ? UNKNOWN_RUNNING : UNKNOWN_FINISHED)
  );
}

/** The optional half of a step's line: what `detail` adds, or nothing.
 *
 *  Kept apart from `progressText` because `detail` is explicitly optional in the
 *  contract — a frame that carries none still reads as a complete step. */
export function progressDetailText(
  label: string,
  detail: ProgressDetail | undefined,
  phase: StepPhase,
): string | null {
  if (detail === undefined || phase === "running") return null;

  switch (label as ProgressLabel) {
    case "search.broad":
    case "search.filtered": {
      const count = detail.decision_count;
      if (count === undefined) return null;
      const found = count === 1 ? "1 beslut" : `${count} beslut`;
      // The widening is worth saying: those passages are the appealed
      // decisions, not the nämnd's own reasoning.
      return detail.widened_to_appendices === true
        ? `${found} — inget matchade i besluten själva, så bilagorna söktes också`
        : found;
    }
    case "sql.query": {
      if (detail.answered === false) return "ingen fråga kunde byggas";
      const rows = detail.row_count;
      return rows === undefined ? null : rows === 1 ? "1 rad" : `${rows} rader`;
    }
    case "answer.compose": {
      const cited = detail.cited_chunks;
      if (cited === undefined) return null;
      return cited === 1 ? "1 stycke" : `${cited} stycken`;
    }
    default:
      return null;
  }
}

/** Whether a finished step went the ordinary way.
 *
 *  `refused` is deliberately not a failure: it is a policy decline the agent
 *  repairs from on its next iteration, and showing it as a problem would tell
 *  the reader something went wrong when nothing did. */
export function isStepFailure(status: ToolStatus): boolean {
  return status === "error";
}
