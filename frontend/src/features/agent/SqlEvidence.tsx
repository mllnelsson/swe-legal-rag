import { Icon } from "../../components/display/Icon";
import type { SqlCell, SqlEvent } from "../../api/chat-events";

export type SqlEvidenceProps = {
  events: SqlEvent[];
};

/** The query behind a count, reachable from the answer that rests on it.
 *
 *  A number reads as authoritative and carries no excerpt to check it against,
 *  so the SQL agent's contract puts an obligation on whoever renders the answer:
 *  the query that produced the number must be *reachable*. It is not, however,
 *  the thing most readers came for — a table of SQL rows above the prose reads as
 *  machinery to anyone who does not write SQL, and machinery is what a reader
 *  skips past to find the answer. So the obligation is met by a disclosure, open
 *  in one click: discreet by default, and there in full for the reader who wants
 *  to verify. */
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

  // The whole block is a disclosure: the summary is what shows by default, and
  // the rows and query are a click away for the reader who wants to check the
  // number. The one-line "Ingen databasfråga kunde byggas" case above stays
  // visible — it is a claim about the answer, not machinery to drill into.
  return (
    <details
      style={{
        background: "var(--surface-sunken)",
        border: "1px solid var(--border-hairline)",
        borderRadius: "var(--radius-md)",
        padding: "var(--space-5)",
      }}
    >
      <summary
        style={{
          cursor: "pointer",
          display: "flex",
          alignItems: "center",
          gap: "var(--space-2)",
          fontFamily: "var(--font-sans)",
          fontSize: "var(--text-small-size)",
          color: "var(--text-muted)",
        }}
      >
        <Icon name="search" size={14} />
        Så räknades siffrorna fram
      </summary>

      <div
        style={{
          display: "flex",
          flexDirection: "column",
          gap: "var(--space-4)",
          marginTop: "var(--space-5)",
        }}
      >
        {event.columns.length > 0 && <ResultTable event={event} />}

        <div style={{ display: "flex", flexDirection: "column", gap: "var(--space-2)" }}>
          <span style={noteStyle}>Databasfrågan:</span>
          <pre
            style={{
              margin: 0,
              overflowX: "auto",
              fontFamily: "var(--font-mono)",
              fontSize: "var(--text-caption-size)",
              lineHeight: "var(--text-cite-lh)",
              color: "var(--text-body)",
              whiteSpace: "pre-wrap",
            }}
          >
            {event.sql}
          </pre>
        </div>

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
    </details>
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
