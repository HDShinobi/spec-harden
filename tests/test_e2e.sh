#!/usr/bin/env bash
# Simulates one full spec-harden cycle using the scripts directly (no LLM/Codex call):
# init -> (fake Codex round with 1 major) -> author resolves -> (fake clean round) -> converged.
# The real Codex critic turn is exercised separately by tests/test_codex_critic.py.
set -euo pipefail
SCRIPTS="$(cd "$(dirname "${BASH_SOURCE[0]}")/../claude-skill/scripts" && pwd)"
WORK="$(mktemp -d)"; trap 'rm -rf "$WORK"' EXIT
H="$WORK/demo.harden"; mkdir -p "$H"

# init artifacts
printf '# Demo Spec\n\nThe cache TTL is 5 minutes.\n\n## Design\n\nConcrete detail.\n' > "$H/draft.md"
python3 "$SCRIPTS/lint.py" "$H/draft.md" >/dev/null && echo "lint: clean"
python3 "$SCRIPTS/protocol.py" status-write "$H" claude 1 false

# round 1: fake Codex finds one major
cat > "$H/r1.codex.md" <<'EOF'
ROUND: 1
AUTHOR: codex
READS: draft.md
VERDICT: needs-work
OPEN_BLOCKERS: 0
OPEN_MAJORS: 1

[SEVERITY: major]
LENS: completeness
LOCATION: Design
ISSUE: No cache eviction policy defined
SUGGESTION: Specify LRU with max size
EOF
python3 "$SCRIPTS/protocol.py" findings "$H/r1.codex.md" >/dev/null && echo "r1 parse: ok"
python3 "$SCRIPTS/protocol.py" converged "$H/r1.codex.md" && echo "BUG: should not be converged" && exit 1 || echo "r1: not converged (correct)"

# author accepts -> edits draft, advances round
printf '\n## Eviction\n\nLRU, max 128 entries.\n' >> "$H/draft.md"
python3 "$SCRIPTS/protocol.py" status-write "$H" claude 2 false

# round 2: fake Codex clean
cat > "$H/r2.codex.md" <<'EOF'
ROUND: 2
AUTHOR: codex
READS: draft.md, r1.claude.md
VERDICT: converged
OPEN_BLOCKERS: 0
OPEN_MAJORS: 0
EOF
python3 "$SCRIPTS/protocol.py" converged "$H/r2.codex.md" && echo "r2: converged (correct)"

# finalize: promote draft (simulated)
cp "$H/draft.md" "$WORK/demo-spec.md"
grep -q "Eviction" "$WORK/demo-spec.md" && echo "finalize: promoted OK"
echo "E2E PASS"
