#!/usr/bin/env bash
# Create or refresh the coding agent's disposable copy of the development
# database.
#
# The development database holds locally crawled data that no amount of
# re-running the pipeline reproduces, so an agent must never write to it.
# `db-guard.sh` refuses the writes; this script provides the place they can go
# instead. `createdb -T` is a file-level copy rather than a dump/restore, which
# makes a fresh snapshot cheap enough to take whenever it is wanted.
#
#   ensure  (default) create the snapshot only if it is missing — the
#           SessionStart path, so an existing sandbox and whatever has been done
#           to it survive a restart
#   refresh --yes
#           drop and re-copy, for when the sandbox has drifted from the
#           development data. Destructive, so it requires --yes: one cluster
#           serves every worktree, which means one sandbox shared by every
#           session and every agent running against this checkout. Dropping it
#           discards their work as well as yours, and nothing here can tell
#           whose it was. The confirmation is the user's call to make, not an
#           agent's — see /playbooks/local-dev.md.
#
# `ensure` is idempotent and never drops anything, so any number of concurrent
# sessions can start up safely; `refresh` re-copies for all of them at once.
#
# Never fails a session: every problem here is reported and exits 0. Refusing an
# unconfirmed refresh is the exception — that is a caller error, not a session
# problem, so it exits non-zero where it will be noticed.
#
# "Reported" is the operative word. A silent exit 0 is indistinguishable from a
# working sandbox, and on a host with no Postgres client that is exactly what
# used to happen — so every path out of here says what it did or did not do.

set -uo pipefail

readonly SANDBOX_SUFFIX="_coding_agent"
readonly FALLBACK_SOURCE_DB="overklagan"
readonly MAINTENANCE_DB="postgres"
readonly EX_USAGE=64

PROJECT_DIR="${CLAUDE_PROJECT_DIR:-$(cd "$(dirname "$0")/../.." && pwd)}"
readonly PROJECT_DIR
ACTION="${1:-ensure}"
readonly ACTION
CONFIRMATION="${2:-}"
readonly CONFIRMATION

# The source database, in the order the answer is most likely to be right:
# whatever this checkout's .env actually connects to, then an explicit override,
# then the project default. Worktrees without a .env fall through to the last
# two — hardcoding would snapshot the wrong database the day .env changes.
source_database_from_env_file() {
  local env_file="${PROJECT_DIR}/.env" url
  [[ -f "$env_file" ]] || return 1
  url=$(grep -E '^[[:space:]]*DATABASE_URL=' "$env_file" | tail -n 1) || return 1
  url="${url#*=}"
  url="${url%%\?*}"
  url="${url##*/}"
  [[ -n "$url" ]] || return 1
  printf '%s' "$url"
}

SOURCE_DB="${CLAUDE_DB_SOURCE:-$(source_database_from_env_file || printf '%s' "$FALLBACK_SOURCE_DB")}"
readonly SOURCE_DB
readonly SANDBOX_DB="${SOURCE_DB}${SANDBOX_SUFFIX}"

# How the Postgres client tools get run. A native install puts them on PATH; a
# host where Postgres is only a container has none, and reaching them means
# going through the service. Deciding once here keeps every call site below
# identical on both platforms.
#
# The container path was not a refinement: without it this script found no
# `psql`, exited 0 in silence, and left the session with no sandbox at all while
# `.claude/settings.json` still pointed DATABASE_URL at one.
readonly COMPOSE_SERVICE="db"
readonly COMPOSE_SUPERUSER="postgres"

if command -v psql >/dev/null 2>&1 && command -v createdb >/dev/null 2>&1; then
  RUNNER="host"
elif docker compose -f "${PROJECT_DIR}/docker-compose.yml" exec -T \
  "$COMPOSE_SERVICE" true >/dev/null 2>&1; then
  RUNNER="compose"
else
  echo "No Postgres client on PATH and the ${COMPOSE_SERVICE} service is not reachable."
  echo "Sandbox ${SANDBOX_DB} was not created; start the database and run"
  echo ".claude/hooks/db-sandbox.sh ensure to get one."
  exit 0
fi
readonly RUNNER

# run_pg TOOL [ARG...] — invoke a Postgres client tool wherever it lives.
run_pg() {
  local tool="$1"
  shift
  if [[ "$RUNNER" == "host" ]]; then
    "$tool" "$@"
  else
    docker compose -f "${PROJECT_DIR}/docker-compose.yml" exec -T \
      "$COMPOSE_SERVICE" "$tool" -U "$COMPOSE_SUPERUSER" "$@"
  fi
}

db_exists() {
  run_pg psql -d "$MAINTENANCE_DB" -tAc \
    "SELECT 1 FROM pg_database WHERE datname = '$1'" 2>/dev/null | grep -q 1
}

# No source database means no local Postgres worth snapshotting — say nothing.
db_exists "$SOURCE_DB" || exit 0

case "$ACTION" in
  ensure)
    if db_exists "$SANDBOX_DB"; then
      echo "Database sandbox ${SANDBOX_DB} is in place."
      echo "Writes to ${SOURCE_DB} are refused; .claude/hooks/db-sandbox.sh refresh --yes re-copies the sandbox."
      exit 0
    fi
    ;;
  refresh)
    if [[ "$CONFIRMATION" != "--yes" ]]; then
      echo "Refusing to refresh without confirmation." >&2
      echo "This drops ${SANDBOX_DB} and re-copies it from ${SOURCE_DB}. One cluster" >&2
      echo "serves every worktree, so that sandbox is shared with any other session" >&2
      echo "running against this checkout and their work goes with it." >&2
      echo >&2
      echo "  .claude/hooks/db-sandbox.sh refresh --yes" >&2
      exit "$EX_USAGE"
    fi
    if db_exists "$SANDBOX_DB"; then
      if ! run_pg dropdb "$SANDBOX_DB" >/dev/null 2>&1; then
        echo "Could not drop ${SANDBOX_DB} — something is still connected to it." >&2
        exit 0
      fi
    fi
    ;;
  *)
    echo "usage: db-sandbox.sh [ensure|refresh --yes]" >&2
    exit "$EX_USAGE"
    ;;
esac

if error=$(run_pg createdb -T "$SOURCE_DB" "$SANDBOX_DB" 2>&1); then
  echo "Copied ${SOURCE_DB} into ${SANDBOX_DB}."
  echo "Writes to ${SOURCE_DB} are refused; .claude/hooks/db-sandbox.sh refresh --yes re-copies the sandbox."
else
  echo "Could not copy ${SOURCE_DB} into ${SANDBOX_DB}: ${error}" >&2
  echo "A template copy needs no other session connected to ${SOURCE_DB}." >&2
fi
exit 0
