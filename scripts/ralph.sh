#!/usr/bin/env bash
set -euo pipefail

# --- Helpers ---

usage() {
  cat <<EOF
Usage: ralph.sh <story_id> [-e INSTRUCTIONS] [-f FILE] [-i] [--verbose]

Run Claude Code for each pending task in an ATM story, sequentially.
Maintains a growing implementation notes file (~200 lines) passed between tasks.

Arguments:
  story_id                            Story UUID or sequence number

Options:
  -e, --extra-instructions TEXT       Extra instructions appended to each task prompt
  -f, --extra-instructions-file PATH  File whose content is appended to each task prompt
  -i, --interactive                   Run Claude in interactive mode (default: non-interactive)
  --verbose                           Pass --verbose to each Claude invocation
  -h, --help                          Show this help
EOF
  exit "${1:-0}"
}

err() {
  echo "Error: $*" >&2
  exit 1
}

# --- Prerequisites ---

for cmd in jq atm claude; do
  command -v "$cmd" >/dev/null 2>&1 || err "'$cmd' not found on PATH"
done

# --- Parse args ---

story_id=""
extra_instructions=""
verbose=false
interactive=false

while [[ $# -gt 0 ]]; do
  case "$1" in
    -e | --extra-instructions)
      if [[ $# -lt 2 ]]; then err "--extra-instructions requires a value"; fi
      extra_instructions="$2"
      shift 2
      ;;
    -f | --extra-instructions-file)
      if [[ $# -lt 2 ]]; then err "--extra-instructions-file requires a value"; fi
      if [[ ! -f "$2" ]]; then err "File not found: $2"; fi
      extra_instructions="$(cat "$2")"
      shift 2
      ;;
    -i | --interactive)
      interactive=true
      shift
      ;;
    --verbose)
      verbose=true
      shift
      ;;
    -h | --help)
      usage 0
      ;;
    -*)
      err "Unknown option: $1"
      ;;
    *)
      if [[ -n "$story_id" ]]; then err "Unexpected argument: $1"; fi
      story_id="$1"
      shift
      ;;
  esac
done

if [[ -z "$story_id" ]]; then
  echo "Missing story_id"
  usage 1
fi

# --- Read project ID ---

if [[ ! -f ".atm_project_id" ]]; then
  err ".atm_project_id not found in current directory"
fi
ATM_PROJECT_ID="$(cat .atm_project_id)"
export ATM_PROJECT_ID

# --- Get pending tasks ---

story_json="$(atm stories get "$story_id")"
pending_json="$(printf '%s' "$story_json" | jq -c '[.tasks[] | select(.status != "completed")]')"
count="$(printf '%s' "$pending_json" | jq 'length')"

if [[ "$count" -eq 0 ]]; then
  echo "No pending tasks found."
  exit 0
fi

echo "Found $count pending task(s)."

# --- Notes file (deterministic per project+story, persists across re-runs) ---

notes_file="/tmp/ralph-notes-${ATM_PROJECT_ID:0:8}-${story_id}.md"
if [[ ! -f "$notes_file" ]]; then
  touch "$notes_file"
  echo "Notes file: $notes_file (new)"
else
  note_lines="$(wc -l <"$notes_file")"
  echo "Notes file: $notes_file (${note_lines} lines)"
fi

# --- Temp file cleanup ---

tmp_md=""
tmp_prompt=""

cleanup() {
  if [[ -n "$tmp_md" && -f "$tmp_md" ]]; then rm -f "$tmp_md"; fi
  if [[ -n "$tmp_prompt" && -f "$tmp_prompt" ]]; then rm -f "$tmp_prompt"; fi
}
trap cleanup EXIT

# --- Process each task sequentially ---

i=0
while IFS= read -r task; do
  i=$((i + 1))
  task_id="$(printf '%s' "$task" | jq -r '.id')"
  title="$(printf '%s' "$task" | jq -r '.title')"

  echo ""
  echo "[$i/$count] Task: $title"

  # Get rendered task export from ATM
  tmp_md="$(mktemp /tmp/ralph-task-XXXXXX.md)"
  atm admin tasks dispatch "$task_id" --output "$tmp_md"

  # Read current notes (may be empty on first task)
  notes_content=""
  if [[ -s "$notes_file" ]]; then
    notes_content="$(cat "$notes_file")"
  fi

  # Build prompt
  tmp_prompt="$(mktemp /tmp/ralph-prompt-XXXXXX.txt)"
  {
    printf 'You are a build agent dispatched to work on ONE specific task.\n'
    printf 'IMPORTANT: Work only on the task below. Do NOT run `atm completions active`.\n'
    printf 'Do NOT discover or work on any other tasks. Your scope is strictly this single task.\n\n'
    cat "$tmp_md"

    # Story implementation notes — context from previous tasks
    printf '\n\n---\n\n'
    printf '## Story Implementation Notes\n\n'
    if [[ -n "$notes_content" ]]; then
      printf '%s\n' "$notes_content"
    else
      printf '_(No notes yet — this is the first task in this story.)_\n'
    fi
    printf '\nThese notes were captured from previous tasks in this story. Read them for context before starting work.\n'

    # Instruction to update the notes after completing
    printf '\n\n---\n\n'
    printf 'Workflow\n\n'
    printf '1. Use the atm-cli to mark the task as started\n'
    printf '2. Rely on the task instructions you have already been given first hand. Only explore the codebase if you have verified you need more information\n'
    printf '3. Think careful about how you will implment the solution. You should prefer the task and steps given to you, but if the prerequisites and enviroment have changed you may deviate.\n'
    printf '4. Adhere to the coding guidlines from the coding guidlines skill and always use uv from the uv skill when working with python\n'
    printf '5. Verify the DoD. If anything else is broken you will fix that as well\n'
    printf '6. When all test and linting passes you can first make a desriptive commit. IMPORTANT keep to the current branch unless otherwise instructed\n'
    printf '7. Update any relevant documentation. Be careful what you add to the documentation, the documentation should be kept to the point and not contain unnessecary information\n'
    printf '8. Mark the task as completed using atm cli\n'
    printf '9. Note updates (Required)\n'
    printf 'After completing the task %s\n\n' "$notes_file"
    printf 'Guidelines:\n'
    printf '%s\n' \
      '- Read the existing content first' \
      '- Add important decisions, patterns, gotchas, and insights from this task' \
      '- Consolidate and trim to stay around 200 lines of markdown' \
      '- Keep the most recent and actionable information' \
      '- Write the complete updated file (not just the additions)'

    if [[ -n "$extra_instructions" ]]; then
      printf '\n\n---\n\n%s' "$extra_instructions"
    fi
  } >"$tmp_prompt"

  # Build Claude args
  if [[ "$interactive" == true ]]; then
    claude_args=()
    if [[ "$verbose" == true ]]; then claude_args+=(--verbose); fi
  else
    claude_args=(-p --permission-mode bypassPermissions --verbose --output-format stream-json)
  fi
  claude_args+=(--model claude-sonnet-4-6)
  claude_args+=(--effort xhigh)

  if [[ "$interactive" == true ]]; then
    if ! claude "${claude_args[@]}" "$(cat "$tmp_prompt")"; then
      echo "" >&2
      err "Claude exited with non-zero status on task $task_id — aborting"
    fi
  else
    if ! claude "${claude_args[@]}" "$(cat "$tmp_prompt")" | \
      jq --unbuffered -rj 'if .type == "assistant" then (.message.content[]? | select(.type == "text") | .text) elif .type == "result" then "\n" else empty end' 2>/dev/null; then
      echo "" >&2
      err "Claude exited with non-zero status on task $task_id — aborting"
    fi
  fi

  # Clean up this iteration's temp files
  rm -f "$tmp_md" "$tmp_prompt"
  tmp_md=""
  tmp_prompt=""

done < <(printf '%s' "$pending_json" | jq -c '.[]')

echo ""
echo "All tasks processed."
echo "Notes file: $notes_file"
