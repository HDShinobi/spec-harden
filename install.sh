#!/usr/bin/env bash
# spec-harden installer.
#   ./install.sh                     # global: Claude author skill + CLAUDE.md auto-hook (once)
#   ./install.sh --project <path>    # per-project: Gemini critic skill in <path>/.agents/skills
set -euo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CLAUDE_SKILLS="$HOME/.claude/skills"
CLAUDE_MD="$HOME/.claude/CLAUDE.md"
CONFIG="$HOME/.spec-harden.json"
HOOK_MARKER="<!-- spec-harden-auto-hook -->"

install_global() {
  mkdir -p "$CLAUDE_SKILLS"
  ln -sfn "$REPO/claude-skill" "$CLAUDE_SKILLS/spec-harden"
  echo "linked: $CLAUDE_SKILLS/spec-harden -> $REPO/claude-skill"

  # Seed the settings file (model / effort / final_verify) if the user has none yet.
  if [ -f "$CONFIG" ]; then
    echo "settings already present: $CONFIG"
  else
    cp "$REPO/.spec-harden.example.json" "$CONFIG"
    echo "created settings: $CONFIG (edit critic_model / critic_effort / final_verify here)"
  fi

  if [ -f "$CLAUDE_MD" ] && grep -q "$HOOK_MARKER" "$CLAUDE_MD"; then
    echo "auto-hook already present in $CLAUDE_MD"
  else
    cat >> "$CLAUDE_MD" <<EOF

$HOOK_MARKER
## spec-harden auto-hook
After the \`superpowers:brainstorming\` skill writes and commits a spec, and BEFORE presenting
the user-review gate, invoke the \`spec-harden\` skill on that spec. spec-harden runs a fully
automatic loop — Codex (GPT, via \`codex exec\`) is the primary critic and Claude drives the
author⇄critic loop hands-free (Gemini is only an opt-in \`--final-verify\`). Model/effort come
from \`~/.spec-harden.json\`. If brainstorming wrote more than one spec, ask which to harden.
Only present the spec for approval once the loop has converged (or the user opts out).
EOF
    echo "appended auto-hook to $CLAUDE_MD"
  fi

  if ! command -v codex >/dev/null 2>&1; then
    echo
    echo "WARNING: \`codex\` CLI not found on PATH — the automatic critic needs it."
    echo "  npm install -g @openai/codex   &&   codex login   (sign in to your ChatGPT account)"
  fi
  echo
  echo "Global install done. Run:  /spec-harden <spec-path>   (no flags needed)."
  echo "Optional Gemini final-verify in a project:  $REPO/install.sh --project /path/to/project"
}

install_project() {
  local proj="$1"
  [ -d "$proj" ] || { echo "error: no such directory: $proj" >&2; exit 1; }
  proj="$(cd "$proj" && pwd)"
  mkdir -p "$proj/.agents/skills"
  ln -sfn "$REPO/gemini-skill" "$proj/.agents/skills/spec-harden"
  echo "linked: $proj/.agents/skills/spec-harden -> $REPO/gemini-skill"
  echo "Open this project in Antigravity; /skills should list 'spec-harden'."
}

case "${1:-}" in
  --project) shift; install_project "${1:?usage: install.sh --project <path>}" ;;
  ""|--global) install_global ;;
  -h|--help) sed -n '2,4p' "$0" ;;
  *) echo "usage: install.sh [--global] | --project <path>" >&2; exit 2 ;;
esac
