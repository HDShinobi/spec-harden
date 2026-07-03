#!/usr/bin/env bash
# spec-harden installer.
#   ./install.sh                     # global: Claude author skill + CLAUDE.md auto-hook (once)
#   ./install.sh --project <path>    # per-project: Gemini critic skill in <path>/.agents/skills
set -euo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CLAUDE_SKILLS="$HOME/.claude/skills"
CLAUDE_MD="$HOME/.claude/CLAUDE.md"
HOOK_MARKER="<!-- spec-harden-auto-hook -->"

install_global() {
  mkdir -p "$CLAUDE_SKILLS"
  ln -sfn "$REPO/claude-skill" "$CLAUDE_SKILLS/spec-harden"
  echo "linked: $CLAUDE_SKILLS/spec-harden -> $REPO/claude-skill"

  if [ -f "$CLAUDE_MD" ] && grep -q "$HOOK_MARKER" "$CLAUDE_MD"; then
    echo "auto-hook already present in $CLAUDE_MD"
  else
    cat >> "$CLAUDE_MD" <<EOF

$HOOK_MARKER
## spec-harden auto-hook
After the \`superpowers:brainstorming\` skill writes and commits a spec, and BEFORE presenting
the user-review gate, invoke the \`spec-harden\` skill (\`init\`) on that spec, then tell the user
to run the Gemini turn in Antigravity. Only present the spec for approval once the loop has
converged (or the user opts out).
EOF
    echo "appended auto-hook to $CLAUDE_MD"
  fi
  echo
  echo "Global install done. To enable the Gemini critic in a project, run:"
  echo "  $REPO/install.sh --project /path/to/your/project"
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
