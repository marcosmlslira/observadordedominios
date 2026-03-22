#!/usr/bin/env bash
set -euo pipefail

SKILL_DIR="${1:-.}"

if [[ ! -f "$SKILL_DIR/SKILL.md" ]]; then
  echo "Error: SKILL.md not found in $SKILL_DIR" >&2
  exit 1
fi

echo "Basic validation passed: found $SKILL_DIR/SKILL.md"
echo "Recommended external validation command:"
echo "  skills-ref validate $SKILL_DIR"
