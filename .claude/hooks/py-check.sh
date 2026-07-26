#!/usr/bin/env bash
# PostToolUse hook — advisory, read-only.
# Lints the single .py file Claude just touched and reports findings as
# context. Never writes to the file. Never blocks. Always exits 0.
#
# Install: .claude/hooks/py-check.sh   (chmod +x)
# Requires: jq, uv

set -uo pipefail

input=$(cat)
file=$(jq -r '.tool_input.file_path // empty' <<<"$input")

# Belt and braces — the `if` filter in settings.json should already guarantee this.
[[ "$file" == *.py ]] || exit 0
[[ -f "$file" ]] || exit 0

# Degrade quietly on a machine without uv rather than erroring on every edit.
command -v uv >/dev/null 2>&1 || exit 0

# Clean — say nothing.
out=$(uvx ruff check --output-format concise "$file" 2>/dev/null) && exit 0
[[ -z "$out" ]] && exit 0

# Phrased as a factual report. Imperative, system-command-shaped text here can
# trip Claude's prompt-injection defenses and get surfaced to you instead.
# Findings marked [*] are ones `ruff check --fix` could resolve automatically.
body=$(printf '%s' "$out" | head -n 40)
jq -n --arg file "$file" --arg body "$body" '{
  hookSpecificOutput: {
    hookEventName: "PostToolUse",
    additionalContext: ("ruff reports lint findings in " + $file + ":\n" + $body)
  }
}'

exit 0
