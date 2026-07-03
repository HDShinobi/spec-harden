# spec-harden PROTOCOL

Two tools that cannot see each other's context coordinate ONLY through the files
in this `harden/` folder. Obey this contract exactly.

## Roles
- **Author (Claude Code):** owns `draft.md`; adjudicates each finding ACCEPT (edit
  the draft) or REBUT (record a reason); never accepts blindly. Writes `rN.claude.md`.
- **Primary critic (Gemini, in Antigravity):** reads `draft.md` + latest `rN.claude.md`;
  writes findings to `rN.gemini.md`. NEVER edits `draft.md`.
- **Secondary critic (Claude subagent):** one automatic pre-pass at `init`; logs
  `r0.claude-critic.md`. Same-family, so it supplements — never replaces — Gemini.
- **Driver (user):** alternates the two tools; makes the final confirm.

## Folder layout
```
<name>.harden/
  PROTOCOL.md        # this file (copied by init)
  draft.md           # working draft — Author edits; real spec untouched until finalize
  r0.claude-critic.md# optional secondary-critic pre-pass log
  rN.gemini.md       # round N critic findings (Gemini)
  rN.claude.md       # round N author adjudication (Claude)
  STATUS.md          # turn/round/converged
  SUMMARY.md         # written at finalize
```

## File header (every rN.*.md)
```
ROUND: <int>
AUTHOR: gemini | claude
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

## Five lenses
Completeness · Testability · Ambiguity · Assumptions · Scope.

## Critic guards (both critics)
- **Anti-perfectionism:** a low/no-finding round is a legitimate convergence signal.
  Do NOT invent blockers to look thorough.
- **High-confidence bias:** only raise blocker/major when confident; uncertain → minor/nit.
- Only raise NEW or still-unaddressed issues vs prior rounds.

## Convergence
Converged when a Gemini round reports `OPEN_BLOCKERS: 0` and `OPEN_MAJORS: 0` AND the
prior Author round accepted no new blocker/major.
- **Circuit-breaker:** if the same blocker/major recurs across two rounds unresolved
  (Author REBUT vs critic re-raise, or an ACCEPTed fix still fails), STOP and surface it
  to the user to arbitrate.
- **Cap:** `MAX_ROUNDS = 4`. Hitting the cap with open majors is NOT convergence — report
  the unresolved majors to the user; never present as "clean".
