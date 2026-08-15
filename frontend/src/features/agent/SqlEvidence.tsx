import { Icon } from "../../components/display/Icon";
import type { SqlCell, SqlEvent } from "../../api/chat-events";

export type SqlEvidenceProps = {
  events: SqlEvent[];
};

/** The query behind a count, shown before the answer that rests on it.
 *
 *  Not a debugging affordance and not collapsible. A number reads as
 *  authoritative and carries no excerpt to check it against, so the SQL agent's
 *  contract puts the obligation on whoever renders the answer: show the query
 *  that produced it. Hiding this behind a disclosure would be the same as not
 *  showing it — the reader who should see it is exactly the one who would not
 *  open it. */
export function SqlEvidence({ events }: SqlEvidenceProps) {
  if (events.length === 0) return null;

  return (
    <section style={{ display: "flex", flexDirection: "column", gap: "var(--space-4)" }}>
      {events.map((event, index) => (
        // The frames carry no id, and a turn may count more than once. The list
        // is append-only within a turn, so position is a stable identity.
        // oxlint-disable-next-line react/no-array-index-key
        <SqlBlock key={index} event={event} />
      ))}
    </section>
  );
}

function SqlBlock({ event }: { event: SqlEvent }) {
  if (!event.answered) {
    return (
      <p
        style={{
          margin: 0,
          fontFamily: "var(--font-sans)",
          fontSize: "var(--text-small-size)",
          color: "var(--text-muted)",
          display: "flex",
          alignItems: "center",
          gap: "var(--space-2)",
        }}
      >
        <Icon name="info" size={14} />
        Ingen databasfråga kunde byggas, så svaret innehåller ingen räkning.
      </p>
    );
  }

  return (
    <div
      style={{
        background: "var(--surface-sunken)",
        border: "1px solid var(--border-hairline)",
        borderRadius: "var(--radius-md)",
        padding: "var(--space-5)",
        display: "flex",
        flexDirection: "column",
        gap: "var(--space-4)",
      }}
    >
      <h3
        style={{
          margin: 0,
          fontFamily: "var(--font-sans)",
          fontSize: "var(--text-overline-size)",
          letterSpacing: "var(--text-overline-ls)",
          fontWeight: "var(--text-overline-weight)",
          textTransform: "uppercase",
          color: "var(--text-faint)",
        }}
      >
        Frågan bakom siffran
      </h3>

      <pre
        style={{
          margin: 0,
          overflowX: "auto",
          fontFamily: "var(--font-mono)",
          fontSize: "var(--text-caption-size)",
          lineHeight: "var(--text-cite-lh)",
          color: "var(--text-strong)",
          whiteSpace: "pre-wrap",
        }}
      >
        {event.sql}
      </pre>

      {event.columns.length > 0 && <ResultTable event={event} />}

      {event.truncated && (
        <p style={{ margin: 0, ...noteStyle }}>
          Resultatet är avkortat — fler rader finns än de som visas.
        </p>
      )}

      {event.assumptions.length > 0 && (
        <p style={{ margin: 0, ...noteStyle }}>
          Tolkningsval: {event.assumptions.join("; ")}
        </p>
      )}

      {event.attempts.length > 1 && (
        <details>
          <summary style={{ cursor: "pointer", ...noteStyle }}>
            {event.attempts.length} försök innan frågan gick igenom
          </summary>
          <ol
            style={{
              margin: "var(--space-3) 0 0",
              paddingLeft: "var(--space-6)",
              ...noteStyle,
            }}
          >
            {event.attempts.map((attempt, index) => (
              // The trail is ordered and immutable, and two attempts may hold
              // the same SQL — position is the only identity there is.
              // oxlint-disable-next-line react/no-array-index-key
              <li key={index} style={{ fontFamily: "var(--font-mono)" }}>
                {attempt.sql}
                {attempt.ok ? "" : ` — ${attempt.error ?? "misslyckades"}`}
              </li>
            ))}
          </ol>
        </details>
      )}
    </div>
  );
}

const noteStyle = {
  fontFamily: "var(--font-sans)",
  fontSize: "var(--text-caption-size)",
  color: "var(--text-muted)",
} as const;

const cellStyle = {
  padding: "var(--space-2) var(--space-4)",
  borderBottom: "1px solid var(--border-hairline)",
} as const;

function ResultTable({ event }: { event: SqlEvent }) {
  return (
    <div style={{ overflowX: "auto" }}>
      <table
        style={{
          borderCollapse: "collapse",
          fontFamily: "var(--font-mono)",
          fontSize: "var(--text-caption-size)",
          color: "var(--text-strong)",
        }}
      >
        <thead>
          <tr>
            {event.columns.map((column) => (
              <th
                key={column}
                scope="col"
                style={{
                  textAlign: "left",
                  padding: "var(--space-2) var(--space-4)",
                  borderBottom: "1px solid var(--border-default)",
                  color: "var(--text-muted)",
                  fontWeight: "var(--weight-semibold)",
                }}
              >
                {column}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {event.rows.map((row, rowIndex) => (
            // A result set has no key but its ordering: two rows may be
            // identical, and the table is rendered once and never mutated.
            // oxlint-disable-next-line react/no-array-index-key
            <tr key={rowIndex}>
              {row.map((cell, cellIndex) => (
                // oxlint-disable-next-line react/no-array-index-key
                <td key={cellIndex} style={cellStyle}>
                  {renderCell(cell)}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

/** A null cell is shown as an em dash, never as an empty one that reads as a
 *  missing column or a zero. */
function renderCell(cell: SqlCell): string {
  if (cell === null) return "—";
  return String(cell);
}
