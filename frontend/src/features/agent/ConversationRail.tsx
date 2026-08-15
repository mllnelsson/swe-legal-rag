import { Link, NavLink, useNavigate } from "react-router";

import { Icon } from "../../components/display/Icon";
import { useDeleteSession, useSessions } from "../../api/queries";
import { formatCount, formatShortDate } from "../../lib/format";
import type { SessionSummary } from "../../api/types";

export type ConversationRailProps = {
  /** The conversation currently open, so the rail can mark it. */
  openSessionId: string | undefined;
};

/** Every conversation this app has held.
 *
 *  *Every* one: there are no accounts, so there is nothing to scope the list by
 *  — which the rail says out loud rather than leaving to be worked out from the
 *  fact that a stranger's question is sitting in it.
 *
 *  Titles are the opening question verbatim, truncated by the API. No model
 *  writes them: a generated label would put text the reader cannot check into
 *  the navigation, and cost money per conversation to do it. */
export function ConversationRail({ openSessionId }: ConversationRailProps) {
  const sessions = useSessions();
  const remove = useDeleteSession();
  const navigate = useNavigate();

  const onDelete = (session: SessionSummary) => {
    // The one irreversible thing this app does, so it asks first.
    if (!window.confirm(`Ta bort samtalet "${session.title}"?`)) return;
    remove.mutate(session.id, {
      onSuccess: () => {
        // Standing on a conversation that no longer exists would refetch a 404.
        if (session.id === openSessionId) void navigate("/agent");
      },
    });
  };

  return (
    <nav
      aria-label="Tidigare samtal"
      style={{ display: "flex", flexDirection: "column", gap: "var(--space-5)" }}
    >
      <Link
        to="/agent"
        style={{
          display: "inline-flex",
          alignItems: "center",
          gap: "var(--space-2)",
          height: "var(--control-h-sm)",
          padding: "0 var(--space-4)",
          borderRadius: "var(--radius-sm)",
          border: "1px solid var(--border-default)",
          background: "var(--surface-card)",
          fontFamily: "var(--font-sans)",
          fontSize: "var(--text-small-size)",
          fontWeight: "var(--weight-semibold)",
          color: "var(--text-strong)",
          textDecoration: "none",
        }}
      >
        <Icon name="plus" size={14} />
        Nytt samtal
      </Link>

      <div style={{ display: "flex", flexDirection: "column", gap: "var(--space-2)" }}>
        <h2 style={overlineStyle}>Tidigare samtal</h2>
        <p style={{ ...captionStyle, margin: 0 }}>
          Appen har inga konton, så alla samtal visas här.
        </p>
      </div>

      <RailBody
        sessions={sessions}
        openSessionId={openSessionId}
        onDelete={onDelete}
        deleting={remove.isPending}
      />
    </nav>
  );
}

type RailBodyProps = {
  sessions: ReturnType<typeof useSessions>;
  openSessionId: string | undefined;
  onDelete: (session: SessionSummary) => void;
  deleting: boolean;
};

/** The list, or an honest account of why there is none.
 *
 *  A rail that renders nothing on a failed fetch is indistinguishable from a
 *  rail with nothing in it, and the two mean opposite things to someone
 *  wondering where their question went. */
function RailBody({ sessions, openSessionId, onDelete, deleting }: RailBodyProps) {
  if (sessions.isPending) {
    return <p style={captionStyle}>Hämtar…</p>;
  }

  if (sessions.isError) {
    return (
      <p style={{ ...captionStyle, color: "var(--status-error-fg)" }}>
        Kunde inte hämta tidigare samtal.
      </p>
    );
  }

  const items = sessions.data.items;
  if (items.length === 0) {
    return <p style={captionStyle}>Inga tidigare samtal än.</p>;
  }

  return (
    <ul
      style={{
        listStyle: "none",
        margin: 0,
        padding: 0,
        display: "flex",
        flexDirection: "column",
        gap: "var(--space-1)",
      }}
    >
      {items.map((session) => (
        <ConversationRow
          key={session.id}
          session={session}
          open={session.id === openSessionId}
          onDelete={onDelete}
          deleting={deleting}
        />
      ))}
    </ul>
  );
}

type ConversationRowProps = {
  session: SessionSummary;
  open: boolean;
  onDelete: (session: SessionSummary) => void;
  deleting: boolean;
};

function ConversationRow({ session, open, onDelete, deleting }: ConversationRowProps) {
  const date = formatShortDate(session.last_active_at);
  const turns = `${formatCount(session.turn_count)} ${
    session.turn_count === 1 ? "fråga" : "frågor"
  }`;

  return (
    <li
      style={{
        display: "flex",
        alignItems: "flex-start",
        gap: "var(--space-2)",
        borderRadius: "var(--radius-sm)",
        background: open ? "var(--surface-sunken)" : "transparent",
      }}
    >
      <NavLink
        to={`/agent/${session.id}`}
        // `aria-current="page"` comes from NavLink's own route matching, which
        // is the same fact as `open` — a conversation *is* its URL here.
        style={{
          flex: 1,
          minWidth: 0,
          display: "flex",
          flexDirection: "column",
          gap: "var(--space-1)",
          padding: "var(--space-3) var(--space-4)",
          textDecoration: "none",
        }}
      >
        <span
          style={{
            fontFamily: "var(--font-sans)",
            fontSize: "var(--text-small-size)",
            lineHeight: "var(--text-small-lh)",
            fontWeight: open ? "var(--weight-semibold)" : "var(--weight-regular)",
            color: open ? "var(--text-strong)" : "var(--text-body)",
            // Two lines of the question, then an ellipsis. The API has already
            // truncated it; this is the rail's own width doing the rest.
            display: "-webkit-box",
            WebkitBoxOrient: "vertical",
            WebkitLineClamp: 2,
            overflow: "hidden",
          }}
        >
          {session.title}
        </span>
        <span style={captionStyle}>{date === null ? turns : `${date} · ${turns}`}</span>
      </NavLink>

      <button
        type="button"
        onClick={() => onDelete(session)}
        disabled={deleting}
        aria-label={`Ta bort samtalet ${session.title}`}
        style={{
          flex: "none",
          margin: "var(--space-3) var(--space-2) 0 0",
          padding: "var(--space-1)",
          border: "none",
          borderRadius: "var(--radius-sm)",
          background: "transparent",
          color: "var(--text-faint)",
          cursor: deleting ? "not-allowed" : "pointer",
          lineHeight: 0,
        }}
      >
        <Icon name="x" size={14} />
      </button>
    </li>
  );
}

const overlineStyle = {
  margin: 0,
  fontFamily: "var(--font-sans)",
  fontSize: "var(--text-overline-size)",
  letterSpacing: "var(--text-overline-ls)",
  fontWeight: "var(--text-overline-weight)",
  textTransform: "uppercase",
  color: "var(--text-faint)",
} as const;

const captionStyle = {
  margin: 0,
  fontFamily: "var(--font-sans)",
  fontSize: "var(--text-caption-size)",
  color: "var(--text-muted)",
} as const;
