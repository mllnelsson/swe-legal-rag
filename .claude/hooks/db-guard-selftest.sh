#!/usr/bin/env bash
# Drives db-guard.sh with the hook payload it will really receive and checks the
# verdict on every case the guard exists to decide.
#
# The first case is the incident that prompted the guard: a DELETE against the
# development database that removed rows nobody meant to remove. If that case
# ever passes as ALLOW, the guard is broken however green the rest looks.
#
# Run: .claude/hooks/db-guard-selftest.sh

set -uo pipefail

GUARD="$(dirname "$0")/db-guard.sh"

# The environment the guard sees in a real session: PGDATABASE already redirected
# to the sandbox by .claude/settings.json. Several cases only mean anything with
# it set, so the test sets it rather than inheriting whatever the shell has.
export PGDATABASE="overklagan_coding_agent"
unset PGSERVICE PGSERVICEFILE 2>/dev/null

passed=0
failed=0

# verdict COMMAND -> prints "deny" or "allow"
verdict() {
  local output
  output=$(jq -cn --arg command "$1" \
    '{tool_name: "Bash", tool_input: {command: $command}}' | "$GUARD")
  if [[ -n "$output" ]]; then echo "deny"; else echo "allow"; fi
}

check() {
  local expected="$1" command="$2" actual
  actual=$(verdict "$command")
  if [[ "$actual" == "$expected" ]]; then
    passed=$((passed + 1))
  else
    failed=$((failed + 1))
    printf 'FAIL  expected %-5s got %-5s  %s\n' "$expected" "$actual" "$command"
  fi
}

# --- Must be refused: a write reaching the development database ---------------

check deny 'psql -d overklagan -c "DELETE FROM entities WHERE id NOT IN (SELECT entity_id FROM document_entities)"'
check deny 'psql overklagan -c "TRUNCATE documents"'
check deny 'psql postgresql://mlnelsson@localhost:5432/overklagan -c "DROP TABLE entities"'
check deny 'psql "host=localhost dbname=overklagan" -c "UPDATE documents SET raw_text=NULL"'
check deny 'PGDATABASE=overklagan psql -c "INSERT INTO entities VALUES (1)"'
check deny 'psql --dbname=overklagan -c "WITH x AS (SELECT 1) DELETE FROM entities"'
check deny 'psql -d postgres -c "DROP DATABASE overklagan"'
check deny 'psql -d overklagan -f cleanup.sql'
check deny 'psql -d overklagan < cleanup.sql'
check deny "psql -d overklagan_coding_agent -c '\\c overklagan' -c \"DELETE FROM entities\""
check deny 'dropdb overklagan'
check deny 'psql -d overklagan -c "SELECT 1; DELETE FROM entities"'
check deny 'psql -d overklagan'
check deny 'echo "DELETE FROM entities" | psql -d overklagan'
check deny 'DATABASE_URL=postgresql://mlnelsson@localhost:5432/overklagan uv run alembic upgrade head'

check deny 'psql -d overklagan -c "SELECT 1" -c "DROP TABLE entities"'
check deny 'psql -h db.example.com -d overklagan_test -c "TRUNCATE documents"'
check deny 'psql -d overklagan -c "\copy documents to stdout"'
check deny 'psql --dbname overklagan -c "VACUUM FULL"'
check deny 'psql -d overklagan -c "SELECT 1" ; psql -d overklagan -c "DELETE FROM entities"'
check deny 'psql -d overklagan -c "DELETE FROM entities" || true'
check deny 'psql -doverklagan -c "UPDATE documents SET raw_text = NULL"'

# --- Must be allowed ---------------------------------------------------------

check allow 'psql -d overklagan -c "SELECT count(*) FROM documents"'
check allow 'psql -d overklagan -tAc "\dt"'
check allow 'psql -d overklagan_coding_agent -c "DELETE FROM entities"'
check allow 'psql -d overklagan_test -c "TRUNCATE documents"'
check allow 'psql -c "DELETE FROM entities"'
check allow 'createdb -T overklagan overklagan_coding_agent'
check allow 'uv run pytest packages/shared'
check allow 'git status'
check allow 'psql -d overklagan -tAc "SELECT 1 FROM pg_database WHERE datname = '"'"'overklagan'"'"'"'
check allow "psql -d 'overklagan' -c 'SELECT 1'"
check allow 'PGDATABASE=overklagan_test psql -c "DELETE FROM documents"'
check allow 'pg_dump overklagan > backup.sql'
check allow 'psql -d overklagan -c "EXPLAIN SELECT * FROM documents"'
check allow 'grep -rn psql .claude/hooks'
check allow 'psql -d overklagan_coding_agent -f seed.sql'
# Prose that merely mentions the tools — including quoting shlex cannot parse,
# which is what an apostrophe in a commit message does.
check allow 'git commit -m "psql and createdb now go through the sandbox"'
check allow "git commit -m \"reads .env's DATABASE_URL, then runs createdb -T\""
check allow "echo \"the guard's psql resolver\" >> notes.md"

printf '\n%d passed, %d failed\n' "$passed" "$failed"
(( failed == 0 ))
