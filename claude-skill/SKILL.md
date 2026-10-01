---
name: spec-harden
description: Harden a written spec via an automatic cross-model adversarial review loop — Codex (GPT, run headless via `codex exec`) is the primary critic; Claude is the author/orchestrator and runs the whole author⇄critic loop hands-free until the spec is design-complete (every design decision closed; implementation precision deferred to writing-plans/TDD), then promotes the hardened draft to the real spec on user confirmation. `--depth design` also challenges the approach/tradeoffs/alternatives (not just spec quality); optional `--final-verify {sonnet|opus|haiku|fable|gemini}` adds one extra cross-check pass before finalize. Use after brainstorming writes a spec, or on any existing spec document. Accepts an optional spec path, `--critic-model`, `--critic-effort`, `--depth`, and `--final-verify`.
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
- **Settings file `~/.spec-harden.json`** (keys `critic_model`, `critic_effort`, `depth`,
  `critic_timeout`, `context`, `final_verify`) is the place to change these once.
  `codex_critic.py` reads every key except `final_verify` itself, so you never pass them on the
  loop calls. For `final_verify`, YOU read the file:
  `python3 -c "import json,os;print(json.load(open(os.path.expanduser('~/.spec-harden.json'))).get('final_verify','off'))"`
  (treat a missing file or `off` as "no final-verify").
- `--critic-model M` / `--critic-effort E` / `--depth {spec|design}` = one-off overrides for this
  run (Codex model, e.g. `gpt-5.6-terra`/`gpt-5.6-sol`/`gpt-5.5`; effort `low|medium|high|xhigh`;
  depth `spec` = spec-quality only [default], `design` = ALSO challenge the approach, tradeoffs,
  and alternatives). Pass them straight through to `codex_critic.py`; it reads its own defaults
  from `~/.spec-harden.json` otherwise.
- `--context DIR…|none` / `--timeout S` = one-off overrides. **Context** = directories the critic
  may READ to verify the draft's factual claims (file paths, `file:line` refs, APIs); default is
  the git toplevel of the spec's repo, so codebase-grounded specs get their citations checked.
  Add extra roots (e.g. an extracted upstream tree the spec cites); `none` = draft only.
  **Timeout** = seconds per critic round (default 900).
- `--final-verify T` = one-off override of the config's `final_verify`: `sonnet|opus|haiku|fable`
  (a fresh Claude subagent critic) or `gemini` (manual Antigravity handoff), or `off`.
- Harden dir = `<spec-dir>/<spec-stem>.harden/`. `SKILL_DIR` = this skill's directory
  (`scripts/` and `references/` live there).

## Pick the phase
- Harden dir does not exist → **init + loop**.
- User asks to finalize / confirms / says "chốt" → **finalize**.
- Harden dir exists and `STATUS.md` turn = `gemini` → user just ran the Gemini final-verify in
  Antigravity → **resume-after-gemini**.
- Harden dir exists and `STATUS.md` `finalized: true` → the run is TERMINAL (spec already
  promoted). Report the recorded `finalization_basis` and point at `SUMMARY.md`; do NOT open a
  round. Re-harden only if the user explicitly asks to start a new run.
- Harden dir exists and `STATUS.md` `converged: true` (turn ≠ gemini) → the loop already
  converged; go to **final-verify / wrap-up** and ask to finalize — do NOT open another round.
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
      `python3 $SKILL_DIR/scripts/codex_critic.py <harden> N [--model M] [--effort E] [--depth D] [--context DIR…] [--timeout S]`.
      **A round takes 1–5 minutes** — run it with the Bash tool's `timeout: 600000` (or higher to
      match `critic_timeout`) or with `run_in_background: true` and wait for the completion
      notice. Claude Code's default 120 s Bash timeout will kill a normal round mid-flight.
      It runs `codex exec` read-only over `draft.md` (+ prior `r(N-1).claude.md`) and writes a
      format-validated `<harden>/rN.codex.md`. If it exits non-zero, show its stderr and STOP
      (env/auth issue — do NOT count as a round; e.g. re-run `codex login`).
   2. **Adjudicate:** `protocol.py findings <harden>/rN.codex.md`. For each finding: **ACCEPT**
      → edit `draft.md` to fix; **REBUT** → one-line reason it is invalid/out-of-scope. Do not
      accept blindly — this is the author's judgment.
      - **Altitude check (do this before accepting a major):** is the finding a DESIGN gap or
        IMPLEMENTATION PRECISION? Close design gaps in the draft. For a precision item (exact
        signature, constant, lane count, byte offset) — even if the critic marked it major —
        **REBUT it as "altitude: defer to writing-plans/TDD"** and record it in a `## Deferred to
        plan` list in `draft.md`; do NOT pin it in the spec. Chasing precision is how this loop
        turns into code review and runs forever.
   3. **Write `<harden>/rN.claude.md`:** the header (`AUTHOR: claude`, `OPEN_BLOCKERS`/
      `OPEN_MAJORS` = counts you did NOT resolve), per-finding ACCEPT/REBUT lines, and a short
      list of the draft changes you made.
   4. `protocol.py status-write <harden> claude <N+1> false`.
   5. **Stop conditions** (check in order):
      - **Converged:** `protocol.py converged <harden>/rN.codex.md` exits 0 AND you accepted no
        new blocker/major this round → `protocol.py status-write <harden> claude N true` (this is
        the ONLY path that sets the converged flag true; step 4.4 above always wrote `false`),
        then break the loop and go to **final-verify / wrap-up**.
      - **Circuit-breaker:** the SAME blocker/major appears in `r(N-1).codex.md` and
        `rN.codex.md` still unresolved (you REBUTted it, or your ACCEPTed fix didn't satisfy it)
        → STOP the loop and surface it to the user to arbitrate. Do not keep looping.
      - **Cap (checkpoint, not silent overrun):** `N == MAX_ROUNDS` and not converged → STOP and
        ask the user to choose ONE: finalize as `cap-hit` (never called clean), extend by an
        explicit new max (then continue), or leave the run open. Never run past the cap on your
        own. If the open findings at the cap are all implementation-precision, say so — that is a
        design-complete signal, and finalizing is usually the right call. If instead the last
        round's majors are **regressions of your own previous fixes** and their scope is
        narrowing round over round (a common pattern: each fix exposes an edge of itself),
        recommend **extending by exactly one confirming round** — it is the only way to reach
        `protocol-clean` without calling unverified fixes clean.
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
1. Read `target_spec_path` from `STATUS.md` (`protocol.py status-read` prints **JSON** — parse it
   with `json`, not `awk`/`cut`, and check the path exists before writing). Overwrite THAT file
   with `<harden>/draft.md`.
2. Write `<harden>/SUMMARY.md`: rounds run, critic model(s) used, findings by severity, accepted
   vs rebutted, the `## Deferred to plan` list (implementation-precision handed to writing-plans),
   and the **finalization basis** — exactly one of: `protocol-clean` (a Codex round hit
   `OPEN_BLOCKERS: 0` / `OPEN_MAJORS: 0` = design-complete), `author-judgment` (the author chose to
   stop though a round still raised an adjacent design finding), or `cap-hit` (`MAX_ROUNDS` reached
   with open majors — never present as clean).
   - **Last-mile honesty:** if the LAST Codex round still reported open majors that you then fixed
     (no confirming critic round saw the fixed draft), state plainly *"last fixes are
     critic-unverified"* and offer the user one confirming Codex round before promoting. Only
     `protocol-clean` means a critic round actually saw a zero-major draft.
   - End with the closing line: `Converged = spec quality only, not implementation correctness —
     code still needs the project's real verification.`
   - Then run `python3 $SKILL_DIR/scripts/protocol.py summary-check <harden>`; if it exits
     non-zero, fix the missing pieces before continuing.
3. `python3 $SKILL_DIR/scripts/protocol.py finalize-status <harden> <basis>` — stamps
   `finalized: true` + `finalization_basis` so the run is terminal and never re-looped.
4. Commit **only** the target spec + the `<harden>/` dir:
   `git add <target_spec_path> <harden> && git commit -m "docs(spec): harden <name>"`.
   Spec dirs are often gitignored (e.g. `docs/superpowers/`): first run
   `git check-ignore -q <path>` **once per path** (`-q` accepts only a single pathname); if either is ignored, use
   `git add -f` for exactly those two paths and tell the user you force-added ignored files.
   Never change `.gitignore` for this.
5. Tell the user it is done, the finalization basis, and where the summary is.

## Guards
- Apply the PROTOCOL critic guards (anti-perfectionism, high-confidence bias) — they are baked
  into `references/CRITIC_PROMPT.md`, which `codex_critic.py` sends to Codex.
- The Codex critic runs in a **read-only sandbox** — it can never touch `draft.md`. Only YOU
  (the author) edit `draft.md`, and only during the loop.
- **Never edit the real spec before `finalize`.** All work happens in `draft.md`.
- Codex uses the logged-in ChatGPT account, NOT the `/codex` plugin's app-server (that pins an
  older client_version and rejects current models). `codex_critic.py` calls `codex exec`
  directly for this reason.
- **This loop hardens the SPEC, not the code.** Never run or imitate the adversarial loop as a
  code-review loop — adversarial rounds sharpen documents; code is proven by the project's own
  verification (a test that fails before and passes after, running the thing), never by another
  review round.
- **"Converged" certifies the spec, not any implementation of it.** It means the spec survived
  adversarial review — zero evidence that code built from it is correct or complete. Never cite
  this loop's verdict as done-evidence for implementation work; only the project's real
  verification is that.
- **Keep the spec at DESIGN altitude.** Harden design decisions (behavior, invariants, states,
  failures, contradictions) to zero-major; hand implementation precision (signatures, constants,
  lane counts, offsets) to writing-plans + TDD. When a round produces only precision findings, the
  spec is design-complete — STOP; do not keep looping. Putting code-level detail (e.g. exact Swift
  signatures) into a spec invites the critic to nitpick it and inflates the round count — a signal
  the spec dropped below design altitude, not that it needs more hardening.
