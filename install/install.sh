#!/usr/bin/env bash
# agent-boss installer for macOS / Linux / WSL / Git Bash.
#   From a clone:   bash install/install.sh
#   One-liner:      curl -fsSL https://raw.githubusercontent.com/tientv2026/Claude_Agent_bot/main/install/install.sh | bash
set -euo pipefail

REPO="${AGENT_BOSS_REPO:-tientv2026/Claude_Agent_bot}"
REF="${AGENT_BOSS_REF:-main}"
DEST="${CLAUDE_CONFIG_DIR:-$HOME/.claude}/skills/boss"
FILES="SKILL.md scripts/orch.py"

src_dir=""
if [ -n "${BASH_SOURCE[0]:-}" ] && [ -f "$(dirname "${BASH_SOURCE[0]}")/../skills/boss/SKILL.md" ]; then
  src_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")/../skills/boss" && pwd)"
fi

mkdir -p "$DEST/scripts"
for f in $FILES; do
  if [ -n "$src_dir" ]; then
    cp "$src_dir/$f" "$DEST/$f"
  else
    curl -fsSL "https://raw.githubusercontent.com/$REPO/$REF/skills/boss/$f" -o "$DEST/$f"
  fi
done
chmod +x "$DEST/scripts/orch.py"
echo "Installed /boss skill -> $DEST"

PY="$(command -v python3 || command -v python || true)"
if [ -z "$PY" ]; then
  echo "Python 3.9+ is required: https://www.python.org/downloads/" >&2
  exit 1
fi
"$PY" "$DEST/scripts/orch.py" doctor || true
echo
echo "Done. In Claude Code, open your project and type:  /boss <what to build>"
