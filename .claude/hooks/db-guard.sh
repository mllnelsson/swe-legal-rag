#!/usr/bin/env bash
# PreToolUse hook — refuses Bash commands that would write to a protected
# Postgres database.
#
# The development database holds locally crawled data that re-running the
# pipeline does not reproduce. The agent gets a disposable copy instead
# (`db-sandbox.sh`), and this hook is what makes the copy the only writable one.
#
# Two stages, so the common case costs nothing:
#   here    a word match on the Postgres tool names; anything else exits 0 at
#           once, which is nearly every Bash command in a session
#   db-guard.py  resolves which database the command targets across every way a
#           target can be declared, and inspects the statement when it turns out
#           to be a protected one
#
# Fails closed. If jq or python3 is missing, or the resolver errors, a command
# that mentions a Postgres tool is refused rather than waved through — the whole
# point is that silence must mean "checked", not "could not check".
#
# Install: .claude/hooks/db-guard.sh   (chmod +x)
# Requires: jq, python3

set -uo pipefail

readonly POSTGRES_TOOLS='psql|dropdb|createdb|dropuser|createuser|pg_dump|pg_dumpall|pg_restore|vacuumdb|reindexdb|clusterdb'

# A line also needs resolving when it names no Postgres tool but redirects one
# at a database itself — `DATABASE_URL=…/overklagan uv run alembic upgrade head`
# writes to the development database without the word `psql` appearing in it.
readonly CONNECTION_VARIABLES='PGDATABASE|PGSERVICE|DATABASE_URL'
readonly TRIGGER_PATTERN="(^|[^[:alnum:]_-])((${POSTGRES_TOOLS})([^[:alnum:]_-]|\$)|(${CONNECTION_VARIABLES})=)"

deny() {
  jq -cn --arg reason "$1" '{
    hookSpecificOutput: {
      hookEventName: "PreToolUse",
      permissionDecision: "deny",
      permissionDecisionReason: $reason
    }
  }' 2>/dev/null || printf '%s\n' "$1" >&2
  exit 0
}

input=$(cat)

# Without jq the command cannot be read out of the hook payload. Refuse only the
# lines that look like they touch Postgres, rather than every Bash command.
if ! command -v jq >/dev/null 2>&1; then
  grep -Eqi "$TRIGGER_PATTERN" <<<"$input" || exit 0
  printf 'The database guard needs jq, which is not installed.\n' >&2
  exit 2
fi

command_text=$(jq -r '.tool_input.command // empty' <<<"$input")
[[ -n "$command_text" ]] || exit 0

# Stage A — nothing Postgres-shaped in this line, so nothing to resolve.
grep -Eqi "$TRIGGER_PATTERN" <<<"$command_text" || exit 0

if ! command -v python3 >/dev/null 2>&1; then
  deny "The database guard needs python3 to resolve which database this command targets, and python3 is not on PATH."
fi

verdict=$(printf '%s' "$command_text" | python3 "$(dirname "$0")/db-guard.py" 2>&1)
status=$?

if (( status != 0 )); then
  deny "The database guard failed while resolving which database this command targets: ${verdict}"
fi

[[ -n "$verdict" ]] && printf '%s' "$verdict"
exit 0
