# spec-harden

A cross-tool **adversarial spec-review loop**. One model writes and defends a spec (the
**author**); a *different* model family critiques it (the **critic**). They exchange files in a
`harden/` folder and iterate until a round surfaces no new blocker/major finding — then the
hardened draft is promoted to the real spec on your confirmation.

- **Author** — Claude Code (owns the spec, adjudicates ACCEPT/REBUT, edits the draft).
- **Primary critic** — Gemini, run interactively inside [Antigravity](https://antigravity.google).
- **Secondary critic** *(optional)* — a fresh Claude subagent, one automatic pre-pass.

## Why a different-model critic?

A model reviewing its own output shares its own blind spots (self-preference bias; correlated
errors in same-model debate). A critic from a *different* family catches gaps the author can't
see — the same reason forwarding a spec to another model surfaces new issues. See
[`docs/design.md`](docs/design.md) for the evidence and prior art.

> **Why manual handoff (not a headless loop)?** Consumer Gemini Pro cannot be driven headlessly
> — the standalone Gemini CLI's free tier is discontinued, and the Antigravity SDK still needs a
> raw API key. The only zero-marginal-cost way to use the Gemini you already pay for is
> *interactively in Antigravity*. So you drive the turns; the filesystem is the message bus. The
> file protocol is designed so a driver script could later replace the human turn-taking without
> changing the format.

## Requirements

- [Claude Code](https://claude.com/claude-code) (the author skill).
- [Antigravity](https://antigravity.google) with a signed-in Gemini account (the critic skill).
- Python 3 (stdlib only — no third-party packages).

## Install

Clone, then run the installer.

```bash
git clone https://github.com/HDShinobi/spec-harden.git
cd spec-harden

# 1) Global (once): installs the Claude author skill + a CLAUDE.md auto-hook
./install.sh

# 2) Per project: installs the Gemini critic skill into a project's .agents/skills
./install.sh --project /path/to/your/project
```

Both use symlinks back to the clone, so `git pull` updates every install at once.

## Usage (the loop)

| Step | Where | What |
|------|-------|------|
| **init** | Claude Code | `/spec-harden [spec-path] [--critic-model opus\|sonnet\|haiku\|fable]` — creates `<name>.harden/`, copies the spec to `draft.md`, lints it, optionally runs the Claude-critic pre-pass, sets turn = gemini |
| **critique** | Antigravity | run the `spec-harden` skill → Gemini reads `draft.md`, writes `rN.gemini.md`, flips turn = claude |
| **respond** | Claude Code | `/spec-harden` → Claude adjudicates ACCEPT/REBUT, edits `draft.md`, writes `rN.claude.md`, checks convergence |
| repeat | | critique → respond … until converged |
| **finalize** | Claude Code | on your confirmation → promotes `draft.md` to the real spec, writes `SUMMARY.md`, commits |

Flags: omit `--critic-model` to skip the Claude pre-pass and let Gemini lead alone. Omit the
spec path to target the most recently modified `*.md` in `docs/superpowers/specs/`.

## The `harden/` folder

```
<name>.harden/
  PROTOCOL.md          # the shared contract both skills obey
  draft.md             # working draft — Claude edits; the real spec is untouched until finalize
  r0.claude-critic.md  # optional secondary-critic pre-pass log
  rN.gemini.md         # round N critic findings (Gemini)
  rN.claude.md         # round N author adjudication (Claude)
  STATUS.md            # turn / round / converged / target_spec_path
  SUMMARY.md           # written at finalize
```

Findings are severity-tagged (`blocker`/`major` block convergence; `minor`/`nit` are logged) and
reviewed through five lenses: **Completeness, Testability, Ambiguity, Assumptions, Scope**.
Convergence = a critic round with 0 open blocker/major and no newly-raised ones; a circuit-breaker
stops ping-ponging and `MAX_ROUNDS = 4` caps thrash. Full contract in
[`claude-skill/references/PROTOCOL.md`](claude-skill/references/PROTOCOL.md).

## Tests

```bash
python3 tests/test_lint.py -v        # deterministic linter
python3 tests/test_protocol.py -v    # findings/header/status/convergence parser
bash    tests/test_e2e.sh            # simulated full cycle (no Antigravity/LLM needed)
```

## How it was built

Dogfooded on its own spec: the loop ran on `docs/design.md` and converged in 3 rounds, with the
Gemini critic surfacing 3 major + 4 minor gaps the author had missed — all fixed. See
[`docs/plan.md`](docs/plan.md) for the TDD implementation plan.

## License

MIT — see [LICENSE](LICENSE).
