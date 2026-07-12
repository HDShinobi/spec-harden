---
name: spec-harden
description: Harden a written spec via an automatic cross-model adversarial review loop — Codex (GPT, run headless via `codex exec`) is the primary critic; Claude is the author/orchestrator and runs the whole author⇄critic loop hands-free until no blocker/major remains, then promotes the hardened draft to the real spec on user confirmation. Optional `--final-verify {sonnet|opus|haiku|fable|gemini}` adds one extra cross-check pass before finalize. Use after brainstorming writes a spec, or on any existing spec document. Accepts an optional spec path, `--critic-model`, `--critic-effort`, and `--final-verify`.
---

# spec-harden (Claude = author & orchestrator; Codex = automatic critic)

You are the **AUTHOR** and **ORCHESTRATOR**. **Codex (GPT), run headless via `codex exec`,
is the primary critic** — you invoke it yourself, so the whole loop runs automatically in one
go (no human handoff). Coordinate through files in a `harden/` folder.
**Read `references/PROTOCOL.md` (next to this skill) once before acting.**

## Resolve inputs
**The common case needs no flags — just `/spec-harden <spec-path>` runs the default Codex model
automatically.** All settings have this precedence: **CLI flag > env var > `~/.spec-harden.json`
> built-in default**.
- **Spec path resolution** (natural-language invocations like `/spec-harden chạy đánh giá spec
  này` must Just Work — resolve in this order):
  1. The first non-flag argument that is an **existing file** → use it.
  2. Else **ignore any natural-language argument text** (do NOT treat words like "chạy đánh giá
     spec này" as a path). Scan `docs/superpowers/specs/` for `*.md` (skip anything already
     inside a `*.harden/` dir), newest `mtime` first:
     - **One clear newest** (no other spec `*.md` modified within ~10 min of it) → use it, and
       tell the user which file you picked.
     - **Two or more modified close together** (superpowers just wrote multiple) → list the
       candidates with their mtimes and **ask the user which to harden** (offer "all, in
       sequence"). Do NOT guess when it is ambiguous.
- **Settings file `~/.spec-harden.json`** (keys `critic_model`, `critic_effort`, `final_verify`)
  is the place to change these once. `codex_critic.py` reads `critic_model`/`critic_effort` from
  it itself, so you never pass them on the loop calls. For `final_verify`, YOU read the file:
  `python3 -c "import json,os;print(json.load(open(os.path.expanduser('~/.spec-harden.json'))).get('final_verify','off'))"`
  (treat a missing file or `off` as "no final-verify").
- `--critic-model M` / `--critic-effort E` = one-off overrides for this run (Codex model, e.g.
  `gpt-5.6-terra`/`gpt-5.6-sol`/`gpt-5.5`; effort `low|medium|high|xhigh`). Pass them straight
  through to `codex_critic.py` only when the user asks for a one-off.
- `--final-verify T` = one-off override of the config's `final_verify`: `sonnet|opus|haiku|fable`
  (a fresh Claude subagent critic) or `gemini` (manual Antigravity handoff), or `off`.
- Harden dir = `<spec-dir>/<spec-stem>.harden/`. `SKILL_DIR` = this skill's directory
  (`scripts/` and `references/` live there).

## Pick the phase
- Harden dir does not exist → **init + loop**.
- User asks to finalize / confirms / says "chốt" → **finalize**.
- Harden dir exists and `STATUS.md` turn = `gemini` → user just ran the Gemini final-verify in
  Antigravity → **resume-after-gemini**.
- Otherwise (harden dir exists mid-run) → continue the **loop** from the next round.

Run `python3 $SKILL_DIR/scripts/protocol.py status-read <harden>` to read turn/round.

## init + loop  (the automatic core — runs hands-free)
1. Create `<harden>/`; copy the spec → `<harden>/draft.md`; copy
   `$SKILL_DIR/references/PROTOCOL.md` → `<harden>/PROTOCOL.md`.
2. **Lint (Step 0):** `python3 $SKILL_DIR/scripts/lint.py <harden>/draft.md`. For each JSON
   finding, fix it directly in `draft.md` (mechanical). Re-run until exit 0.
3. `protocol.py status-write <harden> claude 1 false <spec-path>` (records `target_spec_path`
   so `finalize` promotes back to the exact file).
4. **Loop** for round `N = 1, 2, …` up to `MAX_ROUNDS = 4`:
   1. **Codex critic turn:**
      `python3 $SKILL_DIR/scripts/codex_critic.py <harden> N [--model M] [--effort E]`.
      It runs `codex exec` read-only over `draft.md` (+ prior `r(N-1).claude.md`) and writes a
      format-validated `<harden>/rN.codex.md`. If it exits non-zero, show its stderr and STOP
      (env/auth issue — do NOT count as a round; e.g. re-run `codex login`).
   2. **Adjudicate:** `protocol.py findings <harden>/rN.codex.md`. For each finding: **ACCEPT**
      → edit `draft.md` to fix; **REBUT** → one-line reason it is invalid/out-of-scope. Do not
      accept blindly — this is the author's judgment.
   3. **Write `<harden>/rN.claude.md`:** the header (`AUTHOR: claude`, `OPEN_BLOCKERS`/
      `OPEN_MAJORS` = counts you did NOT resolve), per-finding ACCEPT/REBUT lines, and a short
      list of the draft changes you made.
   4. `protocol.py status-write <harden> claude <N+1> false`.
   5. **Stop conditions** (check in order):
      - **Converged:** `protocol.py converged <harden>/rN.codex.md` exits 0 AND you accepted no
        new blocker/major this round → break the loop, go to **final-verify / wrap-up**.
      - **Circuit-breaker:** the SAME blocker/major appears in `r(N-1).codex.md` and
        `rN.codex.md` still unresolved (you REBUTted it, or your ACCEPTed fix didn't satisfy it)
        → STOP the loop and surface it to the user to arbitrate. Do not keep looping.
      - **Cap:** `N == MAX_ROUNDS` with open majors → STOP; list the unresolved majors. This is
        NOT convergence — never call it clean.
      - Else continue to round `N+1`.

## final-verify / wrap-up
- **No `--final-verify`:** summarize the loop (rounds, findings, unresolved) and ask the user to
  confirm **finalize**.
- **`--final-verify {sonnet|opus|haiku|fable}`:** spawn ONE fresh Claude subagent (Agent tool,
  model = the flag value) with a critic prompt built from `PROTOCOL.md` (five lenses, severity,
  guards) over the converged `draft.md`. Triage its findings: ACCEPT → edit `draft.md`; REBUT →
  note reason. Log `<harden>/verify.claude-<model>.md`. If it surfaces a new blocker/major, fix
  it (one more Codex round is fine); else proceed to ask for finalize.
- **`--final-verify gemini`:** `protocol.py status-write <harden> gemini <N+1> false`; copy the
  converged `draft.md` into the harden dir and tell the user, verbatim intent: *"Codex loop
  converged. For the Gemini cross-check, open Antigravity and run the spec-harden skill on
  `<harden>/draft.md`."* Then STOP and wait.

## resume-after-gemini (only if `--final-verify gemini` was used)
1. Locate the latest `rN.gemini.md`. `protocol.py findings <file>`; if it exits non-zero, show
   errors and ask the user to re-run the Gemini turn.
2. Adjudicate ACCEPT/REBUT into `draft.md`; write `rN.claude.md`. If a new blocker/major
   appears, resolve it; otherwise summarize and ask the user to confirm **finalize**.

## finalize (only after the user confirms)
1. Read `target_spec_path` from `STATUS.md` (`protocol.py status-read`). Overwrite THAT file
   with `<harden>/draft.md`.
2. Write `<harden>/SUMMARY.md`: rounds run, critic model(s) used, findings by severity, accepted
   vs rebutted, any unresolved majors, and the `minor`/`nit` cleanup list.
3. Commit **only** the target spec + the `<harden>/` dir:
   `git add <target_spec_path> <harden> && git commit -m "docs(spec): harden <name>"`.
4. Tell the user it is done and where the summary is.

## Guards
- Apply the PROTOCOL critic guards (anti-perfectionism, high-confidence bias) — they are baked
  into `references/CRITIC_PROMPT.md`, which `codex_critic.py` sends to Codex.
- The Codex critic runs in a **read-only sandbox** — it can never touch `draft.md`. Only YOU
  (the author) edit `draft.md`, and only during the loop.
- **Never edit the real spec before `finalize`.** All work happens in `draft.md`.
- Codex uses the logged-in ChatGPT account, NOT the `/codex` plugin's app-server (that pins an
  older client_version and rejects current models). `codex_critic.py` calls `codex exec`
  directly for this reason.
