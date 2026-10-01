# spec-harden

A cross-model **adversarial spec-review loop**. One model writes and defends a spec (the
**author**); a *different* model family critiques it (the **critic**). They exchange files in a
`harden/` folder and iterate until every **design decision** is closed — then the hardened draft
is promoted to the real spec on your confirmation. It hardens the *spec*, never the code, and it
stops at design altitude: implementation precision (exact signatures, constants, offsets) is
handed to writing-plans / TDD, not chased here.

- **Author / orchestrator** — Claude Code (owns the spec, runs the loop, adjudicates
  ACCEPT/REBUT, edits the draft).
- **Primary critic** — **Codex (GPT), run headless via `codex exec`.** Claude invokes it every
  round, so the whole loop is **automatic** — no human handoff.
- **Final-verify critic** *(optional, opt-in)* — one extra cross-check after the Codex loop
  converges, by a *different* reviewer: a fresh Claude subagent
  (`--final-verify sonnet|opus|haiku|fable`) or Gemini in Antigravity (`--final-verify gemini`).

## What it hardens — and when it stops

**What it does.** It closes *design* holes in a spec before any code is written — undecided
behavior, contradictions, missing invariants/states/cases, unhandled failures. Each round Codex
critiques `draft.md`; Claude adjudicates (fix design gaps into the draft; **defer** implementation
precision to a `## Deferred to plan` list rather than pinning it in the spec). It never touches
code, and never overwrites the real spec until you confirm.

**The altitude line.** A finding is `blocker`/`major` only if it's a *design* gap the spec must
decide — because the implementer builds what the spec says and will silently invent whatever it
left undecided, and no test catches a decision that was never made. Implementation precision (a
signature, a timeout/backoff constant, a lane count, a byte offset) is at most `minor` and is
deferred — the compiler and TDD pin it far better. This is what keeps the loop from turning into
code review and running forever.

**When it stops** — each round checks, in order:

1. **Converged (design-complete)** — a critic round with 0 blocker / 0 major and nothing new
   accepted. Every design decision is closed; only deferred precision minors remain → stop, then
   ask you to finalize.
2. **Circuit-breaker** — the same finding ping-pongs across two rounds unresolved → stop and ask
   you to arbitrate.
3. **Cap (checkpoint)** — `MAX_ROUNDS = 4` reached without converging → stop and ask you to pick
   one: finalize as `cap-hit`, extend by an explicit new max, or leave it open. It never runs past
   the cap on its own.

On finalize (only after you confirm) it promotes `draft.md` to the real spec, writes `SUMMARY.md`
with the **finalization basis** (`protocol-clean` | `author-judgment` | `cap-hit`) and commits.
The run is then marked `finalized` — re-running `/spec-harden` on that spec reports it as done and
will **not** re-loop unless you explicitly start a new run.

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

All three ask what happens if the spec is wrong, and none of them counts files: a size proxy
fires on the wide-but-harmless spec and stays silent on the narrow-but-fatal one. A one-file
cache migration earns the loop; a five-file UI polish doesn't.

Otherwise the hook does nothing and brainstorming carries on as it would without it.
`/spec-harden <path>` runs the loop by hand at any time, gate or no gate.

## Usage (the loop)

Run it once in Claude Code — the loop runs automatically to convergence:

```
/spec-harden [spec-path] [--critic-model gpt-5.6-terra] [--critic-effort medium] \
             [--depth spec|design] [--context DIR…|none] [--timeout SECONDS] \
             [--final-verify sonnet|opus|haiku|fable|gemini]
```

| Step | What (all in Claude Code, automatic) |
|------|--------------------------------------|
| **init** | creates `<name>.harden/`, copies the spec to `draft.md`, lints it |
| **loop** | each round: `codex exec` critiques `draft.md` → `rN.codex.md`; Claude adjudicates ACCEPT (fix design gaps) / REBUT (defer precision to plan), writes `rN.claude.md`, checks convergence. Stops at design-complete, a circuit-breaker, or the `MAX_ROUNDS = 4` checkpoint (which asks you, never runs past silently). |
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
  "critic_timeout": 900,             // seconds per critic round (a round usually takes 1–5 min)
  "context": "repo",                 // repo = critic may read the spec's git repo to verify file/line claims | none | ["/dir", …]
  "final_verify": "off"              // off | sonnet | opus | haiku | fable | gemini
}
```

**`depth`** is the interesting knob. `spec` (default) critiques *how the spec is written* —
completeness, testability, ambiguity, assumptions, scope. `design` adds a sixth **Design** lens
that challenges *the approach itself*: load-bearing assumptions, failure under real-world
conditions, unconsidered alternatives, and the tradeoff being made — the philosophy behind
`/codex:adversarial-review`, applied to your spec instead of a code diff. One-off:
`/spec-harden <path> --depth design`.

**`context`** matters for codebase-grounded specs: by default the critic may read (never write)
the spec's git repository, so it can check that cited paths, `file:line` references and APIs
actually say what the spec claims. Pass extra roots with `--context` (e.g. an extracted upstream
tree the spec cites), or `none` to critique the draft alone.

Precedence: **CLI flag > env var (`SPEC_HARDEN_CRITIC_MODEL` / `_EFFORT` / `_DEPTH` /
`_CRITIC_TIMEOUT` / `SPEC_HARDEN_CONTEXT`) > `~/.spec-harden.json`
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
  STATUS.md                # turn / round / converged / finalized / finalization_basis / target_spec_path
  SUMMARY.md               # written at finalize
```

Findings are severity-tagged by **altitude**: a *design* gap is `blocker`/`major` (blocks
convergence); *implementation precision* and style are `minor`/`nit` (logged, deferred to plan).
They are reviewed through five lenses — **Completeness, Testability, Ambiguity, Assumptions,
Scope** (a sixth, **Design**, in `--depth design`). Convergence = a critic round with 0 open
blocker/major = **design-complete**; a circuit-breaker stops ping-ponging and `MAX_ROUNDS = 4` is
a checkpoint that asks you rather than a silent overrun. `STATUS.md` carries `converged`
(design-clean) and `finalized` (terminal — promoted, never re-looped). Full contract in
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
