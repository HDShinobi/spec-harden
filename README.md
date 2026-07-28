# spec-harden

A cross-model **adversarial spec-review loop**. One model writes and defends a spec (the
**author**); a *different* model family critiques it (the **critic**). They exchange files in a
`harden/` folder and iterate until a round surfaces no new blocker/major finding — then the
hardened draft is promoted to the real spec on your confirmation.

- **Author / orchestrator** — Claude Code (owns the spec, runs the loop, adjudicates
  ACCEPT/REBUT, edits the draft).
- **Primary critic** — **Codex (GPT), run headless via `codex exec`.** Claude invokes it every
  round, so the whole loop is **automatic** — no human handoff.
- **Final-verify critic** *(optional, opt-in)* — one extra cross-check after the Codex loop
  converges, by a *different* reviewer: a fresh Claude subagent
  (`--final-verify sonnet|opus|haiku|fable`) or Gemini in Antigravity (`--final-verify gemini`).

## Why a different-model critic?

A model reviewing its own output shares its own blind spots (self-preference bias; correlated
errors in same-model debate). A critic from a *different* family catches gaps the author can't
see — the same reason forwarding a spec to another model surfaces new issues. See
[`docs/design.md`](docs/design.md) for the evidence and prior art.

> **Why Codex as the automatic critic?** Codex (via the `codex exec` CLI) runs headless against
> your logged-in ChatGPT account, so the entire author⇄critic loop runs hands-free in one Claude
> session. (Earlier versions used Gemini as the primary critic, but consumer Gemini can't be
> driven headlessly, forcing a manual Antigravity handoff each round — Gemini is now an optional
> *final-verify* step instead.) We call `codex exec` directly, not the `/codex` Claude-Code
> plugin's app-server, because that app-server pins an older client version and rejects current
> models.

## Requirements

- [Claude Code](https://claude.com/claude-code) (the author/orchestrator skill).
- [Codex CLI](https://github.com/openai/codex) signed in to a ChatGPT account
  (`npm install -g @openai/codex` && `codex login`).
- *(Optional)* [Antigravity](https://antigravity.google) with a signed-in Gemini account — only
  for `--final-verify gemini`.
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

### The auto-hook is gated

The global install appends a CLAUDE.md hook that fires after `superpowers:brainstorming` writes
a spec. Because every round costs a full `codex exec` pass, the hook is **not** meant to run on
every spec — it only fires when the spec meets at least one of:

- it changes an **interface other code depends on** — a public API, a data contract, a protocol,
  a file format read elsewhere, or
- it changes **stored data** — schema, migration, cache format, file format (getting this wrong
  loses user data), or
- it changes **money, entitlement, or a system permission**.

Gate on *consequence of being wrong*, not on spec length: a one-file migration deserves the loop,
a five-file UI polish usually doesn't. That is why none of the three criteria counts files — a
size proxy fires on the wide-but-harmless spec and stays silent on the narrow-but-fatal one.

When the gate is not met, nothing else about the flow changes: brainstorming goes on to its user
review gate and then to `writing-plans`, exactly as it would without this hook installed. You can
always run the loop by hand with `/spec-harden <path>` regardless of the gate.

## Usage (the loop)

Run it once in Claude Code — the loop runs automatically to convergence:

```
/spec-harden [spec-path] [--critic-model gpt-5.6-terra] [--critic-effort medium] \
             [--depth spec|design] [--final-verify sonnet|opus|haiku|fable|gemini]
```

| Step | What (all in Claude Code, automatic) |
|------|--------------------------------------|
| **init** | creates `<name>.harden/`, copies the spec to `draft.md`, lints it |
| **loop** | each round: `codex exec` critiques `draft.md` → `rN.codex.md`; Claude adjudicates ACCEPT/REBUT, edits `draft.md`, writes `rN.claude.md`, checks convergence. Repeats up to `MAX_ROUNDS = 4`. |
| **final-verify** *(opt-in)* | one extra cross-check by a different reviewer (Claude subagent, or Gemini in Antigravity) |
| **finalize** | on your confirmation → promotes `draft.md` to the real spec, writes `SUMMARY.md`, commits |

In the common case you pass **no flags at all** — `/spec-harden <spec-path>` uses the configured
Codex model automatically. Omit the spec path too to target the most recently modified `*.md` in
`docs/superpowers/specs/`.

### Settings — `~/.spec-harden.json`

Change the model / effort / final-verify **once** here instead of typing flags each run:

```jsonc
{
  "critic_model": "gpt-5.6-terra",   // any model your ChatGPT account supports (gpt-5.6-sol, gpt-5.5, …)
  "critic_effort": "medium",         // low | medium | high | xhigh
  "depth": "spec",                   // spec = spec-quality only | design = also challenge the approach
  "final_verify": "off"              // off | sonnet | opus | haiku | fable | gemini
}
```

**`depth`** is the interesting knob. `spec` (default) critiques *how the spec is written* —
completeness, testability, ambiguity, assumptions, scope. `design` adds a sixth **Design** lens
that challenges *the approach itself*: load-bearing assumptions, failure under real-world
conditions, unconsidered alternatives, and the tradeoff being made — the philosophy behind
`/codex:adversarial-review`, applied to your spec instead of a code diff. One-off:
`/spec-harden <path> --depth design`.

Precedence: **CLI flag > env var (`SPEC_HARDEN_CRITIC_MODEL` / `_EFFORT`) > `~/.spec-harden.json`
> built-in default**. So `--critic-model gpt-5.6-sol` is a one-off override; the file is the
persistent default. `./install.sh` seeds this file for you from
[`.spec-harden.example.json`](.spec-harden.example.json) if you don't already have one.

## The `harden/` folder

```
<name>.harden/
  PROTOCOL.md              # the shared contract every critic obeys
  draft.md                 # working draft — Claude edits; the real spec is untouched until finalize
  rN.codex.md              # round N critic findings (Codex / GPT)
  rN.claude.md             # round N author adjudication (Claude)
  verify.claude-<model>.md # optional final-verify subagent log
  rN.gemini.md             # optional final-verify findings (Gemini, if used)
  STATUS.md                # turn / round / converged / target_spec_path
  SUMMARY.md               # written at finalize
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
