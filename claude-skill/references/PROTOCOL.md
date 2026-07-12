# spec-harden PROTOCOL

Two models that cannot see each other's context coordinate ONLY through the files
in this `harden/` folder. Obey this contract exactly.

## Roles
- **Author / orchestrator (Claude Code):** owns `draft.md`; runs the whole loop; adjudicates
  each finding ACCEPT (edit the draft) or REBUT (record a reason); never accepts blindly.
  Writes `rN.claude.md`.
- **Primary critic (Codex / GPT, headless via `codex exec`):** reads `draft.md` + prior
  `r(N-1).claude.md` in a READ-ONLY sandbox; writes findings to `rN.codex.md`. NEVER edits
  `draft.md`. Claude invokes it automatically each round — no human handoff.
- **Optional final-verify critic (a different reviewer, opt-in):** one extra cross-check after
  the Codex loop converges — a fresh Claude subagent (`--final-verify sonnet|opus|haiku|fable`,
  logged to `verify.claude-<model>.md`) or Gemini in Antigravity (`--final-verify gemini`,
  `rN.gemini.md`). Cross-model, so it supplements — never replaces — the Codex loop.
- **Driver (user):** kicks off the run and makes the final confirm.

## Folder layout
```
<name>.harden/
  PROTOCOL.md              # this file (copied by init)
  draft.md                 # working draft — Author edits; real spec untouched until finalize
  rN.codex.md              # round N critic findings (Codex / GPT)
  rN.claude.md             # round N author adjudication (Claude)
  verify.claude-<model>.md # optional final-verify subagent log
  rN.gemini.md             # optional final-verify findings (Gemini, if used)
  STATUS.md                # turn/round/converged
  SUMMARY.md               # written at finalize
```

## File header (every rN.*.md)
```
ROUND: <int>
AUTHOR: codex | claude | gemini
READS: <files this is based on>
VERDICT: needs-work | converged
OPEN_BLOCKERS: <int>
OPEN_MAJORS: <int>
```

## Finding block (repeat per finding, under the header)
```
[SEVERITY: blocker|major|minor|nit]
LENS: completeness|testability|ambiguity|assumptions|scope
LOCATION: <section / quote>
ISSUE: <what is wrong or missing>
SUGGESTION: <concrete fix>
```

## Severity
- `blocker` — unimplementable / self-contradictory / missing a core decision. Blocks convergence.
- `major` — real gap or wrong assumption that would cause rework. Blocks convergence.
- `minor` — safe-to-resolve ambiguity/omission. Logged, does not block.
- `nit` — style/wording. Logged, does not block.

## Lenses
Completeness · Testability · Ambiguity · Assumptions · Scope.
In `--depth design` mode a sixth lens, **Design**, is also used — it challenges the approach
itself (load-bearing assumptions, failure under real conditions, unconsidered alternatives,
tradeoffs) rather than just how the spec is written.

## Critic guards (both critics)
- **Anti-perfectionism:** a low/no-finding round is a legitimate convergence signal.
  Do NOT invent blockers to look thorough.
- **High-confidence bias:** only raise blocker/major when confident; uncertain → minor/nit.
- Only raise NEW or still-unaddressed issues vs prior rounds.

## Convergence
Converged when a Codex round reports `OPEN_BLOCKERS: 0` and `OPEN_MAJORS: 0` AND the
Author accepted no new blocker/major that round.
- **Circuit-breaker:** if the same blocker/major recurs across two rounds unresolved
  (Author REBUT vs critic re-raise, or an ACCEPTed fix still fails), STOP and surface it
  to the user to arbitrate.
- **Cap:** `MAX_ROUNDS = 4`. Hitting the cap with open majors is NOT convergence — report
  the unresolved majors to the user; never present as "clean".
