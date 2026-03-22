#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SKILL_FILE="$ROOT_DIR/SKILL.md"

if [[ ! -f "$SKILL_FILE" ]]; then
  echo "SKILL.md not found"
  exit 1
fi

if ! grep -q '^---$' "$SKILL_FILE"; then
  echo "Missing YAML frontmatter delimiters"
  exit 1
fi

if ! grep -q '^name:' "$SKILL_FILE"; then
  echo "Missing required frontmatter field: name"
  exit 1
fi

if ! grep -q '^description:' "$SKILL_FILE"; then
  echo "Missing required frontmatter field: description"
  exit 1
fi

echo "Basic validation passed for $SKILL_FILE"
