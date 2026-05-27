#!/usr/bin/env bash
set -euo pipefail

if [[ $# -lt 2 ]]; then
  echo "Usage: start-adr.sh <number> <short-name> [title]" >&2
  echo "Example: start-adr.sh 001 gateway-remote-boundary \"Gateway Remote Boundary\"" >&2
  exit 1
fi

NUM="$1"
NAME="$2"
TITLE="${3:-$NAME}"

if [[ ! "$NAME" =~ ^[a-z0-9]([a-z0-9-]*[a-z0-9])?$ ]]; then
  echo "ERROR: Invalid name '$NAME'. Use lowercase letters, numbers, and hyphens only." >&2
  exit 1
fi

PADDED=$(printf "%03d" "$((10#$NUM))")
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../../../" && pwd)"
SKILL_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
TODAY=$(date +%Y-%m-%d)

DECISIONS_DIR="$ROOT/docs/decisions"
RESEARCH_DIR="$DECISIONS_DIR/research"
ADR_FILE="$DECISIONS_DIR/adr-${PADDED}-${NAME}.md"
PROMPT_FILE="$RESEARCH_DIR/adr-${PADDED}-${NAME}-research-prompt.md"
SYNTHESIS_FILE="$RESEARCH_DIR/adr-${PADDED}-${NAME}-final-synthesis.md"

if [[ -e "$ADR_FILE" ]]; then
  echo "ERROR: $ADR_FILE already exists" >&2
  exit 1
fi

mkdir -p "$RESEARCH_DIR"

escape_sed_replacement() {
  printf '%s' "$1" | sed 's/[\/&]/\\&/g'
}

ESCAPED_TITLE=$(escape_sed_replacement "$TITLE")

sed -e "s/NNN/${PADDED}/g" -e "s/TITLE/${ESCAPED_TITLE}/g" \
  "$SKILL_DIR/templates/adr.md" > "$ADR_FILE"
sed -e "s/NNN/${PADDED}/g" -e "s/TITLE/${ESCAPED_TITLE}/g" -e "s/CREATED_DATE/${TODAY}/g" \
  "$SKILL_DIR/templates/research-prompt.md" > "$PROMPT_FILE"
sed -e "s/NNN/${PADDED}/g" -e "s/TITLE/${ESCAPED_TITLE}/g" \
  "$SKILL_DIR/templates/final-synthesis.md" > "$SYNTHESIS_FILE"

echo "Created:"
echo "  $ADR_FILE"
echo "  $PROMPT_FILE"
echo "  $SYNTHESIS_FILE"
