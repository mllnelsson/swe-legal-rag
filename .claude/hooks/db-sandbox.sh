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
#   refresh drop and re-copy, for when the sandbox has drifted from the
#           development data
#
# One cluster serves every worktree, so there is one sandbox shared between
# them: `ensure` is idempotent, and `refresh` re-copies for all of them.
#
# Never fails a session: every problem here is reported and exits 0.

set -uo pipefail

readonly SANDBOX_SUFFIX="_coding_agent"
readonly FALLBACK_SOURCE_DB="overklagan"
readonly MAINTENANCE_DB="postgres"

PROJECT_DIR="${CLAUDE_PROJECT_DIR:-$(cd "$(dirname "$0")/../.." && pwd)}"
readonly PROJECT_DIR
ACTION="${1:-ensure}"
readonly ACTION

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

command -v psql >/dev/null 2>&1 || exit 0
command -v createdb >/dev/null 2>&1 || exit 0

db_exists() {
  psql -d "$MAINTENANCE_DB" -tAc \
    "SELECT 1 FROM pg_database WHERE datname = '$1'" 2>/dev/null | grep -q 1
}

# No source database means no local Postgres worth snapshotting — say nothing.
db_exists "$SOURCE_DB" || exit 0

case "$ACTION" in
  ensure)
    if db_exists "$SANDBOX_DB"; then
      echo "Database sandbox ${SANDBOX_DB} is in place."
      echo "Writes to ${SOURCE_DB} are refused; .claude/hooks/db-sandbox.sh refresh re-copies the sandbox."
      exit 0
    fi
    ;;
  refresh)
    if db_exists "$SANDBOX_DB"; then
      if ! dropdb "$SANDBOX_DB" 2>/dev/null; then
        echo "Could not drop ${SANDBOX_DB} — something is still connected to it." >&2
        exit 0
      fi
    fi
    ;;
  *)
    echo "usage: db-sandbox.sh [ensure|refresh]" >&2
    exit 64
    ;;
esac

if error=$(createdb -T "$SOURCE_DB" "$SANDBOX_DB" 2>&1); then
  echo "Copied ${SOURCE_DB} into ${SANDBOX_DB}."
  echo "Writes to ${SOURCE_DB} are refused; .claude/hooks/db-sandbox.sh refresh re-copies the sandbox."
else
  echo "Could not copy ${SOURCE_DB} into ${SANDBOX_DB}: ${error}" >&2
  echo "A template copy needs no other session connected to ${SOURCE_DB}." >&2
fi
exit 0
