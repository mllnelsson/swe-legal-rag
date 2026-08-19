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

# --- Through a container ------------------------------------------------------
#
# On a host with no Postgres client this is the only way to reach the database,
# so every rule above has to hold when the command is wrapped in `docker exec`.

check deny 'docker exec church-legal-db-db-1 psql -U postgres -d overklagan -c "DELETE FROM documents"'
check deny 'docker compose exec db psql -d overklagan -c "TRUNCATE documents"'
check deny 'docker compose -f docker-compose.yml exec -T db psql -d overklagan -c "DROP TABLE entities"'
check deny 'docker exec -e PGDATABASE=overklagan church-legal-db-db-1 psql -c "INSERT INTO entities VALUES (1)"'
check deny 'docker compose exec db dropdb overklagan'
check deny 'docker exec db sh -c "psql -d overklagan -c \"DROP TABLE entities\""'
check deny 'docker compose run --rm db psql -d overklagan -c "UPDATE documents SET raw_text = NULL"'
check deny 'docker exec church-legal-db-db-1 pg_restore -d overklagan backup.dump'
check deny 'docker exec church-legal-db-db-1 psql -U postgres -d overklagan -f cleanup.sql'
check deny 'podman exec church-legal-db-db-1 psql -d overklagan -c "DELETE FROM entities"'

# The host's PGDATABASE names the sandbox, but it is not set inside the
# container — an unnamed database there is the *development* one, so the guard
# must not read this as a write to the scratch copy.
check deny 'docker exec church-legal-db-db-1 psql -U postgres -c "DELETE FROM documents"'

# A tool behind a wrapper the unwrapper does not model still has to fail closed.
check deny 'docker exec church-legal-db-db-1 env psql -d overklagan -c "DELETE FROM documents"'

# Option forms that shift where the container name sits. Miscounting by one
# unwraps the wrong argument list, so each of these is a parser regression test.
check deny 'docker exec -it church-legal-db-db-1 psql -d overklagan -c "DELETE FROM documents"'
check deny 'docker exec --user postgres church-legal-db-db-1 psql -d overklagan -c "DELETE FROM documents"'
check deny 'docker exec -w /tmp db psql -d overklagan -c "TRUNCATE documents"'
check deny 'docker exec -e FOO=bar -e PGDATABASE=overklagan db psql -c "DELETE FROM documents"'
check deny 'echo "DELETE FROM documents" | docker exec -i db psql -d overklagan'
check allow 'docker exec -it church-legal-db-db-1 psql -d overklagan_coding_agent -c "DELETE FROM documents"'

check allow 'docker exec church-legal-db-db-1 psql -U postgres -d overklagan -c "SELECT count(*) FROM chunks"'
check allow 'docker exec church-legal-db-db-1 psql -U postgres -d overklagan -tAc "\dt"'
check allow 'docker exec church-legal-db-db-1 psql -U postgres -d overklagan_coding_agent -c "DELETE FROM documents"'
check allow 'docker compose exec -T db psql -U postgres -d overklagan_test -c "TRUNCATE documents"'
check allow 'docker compose exec db createdb -U postgres -T overklagan overklagan_coding_agent'
check allow 'docker exec church-legal-db-db-1 pg_dump -U postgres overklagan'

# Ordinary container work names no database and must stay out of the way.
check allow 'docker compose up -d db'
check allow 'docker compose down'
check allow 'docker ps -a'
check allow 'docker exec church-legal-db-db-1 cat /var/lib/postgresql/data/PG_VERSION'
check allow 'docker inspect church-legal-db-db-1'
check allow 'docker compose logs db'

printf '\n%d passed, %d failed\n' "$passed" "$failed"
(( failed == 0 ))
