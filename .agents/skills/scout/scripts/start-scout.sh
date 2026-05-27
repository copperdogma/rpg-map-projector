#!/usr/bin/env bash
set -euo pipefail

if [[ $# -lt 2 ]]; then
  echo "Usage: start-scout.sh <number> <slug> [title]" >&2
  echo "Example: start-scout.sh 001 projector-camera-hardware-baseline \"Projector Camera Hardware Baseline\"" >&2
  exit 1
fi

NUM="$1"
SLUG="$2"
TITLE="${3:-$SLUG}"

if [[ ! "$SLUG" =~ ^[a-z0-9]([a-z0-9-]*[a-z0-9])?$ ]]; then
  echo "ERROR: Invalid slug '$SLUG'. Use lowercase letters, numbers, and hyphens only." >&2
  exit 1
fi

PADDED=$(printf "%03d" "$((10#$NUM))")
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../../../" && pwd)"
SKILL_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
TODAY=$(date +%Y-%m-%d)
SCOUT_FILE="$ROOT/docs/scout/scout-${PADDED}-${SLUG}.md"

if [[ -e "$SCOUT_FILE" ]]; then
  echo "ERROR: $SCOUT_FILE already exists" >&2
  exit 1
fi

mkdir -p "$ROOT/docs/scout"

escape_sed_replacement() {
  printf '%s' "$1" | sed 's/[\/&]/\\&/g'
}

sed \
  -e "s/NNN/${PADDED}/g" \
  -e "s/TITLE/$(escape_sed_replacement "$TITLE")/g" \
  -e "s/SOURCE/{source or question}/g" \
  -e "s/CREATED_DATE/${TODAY}/g" \
  -e "s/SCOPE/{scope}/g" \
  "$SKILL_DIR/templates/scout.md" > "$SCOUT_FILE"

echo "Created:"
echo "  $SCOUT_FILE"
