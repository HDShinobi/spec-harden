---
name: spec-harden
description: Harden a written spec via a cross-tool adversarial review loop — Gemini (run manually in Antigravity) as primary critic plus an automatic Claude-subagent secondary critic — exchanging files in a `<name>.harden/` folder until no new blocker/major finding remains, then promote the hardened draft to the real spec on user confirmation. Use after brainstorming writes a spec, or on any existing spec document. Accepts an optional spec path and `--critic-model {opus|sonnet|haiku|fable}`.
---

# spec-harden (Claude side — author & orchestrator)

You are the **AUTHOR**. Gemini (run by the user in Antigravity) is the **primary critic**;
a fresh Claude subagent is the **secondary critic**. You coordinate through files in a
`harden/` folder. **Read `references/PROTOCOL.md` (next to this skill) once before acting.**

## Resolve inputs
- Spec path = the first non-flag argument, else the most recently modified `*.md` in
  `docs/superpowers/specs/`.
- `--critic-model {opus|sonnet|haiku|fable}` = model for the secondary-critic pre-pass.
  If absent, **skip the pre-pass** (Gemini leads alone).
- Harden dir = `<spec-dir>/<spec-stem>.harden/`. `SKILL_DIR` = this skill's directory
  (its `scripts/` and `references/` live there).

## Pick the phase
- Harden dir does not exist → **init**.
- User asks to finalize / confirms / says "chốt" → **finalize**.
- Otherwise (harden dir exists, `STATUS.md` turn = claude) → **respond**.
Run `python3 $SKILL_DIR/scripts/protocol.py status-read <harden>` to read turn/round.

## init
1. Create `<harden>/`; copy the spec file → `<harden>/draft.md`; copy
   `$SKILL_DIR/references/PROTOCOL.md` → `<harden>/PROTOCOL.md`.
2. **Lint (Step 0):** `python3 $SKILL_DIR/scripts/lint.py <harden>/draft.md`. For each JSON
   finding, fix it directly in `draft.md` (they are mechanical). Re-run until exit 0.
3. **Secondary-critic pre-pass** — only if `--critic-model` was given: spawn a subagent via
   the Agent tool (model = the flag value) with a critic prompt built from `PROTOCOL.md`
   (five lenses, severity, guards) over `<harden>/draft.md`. Triage its findings: ACCEPT →
   edit `draft.md`; REBUT → note reason. Write `<harden>/r0.claude-critic.md` (header +
   findings + your adjudication).
4. `python3 $SKILL_DIR/scripts/protocol.py status-write <harden> gemini 1 false <spec-path>`
   (records `target_spec_path` so `finalize` promotes back to the exact file).
5. Tell the user, verbatim intent: *"Draft ready and pre-cleaned. Your turn — open Antigravity
   and run the spec-harden skill on `<harden>/draft.md`."*

## respond
**Precondition:** `protocol.py status-read <harden>` → act only when `turn: claude`. If it is
`turn: gemini`, tell the user it is Gemini's turn (Antigravity) and stop.

1. Locate the latest `rN.gemini.md`. Run
   `python3 $SKILL_DIR/scripts/protocol.py findings <file>`. If it exits non-zero (errors /
   malformed blocks), show the errors and STOP — ask the user to re-run the Gemini turn.
2. Adjudicate each finding: **ACCEPT** → edit `draft.md` to fix; **REBUT** → one-line reason
   it is invalid/out-of-scope. Do not accept blindly (this is the author's judgment).
3. Count blocker/major you newly ACCEPTED this round. Write `<harden>/rN.claude.md`: the
   header (`AUTHOR: claude`, `OPEN_BLOCKERS`/`OPEN_MAJORS` = counts you did NOT resolve),
   per-finding ACCEPT/REBUT lines, and a short list of draft changes.
4. **Convergence / stop:**
   - `python3 $SKILL_DIR/scripts/protocol.py converged <rN.gemini.md>` exits 0 AND you
     accepted no new blocker/major → **converged**.
   - Same blocker/major seen in `r(N-1).gemini.md` and `rN.gemini.md` still unresolved →
     **circuit-breaker**: stop, surface to user.
   - Round `N >= 4` → **cap**: stop; list any unresolved majors — do NOT call it clean.
5. If continuing: `protocol.py status-write <harden> gemini <N+1> false`; tell user
   *"Round N done — your turn: Antigravity."* If converged/stopped: summarize and ask the user
   to confirm `finalize`.

## finalize (only after the user confirms)
1. Read `target_spec_path` from `STATUS.md` (`protocol.py status-read`). Overwrite THAT file
   with `<harden>/draft.md`.
2. Write `<harden>/SUMMARY.md`: rounds run, findings by severity, accepted vs rebutted,
   any unresolved majors, and the `minor`/`nit` cleanup list.
3. Commit **only** the target spec + the `<harden>/` dir:
   `git add <target_spec_path> <harden> && git commit -m "docs(spec): harden <name>"`.
4. Tell the user it is done and where the summary is.

## Guards
- Apply the PROTOCOL critic guards (anti-perfectionism, high-confidence bias) when building
  the secondary-critic prompt.
- **Never edit the real spec before `finalize`.** All work happens in `draft.md`.
