#!/usr/bin/env bash
# Stop hook — advisory.
# Runs a project-wide type check when the turn ends and reports errors as
# context rather than as a blocking error. Always exits 0.
#
# NOTE: additionalContext on Stop continues the conversation so Claude can act
# on the feedback. It is softer than exit 2, but it is not silent. For a report
# that only you see and that never extends the turn, replace the jq block with:
#     printf '%s\n' "$body" >&2 ; exit 1
#
# Install: .claude/hooks/py-typecheck.sh   (chmod +x)
# Requires: jq, uv

set -uo pipefail

input=$(cat)

# Loop guard. Without this, a persistent error keeps re-extending the turn.
[[ "$(jq -r '.stop_hook_active // false' <<<"$input")" == "true" ]] && exit 0

command -v uv >/dev/null 2>&1 || exit 0

cd "${CLAUDE_PROJECT_DIR:-.}" || exit 0

# Skip the whole check when the working tree has no Python changes.
if git rev-parse --git-dir >/dev/null 2>&1; then
  [[ -z "$(git status --porcelain -- '*.py' 2>/dev/null)" ]] && exit 0
fi

# Clean — say nothing, let the turn end.
out=$(uvx ty check 2>&1) && exit 0
[[ -z "$out" ]] && exit 0

body=$(printf '%s' "$out" | head -n 60)
jq -n --arg body "$body" '{
  hookSpecificOutput: {
    hookEventName: "Stop",
    additionalContext: ("ty reports type errors in the current working tree:\n" + $body)
  }
}'

exit 0
